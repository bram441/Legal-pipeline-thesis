def explain_liable(case, query, result):
    facts_negligent = set(case["negligent"])
    facts_caused = set(case["caused_damage"])

    lines = []
    lines.append("Toy rule used: if a party is negligent and caused damage, then they are liable.")

    if query["mode"] == "set":
        liable = result.get("liable_set", [])
        if not liable:
            lines.append("No party satisfied both conditions (negligent and caused_damage).")
            return "\n".join(lines)

        lines.append("Witnesses:")
        for p in liable:
            lines.append("- " + p + " is liable because negligent(" + p + ") is true and causedDamage(" + p + ") is true.")
        return "\n".join(lines)

    target = result.get("target", "")
    is_liable = bool(result.get("is_liable", False))

    if is_liable:
        lines.append(
            target + " is liable because negligent(" + target + ") and causedDamage(" + target + ") are both true."
        )
        return "\n".join(lines)

    missing = []
    if target not in facts_negligent:
        missing.append("negligent(" + target + ")")
    if target not in facts_caused:
        missing.append("causedDamage(" + target + ")")

    if missing:
        lines.append(
            target
            + " is not liable because the following required condition(s) were not established: "
            + ", ".join(missing)
            + "."
        )
    else:
        lines.append(target + " is not liable under the toy rule.")

    return "\n".join(lines)
