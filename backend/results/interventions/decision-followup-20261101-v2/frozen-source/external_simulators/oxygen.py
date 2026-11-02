"""Preserve continuous, nonnegative ODE oxygen instead of PenSim's 1mg/L reset.

Versioned adapter correction. No biological coefficient or oxygen balance is
changed. Legacy runs retain the upstream reset. Low oxygen remains a constraint
violation where the study declares a minimum; it is never relabeled as safe.
"""
from contextlib import contextmanager
import math


@contextmanager
def preserve_oxygen(module,audit,enabled=False):
    if not enabled:
        yield lambda state,step: None
        return
    original=module.fastodeint.integrate
    last=[]
    changes=[]
    def capture(*args):
        result=original(*args)
        oxygen=float(result[1])
        if not math.isfinite(oxygen) or oxygen<0:
            raise ValueError('Continuous oxygen requires nonnegative finite raw ODE state')
        last[:]=[oxygen]
        return result
    def restore(state,step):
        if not last:raise ValueError('No raw oxygen result to preserve')
        reported=float(state.DO2.y[step-1])
        if reported!=last[0]:changes.append({'time_h':step*.2,'raw_DO_mg_l':last[0],'legacy_reset_DO_mg_l':reported})
        state.DO2.y[step-1]=last[0]
    module.fastodeint.integrate=capture
    try:
        yield restore
    finally:
        module.fastodeint.integrate=original
        audit['raw_low_oxygen_intervals']=audit['dissolved_oxygen_floor_events']
        audit['dissolved_oxygen_floor_events']=0
        audit['oxygen_policy']='continuous_nonnegative_ODE'
        audit['prevented_upstream_resets']=changes


def run_continuous(paths,operation,*args,**kwargs):
    """Run one adapter/fit with corrected oxygen state between control intervals.

    Native/global simulator state already requires process isolation. The method
    patch is scoped and restored even on failure. Core equations remain intact.
    """
    from pathlib import Path
    from .upstream import pen_module
    module=pen_module(Path(paths['pensim']),Path(paths['native']))
    original_step=module.PenSimEnv.step
    events=[]
    def step(env,k,state,**commands):
        audit={'dissolved_oxygen_floor_events':0}
        with preserve_oxygen(module,audit,True) as restore:
            result=original_step(env,k,state,**commands)
            restore(result[1],k)
        events.extend(audit['prevented_upstream_resets'])
        return result
    module.PenSimEnv.step=step
    try:
        result=operation(*args,**kwargs)
    finally:
        module.PenSimEnv.step=original_step
    if 'audit' in result:
        audit=result['audit']
        audit['raw_low_oxygen_intervals']=audit['dissolved_oxygen_floor_events']
        audit['dissolved_oxygen_floor_events']=0
        audit['oxygen_policy']='continuous_nonnegative_ODE'
        audit['prevented_upstream_resets']=events
    else:
        result['oxygen_policy']='continuous_nonnegative_ODE'
    return result
