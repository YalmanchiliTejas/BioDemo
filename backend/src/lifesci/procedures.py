"""Shared procedure engine for recipes, work instructions and lab methods (LS-006, LS-007, LS-014,
LS-016, LS-033, LS-034; supports LS-003).

One typed-step definition model serves manufacturing recipes, work instructions and laboratory methods.
Definitions are validated deterministically (cycles, dependencies, units, limits, expression names);
revisions are immutable and become effective only through an approved ``publish_procedure`` proposal.
Execution instances pin a revision and keep their own resolved copy, so a later revision never changes
an active run. Numeric rules use a small AST-based evaluator (arithmetic, comparison and boolean over
names; no calls or attribute access). Document interpretation is a deterministic baseline parser with
character-offset source spans; its output is a draft that still requires human review.
"""

from __future__ import annotations

import ast
import copy
import math
import operator
import re
from functools import lru_cache
from typing import Any, Callable, Mapping

from .actions import CONTENT_FIELDS, ActionService
from .evidence import EvidenceRef, EvidenceService
from .identity import AccessContext, AuthorizationError, Decision, IdentityService
from .ids import content_hash, iso, new_id, utc_now
from .records import SIGNATURE_MEANINGS
from .store import ConflictError, NotFoundError, RecordStore

CATEGORIES = ("recipe", "work_instruction", "lab_method")
STEP_KINDS = ("instruction", "data_entry", "calculation", "material_check", "equipment_check", "signature", "sample")
MEDIA_TYPES = ("image", "video", "pdf")
ENFORCEMENT_KEYS = ("strict_dependencies", "hold_on_out_of_limit", "require_resources")
AMENDABLE_FIELDS = ("low", "high", "target")
SATISFIED = frozenset({"completed", "not_applicable", "skipped_branch"})
TERMINAL = SATISFIED
PSEUDO_UNITS = frozenset({"pH", "OD", "OD600", "AU", "count", "ratio", "1", "%"})
DEVICE_GUIDANCE_NOTE = "declared, not device-tested"
_TEMPLATE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class ProcedureInvalid(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class ExpressionError(ValueError):
    pass


# --- safe expression evaluation ---------------------------------------------------------------
_ARITH: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_CMP: dict[type, Callable[[Any, Any], bool]] = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.Eq: operator.eq, ast.NotEq: operator.ne}
_ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Constant, ast.Name, ast.Load,
            ast.And, ast.Or, ast.Not, ast.UAdd, ast.USub, *_ARITH, *_CMP)


def _parse(expr: str) -> ast.Expression:
    if not isinstance(expr, str) or not expr.strip() or len(expr) > 500:
        raise ExpressionError("expression must be a non-empty string up to 500 characters")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression: {exc.msg}") from None
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExpressionError(f"{type(node).__name__} is not allowed in expressions")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise ExpressionError("only numeric constants are allowed")
    return tree


def expr_names(expr: str) -> set[str]:
    return {n.id for n in ast.walk(_parse(expr)) if isinstance(n, ast.Name)}


def safe_eval(expr: str, env: Mapping[str, Any]) -> Any:
    def go(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return go(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ExpressionError(f"undefined name {node.id}")
            v = env[node.id]
            if not isinstance(v, (int, float)):
                raise ExpressionError(f"{node.id} is not numeric")
            return v
        if isinstance(node, ast.BinOp):
            left, right = go(node.left), go(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 64:
                raise ExpressionError("exponent too large")
            try:
                out = _ARITH[type(node.op)](left, right)
            except ZeroDivisionError:
                raise ExpressionError("division by zero") from None
            except OverflowError:
                raise ExpressionError("numeric overflow") from None
            if isinstance(out, float) and not math.isfinite(out):
                raise ExpressionError("non-finite result")
            return out
        if isinstance(node, ast.UnaryOp):
            v = go(node.operand)
            return not v if isinstance(node.op, ast.Not) else (-v if isinstance(node.op, ast.USub) else +v)
        if isinstance(node, ast.BoolOp):
            vals = [go(v) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.Compare):
            left = go(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = go(comp)
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        raise ExpressionError(f"{type(node).__name__} is not allowed")

    return go(_parse(expr))


# --- units ------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _ureg() -> Any:
    import pint
    return pint.UnitRegistry()


@lru_cache(maxsize=512)
def unit_ok(unit: str | None) -> bool:
    if unit in (None, ""):
        return True
    if unit in PSEUDO_UNITS:
        return True
    try:
        _ureg().Unit(unit)
        return True
    except Exception:
        return False


def convert(value: float, src: str | None, dst: str | None) -> float:
    if src == dst or not src or not dst:
        return value
    if src in PSEUDO_UNITS or dst in PSEUDO_UNITS:
        raise ValueError(f"cannot convert {src} to {dst}")
    try:
        return float(_ureg().Quantity(value, src).to(dst).magnitude)
    except Exception as exc:
        raise ValueError(f"cannot convert {src} to {dst}: {type(exc).__name__}") from None


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# --- templates --------------------------------------------------------------------------------
def resolve_template(definition: dict[str, Any], params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Substitute ``{{name}}`` placeholders; a whole-string placeholder keeps the parameter's type."""
    params = dict(params or {})
    declared = {p["name"]: p for p in definition.get("template_params", [])}
    values: dict[str, Any] = {}
    for name, spec in declared.items():
        if name in params:
            v = params[name]
        elif "default" in spec:
            v = spec["default"]
        else:
            raise ValueError(f"template parameter {name} has no value")
        if spec.get("type", "number") == "number" and not _is_num(v):
            raise ValueError(f"template parameter {name} must be numeric")
        if spec.get("allowed") is not None and v not in spec["allowed"]:
            raise ValueError(f"template parameter {name}={v!r} not in allowed values")
        values[name] = v
    unknown = set(params) - set(declared)
    if unknown:
        raise ValueError(f"unknown template parameters {sorted(unknown)}")

    def sub(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: sub(v) for k, v in node.items()}
        if isinstance(node, list):
            return [sub(v) for v in node]
        if isinstance(node, str):
            whole = _TEMPLATE.fullmatch(node.strip())
            if whole:
                return values.get(whole.group(1), node)
            return _TEMPLATE.sub(lambda m: str(values.get(m.group(1), m.group(0))), node)
        return node

    out = sub(copy.deepcopy(definition))
    out["template_values"] = values
    return out


def normalize_definition(definition: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(definition.get("steps", []), list):
        raise ValueError("procedure steps must be a list")
    for step in definition.get("steps", []):
        if not isinstance(step, dict):
            raise ValueError("each procedure step must be an object")
        for key in ("parameters", "depends_on", "required_signatures"):
            if key in step and not isinstance(step[key], list):
                raise ValueError(f"step {key} must be a list")
        if any(not isinstance(p, dict) for p in step.get("parameters", [])):
            raise ValueError("step parameters must be objects")
        for key in ("calculation", "branch", "resources", "enforcement"):
            if step.get(key) is not None and not isinstance(step[key], dict):
                raise ValueError(f"step {key} must be an object")
    out = copy.deepcopy(definition)
    for step in out.get("steps", []):
        if isinstance(step, dict) and step.get("supported_devices"):
            step["device_guidance_status"] = DEVICE_GUIDANCE_NOTE
    return out


def _all_params(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p["name"]: p for s in steps for p in s.get("parameters", []) if isinstance(p, dict) and "name" in p}


def topo_order(steps: list[dict[str, Any]]) -> list[str]:
    """Kahn's algorithm with definition order as the tie-break; raises ValueError on a cycle."""
    ids = [s["step_id"] for s in steps]
    deps = {s["step_id"]: [d for d in s.get("depends_on", []) if d in ids] for s in steps}
    done: list[str] = []
    while len(done) < len(ids):
        ready = [i for i in ids if i not in done and all(d in done for d in deps[i])]
        if not ready:
            raise ValueError("dependency cycle among " + ", ".join(i for i in ids if i not in done))
        done.append(ready[0])
    return done


def ancestors(steps: list[dict[str, Any]], step_id: str) -> set[str]:
    by_id = {s["step_id"]: s for s in steps}
    seen: set[str] = set()
    stack = list(by_id[step_id].get("depends_on", []))
    while stack:
        d = stack.pop()
        if d in by_id and d not in seen:
            seen.add(d)
            stack.extend(by_id[d].get("depends_on", []))
    return seen


def descendants(steps: list[dict[str, Any]], step_id: str) -> set[str]:
    return {s["step_id"] for s in steps if s["step_id"] != step_id and step_id in ancestors(steps, s["step_id"])}


def validate_definition(definition: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        return ["definition has no steps"]
    declared_t = {p.get("name") for p in definition.get("template_params", []) if isinstance(p, dict)}
    for ref in sorted(set(_TEMPLATE.findall(repr(definition))) - declared_t):
        errs.append(f"placeholder {{{{{ref}}}}} is not a declared template parameter")
    ids: list[str] = []
    for i, s in enumerate(steps):
        sid = s.get("step_id") if isinstance(s, dict) else None
        if not sid or not isinstance(sid, str):
            errs.append(f"step #{i + 1} has no step_id")
        elif sid in ids:
            errs.append(f"duplicate step_id {sid}")
        else:
            ids.append(sid)
    if errs:
        return errs
    probe = definition
    if declared_t or _TEMPLATE.search(repr(definition)):
        try:
            probe = resolve_template({**definition, "template_params": [
                {**p, "default": p.get("default", 1 if p.get("type", "number") == "number" else "x")}
                for p in definition.get("template_params", [])]}, {})
        except ValueError as exc:
            return [str(exc)]
        steps = probe["steps"]
    constants = {k for k, v in (probe.get("constants") or {}).items()}
    for k, v in (probe.get("constants") or {}).items():
        if not _is_num(v):
            errs.append(f"constant {k} must be numeric")
    names_seen: dict[str, str] = {}
    for s in steps:
        sid = s["step_id"]
        if not s.get("title"):
            errs.append(f"step {sid}: missing title")
        if s.get("kind") not in STEP_KINDS:
            errs.append(f"step {sid}: kind {s.get('kind')!r} not one of {list(STEP_KINDS)}")
        for d in s.get("depends_on", []):
            if d not in ids:
                errs.append(f"step {sid}: unknown dependency {d}")
            if d == sid:
                errs.append(f"step {sid}: depends on itself")
        for p in s.get("parameters", []):
            pname = p.get("name")
            if not isinstance(pname, str) or not pname.isidentifier():
                errs.append(f"step {sid}: parameter name {pname!r} is not a valid identifier")
                continue
            if pname in names_seen or pname in constants:
                errs.append(f"step {sid}: parameter {pname} duplicates a name already defined")
            names_seen[pname] = sid
            if not unit_ok(p.get("unit")):
                errs.append(f"step {sid}: unit {p.get('unit')!r} of parameter {pname} is unknown")
            lo, hi, tg = p.get("low"), p.get("high"), p.get("target")
            for label, v in (("low", lo), ("high", hi), ("target", tg)):
                if v is not None and not _is_num(v):
                    errs.append(f"step {sid}: {pname}.{label} must be numeric")
            if _is_num(lo) and _is_num(hi) and lo > hi:
                errs.append(f"step {sid}: parameter {pname} has low {lo} greater than high {hi}")
            elif _is_num(tg) and ((_is_num(lo) and tg < lo) or (_is_num(hi) and tg > hi)):
                errs.append(f"step {sid}: target of {pname} lies outside its limits")
            sr = p.get("site_range")
            if sr is not None and not (_is_num(sr.get("low")) and _is_num(sr.get("high")) and sr["low"] <= sr["high"]):
                errs.append(f"step {sid}: site_range of {pname} is invalid")
        calc = s.get("calculation")
        if s.get("kind") == "calculation" and not calc:
            errs.append(f"step {sid}: calculation step has no calculation")
        if calc:
            cname = calc.get("name")
            if not isinstance(cname, str) or not cname.isidentifier():
                errs.append(f"step {sid}: calculation needs an identifier name")
            elif cname in names_seen or cname in constants:
                errs.append(f"step {sid}: calculation name {cname} duplicates another name")
            else:
                names_seen[cname] = sid
            if not unit_ok(calc.get("unit")):
                errs.append(f"step {sid}: calculation unit {calc.get('unit')!r} is unknown")
            lo, hi = calc.get("low"), calc.get("high")
            if _is_num(lo) and _is_num(hi) and lo > hi:
                errs.append(f"step {sid}: calculation limits low {lo} greater than high {hi}")
        sigs = s.get("required_signatures", [])
        for m in sigs:
            if m not in SIGNATURE_MEANINGS:
                errs.append(f"step {sid}: unknown signature meaning {m!r}")
        if s.get("kind") == "signature" and not sigs:
            errs.append(f"step {sid}: signature step lists no required_signatures")
        for m in s.get("media", []):
            if m.get("type") not in MEDIA_TYPES or not m.get("ref"):
                errs.append(f"step {sid}: media needs type in {list(MEDIA_TYPES)} and a ref")
        for k in s.get("enforcement", {}):
            if k not in ENFORCEMENT_KEYS:
                errs.append(f"step {sid}: unknown enforcement rule {k}")
    if errs:
        return errs
    try:
        topo_order(steps)
    except ValueError as exc:
        return [str(exc)]
    by_id = {s["step_id"]: s for s in steps}
    for s in steps:
        sid = s["step_id"]
        anc = ancestors(steps, sid)
        visible = set(constants) | {p["name"] for p in s.get("parameters", [])}
        visible |= {p["name"] for a in anc for p in by_id[a].get("parameters", [])}
        visible |= {by_id[a]["calculation"]["name"] for a in anc if by_id[a].get("calculation")}
        for label, expr in (("calculation", (s.get("calculation") or {}).get("expr")),
                            ("branch condition", (s.get("branch") or {}).get("condition"))):
            if expr is None:
                continue
            try:
                missing = expr_names(expr) - visible
                if label == "branch condition" and s.get("calculation"):
                    missing -= {s["calculation"]["name"]}
            except ExpressionError as exc:
                errs.append(f"step {sid}: {label}: {exc}")
                continue
            if missing:
                errs.append(f"step {sid}: {label} references undefined names {sorted(missing)}")
        b = s.get("branch")
        if b:
            for key in ("true_next", "false_next"):
                t = b.get(key)
                if t not in ids:
                    errs.append(f"step {sid}: branch {key} {t!r} is not a known step")
                elif sid not in by_id[t].get("depends_on", []):
                    errs.append(f"step {sid}: branch target {t} must depend on {sid}")
            if b.get("true_next") == b.get("false_next"):
                errs.append(f"step {sid}: branch targets must differ")
    return errs


def cascade_skips(steps: dict[str, dict[str, Any]], defs: dict[str, dict[str, Any]]) -> None:
    """A pending step whose every dependency was skipped by a branch is itself skipped."""
    changed = True
    while changed:
        changed = False
        for sid, st in steps.items():
            deps = defs[sid].get("depends_on", [])
            if st["status"] == "pending" and deps and all(steps[d]["status"] == "skipped_branch" for d in deps):
                st["status"] = "skipped_branch"
                st["version"] = st.get("version", 0) + 1
                changed = True


def evaluate_step(step: dict[str, Any], captured: Mapping[str, Any], values: Mapping[str, Any],
                  constants: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic capture/limit/calculation evaluation shared by manufacturing and lab execution."""
    declared = {p["name"]: p for p in step.get("parameters", [])}
    unknown = set(captured) - set(declared)
    if unknown:
        raise ValueError(f"values for undeclared parameters {sorted(unknown)} (calculated values cannot be entered)")
    env = {**constants, **values}
    inputs: dict[str, Any] = {}
    evaluations: list[dict[str, Any]] = []
    for name, p in declared.items():
        if name not in captured:
            raise ValueError(f"missing value for parameter {name}")
        raw = captured[name]
        unit = p.get("unit")
        if isinstance(raw, dict):
            val, given = raw.get("value"), raw.get("unit")
        else:
            val, given = raw, None
        if p.get("type") == "text":
            inputs[name] = str(val)
            continue
        if not _is_num(val):
            raise ValueError(f"parameter {name} must be numeric")
        if given and unit and given != unit:
            if not unit_ok(given):
                raise ValueError(f"unit {given!r} for {name} is unknown")
            val = convert(val, given, unit)
        lo, hi = p.get("low"), p.get("high")
        within = (lo is None or val >= lo) and (hi is None or val <= hi)
        inputs[name] = val
        env[name] = val
        evaluations.append({"name": name, "source": "parameter", "value": val, "unit": unit, "low": lo, "high": hi,
                            "target": p.get("target"), "within_limits": within, "entered_unit": given})
    calculated: dict[str, Any] = {}
    calc = step.get("calculation")
    if calc:
        result = safe_eval(calc["expr"], env)
        lo, hi = calc.get("low"), calc.get("high")
        within = (lo is None or result >= lo) and (hi is None or result <= hi)
        calculated[calc["name"]] = result
        evaluations.append({"name": calc["name"], "source": "calculation", "value": result, "unit": calc.get("unit"),
                            "low": lo, "high": hi, "target": None, "within_limits": within, "expr": calc["expr"]})
    return {"inputs": inputs, "calculated": calculated, "evaluations": evaluations,
            "violations": [e for e in evaluations if not e["within_limits"]]}


def blocking_reasons(inst: dict[str, Any], step_id: str) -> list[str]:
    """Why a step cannot be performed now (dependency order, branch, pause, instance state)."""
    if step_id not in inst["steps"]:
        return [f"unknown step {step_id}"]
    reasons = []
    if inst["status"] != "in_progress":
        reasons.append(f"instance is {inst['status']}")
    status = inst["steps"][step_id]["status"]
    if status not in ("pending", "exception"):
        reasons.append(f"step is {status}")
    if inst["steps"][step_id].get("hold"):
        reasons.append("step is held")
    for d in inst["steps_def"][step_id].get("depends_on", []):
        if inst["steps"][d]["status"] not in SATISFIED:
            reasons.append(f"dependency {d} is {inst['steps'][d]['status']}")
    return reasons


def finish_step(inst: dict[str, Any], step_id: str, new_values: Mapping[str, Any], *, extra: dict[str, Any]) -> dict[str, Any]:
    """Return instance state with the step completed, branch applied, skips cascaded and completion detected."""
    out = copy.deepcopy(inst)
    st = out["steps"][step_id]
    st.update(extra)
    st["status"], st["version"] = "completed", st.get("version", 0) + 1
    out["values"] = {**out["values"], **new_values}
    step = out["steps_def"][step_id]
    if step.get("branch"):
        b = step["branch"]
        taken = bool(safe_eval(b["condition"], {**out.get("constants", {}), **out["values"]}))
        skip = b["false_next"] if taken else b["true_next"]
        st["branch_taken"] = {"condition": b["condition"], "result": taken, "next": b["true_next"] if taken else b["false_next"],
                              "skipped": skip}
        if out["steps"][skip]["status"] == "pending":
            out["steps"][skip].update(status="skipped_branch", version=out["steps"][skip].get("version", 0) + 1)
    cascade_skips(out["steps"], out["steps_def"])
    if all(s["status"] in TERMINAL for s in out["steps"].values()):
        out["status"], out["completed_at"] = "completed", iso(utc_now())
    return out


def _deny(msg: str) -> AuthorizationError:
    return AuthorizationError(Decision(False, msg))


# --- document interpretation -------------------------------------------------------------------
_STEP_RE = re.compile(r"(?m)^[ \t]*(?:Step[ \t]+)?(\d{1,3})[.):][ \t]+(?=\S)", re.I)
_NUM = r"\d+(?:\.\d+)?"
_UNIT = r"(?:°\s?[CF]|%|[A-Za-z]+(?:/[A-Za-z]+)?)"
_PM_RE = re.compile(rf"(?P<t>{_NUM})\s*(?:±|\+/-)\s*(?P<d>{_NUM})(?:\s*(?P<u>{_UNIT}))?")
_BETWEEN_RE = re.compile(rf"between\s+(?P<lo>{_NUM})(?:\s*(?P<u1>{_UNIT}))?\s+and\s+(?P<hi>{_NUM})(?:\s*(?P<u2>{_UNIT}))?", re.I)
_KEYWORDS = (("ph", "pH", "pH"), ("temperature", "temperature", "degC"), ("temp", "temperature", "degC"),
             ("speed", "speed", "rpm"), ("rpm", "speed", "rpm"), ("volume", "volume", None), ("time", "time", None),
             ("duration", "time", None), ("pressure", "pressure", None), ("conductivity", "conductivity", None))
_DEGREE = {"°C": "degC", "°F": "degF"}


def _norm_unit(raw: str | None, fallback: str | None) -> str | None:
    if not raw:
        return fallback
    raw = re.sub(r"\s+", "", raw)
    raw = _DEGREE.get(raw, raw)
    return raw if unit_ok(raw) else None


def _name_guess(context: str, used: set[str]) -> tuple[str, str | None, bool]:
    window = context[-60:].lower()
    best = None
    for kw, name, unit in _KEYWORDS:
        for m in re.finditer(rf"\b{kw}\b", window):
            if best is None or m.start() > best[0]:
                best = (m.start(), name, unit)
    base, unit, unresolved = (best[1], best[2], False) if best else ("value", None, True)
    name, i = base, 1
    while name in used:
        i += 1
        name = f"{base}_{i}"
    used.add(name)
    return name, unit, unresolved


def parse_procedure_text(text: str) -> dict[str, Any]:
    """Split numbered steps and extract parameter ranges. Every item carries absolute character offsets."""
    matches = list(_STEP_RE.finditer(text))
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    used: set[str] = set()
    if not matches:
        issues.append("no numbered steps found")
    for idx, m in enumerate(matches):
        start, end = m.start(), (matches[idx + 1].start() if idx + 1 < len(matches) else len(text))
        while end > start and text[end - 1].isspace():
            end -= 1
        body_start = m.end()
        body = text[body_start:end]
        first = re.split(r"(?<=[.:;])\s", body.strip(), maxsplit=1)[0][:80]
        params: list[dict[str, Any]] = []
        for pm in _PM_RE.finditer(body):
            t, d = float(pm["t"]), float(pm["d"])
            u_raw, u_end = pm["u"], pm.end()
            unit = _norm_unit(u_raw, None)
            if u_raw and unit is None:
                u_end = pm.end("d")
            name, kw_unit, unresolved = _name_guess(body[:pm.start()], used)
            params.append(_param_item(name, unit or kw_unit, round(t - d, 10), round(t + d, 10), t, unresolved,
                                      body_start + pm.start(), body_start + u_end, text))
        for bm in _BETWEEN_RE.finditer(body):
            lo, hi = float(bm["lo"]), float(bm["hi"])
            raw = bm["u2"] or bm["u1"]
            unit = _norm_unit(raw, None)
            name, kw_unit, unresolved = _name_guess(body[:bm.start()], used)
            stop = bm.end() if (not raw or unit) else bm.end("hi")
            params.append(_param_item(name, unit or kw_unit, lo, hi, None, unresolved,
                                      body_start + bm.start(), body_start + stop, text))
            if lo > hi:
                issues.append(f"step {m.group(1)}: extracted range {lo}..{hi} is inverted")
        steps.append({"step_number": int(m.group(1)), "step_id": f"S{int(m.group(1))}", "title": first,
                      "text": text[start:end], "source_span": {"start": start, "end": end, "text": text[start:end]},
                      "kind": "data_entry" if params else "instruction", "parameters": params})
    numbers = [s["step_number"] for s in steps]
    if numbers and numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        issues.append("step numbering is not sequential; order needs review")
    return {"steps": steps, "issues": issues}


def _param_item(name: str, unit: str | None, low: float, high: float, target: float | None, unresolved: bool,
                start: int, end: int, text: str) -> dict[str, Any]:
    return {"name": name, "unit": unit, "low": low, "high": high, "target": target, "name_unresolved": unresolved,
            "source_span": {"start": start, "end": end, "text": text[start:end]},
            "extraction": "baseline pattern match; requires review"}


def _span_ok(span: Any, text: str) -> bool:
    try:
        s, e = int(span["start"]), int(span["end"])
    except (TypeError, KeyError, ValueError):
        return False
    return 0 <= s < e <= len(text) and ("text" not in span or text[s:e] == span["text"])


# --- service ------------------------------------------------------------------------------------
class ProcedureService:
    def __init__(self, store: RecordStore, identity: IdentityService, actions: ActionService,
                 evidence: EvidenceService | None = None) -> None:
        self.store, self.idn, self.actions, self.evidence = store, identity, actions, evidence
        self._validators: dict[str, Callable[[dict[str, Any]], list[str]]] = {}

    def register_validator(self, category: str, fn: Callable[[dict[str, Any]], list[str]]) -> None:
        self._validators[category] = fn

    # --- validation and preview (LS-006) ---
    def validate(self, definition: dict[str, Any], category: str | None = None) -> list[str]:
        errs = validate_definition(definition)
        if not errs and category in self._validators:
            errs = self._validators[category](definition)
        return errs

    def preview(self, definition: dict[str, Any], params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        resolved = resolve_template(definition, params)
        errs = validate_definition(resolved)
        if errs:
            raise ProcedureInvalid(errs)
        steps = resolved["steps"]
        by_id = {s["step_id"]: s for s in steps}
        order = topo_order(steps)
        env = {**(resolved.get("constants") or {}), **{k: v for k, v in resolved["template_values"].items() if _is_num(v)}}
        forced_skip: set[str] = set()
        conditional: set[str] = set()
        out = []
        for pos, sid in enumerate(order, 1):
            s = by_id[sid]
            deps = s.get("depends_on", [])
            skipped = sid in forced_skip or bool(deps and all(d in forced_skip for d in deps))
            cond = (not skipped) and (sid in conditional or any(d in conditional for d in deps))
            if skipped:
                forced_skip.add(sid)
            branch_res = None
            if s.get("branch") and not skipped:
                b = s["branch"]
                try:
                    result: bool | None = bool(safe_eval(b["condition"], env))
                except ExpressionError:
                    result = None
                if result is None:
                    conditional.update({b["true_next"], b["false_next"]})
                else:
                    forced_skip.add(b["false_next"] if result else b["true_next"])
                branch_res = {"condition": b["condition"], "result": result,
                              "selected": None if result is None else (b["true_next"] if result else b["false_next"])}
            wave = 1 + max((o["wave"] for o in out if o["step_id"] in deps), default=0)
            out.append({"order": pos, "step_id": sid, "title": s["title"], "kind": s["kind"], "wave": wave,
                        "status": "skipped_branch" if skipped else ("conditional" if cond else "planned"),
                        "depends_on": deps, "parallel_group": s.get("parallel_group"),
                        "parameters": s.get("parameters", []), "calculation": s.get("calculation"),
                        "required_signatures": s.get("required_signatures", []), "media": s.get("media", []),
                        "enforcement": s.get("enforcement", {}), "branch": branch_res})
        return out

    # --- draft / submit / publish (LS-006, LS-033) ---
    def create_draft(self, ctx: AccessContext, procedure_id: str, *, name: str, category: str,
                     definition: dict[str, Any], site_id: str | None = None) -> dict[str, Any]:
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {list(CATEGORIES)}")
        self.idn.require(ctx, "propose", "procedure", procedure_id, site_id=site_id)
        definition = normalize_definition(definition)
        state = {"procedure_id": procedure_id, "name": name, "category": category, "scope": "site" if site_id else "global",
                 "site_id": site_id, "status": "draft", "draft": definition, "draft_hash": content_hash(definition),
                 "effective_revision": None, "revisions": [], "pending_submission": None, "parent": None,
                 "overrides": {}, "local_approval": None, "adaptations": [], "created_by": ctx.actor_id}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, "procedure", procedure_id, state, expected_revision=None, action="create_draft",
                         event_type="procedure.draft_created", event_payload={"procedure_id": procedure_id})
        return {**state, "revision": rec.revision, "validation_errors": self.validate(definition, category)}

    def update_draft(self, ctx: AccessContext, procedure_id: str, definition: dict[str, Any], *,
                     expected_revision: int) -> dict[str, Any]:
        definition = normalize_definition(definition)
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure", procedure_id)
            self.idn.require(ctx, "propose", "procedure", procedure_id, site_id=rec.state["site_id"], tx=tx)
            state = {**rec.state, "draft": definition, "draft_hash": content_hash(definition), "status": "draft",
                     "pending_submission": None}
            out = tx.put(ctx.tenant_id, "procedure", procedure_id, state, expected_revision=expected_revision,
                         action="update_draft", event_type="procedure.draft_updated",
                         event_payload={"procedure_id": procedure_id})
        return {**state, "revision": out.revision, "validation_errors": self.validate(definition, state["category"])}

    def submit_for_publication(self, ctx: AccessContext, procedure_id: str, *, rationale: str,
                               owner_id: str | None = None) -> dict[str, Any]:
        rec = self.store.read().require(ctx.tenant_id, "procedure", procedure_id)
        s = rec.state
        self.idn.require(ctx, "propose", "procedure", procedure_id, site_id=s["site_id"])
        errors = self.validate(s["draft"], s["category"])
        if errors:
            raise ProcedureInvalid(errors)
        dhash = content_hash(s["draft"])
        pending = s.get("pending_submission")
        if pending and pending["definition_hash"] == dhash:
            existing = self.store.read().get(ctx.tenant_id, "proposal", pending["proposal_id"])
            if existing and existing.state["status"] in ("proposed", "approved"):
                return existing.state
        next_rev = len(s["revisions"]) + 1
        snap_id = f"{procedure_id}#draft-{dhash[:16]}"
        with self.store.transaction(ctx.actor_id) as tx:
            if tx.get(ctx.tenant_id, "procedure_draft_snapshot", snap_id) is None:
                tx.put(ctx.tenant_id, "procedure_draft_snapshot", snap_id,
                       {"procedure_id": procedure_id, "definition": s["draft"], "definition_hash": dhash},
                       expected_revision=None, action="snapshot")
        proposal = self.actions.propose(
            ctx, target_system="native", operation="publish_procedure", target_id=procedure_id,
            payload={"procedure_id": procedure_id, "revision": next_rev, "definition_hash": dhash,
                     "category": s["category"], "scope": s["scope"], "parent": s["parent"]},
            basis=[{"kind": "procedure_draft_snapshot", "id": snap_id, "revision": 1, "site_id": s["site_id"]}],
            rationale=rationale, expected_result=f"{procedure_id} revision {next_rev} becomes effective",
            owner_id=owner_id or ctx.actor_id, site_id=s["site_id"], record_class="procedure")
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.require(ctx.tenant_id, "procedure", procedure_id)
            tx.put(ctx.tenant_id, "procedure", procedure_id,
                   {**cur.state, "status": "submitted",
                    "pending_submission": {"proposal_id": proposal["proposal_id"], "definition_hash": dhash,
                                           "revision": next_rev, "snapshot_id": snap_id},
                    "local_approval": ({**(cur.state["local_approval"] or {}), "status": "pending"}
                                       if cur.state["parent"] else None)},
                   expected_revision=cur.revision, action="submit_for_publication")
        return proposal

    def publish(self, ctx: AccessContext, procedure_id: str, approved_proposal_id: str) -> dict[str, Any]:
        if ctx.actor_kind == "agent":
            raise _deny("agent credentials cannot publish procedures")
        self.idn.require(ctx, "propose", "procedure", procedure_id)
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure", procedure_id)
            prop = tx.require(ctx.tenant_id, "proposal", approved_proposal_id).state
            self.idn.require(ctx, "propose", "procedure", procedure_id, site_id=rec.state["site_id"], tx=tx)
            if prop["operation"] != "publish_procedure" or prop["target_id"] != procedure_id:
                raise ValueError("proposal does not authorize publishing this procedure")
            if prop["status"] != "approved":
                raise PermissionError(f"publication proposal is {prop['status']}, not approved")
            if content_hash({k: prop.get(k) for k in CONTENT_FIELDS}) != prop["content_hash"]:
                raise PermissionError("proposal content no longer matches its approved hash")
            approvals = [a.state for a in tx.list(ctx.tenant_id, "approval", lambda a: a["proposal_id"] == approved_proposal_id
                                                  and a["content_hash"] == prop["content_hash"] and a["decision"] == "approved")]
            if not {a["role"] for a in approvals} >= set(prop["required_roles"]):
                raise PermissionError("required approvals are missing for this proposal content")
            for approval in approvals:
                live = self.idn.context_for(ctx.tenant_id, approval["actor_id"], role=approval["role"])
                if approval["role"] not in live.roles or not self.idn.check(
                    live, "approve", "proposal", approved_proposal_id, site_id=rec.state["site_id"], tx=tx
                ):
                    raise PermissionError("publication approver no longer holds authority at this site")
            s = rec.state
            dhash = content_hash(s["draft"])
            if prop["payload"]["definition_hash"] != dhash:
                raise ValueError("draft changed after approval; submit the current draft for approval")
            n = prop["payload"]["revision"]
            if n != len(s["revisions"]) + 1:
                raise ConflictError(f"revision {n} is not the next revision ({len(s['revisions']) + 1})")
            rev_state = {"procedure_id": procedure_id, "revision": n, "definition": s["draft"], "definition_hash": dhash,
                         "category": s["category"], "scope": s["scope"], "site_id": s["site_id"], "parent": s["parent"],
                         "proposal_id": approved_proposal_id, "approval_ids": [a["approval_id"] for a in approvals],
                         "published_by": ctx.actor_id, "published_at": iso(utc_now())}
            tx.put(ctx.tenant_id, "procedure_revision", f"{procedure_id}@{n}", rev_state, expected_revision=None,
                   action="publish", event_type="procedure.published",
                   event_payload={"procedure_id": procedure_id, "revision": n, "site_id": s["site_id"]})
            local = ({"status": "approved", "revision": n, "proposal_id": approved_proposal_id,
                      "approved_at": iso(utc_now())} if s["parent"] else None)
            tx.put(ctx.tenant_id, "procedure", procedure_id,
                   {**s, "status": "effective", "effective_revision": n, "pending_submission": None,
                    "revisions": [*s["revisions"], {"revision": n, "definition_hash": dhash, "proposal_id": approved_proposal_id,
                                                    "published_at": rev_state["published_at"]}],
                    "local_approval": local or s["local_approval"]},
                   expected_revision=rec.revision, action="publish")
        return rev_state

    def get_revision(self, ctx: AccessContext, procedure_id: str, revision: int | None = None) -> dict[str, Any]:
        tx = self.store.read()
        proc = tx.require(ctx.tenant_id, "procedure", procedure_id)
        self.idn.require(ctx, "read", "procedure", procedure_id, site_id=proc.state["site_id"], tx=tx)
        n = revision or proc.state["effective_revision"]
        if n is None:
            raise NotFoundError(f"{procedure_id} has no effective revision")
        return tx.require(ctx.tenant_id, "procedure_revision", f"{procedure_id}@{n}").state

    # --- instances (LS-006/LS-033) ---
    def create_instance(self, ctx: AccessContext, procedure_id: str, *, site_id: str, params: Mapping[str, Any] | None = None,
                        revision: int | None = None, context: dict[str, Any] | None = None,
                        instance_id: str | None = None) -> dict[str, Any]:
        self.idn.require(ctx, "propose", "procedure_instance", site_id=site_id)
        rev = self.get_revision(ctx, procedure_id, revision)
        if rev["site_id"] and rev["site_id"] != site_id:
            raise ValueError(f"procedure variant applies to site {rev['site_id']} only")
        resolved = resolve_template(rev["definition"], params)
        errs = self.validate(resolved, rev["category"])
        if errs:
            raise ProcedureInvalid(errs)
        steps = resolved["steps"]
        instance_id = instance_id or new_id("inst")
        state = {"instance_id": instance_id, "procedure_id": procedure_id, "revision": rev["revision"],
                 "definition_hash": rev["definition_hash"], "category": rev["category"], "site_id": site_id,
                 "params": resolved["template_values"], "constants": resolved.get("constants") or {},
                 "steps_def": {s["step_id"]: s for s in steps}, "order": topo_order(steps), "status": "created",
                 "steps": {s["step_id"]: {"status": "pending", "version": 0, "attempts": 0} for s in steps},
                 "values": {}, "amendments": [], "redlines": [], "amendment_count": 0, "context": context or {},
                 "authority": {"available": True, "lost_scopes": []}, "created_by": ctx.actor_id,
                 "created_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.put(ctx.tenant_id, "procedure_instance", instance_id, state, expected_revision=None,
                         action="create_instance", event_type="procedure.instance_created",
                         event_payload={"instance_id": instance_id, "procedure_id": procedure_id, "revision": rev["revision"]})
            tx.add_edge(ctx.tenant_id, ("procedure_revision", f"{procedure_id}@{rev['revision']}"),
                        ("procedure_instance", instance_id), "pinned_by")
        return {**state, "record_revision": rec.revision}

    def get_instance(self, ctx: AccessContext, instance_id: str) -> dict[str, Any]:
        tx = self.store.read()
        rec = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
        self.idn.require(ctx, "read", "procedure_instance", instance_id, site_id=rec.state["site_id"], tx=tx)
        return {**rec.state, "record_revision": rec.revision}

    # --- mid-run amendment (LS-007) ---
    def amend_instance(self, ctx: AccessContext, instance_id: str, change: dict[str, Any], reason: str) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise ValueError("an amendment requires a reason")
        inst = self.get_instance(ctx, instance_id)
        before = self._check_change(inst, change)
        proposal = self.actions.propose(
            ctx, target_system="native", operation="change_recipe_parameter", target_id=instance_id,
            payload={"instance_id": instance_id, "change": change, "before": before, "pinned_revision": inst["revision"]},
            basis=[{"kind": "procedure_revision", "id": f"{inst['procedure_id']}@{inst['revision']}", "revision": 1,
                    "site_id": inst["site_id"]}],
            rationale=reason, expected_result=f"{change['step_id']}.{change['parameter']}.{change['field']} becomes {change['value']}",
            owner_id=ctx.actor_id, site_id=inst["site_id"], record_class="recipe_instance")
        amd_id = new_id("amd")
        state = {"amendment_id": amd_id, "instance_id": instance_id, "change": change, "before": before, "reason": reason,
                 "proposal_id": proposal["proposal_id"], "proposal_content_hash": proposal["content_hash"],
                 "requested_by": ctx.actor_id, "status": "requested", "requested_at": iso(utc_now())}
        with self.store.transaction(ctx.actor_id) as tx:
            tx.put(ctx.tenant_id, "amendment_request", amd_id, state, expected_revision=None, action="request_amendment",
                   event_type="procedure.amendment_requested", event_payload={"instance_id": instance_id})
        return state

    @staticmethod
    def _check_change(inst: dict[str, Any], change: dict[str, Any]) -> Any:
        sid = change.get("step_id")
        if sid not in inst["steps"]:
            raise ValueError(f"unknown step {sid}")
        status = inst["steps"][sid]["status"]
        if status not in ("pending", "exception", "paused_authority_lost"):
            raise ValueError(f"step {sid} is {status}; completed or recorded steps cannot be amended")
        param = next((p for p in inst["steps_def"][sid].get("parameters", []) if p["name"] == change.get("parameter")), None)
        if param is None:
            raise ValueError(f"step {sid} has no parameter {change.get('parameter')}")
        if change.get("field") not in AMENDABLE_FIELDS or not _is_num(change.get("value")):
            raise ValueError(f"change.field must be one of {list(AMENDABLE_FIELDS)} with a numeric value")
        new = {**param, change["field"]: change["value"]}
        if _is_num(new.get("low")) and _is_num(new.get("high")) and new["low"] > new["high"]:
            raise ValueError("amended limits would have low greater than high")
        return param.get(change["field"])

    def apply_amendment(self, ctx: AccessContext, amendment_id: str) -> dict[str, Any]:
        if ctx.actor_kind == "agent":
            raise _deny("agent credentials cannot apply amendments")
        with self.store.transaction(ctx.actor_id) as tx:
            amd = tx.require(ctx.tenant_id, "amendment_request", amendment_id)
            a = amd.state
            inst_rec = tx.require(ctx.tenant_id, "procedure_instance", a["instance_id"])
            self.idn.require(ctx, "propose", "procedure_instance", a["instance_id"], site_id=inst_rec.state["site_id"], tx=tx)
            if a["status"] != "requested":
                raise ValueError(f"amendment is {a['status']}")
            prop = tx.require(ctx.tenant_id, "proposal", a["proposal_id"]).state
            self.actions.require_current_approval(ctx, a["proposal_id"], tx)
            if prop["status"] != "approved" or prop["content_hash"] != a["proposal_content_hash"]:
                raise PermissionError(f"amendment proposal is {prop['status']}; approval of the exact change is required")
            inst = copy.deepcopy(inst_rec.state)
            before = self._check_change(inst, a["change"])
            if before != a["before"]:
                raise ConflictError("parameter changed since the amendment was requested; request a new amendment")
            ch = a["change"]
            for p in inst["steps_def"][ch["step_id"]]["parameters"]:
                if p["name"] == ch["parameter"]:
                    p[ch["field"]] = ch["value"]
            approvals = [{"approval_id": r.id, "actor_id": r.state["actor_id"], "role": r.state["role"],
                          "decided_at": r.state["decided_at"]}
                         for r in tx.list(ctx.tenant_id, "approval", lambda s: s["proposal_id"] == a["proposal_id"]
                                          and s["content_hash"] == prop["content_hash"] and s["decision"] == "approved")]
            redline = {"redline_id": new_id("rl"), **{k: ch[k] for k in ("step_id", "parameter", "field")},
                       "before": before, "after": ch["value"], "reason": a["reason"], "approval": approvals,
                       "proposal_id": a["proposal_id"], "applied_by": ctx.actor_id, "applied_at": iso(utc_now()),
                       "completed_steps_at_time": sorted(k for k, v in inst["steps"].items() if v["status"] == "completed")}
            inst["redlines"].append(redline)
            inst["amendments"].append(amendment_id)
            inst["amendment_count"] += 1
            inst["steps"][ch["step_id"]]["version"] += 1
            tx.put(ctx.tenant_id, "procedure_instance", a["instance_id"], inst, expected_revision=inst_rec.revision,
                   action="apply_amendment", reason=a["reason"], event_type="procedure.amended",
                   event_payload={"instance_id": a["instance_id"], "redline_id": redline["redline_id"]})
            tx.put(ctx.tenant_id, "amendment_request", amendment_id, {**a, "status": "applied", "redline_id": redline["redline_id"]},
                   expected_revision=amd.revision, action="apply")
        return redline

    def mark_not_applicable(self, ctx: AccessContext, instance_id: str, step_id: str, reason: str) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise ValueError("marking a step not applicable requires a reason")
        with self.store.transaction(ctx.actor_id) as tx:
            rec = tx.require(ctx.tenant_id, "procedure_instance", instance_id)
            inst = copy.deepcopy(rec.state)
            self.idn.require(ctx, "approve", "step_execution", f"{instance_id}:{step_id}", site_id=inst["site_id"], tx=tx)
            if not ({"supervisor", "qa"} & set(ctx.roles)):
                raise _deny("only a supervisor or QA role can mark a step not applicable")
            if step_id not in inst["steps"]:
                raise ValueError(f"unknown step {step_id}")
            st = inst["steps"][step_id]
            if st["status"] in TERMINAL or st["status"] == "awaiting_signature":
                raise ValueError(f"step {step_id} is {st['status']}; it cannot be marked not applicable")
            st.update(status="not_applicable", version=st["version"] + 1,
                      na={"reason": reason, "by": ctx.actor_id, "at": iso(utc_now())})
            cascade_skips(inst["steps"], inst["steps_def"])
            if all(s["status"] in TERMINAL for s in inst["steps"].values()):
                inst["status"], inst["completed_at"] = "completed", iso(utc_now())
            tx.put(ctx.tenant_id, "procedure_instance", instance_id, inst, expected_revision=rec.revision,
                   action="not_applicable", reason=reason, event_type="procedure.step_not_applicable",
                   event_payload={"instance_id": instance_id, "step_id": step_id})
        return st["na"]

    # --- global templates and site adaptation (LS-014, LS-016) ---
    def adapt_for_site(self, ctx: AccessContext, template_id: str, template_revision: int, site_id: str,
                       overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
        self.idn.require(ctx, "propose", "procedure", site_id=site_id)
        tx0 = self.store.read()
        parent = tx0.get(ctx.tenant_id, "procedure_revision", f"{template_id}@{template_revision}")
        if parent is None:
            raise NotFoundError(f"{template_id} revision {template_revision}")
        if parent.state["scope"] != "global":
            raise ValueError("only global templates can be adapted for a site")
        definition = copy.deepcopy(parent.state["definition"])
        params = _all_params(definition["steps"])
        errors = []
        for pname, change in overrides.items():
            p = params.get(pname)
            if p is None:
                errors.append(f"unknown parameter {pname}")
                continue
            if not p.get("site_adjustable"):
                errors.append(f"parameter {pname} is not site adjustable")
                continue
            bad = set(change) - set(AMENDABLE_FIELDS)
            if bad:
                errors.append(f"{pname}: unsupported override fields {sorted(bad)}")
                continue
            rng = p.get("site_range") or {"low": p.get("low"), "high": p.get("high")}
            for f, v in change.items():
                if not _is_num(v):
                    errors.append(f"{pname}.{f} must be numeric")
                elif (rng.get("low") is not None and v < rng["low"]) or (rng.get("high") is not None and v > rng["high"]):
                    errors.append(f"{pname}.{f}={v} outside allowed site range [{rng.get('low')}, {rng.get('high')}]")
            new = {**p, **change}
            if _is_num(new.get("low")) and _is_num(new.get("high")) and new["low"] > new["high"]:
                errors.append(f"{pname}: low exceeds high after override")
            elif _is_num(new.get("target")) and ((_is_num(new.get("low")) and new["target"] < new["low"])
                                                 or (_is_num(new.get("high")) and new["target"] > new["high"])):
                errors.append(f"{pname}: target outside overridden limits")
            p.update(change)
        if errors:
            raise ProcedureInvalid(errors)
        definition = normalize_definition(definition)
        pid = f"{template_id}~{site_id}"
        parent_ref = {"procedure_id": template_id, "revision": template_revision,
                      "definition_hash": parent.state["definition_hash"]}
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.get(ctx.tenant_id, "procedure", pid)
            hist = {"parent": parent_ref, "overrides": overrides, "by": ctx.actor_id, "at": iso(utc_now())}
            base = cur.state if cur else {"procedure_id": pid, "name": f"{template_id} @ {site_id}", "revisions": [],
                                         "effective_revision": None, "created_by": ctx.actor_id, "adaptations": []}
            state = {**base, "category": parent.state["category"], "scope": "site", "site_id": site_id, "status": "draft",
                     "draft": definition, "draft_hash": content_hash(definition), "pending_submission": None,
                     "parent": parent_ref, "overrides": overrides,
                     "local_approval": {"status": "not_submitted", "revision": None, "proposal_id": None},
                     "adaptations": [*base.get("adaptations", []), hist]}
            rec = tx.put(ctx.tenant_id, "procedure", pid, state, expected_revision=cur.revision if cur else None,
                         action="adapt_for_site", event_type="procedure.site_adapted",
                         event_payload={"procedure_id": pid, "parent": parent_ref, "site_id": site_id})
            tx.add_edge(ctx.tenant_id, ("procedure_revision", f"{template_id}@{template_revision}"), ("procedure", pid),
                        "adapted_into")
        return {**state, "revision": rec.revision}

    def site_variant_status(self, ctx: AccessContext, variant_id: str) -> dict[str, Any]:
        tx = self.store.read()
        v = tx.require(ctx.tenant_id, "procedure", variant_id)
        self.idn.require(ctx, "read", "procedure", variant_id, site_id=v.state["site_id"], tx=tx)
        parent = v.state["parent"]
        tpl = tx.require(ctx.tenant_id, "procedure", parent["procedure_id"]).state
        return {"parent": parent, "local_approval": v.state["local_approval"],
                "parent_is_current": tpl["effective_revision"] == parent["revision"],
                "template_effective_revision": tpl["effective_revision"]}

    # --- document interpretation (LS-034) ---
    def interpret_document(self, ctx: AccessContext, evidence_id: str, text: str, gateway: Any = None, *,
                           media: list[dict[str, Any]] | None = None,
                           supported_devices: list[str] | None = None) -> dict[str, Any]:
        if self.evidence is None:
            raise RuntimeError("EvidenceService is required for document interpretation")
        ev = self.store.read().require(ctx.tenant_id, "evidence", evidence_id)
        self.idn.require(ctx, "read", "evidence", evidence_id, site_id=ev.state.get("site_id"))
        bad_media = [m for m in (media or []) if m.get("type") not in MEDIA_TYPES or not m.get("ref")]
        if bad_media:
            raise ValueError(f"media needs type in {list(MEDIA_TYPES)} and a ref")
        parsed = parse_procedure_text(text)
        payload: dict[str, Any] = {
            "interpretation_status": "draft_requires_review", "evidence_id": evidence_id,
            "evidence_digest": ev.state["digest"], "text_length": len(text), "steps": parsed["steps"],
            "issues": parsed["issues"], "media": media or [], "supported_devices": supported_devices or [],
            "device_guidance_status": DEVICE_GUIDANCE_NOTE if supported_devices else None,
            "model_suggestions": None, "requires_human_review": True}
        produced = {"method": "baseline_regex_v1", "model": None}
        ref = EvidenceRef("evidence", evidence_id, ev.revision, ev.state.get("site_id"))
        if gateway is not None:
            from .gateway import TaskRequest
            res = gateway.run(TaskRequest(task_kind="procedure_interpretation", ctx=ctx, payload={"text": text},
                                          prompt=f"Interpret this controlled document into steps with source spans:\n{text}",
                                          inputs=[ref.to_dict()]))
            payload["model_suggestions"] = self._merge_model(payload, res, text)
            produced = {"method": "baseline_regex_v1+gateway", "run_id": getattr(res, "run_id", None),
                        "model_status": getattr(res, "status", None)}
        out = self.evidence.record_derived(ctx, "procedure_interpretation", payload, inputs=[ref], produced_by=produced)
        with self.store.transaction(ctx.actor_id) as tx:
            cur = tx.require(ctx.tenant_id, "procedure_interpretation", out["id"])
            tx.put(ctx.tenant_id, "procedure_interpretation", out["id"], {**cur.state, "status": "draft_requires_review"},
                   expected_revision=cur.revision, action="mark_draft_requires_review")
        return {**out, "status": "draft_requires_review"}

    @staticmethod
    def _merge_model(payload: dict[str, Any], res: Any, text: str) -> dict[str, Any]:
        output = getattr(res, "output", None) or {}
        info: dict[str, Any] = {"status": getattr(res, "status", None), "issues": list(getattr(res, "issues", []) or []),
                                "verified_steps": 0, "rejected_items": []}
        by_no = {s["step_number"]: s for s in payload["steps"]}
        for item in output.get("steps", []) if isinstance(output, dict) else []:
            if not isinstance(item, dict) or not _span_ok(item.get("source_span"), text):
                info["rejected_items"].append({"item": item, "reason": "source span missing or does not match the document"})
                continue
            info["verified_steps"] += 1
            target = by_no.get(item.get("step_number"))
            suggestion = {"origin": "model", "title": item.get("title"), "source_span": item["source_span"],
                          "span_verified": True}
            if target is not None:
                target.setdefault("model_suggestions", []).append(suggestion)
            else:
                payload["steps"].append({"step_number": item.get("step_number"), "step_id": f"M{len(payload['steps']) + 1}",
                                         "title": item.get("title") or "", "text": text[item["source_span"]["start"]:item["source_span"]["end"]],
                                         "source_span": item["source_span"], "kind": "instruction", "parameters": [],
                                         "origin": "model", "extraction": "model suggestion; span verified, content requires review"})
        return info

    def draft_from_interpretation(self, ctx: AccessContext, interpretation_id: str, procedure_id: str, *, name: str,
                                  category: str = "work_instruction", site_id: str | None = None) -> dict[str, Any]:
        if self.evidence is None:
            raise RuntimeError("EvidenceService is required")
        interp = self.evidence.read_derived(ctx, "procedure_interpretation", interpretation_id)
        steps, notes, prev = [], [], None
        for s in interp["steps"]:
            params = []
            for p in s["parameters"]:
                if unit_ok(p["unit"]) and p["low"] <= p["high"]:
                    params.append({k: p[k] for k in ("name", "unit", "low", "high", "target")})
                else:
                    notes.append(f"{s['step_id']}: parameter {p['name']} dropped (invalid unit or inverted range)")
            steps.append({"step_id": s["step_id"], "title": s["title"] or s["step_id"], "kind": "data_entry" if params else "instruction",
                          "depends_on": [prev] if prev else [], "parameters": params, "source_span": s["source_span"],
                          "media": [], "supported_devices": []})
            prev = s["step_id"]
        if steps and interp["media"]:
            steps[0]["media"] = interp["media"]
        if steps and interp["supported_devices"]:
            steps[0]["supported_devices"] = interp["supported_devices"]
        definition = {"steps": steps, "interpretation_notes": notes,
                      "provenance": {"interpretation_id": interpretation_id, "evidence_id": interp["evidence_id"],
                                     "interpretation_status": "draft_requires_review"}}
        return self.create_draft(ctx, procedure_id, name=name, category=category, definition=definition, site_id=site_id)
