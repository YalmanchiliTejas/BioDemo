"""Recover real provider receipts even when final report validation failed."""
import json
from pathlib import Path


def recover_usage(directory):
    directory=Path(directory)
    saved=directory/'provider-usage.json'
    if saved.is_file():return json.loads(saved.read_text())
    response=directory/'single-pass-response.json'
    if response.is_file():
        value=json.loads(response.read_text())
        return {**value.get('usage',{}),'model_id':value.get('model'),'model_calls':1,
                'inference_cost_usd':None,'total_cost_usd':None,'cost_status':'pricing_not_captured',
                'usage_scope':'single_pass_provider_response; failed_validation_included'}
    totals={'model_calls':0,'input_tokens':0,'output_tokens':0,'cached_input_tokens':0}
    for path in directory.glob('*.jsonl'):
        if path.name.endswith('.tools.jsonl'):continue
        for line in path.read_text(errors='replace').splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            message=event.get('message') or {}
            if event.get('type')=='message_end' and isinstance(message.get('usage'),dict):
                u=message['usage'];totals['model_calls']+=1
                totals['input_tokens']+=u.get('input',0);totals['output_tokens']+=u.get('output',0)
                totals['cached_input_tokens']+=u.get('cacheRead',0)
    if not totals['model_calls']:return {}
    return {**totals,'inference_cost_usd':None,'total_cost_usd':None,
            'usage_scope':'root_sdk_session_only; failed_execution_included','cost_status':'provider_and_child_telemetry_incomplete'}
