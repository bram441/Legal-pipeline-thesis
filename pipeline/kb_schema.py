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
