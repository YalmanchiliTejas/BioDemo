"""Build and audit the pinned PenSimPy native port without editing upstream files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sysconfig


def build(source: Path, destination: Path, boost_include: Path):
    import pybind11
    original = (source / 'src/main.cpp').read_text()
    needle = 'pow(a_0, (1 / 3))'
    if original.count(needle) != 1:
        raise ValueError('Pinned integer-division correction no longer applies exactly')
    corrected = original.replace(needle, 'pow(a_0, (1.0 / 3.0))')
    extra = r'''
py::array_t<double> audited_rhs(py::array_t<double> yy, py::array_t<double> pp, double t) {
    auto y = yy.unchecked<1>(); auto p = pp.unchecked<1>();
    if (y.shape(0)!=33 || p.shape(0)!=31) throw std::runtime_error("state/parameter dimension");
    state_type x{}, dx{};
    for (int i=0;i<33;i++) x[i]=y(i);
    for (int i=0;i<31;i++) params[i]=p(i);
    pensim_func(x,dx,t);
    return py::array_t<double>(33,dx.data());
}
py::array_t<double> audited_integrate(py::array_t<double> yy, py::array_t<double> pp,
    double t0, double t1, double dt, double atol, double rtol) {
    auto y=yy.unchecked<1>(); auto p=pp.unchecked<1>();
    if (y.shape(0)!=33 || p.shape(0)!=31) throw std::runtime_error("state/parameter dimension");
    state_type x{};
    for(int i=0;i<33;i++) x[i]=y(i);
    for(int i=0;i<31;i++) params[i]=p(i);
    auto solver=make_controlled(atol,rtol,runge_kutta_dopri5<state_type>());
    integrate_adaptive(solver,pensim_func,x,t0,t1,dt);
    return py::array_t<double>(33,x.data());
}
'''
    corrected = corrected.replace('PYBIND11_MODULE(fastodeint, m)', extra+'\nPYBIND11_MODULE(fastodeint, m)')
    corrected = corrected.replace('m.def("integrate", &odeint_integrate);',
        'm.def("integrate", &odeint_integrate);\n m.def("rhs", &audited_rhs);\n m.def("integrate_checked", &audited_integrate);')
    destination.mkdir(parents=True, exist_ok=True)
    translation = destination / 'fastodeint-audited.cpp'
    translation.write_text(corrected)
    binary = destination / ('fastodeint'+sysconfig.get_config_var('EXT_SUFFIX'))
    command = ['clang++','-O3','-shared','-std=c++14','-undefined','dynamic_lookup',
               '-Wno-deprecated-declarations','-Wno-deprecated-builtins',
               '-I'+pybind11.get_include(),'-I'+sysconfig.get_paths()['include'],
               '-I'+str(boost_include),str(translation),'-o',str(binary)]
    completed = subprocess.run(command, capture_output=True, text=True)
    (destination/'build.log').write_text(completed.stdout+completed.stderr)
    if completed.returncode:
        raise RuntimeError('Native build failed; inspect '+str(destination/'build.log'))
    receipt = {'original_sha256':hashlib.sha256(original.encode()).hexdigest(),
               'translation_sha256':hashlib.sha256(corrected.encode()).hexdigest(),
               'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
               'correction':{'before':needle,'after':'pow(a_0, (1.0 / 3.0))'},
               'added_interfaces':['rhs','integrate_checked'],
               'build_only_change':'Use installed Boost headers and pybind11; omit unused OpenMP build dependency.',
               'command':command}
    (destination/'build.json').write_text(json.dumps(receipt,indent=2))
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--boost-include',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.source,args.output,args.boost_include),indent=2))
