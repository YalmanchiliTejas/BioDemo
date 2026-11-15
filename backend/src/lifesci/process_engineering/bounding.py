"""Fit a result into the model's context without cutting it mid-structure.

Cutting a JSON string at a character count hides whatever came after the cut and tells the model nothing about
what is missing (live: a three-batch comparison arrived with one batch; the answer reported one). Here long lists
and strings are shortened in place, each with a marker that says how much was left out, so the result stays valid
JSON and the model can see exactly what it has not been shown and ask for it.
"""
import json
from typing import Any


def _trim(value: Any, items: int, chars: int) -> Any:
    if isinstance(value, dict):
        return {k: _trim(v, items, chars) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > items:
            return [*(_trim(v, items, chars) for v in value[:items]),
                    {'not_shown': len(value) - items, 'of': len(value),
                     'note': 'the rest of this list is saved in the result; page it or narrow the request'}]
        return [_trim(v, items, chars) for v in value]
    if isinstance(value, str) and len(value) > chars:
        return value[:chars] + f' … [{len(value) - chars} more characters not shown]'
    return value


def bounded(value: Any, limit: int) -> tuple[str, bool]:
    """JSON text of at most `limit` characters, and whether anything was left out."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text, False
    items = 256
    while True:
        text = json.dumps(_trim(value, items, max(200, items * 40)), ensure_ascii=False, default=str)
        if len(text) <= limit or items == 1:
            break
        items //= 2
    if len(text) > limit:
        keys = sorted(value) if isinstance(value, dict) else []
        text = json.dumps({'not_shown': 'this result is too large to show even in outline',
                           'top_level_fields': keys[:50], 'note': 'read a narrower record, or page the source'},
                          ensure_ascii=False)
    return text, True


if __name__ == '__main__':
    wide = {'summary': 'ok', 'rows': [{'batch': f'B{i}', 'values': list(range(40))} for i in range(400)]}
    text, cut = bounded(wide, 20_000)
    shown = json.loads(text)  # still valid JSON
    assert cut and len(text) <= 20_000 and shown['summary'] == 'ok'
    assert shown['rows'][-1]['of'] == 400 and shown['rows'][-1]['not_shown'] > 0
    assert bounded({'a': 1}, 100) == ('{"a": 1}', False)
    assert json.loads(bounded({'t': 'x' * 100_000}, 2_000)[0])['t'].endswith('not shown]')
    print('ok')
