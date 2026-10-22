"""Discover source time coordinates without treating row numbers as elapsed time."""
from __future__ import annotations

import re

HOUR_FACTORS = {'h':1.0,'hr':1.0,'hrs':1.0,'hour':1.0,'hours':1.0,
                'min':1/60,'minute':1/60,'minutes':1/60,'s':1/3600,
                'sec':1/3600,'second':1/3600,'seconds':1/3600,'d':24.0,'day':24.0,'days':24.0}


def discover_time_axis(columns: list[dict]) -> dict:
    elapsed, calendar = [], []
    for column in columns:
        name = column['name'].lower()
        if any(word in name for word in ('available','released','approved','reviewed','reported')):
            continue
        if not re.search(r'\b(time|timestamp|date|occurred|collected|sampled)\b',name.replace('_',' ')):
            continue
        unit = (column.get('unit') or '').lower().strip()
        if unit in HOUR_FACTORS:
            elapsed.append({**column,'kind':'elapsed_hours','factor':HOUR_FACTORS[unit]})
        elif unit == '':
            calendar.append({**column,'kind':'calendar_hours','factor':None})
    candidates = elapsed or calendar
    if len(candidates) == 1:
        return {**candidates[0],'status':'source_column'}
    return {'status':'ambiguous' if candidates else 'unavailable','kind':'unresolved'}
