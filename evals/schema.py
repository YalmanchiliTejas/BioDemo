"""Reject unknown timeline events and assertions rather than silently dropping coverage."""
from datetime import datetime
from pathlib import Path
import yaml

EVENTS={'user_message','enable_followup','close_session','ingest_document','inject_document',
        'equipment_alert','restart_runtime','duplicate_delivery','scheduled_tick',
        'inject_tool_failure','seed_isolation'}
ASSERTIONS={'autonomous_progress','background_trigger','evidence_in_state','notification','recall',
            'two_sessions','checkpoint','no_unauthorised_writes','no_duplicate_notifications',
            'no_new_provider_calls','no_simulation','work_status_any_of','tool_recovered',
            'no_scope_leakage','current_revision','approval_boundary','tool_any_of','simulation_executed'}


def load_case(path):
    case=yaml.safe_load(Path(path).read_text())
    for key in ('id','world','mission_goal','initial_clock','limits','timeline','final_expect'):
        if key not in case:raise ValueError(f'missing {key}')
    for name,value in case['limits'].items():
        if not isinstance(value,int) or value<1 or value>3600:
            raise ValueError('limits must be positive bounded integers: '+name)
    previous=datetime.fromisoformat(case['initial_clock'])
    if previous.tzinfo is None:raise ValueError('clock must include a timezone')
    if case['limits']['max_test_steps'] < len(case['timeline']):raise ValueError('timeline exceeds step cap')
    for event in case['timeline']:
        if event['type'] not in EVENTS:raise ValueError('unknown event: '+event['type'])
        stamp=datetime.fromisoformat(event['at'])
        if stamp.tzinfo is None or stamp<previous:raise ValueError('unordered or naive event clock')
        previous=stamp
        validate_expect(event.get('expect',{}))
    validate_expect(case['final_expect'])
    return case


def validate_expect(expect):
    unknown=set(expect)-ASSERTIONS
    if unknown:raise ValueError(f'unknown assertions: {sorted(unknown)}')
    if 'notification' in expect and expect['notification']['mode'] not in ('stay_silent','notify_if_material','required'):
        raise ValueError('unknown notification mode')
