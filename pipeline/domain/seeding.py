# Common words that are never entities (articles, determiners, pronouns, logical operators, etc.)
_NON_ENTITY_WORDS = frozenset({
    "de", "het", "een", "die", "dat", "dit", "deze", "een", "der", "den",  # Dutch
    "the", "a", "an", "this", "that", "these", "those", "some", "any",    # English
    "le", "la", "les", "un", "une", "des", "du",                          # French
    "der", "die", "das", "ein", "eine",                                    # German
    "el", "la", "los", "las", "un", "una", "unos", "unas",                 # Spanish
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",                # Italian
    "not", "and", "or",                                                    # logical operators (never entity names)
    "after", "before", "during", "when", "while",                          # temporal prepositions (often capitalized in "After X,...")
})


def seed_entities_from_case_text(case_text):
    """Heuristic domain seeding: detect capitalized names and seed domain.

    Filters out common non-entity words (articles, determiners) that are
    often capitalized at sentence start.
    """
    if not isinstance(case_text, str):
        return []

    tokens = []
    for raw in case_text.replace("\n", " ").split(" "):
        w = raw.strip(".,;:!?()[]{}\"'")
        if len(w) >= 2 and w[0].isupper() and w[1:].islower():
            lower = w.lower()
            if lower not in _NON_ENTITY_WORDS:
                tokens.append(lower)

    seen = set()
    out = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
