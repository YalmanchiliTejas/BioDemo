"""Where in the product a person can carry on from an assistant answer: the page for a record the answer read.

Derived from the steps the turn actually ran, never from the answer's wording, so a link always points at
something that was opened under the person's own access. The assistant finds; the page is where the person works.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

DELIVERY = 'cmo-verified-delivery:'
LIMIT = 4


def _mentioned(parameters: list[str], *texts: str | None) -> str | None:
    """The first of the delivery's parameters that the question or answer names."""
    text = ' '.join(t for t in texts if t).casefold()
    for parameter in parameters:
        if parameter.casefold() in text or parameter.replace('_', ' ').casefold() in text:
            return parameter
    return None


def open_links(steps: list[dict[str, Any]], *, evidence, question: str | None = None, answer: str | None = None) -> list[dict[str, str]]:
    """``evidence(record_id)`` returns the state of an evidence record the person may read, or None."""
    links: list[dict[str, str]] = []

    def add(label: str, href: str) -> None:
        if len(links) < LIMIT and all(link['href'] != href for link in links):
            links.append({'label': label, 'href': href})

    for step in steps:
        payload = step.get('payload') or {}
        if step.get('status') != 'completed' or step.get('task_kind') != 'workspace_read':
            continue
        kind, record_id = payload.get('kind'), str(payload.get('record_id') or '')
        if kind == 'deviation_signal' and record_id:
            add('Open the signal and its chart', f'/signals/?id={quote(record_id, safe="")}')
        elif kind == 'evidence' and record_id.startswith(DELIVERY):
            state = evidence(record_id)
            meta = (state or {}).get('metadata') or {}
            # A seeded synthetic dataset has no delivery behind it, so there is no page to open.
            if state is None or meta.get('synthetic'):
                continue
            parameter = _mentioned(list(meta.get('parameters') or []), question, answer)
            add(f"Plot {parameter.replace('_', ' ')} across batches" if parameter else 'Plot this data across batches',
                '/trends/' + (f'?parameter={quote(parameter, safe="")}' if parameter else ''))
            add('Open the delivery and its source files', f'/cmo/?run={quote(record_id[len(DELIVERY):], safe="")}')
    return links
