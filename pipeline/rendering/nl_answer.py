"""
Convert raw symbolic answers to natural language. Template-based only – no LLM, no hallucination.
"""
import re

# Exact symbol -> description. Extend as needed. Fallback uses heuristic.
_SYMBOL_DESC = {
    "imprisonmentmindays": "minimum prison sentence",
    "imprisonmentmaxdays": "maximum prison sentence",
    "finemineuro": "minimum fine",
    "finemaxeuro": "maximum fine",
}


def _symbol_to_description(symbol):
    """Map symbol name to human-readable phrase. Heuristic only."""
    s = ((symbol or "").strip().lower()).replace("_", "")
    if not s:
        return symbol or "value"
    if s in _SYMBOL_DESC:
        return _SYMBOL_DESC[s]
    if "imprisonment" in s and "max" in s:
        return "maximum prison sentence"
    if "imprisonment" in s and "min" in s:
        return "minimum prison sentence"
    if "fine" in s and "max" in s:
        return "maximum fine"
    if "fine" in s and "min" in s:
        return "minimum fine"
    return symbol


def _symbol_unit(symbol):
    """Infer unit from symbol name."""
    s = (symbol or "").lower()
    if "days" in s or "day" in s:
        return "days"
    if "euro" in s or "fine" in s:
        return "euros"
    return ""


def render_get_range_nl(symbol, range_val, entity):
    """Convert get_range raw output to natural language. Template-based, fully grounded."""
    if not symbol:
        return str(range_val)
    desc = _symbol_to_description(symbol)
    unit = _symbol_unit(symbol)
    entity_cap = (entity or "").strip()
    if entity_cap:
        entity_cap = entity_cap[0].upper() + entity_cap[1:] if len(entity_cap) > 1 else entity_cap.upper()

    if entity_cap:
        if unit:
            return f"The {desc} for {entity_cap} is {range_val} {unit}."
        return f"The {desc} for {entity_cap} is {range_val}."
    if unit:
        return f"The {desc} is {range_val} {unit}."
    return f"The {desc} is {range_val}."


def _description_from_schema(predicate: str, kb_schema: dict | None) -> str | None:
    if not kb_schema or not predicate:
        return None
    for p in kb_schema.get("predicates") or []:
        if isinstance(p, dict) and p.get("name") == predicate:
            d = str(p.get("description") or "").strip()
            return d or None
    return None


def _entity_label(args: list) -> str:
    if not args:
        return ""
    parts = [str(a).strip() for a in args if str(a).strip()]
    if not parts:
        return ""
    out = []
    for entity in parts:
        out.append(entity[0].upper() + entity[1:] if len(entity) > 1 else entity.upper())
    return ", ".join(out)


def _predicate_to_phrase(predicate, args, kb_schema: dict | None = None):
    """Convert predicate(args) to human phrase; prefer KB schema description when available."""
    pred = (predicate or "").strip()
    if not pred:
        return predicate
    desc = _description_from_schema(pred, kb_schema)
    entity_cap = _entity_label(list(args or []))
    if desc:
        text = desc.rstrip(".")
        if entity_cap:
            return f"{entity_cap}: {text}"
        return text

    s = pred.lower()
    art_match = re.search(r"art\.?(\d+)", s) or re.search(r"(\d{3})", pred)
    art = art_match.group(1) if art_match else ""

    if "punished" in s or "punish" in s:
        phrase = f"punished under Article {art}" if art else "punished"
    elif "liable" in s:
        phrase = f"liable under Article {art}" if art else "liable"
    elif "strafbaar" in s or "criminal" in s:
        phrase = "criminally liable"
    else:
        phrase = pred

    if entity_cap:
        return f"{entity_cap} is {phrase}"
    return phrase


def render_boolean_nl(predicate, args, certain, possible, kb_schema: dict | None = None):
    """Convert boolean predicate result to natural language."""
    if certain is True:
        phrase = _predicate_to_phrase(predicate, args, kb_schema=kb_schema)
        return f"Yes. {phrase}."
    if possible is False:
        phrase = _predicate_to_phrase_negative(predicate, args, kb_schema=kb_schema)
        msg = f"No. {phrase}."
        # Hint when answer is No: often caused by case facts using different predicate names than the KB
        msg += " (If you expected Yes, ensure case facts use the exact predicate names from the KB schema.)"
        return msg
    return "Unknown. The law and case facts do not determine this."


def _predicate_to_phrase_negative(predicate, args, kb_schema: dict | None = None):
    """Phrase for when predicate does NOT hold."""
    pred = (predicate or "").strip()
    if not pred:
        return "this does not hold"
    desc = _description_from_schema(pred, kb_schema)
    entity_cap = _entity_label(list(args or []))
    if desc:
        text = desc.rstrip(".")
        if entity_cap:
            return f"{entity_cap} does not satisfy: {text}"
        return f"It is not the case that {text.lower()}"

    s = pred.lower()
    art_match = re.search(r"art\.?(\d+)", s) or re.search(r"(\d{3})", pred)
    art = art_match.group(1) if art_match else ""

    if "punished" in s or "punish" in s:
        phrase = f"not punished under Article {art}" if art else "not punished"
    elif "liable" in s:
        phrase = f"not liable under Article {art}" if art else "not liable"
    else:
        phrase = f"does not satisfy {pred}"

    if entity_cap:
        if phrase.startswith("does not"):
            return f"{entity_cap} {phrase}"
        return f"{entity_cap} is {phrase}"
    return phrase


def render_set_nl(predicate, certain, possible):
    """Convert set query raw output to natural language. Template-based, fully grounded."""
    pred = (predicate or "").strip()
    cert = list(certain or [])
    poss = list(possible or [])

    if not cert and not poss:
        return f"No results for {pred}."

    parts = []
    if cert:
        if len(cert) == 1:
            parts.append(f"{pred}({cert[0]}) is certain.")
        else:
            parts.append(f"Certainly: {', '.join(cert)}.")
    if poss and poss != cert:
        if len(poss) == 1:
            parts.append(f"{pred}({poss[0]}) is possible.")
        else:
            parts.append(f"Possibly: {', '.join(poss)}.")

    return " ".join(parts) if parts else f"No results for {pred}."
