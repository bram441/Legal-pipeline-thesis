# tests/metrics.py

def normalize_set(values):
    if values is None:
        return []
    out = []
    for v in values:
        s = str(v).strip().lower()
        if s:
            out.append(s)
    return sorted(set(out))

def set_equal(a, b):
    return normalize_set(a) == normalize_set(b)

def any_set_equal(actual, acceptable_sets):
    if acceptable_sets is None:
        return False
    for s in acceptable_sets:
        if set_equal(actual, s):
            return True
    return False

def prf1(predicted, expected):
    p = set(normalize_set(predicted))
    e = set(normalize_set(expected))

    if not p and not e:
        return 1.0, 1.0, 1.0
    if not p and e:
        return 0.0, 0.0, 0.0

    tp = len(p.intersection(e))
    fp = len(p.difference(e))
    fn = len(e.difference(p))

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return precision, recall, f1