# pipeline/utils/unicode_sanitize.py
"""Sanitize IDP/Z3 output that may contain mathematical Unicode (e.g. U+1D539)."""

import unicodedata


def sanitize_for_output(s):
    """Replace mathematical/special Unicode with ASCII equivalents for safe output on all platforms."""
    if s is None:
        return ""
    if not isinstance(s, str):
        return str(s)
    out = []
    for c in s:
        try:
            name = unicodedata.name(c, "")
        except ValueError:
            name = ""
        # Mathematical Alphanumeric Symbols (U+1D400–U+1D7FF) and similar
        if "DOUBLE-STRUCK" in name or "MATHEMATICAL" in name:
            code = ord(c)
            # Mathematical Double-Struck Capital (U+1D538–U+1D551): A–Z
            if 0x1D538 <= code <= 0x1D551:
                out.append(chr(ord("A") + (code - 0x1D538)))
            # Mathematical Double-Struck Small (U+1D552–U+1D56B): a–z
            elif 0x1D552 <= code <= 0x1D56B:
                out.append(chr(ord("a") + (code - 0x1D552)))
            # Mathematical Bold/Italic/Sans etc. – similar ranges
            elif 0x1D400 <= code <= 0x1D419:  # Bold Capital
                out.append(chr(ord("A") + (code - 0x1D400)))
            elif 0x1D41A <= code <= 0x1D433:  # Bold Small
                out.append(chr(ord("a") + (code - 0x1D41A)))
            elif 0x1D7CE <= code <= 0x1D7D7:  # Mathematical digits
                out.append(chr(ord("0") + (code - 0x1D7CE)))
            else:
                n = unicodedata.normalize("NFKD", c)
                out.append(n if n.isascii() and len(n) == 1 else "?")
        elif ord(c) > 127 and not c.isascii():
            # Other non-ASCII: try NFKC, else replace
            n = unicodedata.normalize("NFKD", c)
            out.append(n if n.isascii() and len(n) == 1 else "?")
        else:
            out.append(c)
    return "".join(out)
