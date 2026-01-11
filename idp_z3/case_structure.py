# idp_z3/case_structure.py

import re


_atom_line = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_neg_atom_line = re.compile(r"^\s*(?:not|~|¬)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_bool_assign_line = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*=\s*(true|false)\s*\.\s*$",
    re.IGNORECASE
)
_bad_star_call = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\*\s*\(")
_number = re.compile(r"^-?\d+(\.\d+)?$")


def _to_idp_elem(token):
    """
    Convert token like alice -> 'alice' so it is a domain element literal,
    not a vocabulary constant.
    """
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


def build_structure_block(parties, negligent, caused_damage):
    party_set = _mk_set([_to_idp_elem(p) for p in parties or []])
    negligent_set = _mk_set([_to_idp_elem(p) for p in negligent or []])
    caused_set = _mk_set([_to_idp_elem(p) for p in caused_damage or []])

    return f"""
structure S:V {{
  Party := {party_set}.
  negligent := {negligent_set}.
  causedDamage := {caused_set}.
}}
""".strip()


def _split_args(arg_blob):
    parts = []
    for p in arg_blob.split(","):
        raw = p.strip()
        if raw:
            parts.append(_to_idp_elem(raw))
    return parts


def build_structure_block_from_facts(facts):
    if not isinstance(facts, list):
        raise ValueError("case.facts must be a list of strings")

    for ln in facts:
        if isinstance(ln, str) and _bad_star_call.search(ln):
            raise ValueError("Invalid symbol token in case facts (unexpected '*'): " + ln.strip())

    passthrough = []
    pos_atoms = []
    neg_atoms = []

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
            val = mb.group(3).strip().lower()
            if not args:
                raise ValueError("Empty argument list in fact: " + s)
            if val == "true":
                pos_atoms.append((pred, args))
            else:
                neg_atoms.append((pred, args))
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

    for pred in list(ext.keys()):
        if pred in neg:
            ext[pred] = ext[pred] - neg[pred]

    has_party_domain = any(x.strip().startswith("Party") and ":=" in x for x in passthrough)
    inferred_party_line = None
    if not has_party_domain and constants:
        inferred_party_line = "Party := " + _mk_set(sorted(constants)) + "."

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

    lines = []
    if inferred_party_line:
        lines.append(inferred_party_line)
    lines.extend(passthrough)
    lines.extend(pred_lines)

    body = "\n  ".join(lines)
    return f"""
structure S:V {{
  {body}
}}
""".strip()
