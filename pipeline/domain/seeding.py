
def seed_entities_from_case_text(case_text):
    """Heuristic domain seeding: detect capitalized names and seed Party domain.

    This is intentionally simple and conservative.
    """
    if not isinstance(case_text, str):
        return []

    tokens = []
    for raw in case_text.replace("\n", " ").split(" "):
        w = raw.strip(".,;:!?()[]{}\"'")
        if len(w) >= 2 and w[0].isupper() and w[1:].islower():
            tokens.append(w.lower())

    seen = set()
    out = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
