"""Minimal SGF parser for single-game records (no variations needed).

Designed for the SGF files exported by yikeweiqi and yehu/Fox.
Pure standard library. Extracts headers, setup stones, and the move list, and
converts SGF coordinates to GTP coordinates.
"""

import re
import os


GTP_COLS = "ABCDEFGHJKLMNOPQRST"  # GTP skips the letter 'I'


def sgf_coord_to_gtp(coord, board_size):
    """Convert an SGF coordinate like 'pd' to a GTP coordinate like 'Q16'.

    Returns 'pass' for an empty coordinate or the 'tt' pass convention.
    """
    if coord is None:
        return "pass"
    coord = coord.strip().lower()
    if coord == "" or (board_size <= 19 and coord == "tt"):
        return "pass"
    if len(coord) < 2:
        return "pass"
    col = ord(coord[0]) - ord("a")          # 0-based from left
    row = ord(coord[1]) - ord("a")          # 0-based from top
    if not (0 <= col < board_size and 0 <= row < board_size):
        return "pass"
    gtp_col = GTP_COLS[col]
    gtp_row = board_size - row               # GTP rows count from the bottom
    return f"{gtp_col}{gtp_row}"


def main_line_text(text):
    """Return SGF text containing only the *main line* (root sequence, and at
    every branch point the FIRST child variation).  Bracket/escape aware.

    SGF files exported by analysis tools (e.g. LizzieYZY) embed candidate
    variations as real SGF sub-trees; a naive ';B[..]/;W[..]' scan over the whole
    file would wrongly count those branch moves as part of the game.  Restricting
    to the main line fixes the move count.  Non-variation SGFs are unaffected.
    """
    n = len(text)
    try:
        start = text.index("(")
    except ValueError:
        return text

    def _skip_bracket(i):
        j = i + 1
        while j < n:
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == "]":
                break
            j += 1
        return j + 1  # index just past the closing ']'

    def parse(i):
        # text[i] == '('
        i += 1
        out = []
        while i < n:
            c = text[i]
            if c == "[":
                j = _skip_bracket(i)
                out.append(text[i:j])
                i = j
                continue
            if c == "(":
                child, i = parse(i)          # first child continues main line
                out.append(child)
                # skip sibling variations up to this game-tree's own ')'
                depth = 0
                while i < n:
                    c2 = text[i]
                    if c2 == "[":
                        i = _skip_bracket(i)
                        continue
                    if c2 == "(":
                        depth += 1
                        i += 1
                        continue
                    if c2 == ")":
                        if depth == 0:
                            return "".join(out), i + 1
                        depth -= 1
                        i += 1
                        continue
                    i += 1
                return "".join(out), i
            if c == ")":
                return "".join(out), i + 1
            out.append(c)
            i += 1
        return "".join(out), i

    s, _ = parse(start)
    return s


def _find_prop(text, key):
    """Return the first value of an SGF property, or None."""
    m = re.search(re.escape(key) + r"\[(.*?)\]", text, re.DOTALL)
    return m.group(1) if m else None


def _find_all_prop_values(text, key):
    """Return all bracket values for a property that may repeat, e.g. AB[..][..]."""
    # Match KEY followed by one or more [..] groups.
    m = re.search(re.escape(key) + r"((?:\[[^\]]*\])+)", text)
    if not m:
        return []
    return re.findall(r"\[([^\]]*)\]", m.group(1))


def parse_sgf(path):
    """Parse an SGF file into a dict describing the game.

    Returned dict keys:
      path, filename, board_size, komi, handicap, result, date,
      pb, pw, br, wr,                       # player names / ranks
      setup: list of (color, gtp_coord)     # AB/AW handicap or placed stones
      moves: list of (color, gtp_coord)     # 'B'/'W', coord or 'pass'
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    board_size = int(_find_prop(text, "SZ") or 19)

    komi_raw = _find_prop(text, "KM")
    try:
        komi = float(komi_raw) if komi_raw not in (None, "") else 7.5
    except ValueError:
        komi = 7.5
    # Fox (foxwq) stores komi multiplied by 50, e.g. KM[375] == 7.5 points.
    # Real komi never exceeds ~40, so a large value means the Fox encoding.
    if komi >= 40:
        komi = komi / 50.0

    ha_raw = _find_prop(text, "HA")
    try:
        handicap = int(ha_raw) if ha_raw not in (None, "") else 0
    except ValueError:
        handicap = 0

    setup = []
    for c in _find_all_prop_values(text, "AB"):
        setup.append(("B", sgf_coord_to_gtp(c, board_size)))
    for c in _find_all_prop_values(text, "AW"):
        setup.append(("W", sgf_coord_to_gtp(c, board_size)))

    # Moves: each SGF node begins with ';', and a move is the property right
    # after it, e.g. ';B[pd]'. Anchoring on ';' avoids matching root/markup
    # properties (PB, WR, AB, TB, TW, LB, ...) and text inside comments.
    moves = []
    for m in re.finditer(r";([BW])\[([^\]]*)\]", main_line_text(text)):
        color = m.group(1)
        coord = m.group(2)
        moves.append((color, sgf_coord_to_gtp(coord, board_size)))

    return {
        "path": path,
        "filename": os.path.basename(path),
        "board_size": board_size,
        "komi": komi,
        "handicap": handicap,
        "result": _find_prop(text, "RE") or "",
        "date": _find_prop(text, "DT") or "",
        "pb": _find_prop(text, "PB") or "",
        "pw": _find_prop(text, "PW") or "",
        "br": _find_prop(text, "BR") or "",
        "wr": _find_prop(text, "WR") or "",
        "setup": setup,
        "moves": moves,
    }


def detect_user_color(game, user_names):
    """Return 'B', 'W', or None depending on which side the user played.

    user_names is a collection of strings; matching is case-insensitive and
    also matches if a user name is a substring of the SGF player field (handles
    rank suffixes etc.).
    """
    pb = (game.get("pb") or "").lower()
    pw = (game.get("pw") or "").lower()
    names = [n.lower() for n in user_names if n]
    for n in names:
        if n and (n == pb or n in pb):
            return "B"
    for n in names:
        if n and (n == pw or n in pw):
            return "W"
    return None
