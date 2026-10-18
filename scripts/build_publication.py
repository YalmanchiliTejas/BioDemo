"""Build public artifacts from immutable run files, never hand-entered scores."""
from collections import Counter, defaultdict
import hashlib
import html
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
DISCLOSURE='Fresenius: a synthetic manufacturing reconstruction informed by publicly available FDA-related materials. No internal Fresenius manufacturing data, participation, endorsement or validation. CHO: authentic laboratory measurements. No production or quality improvement has been experimentally demonstrated.'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def esc(value):return html.escape(str(value),quote=True)
def show(value):return 'Not measured' if value is None else f'{value:.3f}' if isinstance(value,float) else str(value)


def canonical_citations(output):
    result=set()
    for citation in output.get('citations',[]):
        source=citation.get('source',{})
        if isinstance(source,dict):
            result.add(json.dumps({k:source.get(k) for k in ('path','sheet','cell','row','column','page','span','region')},sort_keys=True))
    return result


def diagnosis(directory,run):
    stderr=' '.join(p.read_text(errors='replace') for p in (directory/'runtime-artifacts').glob('*.stderr'))
    reason=run.get('reason','');combined=stderr+' '+reason
    if '402' in combined or 'provider_payment_required' in combined:
        return {'category':'provider_payment_required','action':'Fund the configured provider account or configure an authorized funded provider. Then repeat unchanged frozen trials.'}
    if 'authentication is missing' in combined or 'proxy auth required' in combined:
        return {'category':'provider_authentication','action':'Provide the configured provider credential in the launching process; never store credentials in reports.'}
    if 'sandbox_apply' in combined:
        return {'category':'evaluation_host_permission','action':'Run the evaluator with permission to launch sandbox-exec. Do not disable hidden-reference isolation.'}
    if 'wall-clock' in combined:
        return {'category':'deadline_exceeded','action':'Inspect checkpoint, per-call timing and candidate coverage; reserve synthesis before deadline. Do not mark checkpoint complete.'}
    if 'coverage evidence does not belong' in combined:
        return {'category':'coverage_source_entity_mismatch','action':'The model assigned a citation to the wrong source/entity coverage unit. Preserve the partial output; provide explicit unit-to-anchor mappings and repeat without changing labels.'}
    if 'without submitting' in combined:
        return {'category':'final_report_not_submitted','action':'Inspect report-validation receipts and budget logs; fix missing fields and submit a validated final or explicit partial report.'}
    if run.get('status')=='incomplete':
        return {'category':'incomplete_investigation','action':'Resolve missing scope, candidate dispositions and verification flags from the checkpoint; source transcription alone is insufficient.'}
    return {'category':run.get('error_code') or 'no_execution_failure_recorded','action':'Read trace, source checks and hash-bound review packet; independent scientific review remains necessary.'}


def load_results(root=ROOT):
    runs=[];unreadable=[];unfinalized=[]
    for trace in sorted((root/'results/evaluation').glob('*/trace.jsonl')):
        if (trace.parent/'run.json').exists():continue
        events=[]
        for line in trace.read_text(errors='replace').splitlines():
            try:events.append(json.loads(line))
            except ValueError:continue
        unfinalized.append({'run_id':trace.parent.name,'case_id':events[0].get('case_id') if events else None,
            'status':'evaluation_unavailable','last_recorded_action':events[-1].get('action') if events else None,
            'mode':None,'execution_attempted':None,'trace':str(trace.relative_to(root)),
            'explanation':'Trace exists without run.json; execution, method and outcome cannot be established. Kept separate from known execution-rate denominators.'})
    for path in sorted((root/'results/evaluation').glob('*/run.json')):
        try:r=json.loads(path.read_text())
        except (ValueError,OSError):unreadable.append(str(path.relative_to(root)));continue
        if r.get('version')!='manufacturing-evaluation-v2':continue
        from benchmarks.common.usage import recover_usage
        output=r.get('output') or {};report=output.get('analysis') or {};usage=dict(r.get('usage') or recover_usage(path.parent/'runtime-artifacts'))
        # Legacy provider adapters emitted zero even with unpriced/missing usage.
        if r.get('mode')=='full_rlm' and usage.get('inference_cost_usd')==0:
            usage['recorded_inference_cost_usd']=0
            usage['inference_cost_usd']=None
            usage['cost_status']='unknown_legacy_zero_and_child_telemetry'
        usage.setdefault('total_cost_usd',None)
        scores=r.get('objective_scores') or {}
        data=scores.get('data_preparation',{});evidence=scores.get('evidence',{})
        checks=scores.get('objective_checks',{})
        structural=report.get('report_status')=='complete_for_available_evidence'
        claims=report.get('verification',{}).get('claim_verification',{})
        output_matches=sha(path.parent/'output.json')==r.get('output_sha256') if (path.parent/'output.json').exists() else None
        automatic=(r.get('audit',{}).get('pass') is True and r.get('isolation_audit',{}).get('pass') is True and
                   output_matches is True and structural and claims.get('status')=='technical_checks_passed' and
                   checks.get('field_values_correct') is True and checks.get('material_citations_resolve') is True)
        state=('execution_failed' if r.get('status')=='failed' else 'incomplete' if r.get('status')=='incomplete' else
               'scientifically_qualified' if r.get('qualification',{}).get('qualified') is True else
               'scientific_review_pending' if automatic else 'evaluation_unavailable')
        runs.append({'run_id':r['run_id'],'case_id':r['case_id'],'benchmark_id':r['benchmark_id'],
                     'condition':r['condition'],'mode':r['mode'],'attempted':r.get('attempted',False),
                     'recorded_execution_status':r['status'],'publication_status':state,
                     'technical_checks_passed':automatic,'structural_completion':structural,
                     'claim_checks':claims or None,'scientific_qualification':r.get('qualification'),
                     'field_accuracy':data.get('field_accuracy'),'field_coverage':data.get('field_coverage'),
                     'file_coverage':data.get('file_coverage'),'citation_location_validity':evidence.get('citation_location_validity'),
                     'critical_evidence_recall':evidence.get('critical_evidence_recall'),
                     'evidence_precision':evidence.get('evidence_precision'),
                     'scientific_quality':None if r.get('qualification',{}).get('quality_score') is None else r['qualification']['quality_score'],
                     'claim_support':'independent_review_pending','contradiction_coverage':'independent_review_pending',
                     'usage':usage,'wall_clock_seconds':r.get('wall_clock_seconds'),
                     'case_hash':r['case'].get('task_spec_sha256'),'dataset_hash':r['case'].get('package_sha256'),
                     'policy_hash':r['case'].get('quality_policy_sha256'),'environment':r.get('environment'),
                     'output_sha256':r.get('output_sha256'),'run_file_sha256':sha(path),
                     'artifact':str(path.relative_to(root)),'diagnostics':diagnosis(path.parent,r),
                     'canonical_citations':sorted(canonical_citations(output)),
                     'coverage_review':report.get('investigation_review'),
                     'original_output_hash_matches':output_matches})
    cohorts=[];groups=defaultdict(list)
    for r in runs:
        if r['attempted']:groups[(r['benchmark_id'],r['case_id'],r['condition'],r['mode'],r['case_hash'],
            (r.get('environment') or {}).get('working_tree_code_sha256') or 'legacy-unpinned')].append(r)
    for key,group in sorted(groups.items()):
        times=[r['wall_clock_seconds'] for r in group if r['wall_clock_seconds'] is not None]
        sets=[set(r['canonical_citations']) for r in group if r['canonical_citations']]
        overlaps=[len(a&b)/len(a|b) for i,a in enumerate(sets) for b in sets[i+1:] if a|b]
        cohorts.append({'benchmark_id':key[0],'case_id':key[1],'condition':key[2],'mode':key[3],
            'case_hash':key[4],'implementation_hash':key[5],'attempts':len(group),
            'recorded_execution_statuses':dict(Counter(r['recorded_execution_status'] for r in group)),
            'technical_check_passes':sum(r['technical_checks_passed'] for r in group),
            'wall_seconds_median_all_attempts':statistics.median(times) if times else None,
            'wall_seconds_range_all_attempts':[min(times),max(times)] if times else None,
            'canonical_location_jaccard':overlaps,
            'material_finding_stability':None,'generalization':'not_established',
            'reliability_scope':'All attempts included; legacy code versions are not fully pinned.'})
    return {'schema_version':'publication-benchmark-v1','disclosure':DISCLOSURE,'runs':runs,'cohorts':cohorts,
            'unreadable_run_files':unreadable,'unfinalized_records':unfinalized,
            'unmeasured':['manual engineer','incumbent product','human effort savings','independent causal accuracy','untouched held-out generalization'],
            'gates':{'technical_demonstration':'pending_complete_verified_current_full_os_run_and_claim_review',
                     'benchmark_comparison':'pending_matched_repeated_quality_checked_trials',
                     'independent_scientific_qualification':'pending_approved_policy_blinded_reviews_adjudication_and_output_hash_binding'}}


def example(root):
    # Select from source checks actually persisted by a completed recorded run.
    candidates=[]
    for path in (root/'results/verification').glob('*/verification.json'):
        verification=json.loads(path.read_text());summary_path=path.parent/'summary.json'
        if not summary_path.exists():continue
        summary=json.loads(summary_path.read_text());run_id=summary.get('run_id')
        if not run_id:continue
        # An audit can outlive its recorded run. Such a detached example cannot
        # bind the dataset/output hashes and must not crash or appear as a demo.
        if not (root/'results/evaluation'/run_id/'run.json').is_file():continue
        checked=[c for c in verification.get('evidence_checks',{}).values() if c.get('source_integrity') is True and c.get('value_matches') is True]
        by_key=defaultdict(list)
        for check in checked:
            ref=check.get('source_ref',{})
            if 'viability' in str(ref.get('column','')).lower():
                try:by_key[(ref['path'],ref['row'],ref['column'])].append((float(check['observed']),ref,check['observation_id']))
                except (TypeError,ValueError):continue
        for key,values in by_key.items():
            for i,a in enumerate(values):
                for b in values[i+1:]:
                    if a[1].get('sheet')!=b[1].get('sheet'):
                        candidates.append((abs(a[0]-b[0]),run_id,a,b,summary,verification['status']))
    if not candidates:return None
    _,run_id,a,b,summary,status=max(candidates,key=lambda x:x[0])
    run=json.loads((root/'results/evaluation'/run_id/'run.json').read_text())
    ref=a[1];source=root/'benchmarks/cho/raw/workbooks'/ref['path']
    expected=next((f['sha256'] for f in run['case']['allowlist'] if f['path']==ref['path']),None)
    source_matches=source.is_file() and sha(source)==expected
    trajectories=[]
    if source_matches:
        from openpyxl import load_workbook
        book=load_workbook(source,read_only=True,data_only=True)
        try:
            for selected in (a,b):
                location=selected[1];sheet=book[location['sheet']]
                iterator=sheet.iter_rows(values_only=True);headers=list(next(iterator))
                time_index=next((i for i,h in enumerate(headers) if str(h).strip().lower()=='time (h)'),None)
                if time_index is None:continue
                value_index=headers.index(location['column']);points=[]
                for row_number,cells in enumerate(iterator,2):
                    t,y=cells[time_index],cells[value_index]
                    if type(t) in (int,float) and type(y) in (int,float):
                        points.append({'time_hours':t,'value':y,'source_row':row_number})
                trajectories.append({'sheet':location['sheet'],'time_column':headers[time_index],
                                     'value_column':location['column'],'points':points})
        finally:book.close()
    return {'recorded_run_id':run_id,'selection':'Illustrative largest paired viability difference among rechecked cited cells at matching source rows; not an outcome ranking.',
            'values':[{'value':x[0],'source':x[1],'evidence_id':x[2]} for x in (a,b)],
            'original_output_sha256':run.get('output_sha256'),'audit_status':status,
            'current_source_sha256_matches_frozen':source_matches,'trajectories':trajectories,
            'source_checks_passed':summary['source_checks_passed'],'source_checks_count':summary['source_checks_count'],
            'replayed_report_status':summary['replayed_report_status'],
            'competing_explanations':['Operating strategy differences','Measurement or acquisition problems','Biological/process stress requiring further evidence'],
            'contradiction_and_uncertainty':'Source-value agreement does not prove biological interpretation. Operating intent, calibration and causal direction remain unresolved. Matching rows alone do not establish temporal alignment.',
            'next_actions':['Review approved recipes and setpoints','Check independent viability and sensor measurements','Resolve source clocks before making event-order claims'],
            'artifact':'results/verification/'+next(p.parent.name for p in sorted((root/'results/verification').glob('*/summary.json')) if json.loads(p.read_text()).get('run_id')==run_id)}


def status_chart(runs):
    cards=[]
    for bid in ('cho','fresenius'):
        selected=[r for r in runs if r['benchmark_id']==bid and r['mode']=='full_rlm' and r['attempted']]
        counts=Counter(r['recorded_execution_status'] for r in selected);n=len(selected)
        bars=''.join(f'<div class="bar"><span>{esc(status)}</span><div><i style="width:{100*counts[status]/n if n else 0:.4f}%;background:{color}"></i></div><b>{counts[status]}/{n}</b></div>' for status,color in [('completed','#238267'),('incomplete','#ba8d4b'),('failed','#b4675b')])
        provenance='Authentic laboratory measurements.' if bid=='cho' else 'A synthetic manufacturing reconstruction informed by publicly available FDA-related materials.'
        cards.append(f'<article><p class="eyebrow">{bid.upper()} · Manufacturing OS</p><h2>Every attempt counts.</h2><p>{provenance}</p>{bars}<p>Recorded execution statuses across historical versions. Completion is not scientific qualification. Infrastructure failures remain included.</p></article>')
    return ''.join(cards)


def dashboard(results):
    from benchmark.case_comparison.visual_report import CSS
    rows=''
    for r in results['runs']:
        accuracy=(r.get('field_accuracy') or {}).get('value');coverage=(r.get('field_coverage') or {}).get('value')
        rows+=f'<tr><td>{esc(r["run_id"][:8])}</td><td>{esc(r["case_id"])}</td><td>{esc(r["mode"])}</td><td>{esc(r["recorded_execution_status"])}</td><td>{esc(show(accuracy))}</td><td>{esc(show(coverage))}</td><td>{esc(show(r["wall_clock_seconds"]))}</td><td>{esc(show(r["usage"].get("inference_cost_usd")))}</td></tr>'
    latency=''
    for bid in ('cho','fresenius'):
        selected=[r for r in results['runs'] if r['benchmark_id']==bid and r['wall_clock_seconds'] is not None]
        if not selected:continue
        maximum=max(r['wall_clock_seconds'] for r in selected) or 1
        bars=''.join(f'<div class="bar"><span>{esc(r["run_id"][:6])}</span><div><i style="width:{r["wall_clock_seconds"]/maximum*100:.3f}%;background:{"#b4675b" if r["recorded_execution_status"]=="failed" else "#238267"}"></i></div><b>{r["wall_clock_seconds"]:.0f}s</b></div>' for r in selected)
        latency+=f'<article><p class="eyebrow">{bid.upper()} · all measured attempts</p><h2>Runtime, with failures included.</h2><details><summary>Show {len(selected)} recorded runtimes</summary>{bars}</details><p>Machine wall time. Red bars are failures. Mixed cases, methods and versions; no speedup inferred.</p></article>'
    ex=results.get('investigation_example');example_html=''
    if ex:
        values=''.join(f'<li><b>{v["value"]:.2f}% viability</b> · <a href="/benchmark-source/{esc(v["source"]["path"])}">{esc(v["source"]["path"])}</a> · {esc(v["source"]["sheet"])} · {esc(v["source"]["cell"])}</li>' for v in ex['values'])
        trajectory=''
        curves=ex.get('trajectories',[]);points=[p for c in curves for p in c['points']]
        if points:
            tmax=max(p['time_hours'] for p in points) or 1;ymax=max(100,max(p['value'] for p in points))
            paths=''
            for index,(c,color) in enumerate(zip(curves,['#238267','#ba8d4b'])):
                coords=' '.join(f'{45+p["time_hours"]/tmax*400:.2f},{185-p["value"]/ymax*150:.2f}' for p in c['points'])
                paths+=f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.5"/><text x="50" y="{15+index*17}" fill="{color}" font-size="10">{esc(c["sheet"])}</text>'
            trajectory=f'<svg viewBox="0 0 480 230" role="img" aria-label="Source viability trajectories"><title>Original sampled viability values; line segments guide the eye and do not establish event onset</title><path d="M45 35V185H445" stroke="#c9d5ce" fill="none"/>{paths}<text x="8" y="40" font-size="10">{ymax:.0f}%</text><text x="25" y="188" font-size="10">0</text><text x="190" y="218" font-size="10">Source time (h), 0–{tmax:.0f}</text></svg>'
        example_html=f'<article class="wide"><p class="eyebrow">Recorded evidence example · {esc(ex["recorded_run_id"][:8])}</p><h2>Reactor divergence worth investigating.</h2>{trajectory}<ul>{values}</ul><p>Original sampled points; connecting lines guide the eye. Frozen source hash checked. Selected cells are examples, not a case-wide accuracy estimate.</p><p>{esc(ex["contradiction_and_uncertainty"])}</p><p>Next: review recipes, independent measurements and source clocks.</p><p>Recorded output reclassified incomplete by the newer coverage audit. {ex["source_checks_passed"]}/{ex["source_checks_count"]} source checks passed; prose and causality remain unqualified.</p></article>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Benchmark report · manufacturing investigation</title><style>{CSS}
main{{max-width:1120px;margin:auto;padding:28px}}h1{{font-size:clamp(36px,6vw,68px);font-weight:500;letter-spacing:-2px;line-height:1.08}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}article{{background:white;padding:28px;border:1px solid #dfe5dd;border-radius:14px;min-width:0}}article p,footer p{{font-size:13px;color:#64766a;line-height:1.6}}.wide{{grid-column:1/-1}}.eyebrow{{text-transform:uppercase;font:11px monospace;letter-spacing:.09em}}.bar{{display:grid;grid-template-columns:85px 1fr 45px;gap:12px;align-items:center;margin:20px 0;font-size:13px}}.bar div{{background:#eef1eb;height:14px}}.bar i{{display:block;height:14px}}svg{{width:100%}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #e4e9e2;white-space:nowrap}}.pipeline{{background:#193e33;color:white;padding:24px;border-radius:12px;line-height:2}}a{{color:#238267}}@media(max-width:650px){{.grid{{grid-template-columns:1fr}}main{{padding:18px}}article{{padding:20px}}}} 
</style><main><nav><a href="/">lotic</a> / benchmark</nav><header><p class="eyebrow">Manufacturing AI OS · measured evidence</p><h1>From scattered data<br>to reviewable investigations.</h1><p>Authentic CHO experiments. A clearly labeled synthetic manufacturing scenario.</p></header><p class="pipeline">Manufacturing data → evidence discovery → anomaly prioritization → competing hypotheses → source checks → human-review tasks</p><div class="grid">{status_chart(results['runs'])}{example_html}{latency}<article><p class="eyebrow">Automated comparison</p><h2>Three methods. Equal obligations.</h2><p>Conventional statistics and fixed assembly; single-pass AI; full Manufacturing OS. Results and failures below. Quality-qualified matched comparisons remain pending.</p><p>Manual engineer, incumbent product and human-hour savings: unmeasured.</p></article><article><p class="eyebrow">Scientific validation</p><h2>Source checks ≠ scientific approval.</h2><p>All publication gates remain pending. Independent blinded review, an approved rubric and output-bound adjudication are required.</p></article></div><details><summary>All attempts, metrics and reproducibility</summary><p>{len(results.get("unfinalized_records",[]))} additional trace-only record(s) have unknown execution/method/outcome and are listed separately in the JSON report.</p><p>Accuracy and coverage are selected frozen field checks, expressed as fractions. Unknown cost stays unknown.</p><div class="scroll"><table><thead><tr><th>Run</th><th>Case</th><th>Method</th><th>Execution</th><th>Field accuracy</th><th>Coverage</th><th>Seconds</th><th>Inference USD</th></tr></thead><tbody>{rows}</tbody></table></div><p><a href="/benchmark-details">Detailed methodology and source reports</a></p></details><footer><p>{esc(DISCLOSURE)}</p><p><a href="/benchmark-artifact/BENCHMARK_RESULTS.json">BENCHMARK_RESULTS.json</a> · <a href="/benchmark-artifact/BENCHMARK_REPORT.md">BENCHMARK_REPORT.md</a> · <a href="/benchmark-artifact/FAILURE_ANALYSIS.md">FAILURE_ANALYSIS.md</a> · <a href="/benchmark-artifact/REPRODUCE.md">REPRODUCE.md</a> · <a href="/benchmark-artifact/PUBLIC_DEMO_SUMMARY.md">PUBLIC_DEMO_SUMMARY.md</a> · <a href="/benchmark-artifact/PUBLIC_SOURCE_AUDIT.json">PUBLIC_SOURCE_AUDIT.json</a></p></footer></main></html>'''


def build(root=ROOT):
    results=load_results(root);results['investigation_example']=example(root)
    dump=json.dumps(results,indent=2,sort_keys=True)+'\n';(root/'BENCHMARK_RESULTS.json').write_text(dump)
    lines=['# Manufacturing AI OS benchmark','',DISCLOSURE,'',
           'Publication snapshot: every recorded v2 attempt is included. Historical host completion is separate from current report completeness. Source values are not scientific qualification.','',
           '| Dataset / method | Attempts | Recorded completed | Incomplete | Failed | Recorded technical checks passed |',
           '|---|---:|---:|---:|---:|---:|']
    for bid in ('cho','fresenius'):
        for method in ('conventional','retrieval_llm','full_rlm'):
            selected=[r for r in results['runs'] if r['benchmark_id']==bid and r['mode']==method and r['attempted']];counts=Counter(r['recorded_execution_status'] for r in selected)
            lines.append(f'| {bid} / {method} | {len(selected)} | {counts["completed"]} | {counts["incomplete"]} | {counts["failed"]} | {sum(r["technical_checks_passed"] for r in selected)} |')
    lines+=['','These mixed historical cohorts are descriptive. Matched, fixed-version repeats and independently assessed investigation quality are pending; no relative performance or productivity claim is justified.','',
            '## Unfinalized records','',
            *[f'- `{r["run_id"]}` / {r["case_id"]}: {r["explanation"]} Last recorded stage: {r["last_recorded_action"]}. Trace: [{r["trace"]}]({r["trace"]}).' for r in results['unfinalized_records']], '',
            '## Gates','',*[f'- {k}: {v}' for k,v in results['gates'].items()],'',
            '## Per-attempt measurements','',
            '| Run / case / method | Selected field checks | Citation validity | Seconds | Input / output tokens | Inference cost USD |',
            '|---|---|---|---:|---|---|']
    for r in results['runs']:
        f=r.get('field_accuracy') or {};c=r.get('citation_location_validity') or {};u=r['usage']
        lines.append(f'| [{r["run_id"][:8]}]({r["artifact"]}) / {r["case_id"]} / {r["mode"]} | {f.get("correct","—")}/{f.get("checked","—")} checked; {f.get("missing","—")} missing | {show(c.get("value"))} ({c.get("checked","—")} checked) | {show(r["wall_clock_seconds"])} | {show(u.get("input_tokens"))} / {show(u.get("output_tokens"))} | {show(u.get("inference_cost_usd"))} |')
    lines+=['','Root-session token totals do not include all child usage in historical runs. Total costs, including compute/OCR/tools, remain unmeasured. A zero reported by an unpriced provider is preserved as a raw telemetry value in JSON and shown as unknown.','',
            'Claim support, scientific plausibility, relevance precision, contradiction coverage, human effort and untouched generalization remain unmeasured unless explicitly annotated per run. Pending review is neither an approved result nor a scientific failure.','',
            '## Recorded investigation example','',json.dumps(results.get('investigation_example'),indent=2),'',
            '## Safe public statements','',
            '- The system ingests laboratory/manufacturing evidence, computes descriptive signals, retrieves source locations and proposes tasks for human review.',
            '- Selected source values and structured calculations can be checked against original files; that does not prove a root cause.',
            '- This is an engineering demonstration under development. Reliability, scientific qualification and effort savings require further evaluation.']
    (root/'BENCHMARK_REPORT.md').write_text('\n'.join(lines)+'\n')
    failures=['# Failure analysis','', 'Historical artifacts remain unchanged. Categories below diagnose execution; qualification pending review is reported separately.','']
    for r in results['runs']:
        failures += [f'## {r["run_id"]} · {r["case_id"]} · {r["mode"]}',
                     f'Execution: {r["recorded_execution_status"]}; publication: {r["publication_status"]}.',
                     f'Diagnosis: {r["diagnostics"]["category"]}. {r["diagnostics"]["action"]}',
                     f'Case hash: `{r["case_hash"]}`; code fingerprint: `{(r.get("environment") or {}).get("working_tree_code_sha256","not captured in legacy run")}`.',
                     f'Artifact: [{r["artifact"]}]({r["artifact"]}).','']
    (root/'FAILURE_ANALYSIS.md').write_text('\n'.join(failures)+'\n')
    (root/'PUBLIC_DEMO_SUMMARY.md').write_text('''# Public demonstration narrative

Manufacturing investigations often start with scattered measurements and records. This engineering demo shows a path from raw evidence to prioritized observations, competing explanations, original-source checks and human-review tasks.

CHO uses authentic laboratory data. A recorded investigation identified reactor divergence worth examining. Show the exact workbook/sheet/cell references in BENCHMARK_RESULTS.json, the source values and competing explanations. Label it **recorded**, and disclose that the newer audit found incomplete dataset-wide coverage and unresolved numerical prose. Do not present it as a qualified final investigation.

The Fresenius example is **a synthetic manufacturing reconstruction informed by publicly available FDA-related materials**. Its batch events and agent findings belong to the simulation. Fresenius did not provide internal data or endorse, participate in or validate this demo.

Suggested walkthrough: open raw sources; show evidence discovery and the coverage ledger; inspect a prioritized candidate; compare operating-strategy, measurement and process-stress hypotheses; open exact source coordinates; show missing-evidence requests and proposed engineer tasks. No regulated action is executed.

If validated on real operations, source retrieval and review preparation could reduce manual work. Human-hour savings, causal accuracy, yield improvements and competitor superiority have not been measured. All publication gates remain pending in this snapshot. Use it as a transparent engineering preview, not a validated benchmark announcement.
''')
    destination=root/'benchmark/application/static/publication-benchmark.html';destination.write_text(dashboard(results))
    return results


if __name__=='__main__':
    result=build();print(json.dumps({'attempts':len(result['runs']),'gates':result['gates']}))
