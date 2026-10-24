"""Durable mission orchestration (D09, D40).

``temporal_workflows`` holds deterministic workflow code only (no domain imports).
``temporal`` holds activities, the ``TemporalScheduler`` port implementation and
worker construction. Domain records stay in the record store; workflow history
carries only identifiers and wake reasons.
"""
