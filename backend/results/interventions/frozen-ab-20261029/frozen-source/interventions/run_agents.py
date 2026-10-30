"""Restricted research SDK adapter for sequential PenSim development sessions.

A/B retain identical evidence, tools/ceilings except B's supplied model. The
conventional optimizer runs separately against the identical model interface.
No agent sees evaluator outcomes until its recommendation is frozen.
"""
from pathlib import Path
import json,os,queue,shutil,subprocess,threading,time,signal
from src.paths import DEFAULT_PRIME_BUNDLE
from benchmarks.external_simulators.run_agents import numerical

SYSTEM='''Investigate this simulated receiving fermentation and recommend one reviewable intervention. Use only the public observations and tools. Source and receiving processes differ; hidden parameters/states and future outcomes are unavailable. All routine assays carry sample and availability clocks. You may request one extra assay; the process runs KEEP while waiting. Compare bounded interventions when useful. Avoid oxygen-constraint violations and retain product mass; concentration alone is insufficient. A stop produces zero counted production. Normal cases may need no intervention. A physics tool, if available, is an imperfect source-calibrated prediction, not truth. Explain evidence, alternatives, uncertainty and your chosen action. Submit once via submit_decision; its predictions object must be empty because this task evaluates interventions separately from forecasting. No action is approved or executed on physical equipment.'''


def attempt(session,arm,model,output,*,wall_seconds=180):
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    if (output/'run.json').exists():raise ValueError('Never overwrite an attempt')
    packet=session.public_packet();(output/'packet.json').write_text(json.dumps(packet,indent=2)+'\n')
    request={'type':'initialize','bundle_root':str(DEFAULT_PRIME_BUNDLE),'cwd':str(output),'model':model,
        'task':'intervention','arm':arm,'system_prompt':SYSTEM,'prompt':json.dumps(packet),
        'timeout_seconds':wall_seconds,'max_model_calls':10,'max_output_tokens':8192,
        'public_schema':{'actions':list(packet['allowed_actions']),'forecast_fields':[],'measurements':['extra_product_assay']},'preflight':False}
    proc=subprocess.Popen([shutil.which('node'),str(Path(__file__).with_name('sdk_intervention.mjs').resolve())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,start_new_session=True)
    events=queue.Queue();logs=[];errors=[];submitted=None;receipt=None;finished={};history=[];started=time.monotonic()
    def read():
        for line in proc.stdout:events.put(line)
        events.put(None)
    def readerr():errors.extend(proc.stderr)
    threading.Thread(target=read,daemon=True).start();threading.Thread(target=readerr,daemon=True).start()
    proc.stdin.write(json.dumps(request)+'\n');proc.stdin.flush()
    try:
        while time.monotonic()-started<wall_seconds+15:
            try:line=events.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            if line is None:break
            event=json.loads(line);logs.append(event)
            if event.get('type')=='finished':finished=event;break
            if event.get('type')!='tool_request':continue
            name=event['name'];args=event.get('args',{});before=time.monotonic()
            try:
                if submitted is not None:raise ValueError('Recommendation frozen')
                if len(history)>=12 and name!='submit_decision':raise ValueError('Tool budget exhausted; submit')
                if name=='python_analysis':result=numerical(args['code'],session.public_packet(),output/'scratch')
                elif name=='request_measurement':result=session.measure(args['measurement'])
                elif name=='physical_forward_model' and arm=='B':result=session.predict(args['action_id'])
                elif name=='submit_decision':
                    submitted=args
                    receipt=session.recommend(args['action_id'],rationale=args['rationale'],uncertainty=args['uncertainty'],evidence=args['evidence'])
                    # Return acceptance only; outcome is evaluator-only.
                    result={'accepted':True,'decision_frozen':True}
                else:raise ValueError('Unavailable tool')
            except Exception as exc:result={'error':type(exc).__name__+': '+str(exc)}
            history.append({'name':name,'arguments':args,'result':result,'wall_seconds':time.monotonic()-before})
            proc.stdin.write(json.dumps({'type':'tool_result','id':event['id'],'result':result})+'\n');proc.stdin.flush()
    finally:
        if proc.poll() is None:
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=2)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    value={'status':'completed' if receipt else finished.get('status','failed'),'arm':arm,'model':model,
        'submission':submitted,'evaluation':receipt,'wall_seconds':time.monotonic()-started,
        'model_calls':finished.get('model_calls'),'usage':finished.get('usage'),'tools':history,
        'error':finished.get('error') or (''.join(errors)[-1200:] if receipt is None else None),
        'capability_audit':next((e for e in logs if e.get('type')=='capability_audit'),None),
        'provider_billing':'unknown','real_equipment_actions':False}
    (output/'run.json').write_text(json.dumps(value,indent=2)+'\n');(output/'events.json').write_text(json.dumps(logs,indent=2)+'\n')
    return value
