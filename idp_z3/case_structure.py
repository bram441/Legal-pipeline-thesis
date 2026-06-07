# idp_z3/case_structure.py

import os
import re
from collections import defaultdict

# Predicates that are legal conclusions (derived by theory), not observable conditions.
# These are NOT closed to {} when absent from case facts.
# Extend via env CONCLUSION_PREDICATE_EXTRAS (comma-separated names/prefixes).
_CONCLUSION_PREFIXES = ("liable", "punishment", "punished")
_CONCLUSION_EXACT = frozenset(("eligible", "qualifies", "convicted"))


def _is_conclusion_predicate(pred_name_lower):
    if not pred_name_lower:
        return False
    for prefix in _CONCLUSION_PREFIXES:
        if pred_name_lower.startswith(prefix):
            return True
    if pred_name_lower in _CONCLUSION_EXACT:
        return True
    if "punished" in pred_name_lower and ("under" in pred_name_lower or "art" in pred_name_lower):
        return True
    extras = os.getenv("CONCLUSION_PREDICATE_EXTRAS", "")
    for x in extras.split(","):
        x = x.strip().lower()
        if x and (pred_name_lower == x or pred_name_lower.startswith(x)):
            return True
    return False


_atom_line = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_neg_atom_line = re.compile(r"^\s*(?:not|~|¬)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_bool_assign_line = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*=\s*(true|false)\s*\.\s*$",
    re.IGNORECASE
)
_bool_is_line = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s+is\s+(true|false)\s*\.\s*$",
    re.IGNORECASE
)
_func_assign_line = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*=\s*(.+?)\s*\.\s*$"
)
_bad_star_call = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\*\s*\(")
_number = re.compile(r"^-?\d+(\.\d+)?$")


def _to_idp_elem(token):
    s = str(token).strip()
    if not s:
        return s
    if s.startswith("'") and s.endswith("'"):
        return s
    if _number.match(s):
        return s
    s = s.lower()
    s = s.replace("'", "''")
    return "'" + s + "'"


def _mk_set(elems):
    xs = []
    for e in elems or []:
        if isinstance(e, str):
            t = e.strip()
            if t:
                xs.append(t)
    xs = sorted(set(xs))
    return "{" + ",".join(xs) + "}"


def _to_idp_value(token):
    s = str(token).strip()
    if not s:
        return s
    if s.lower() in ("true", "false"):
        return s.lower()
    return _to_idp_elem(s)


def _split_args(arg_blob):
    parts = []
    for p in arg_blob.split(","):
        raw = p.strip()
        if raw:
            parts.append(_to_idp_elem(raw))
    return parts


def _schema_signature_maps(kb_schema):
    """Predicate/function name -> tuple of argument type names from kb_schema."""
    if not isinstance(kb_schema, dict):
        return {}, {}
    pred_sigs: dict[str, tuple[str, ...]] = {}
    for p in kb_schema.get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            pred_sigs[str(p["name"])] = tuple(p.get("args") or [])
    fun_sigs: dict[str, tuple[str, ...]] = {}
    for f in kb_schema.get("functions") or []:
        if isinstance(f, dict) and f.get("name"):
            fun_sigs[str(f["name"])] = tuple(f.get("args") or [])
    return pred_sigs, fun_sigs


def _index_fact_constants_by_type(pred_sigs, fun_sigs, pos_atoms, neg_atoms, func_assignments):
    """Map KB type name -> constants appearing in case facts with that typed argument."""
    by_type: dict[str, set[str]] = defaultdict(set)

    def _note(name, args, sig_map):
        sig = sig_map.get(name)
        if not sig:
            return
        for i, arg in enumerate(args):
            if i >= len(sig):
                break
            if isinstance(arg, str) and arg:
                by_type[sig[i]].add(arg)

    for pred, args in list(pos_atoms) + list(neg_atoms):
        _note(pred, args, pred_sigs)
    for fun, pairs in func_assignments.items():
        for arg_tup, _rhs in pairs:
            _note(fun, list(arg_tup), fun_sigs)
    return dict(by_type)


def build_structure_block_from_facts(
    facts,
    entities=None,
    kb_primary_type=None,
    kb_types=None,
    kb_predicate_names=None,
    predicate_kinds=None,
    close_world_observables=None,
    kb_schema=None,
):
    if not isinstance(facts, list):
        raise ValueError("case.facts must be a list of strings")

    for ln in facts:
        if isinstance(ln, str) and _bad_star_call.search(ln):
            raise ValueError("Invalid symbol token in case facts (unexpected '*'): " + ln.strip())

    passthrough = []
    pos_atoms = []
    neg_atoms = []
    func_assignments = {}

    def _handle_bool(pred, args, val, original_line):
        if not args:
            raise ValueError("Empty argument list in fact: " + original_line)
        v = val.strip().lower()
        if v == "true":
            pos_atoms.append((pred, args))
        else:
            neg_atoms.append((pred, args))

    for ln in facts:
        if not isinstance(ln, str):
            raise ValueError("case.facts entries must be strings")

        s = ln.strip()
        if not s:
            continue
        if not s.endswith("."):
            raise ValueError("Each case fact must end with '.' (got: " + s + ")")

        if ":=" in s or ":>" in s or "≜" in s or "⊇" in s:
            passthrough.append(s)
            continue

        mb = _bool_assign_line.match(s)
        if mb:
            pred = mb.group(1)
            args = _split_args(mb.group(2))
            val = mb.group(3)
            _handle_bool(pred, args, val, s)
            continue

        mbi = _bool_is_line.match(s)
        if mbi:
            pred = mbi.group(1)
            args = _split_args(mbi.group(2))
            val = mbi.group(3)
            _handle_bool(pred, args, val, s)
            continue

        mf = _func_assign_line.match(s)
        if mf:
            fun = mf.group(1)
            args = _split_args(mf.group(2))
            rhs = _to_idp_value(mf.group(3))
            if not args:
                raise ValueError("Empty argument list in function assignment: " + s)
            if not rhs:
                raise ValueError("Empty right-hand side in function assignment: " + s)
            func_assignments.setdefault(fun, set()).add((tuple(args), rhs))
            continue

        mneg = _neg_atom_line.match(s)
        if mneg:
            pred = mneg.group(1)
            args = _split_args(mneg.group(2))
            if not args:
                raise ValueError("Empty argument list in fact: " + s)
            neg_atoms.append((pred, args))
            continue

        m = _atom_line.match(s)
        if not m:
            raise ValueError("Unsupported/invalid fact line in case.facts: " + s)

        pred = m.group(1)
        args = _split_args(m.group(2))
        if not args:
            raise ValueError("Empty argument list in fact: " + s)

        pos_atoms.append((pred, args))

    ext = {}
    constants = set()

    def _tup_key(args):
        return tuple(args)

    for pred, args in pos_atoms:
        constants.update(args)
        ext.setdefault(pred, set()).add(_tup_key(args))

    neg = {}
    for pred, args in neg_atoms:
        constants.update(args)
        neg.setdefault(pred, set()).add(_tup_key(args))

    for _fun, pairs in func_assignments.items():
        for arg_tup, rhs in pairs:
            constants.update(arg_tup)
            if rhs.startswith("'") and rhs.endswith("'"):
                constants.add(rhs)

    for pred in list(ext.keys()):
        if pred in neg:
            ext[pred] = ext[pred] - neg[pred]

    # Include predicates that appear only in neg_atoms (e.g. "not pred(x)") - they need extension {} to assert false
    for pred in neg:
        if pred not in ext:
            ext[pred] = set()

    # Schema-based close world for observables (JSON-IR default when kinds are provided).
    kinds = predicate_kinds if isinstance(predicate_kinds, dict) else None
    if kinds:
        close_obs = close_world_observables
        if close_obs is None:
            from pipeline.config import json_ir_config

            close_obs = bool(json_ir_config().close_world_observables)
        if close_obs:
            for pred, kind in kinds.items():
                if kind == "observable" and pred and pred not in ext:
                    ext[pred] = set()
    else:
        # Legacy FO path: close world only when explicitly enabled, with name heuristics.
        close_world = (os.getenv("CASE_CLOSE_WORLD_PREDICATES", "") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if close_world and kb_predicate_names:
            for pred in kb_predicate_names:
                if not pred or pred in ext:
                    continue
                if _is_conclusion_predicate(pred.lower()):
                    continue
                ext[pred] = set()

    # --- Domain: IDP requires every constant used in queries / __sel constraints to appear
    # in the structure interpretation for its type. Typed `case.entities` are authoritative:
    # list all of them in the corresponding type domain even when `case.facts` is empty or
    # does not mention a name (otherwise: Symbol not in vocabulary).
    #
    # Fact-only constants (e.g. a person appearing only in facts, not in entities.Person)
    # are merged into the KB primary type domain, excluding values explicitly listed under
    # other entity types (so an Estate individual listed under entities.Estate is not copied
    # onto Person when Person is primary).
    #
    # The first KB type is not always the runtime domain for predicate arguments
    # (e.g. first type may be "Vreemdeling", while predicates use "Persoon").
    # When typed entities are provided, seed each domain by entity type.
    domain_type = kb_primary_type if kb_primary_type else None
    constants_from_facts = set(constants)  # constants appearing in fact literals
    non_primary_entity_values = set()
    if isinstance(entities, dict) and kb_primary_type:
        for tn, tvs in entities.items():
            if tn == kb_primary_type:
                continue
            if not (isinstance(tn, str) and isinstance(tvs, list)):
                continue
            for v in tvs:
                if isinstance(v, str) and v.strip():
                    non_primary_entity_values.add(_to_idp_elem(v.strip()))
    primary_constants = set()
    if kb_primary_type:
        primary_constants = {c for c in constants_from_facts if c not in non_primary_entity_values}

    pred_sigs, fun_sigs = _schema_signature_maps(kb_schema)
    constants_by_type = (
        _index_fact_constants_by_type(pred_sigs, fun_sigs, pos_atoms, neg_atoms, func_assignments)
        if pred_sigs or fun_sigs
        else {}
    )
    used_in_facts = set(constants_from_facts)

    has_schema_sigs = bool(pred_sigs or fun_sigs)
    inferred_domain_lines = []
    if isinstance(entities, dict):
        for t_name, t_vals in entities.items():
            if not (isinstance(t_name, str) and isinstance(t_vals, list) and t_vals):
                continue
            vs: set[str] = set()
            typed_used = constants_by_type.get(t_name)
            if typed_used:
                vs |= typed_used
            for v in t_vals:
                if isinstance(v, str) and v.strip():
                    e = _to_idp_elem(v.strip())
                    # Always seed declared/resolved entities into their typed domain so
                    # query-only constants (e.g. company in query args) exist in FO vocabulary.
                    vs.add(e)
                    constants.add(e)
            if t_name == kb_primary_type and primary_constants:
                vs |= primary_constants
            vals = sorted(vs)
            if vals:
                inferred_domain_lines.append((t_name, t_name + " := " + _mk_set(vals) + "."))
        if inferred_domain_lines:
            domain_type = None
    # If no entities dict, constants come from facts only (no filtering needed)

    if domain_type and constants:
        dom_vals = set(constants)
        if constants_by_type.get(domain_type):
            dom_vals = set(constants_by_type[domain_type])
        inferred_domain_lines.append(
            (domain_type, domain_type + " := " + _mk_set(sorted(dom_vals)) + ".")
        )

    # Build predicate extension lines
    pred_lines = []
    for pred in sorted(ext.keys()):
        tuples = sorted(ext[pred])

        if not tuples:
            pred_lines.append(pred + " := {}.")
            continue

        if all(len(t) == 1 for t in tuples):
            elems = [t[0] for t in tuples]
            pred_lines.append(pred + " := " + _mk_set(elems) + ".")
        else:
            tuple_strs = []
            for t in tuples:
                tuple_strs.append("(" + ",".join(t) + ")")
            tuple_strs = sorted(set(tuple_strs))
            pred_lines.append(pred + " := {" + ",".join(tuple_strs) + "}.")

    # Build function interpretation lines
    function_lines = []
    for fun in sorted(func_assignments.keys()):
        pairs = sorted(func_assignments[fun], key=lambda p: (p[0], p[1]))
        if not pairs:
            continue
        map_items = []
        for arg_tup, rhs in pairs:
            if len(arg_tup) == 1:
                left = arg_tup[0]
            else:
                left = "(" + ",".join(arg_tup) + ")"
            map_items.append(left + " -> " + rhs)
        function_lines.append(fun + " := {" + ",".join(map_items) + "}.")

    # Assemble structure lines after domain inference.
    lines = []
    types_defined = set()

    # Only add inferred domain if caller didn't already provide a domain line of that type
    for d_type, d_line in inferred_domain_lines:
        has_domain = any(x.strip().startswith(d_type) and ":=" in x for x in passthrough)
        if not has_domain:
            lines.append(d_line)
            types_defined.add(d_type)

    lines.extend(passthrough)
    for x in passthrough:
        t = x.strip().split(":")[0].strip()
        if t and ":=" in x:
            types_defined.add(t)

    # Provide explicit interpretations for remaining KB types using empty domains.
    # This avoids introducing synthetic constructor symbols while still satisfying
    # IDP's requirement that declared types are interpreted in the structure.
    if kb_types:
        for t in kb_types:
            if t and t not in types_defined:
                lines.append(t + " := {}.")
    lines.extend(pred_lines)
    lines.extend(function_lines)

    body = "\n  ".join(lines)
    return f"""
structure S:V {{
  {body}
}}
""".strip()




def extract_constants_from_facts(facts):
    constants = set()

    for ln in facts or []:
        if not isinstance(ln, str):
            continue
        s = ln.strip()
        if not s or not s.endswith("."):
            continue

        mneg = _neg_atom_line.match(s)
        if mneg:
            args = _split_args(mneg.group(2))
            constants.update(args)
            continue

        mb = _bool_assign_line.match(s)
        if mb:
            args = _split_args(mb.group(2))
            constants.update(args)
            continue

        mbi = _bool_is_line.match(s)
        if mbi:
            args = _split_args(mbi.group(2))
            constants.update(args)
            continue

        mf = _func_assign_line.match(s)
        if mf:
            args = _split_args(mf.group(2))
            constants.update(args)
            rhs = _to_idp_value(mf.group(3))
            if rhs.startswith("'") and rhs.endswith("'"):
                constants.add(rhs)
            continue

        m = _atom_line.match(s)
        if m:
            args = _split_args(m.group(2))
            constants.update(args)

    return sorted(constants)
