"""Generic subject-role hints from symbol names/descriptions (law-agnostic)."""



from __future__ import annotations



import re



# English morphemes in names/descriptions — not tied to any specific legal domain.

_DEAD_SUBJECT_RE = re.compile(

    r"(?:^|[^a-z])(deceased|decedent|dead|died|death|predeceased)(?:[^a-z]|$)|deceased[_ ]",

    re.IGNORECASE,

)

_ALIVE_SUBJECT_RE = re.compile(

    r"(?:^|[^a-z])(survivor|surviving|alive|living)(?:[^a-z]|$)",

    re.IGNORECASE,

)



_ROLE_CONFLICT_PAIRS = (("lifecycle_dead", "lifecycle_alive"),)





def _hints_from_blob(blob: str) -> frozenset[str]:

    if not (blob or "").strip():

        return frozenset()

    hints: set[str] = set()

    if _DEAD_SUBJECT_RE.search(blob):

        hints.add("lifecycle_dead")

    if _ALIVE_SUBJECT_RE.search(blob):

        hints.add("lifecycle_alive")

    return frozenset(hints)





def unary_subject_role_hints(name: str, description: str = "") -> frozenset[str]:

    """Infer lifecycle-style subject hints for a unary predicate from metadata.



    Predicate **name** is authoritative when it already signals a lifecycle role.

    Descriptions often mention other roles in passing (e.g. "surviving spouse of the deceased");

    those must not add conflicting hints on top of a clear name.

    """

    from_name = _hints_from_blob(name or "")

    if from_name:

        return from_name

    return _hints_from_blob(description or "")





def role_hints_conflict(hints: frozenset[str]) -> bool:

    for a, b in _ROLE_CONFLICT_PAIRS:

        if a in hints and b in hints:

            return True

    return False

