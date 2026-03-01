import json
import os
import re


class KBSchemaError(Exception):
    pass


_VOCAB_RE = re.compile(r"vocabulary\s+V\s*\{(.*?)\}\s*", re.DOTALL | re.IGNORECASE)
_TYPE_RE = re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s*$", re.IGNORECASE)

_SIG_RE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*(?:\s*\*\s*[A-Za-z_]\w*)*)\s*->\s*([A-Za-z_]\w*)\s*$"
)


def get_primary_type_from_kb(kb_text):
    """Return the first type declared in the vocabulary (domain/actor type)."""
    all_t = get_all_types_from_kb(kb_text)
    return all_t[0] if all_t else None


def get_predicate_names_from_kb(kb_text):
    """Return all predicate names declared in the vocabulary (Bool-returning symbols)."""
    if not isinstance(kb_text, str):
        return []
    m = _VOCAB_RE.search(kb_text)
    if not m:
        return []
    out = []
    for raw in m.group(1).splitlines():
        ms = _SIG_RE.match(raw.strip())
        if ms and (ms.group(3) or "").lower() == "bool":
            out.append(ms.group(1))
    return out


def get_all_types_from_kb(kb_text):
    """Return all types declared in the vocabulary, in order."""
    if not isinstance(kb_text, str):
        return []
    m = _VOCAB_RE.search(kb_text)
    if not m:
        return []
    out = []
    for raw in m.group(1).splitlines():
        mt = _TYPE_RE.match(raw.strip())
        if mt:
            out.append(mt.group(1))
    return out


def extract_schema_from_kb_fo(kb_text):
    if not isinstance(kb_text, str):
        raise KBSchemaError("KB text must be a string")

    m = _VOCAB_RE.search(kb_text)
    if not m:
        raise KBSchemaError("Cannot find 'vocabulary V { ... }' in KB")

    vocab_body = m.group(1)

    types = []
    predicates = []
    functions = []

    for raw_line in vocab_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("//") or line.startswith("#"):
            continue

        mt = _TYPE_RE.match(line)
        if mt:
            types.append(mt.group(1))
            continue

        ms = _SIG_RE.match(line)
        if ms:
            name = ms.group(1)
            arg_blob = ms.group(2).strip()
            ret = ms.group(3).strip()
            args = [a.strip() for a in arg_blob.split("*")] if arg_blob else []

            if ret.lower() == "bool":
                predicates.append({"name": name, "args": args, "returns": ret})
            else:
                functions.append({"name": name, "args": args, "returns": ret})
            continue

        # Unknown vocab line: ignore for now (incremental).

    return {
        "types": sorted(set(types)),
        "predicates": sorted(predicates, key=lambda x: x["name"]),
        "functions": sorted(functions, key=lambda x: x["name"]),
    }


def save_kb_schema(run_dir, schema, filename="kb_schema.json"):
    path = os.path.join(run_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    return path


def load_kb_schema(run_dir, filename="kb_schema.json"):
    path = os.path.join(run_dir, filename)
    if not os.path.exists(path):
        raise KBSchemaError("Missing " + filename + " in run dir: " + run_dir)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
