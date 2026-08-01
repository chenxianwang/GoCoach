"""Go-board reconstruction, SVG diagram rendering, and blunder-shape similarity."""

from .constants import GTP_COLS, HOSHI, PTS_BLUNDER
from .data import esc


# ---- Go board + blunder diagrams -------------------------------------------

def gtp_to_xy(coord, size):
    """'Q16' -> (col, row_from_top). Returns None for pass/invalid."""
    if not coord:
        return None
    coord = coord.upper()
    if coord == "PASS" or len(coord) < 2 or coord[0] not in GTP_COLS:
        return None
    try:
        col = GTP_COLS.index(coord[0])
        num = int(coord[1:])
    except ValueError:
        return None
    return (col, size - num)


class GoBoard:
    def __init__(self, size):
        self.size = size
        self.g = [[0] * size for _ in range(size)]  # 0 empty, 1 black, 2 white

    def _neighbors(self, x, y):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.size and 0 <= ny < self.size:
                yield nx, ny

    def _group(self, x, y):
        color = self.g[y][x]
        stack = [(x, y)]
        seen = {(x, y)}
        libs = 0
        while stack:
            cx, cy = stack.pop()
            for nx, ny in self._neighbors(cx, cy):
                v = self.g[ny][nx]
                if v == 0:
                    libs += 1
                elif v == color and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        return seen, libs

    def play(self, color, x, y):
        c = 1 if color == "B" else 2
        if not (0 <= x < self.size and 0 <= y < self.size):
            return
        self.g[y][x] = c
        opp = 2 if c == 1 else 1
        for nx, ny in self._neighbors(x, y):
            if self.g[ny][nx] == opp:
                grp, libs = self._group(nx, ny)
                if libs == 0:
                    for gx, gy in grp:
                        self.g[gy][gx] = 0
        grp, libs = self._group(x, y)  # remove own group if suicidal (rare)
        if libs == 0:
            for gx, gy in grp:
                self.g[gy][gx] = 0


def board_before(game, move_number):
    size = game.get("board_size", 19)
    b = GoBoard(size)
    for color, coord in game.get("setup", []):
        xy = gtp_to_xy(coord, size)
        if xy:
            b.play(color, xy[0], xy[1])
    for color, coord in game.get("moves", [])[:move_number - 1]:
        xy = gtp_to_xy(coord, size)
        if xy:
            b.play(color, xy[0], xy[1])
    return b


def count_captures(game, move_number=None):
    """Replay the game and tally stones captured *during play*.
    Returns (black_caps, white_caps): black_caps = white stones black removed,
    white_caps = black stones white removed. ``move_number`` (1-based, exclusive)
    limits the replay to moves[:move_number-1]; None replays the whole game."""
    size = game.get("board_size", 19)
    b = GoBoard(size)
    for color, coord in game.get("setup", []):
        xy = gtp_to_xy(coord, size)
        if xy:
            b.play(color, xy[0], xy[1])
    moves = game.get("moves", [])
    if move_number is not None:
        moves = moves[:move_number - 1]
    black_caps = white_caps = 0
    for color, coord in moves:
        xy = gtp_to_xy(coord, size)
        if not xy:
            continue
        before = sum(r.count(1) + r.count(2) for r in b.g)
        own_before = 1 if color == "B" else 2
        b.play(color, xy[0], xy[1])
        after = sum(r.count(1) + r.count(2) for r in b.g)
        # net change = +1 (placed) - captured(opponent); suicide is rare/ignored.
        captured = before + 1 - after
        if captured > 0:
            if own_before == 1:
                black_caps += captured
            else:
                white_caps += captured
    return black_caps, white_caps


def groups_with_liberties(b):
    """Every group on board ``b`` as (color, stones, liberties).

    Unlike GoBoard._group (which counts liberties with multiplicity — fine for
    'is it captured?'), this de-duplicates shared empty points so ``liberties``
    is the true liberty count suitable for display.
    """
    size = b.size
    seen = [[False] * size for _ in range(size)]
    out = []
    for y in range(size):
        for x in range(size):
            if b.g[y][x] == 0 or seen[y][x]:
                continue
            color = b.g[y][x]
            stack = [(x, y)]
            seen[y][x] = True
            stones = []
            libs = set()
            while stack:
                cx, cy = stack.pop()
                stones.append((cx, cy))
                for nx, ny in b._neighbors(cx, cy):
                    v = b.g[ny][nx]
                    if v == 0:
                        libs.add((nx, ny))
                    elif v == color and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            out.append((color, stones, len(libs)))
    return out


def territory_split(own, size, board):
    """Each side's *territory* (in points) from a KataGo ownership map, excluding that
    side's own living stones — i.e. surrounded empty points plus the opponent's
    dead stones sitting in your area, but not your own stones. ``own`` is
    black-perspective, row-major from the top-left; ``board`` is a GoBoard at the
    same position. Returns (black_territory, white_territory)."""
    bt = wt = 0.0
    for y in range(size):
        for x in range(size):
            o = own[y * size + x]
            cell = board.g[y][x]
            if o > 0:
                if cell != 1:        # not your own (black) stone
                    bt += o
            elif o < 0:
                if cell != 2:        # not your own (white) stone
                    wt += -o
    return round(bt, 1), round(wt, 1)


def group_points(b, own):
    """Per stone-group estimated territory (in points) from an ownership map.

    Each owned point is credited to the nearest same-colour group (multi-source
    BFS over the whole board, like estimate_score.color_nearest_map), so the
    per-group totals add up to each side's territory. A group's own living stones
    are NOT counted (consistent with ``territory_split``). Returns a list of
    dicts: {color(1/2), stones, points, repr:(x,y)}. ``own`` is black-perspective,
    row-major from the top-left."""
    import collections
    size = b.size
    groups = []                      # [color, stones]
    seen = [[False] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            if b.g[y][x] == 0 or seen[y][x]:
                continue
            c = b.g[y][x]
            stack = [(x, y)]
            seen[y][x] = True
            stones = []
            while stack:
                cx, cy = stack.pop()
                stones.append((cx, cy))
                for nx, ny in b._neighbors(cx, cy):
                    if not seen[ny][nx] and b.g[ny][nx] == c:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            groups.append([c, stones])
    pts = [0.0] * len(groups)
    for color in (1, 2):
        owner = [[-1] * size for _ in range(size)]
        dq = collections.deque()
        for gi, (c, stones) in enumerate(groups):
            if c != color:
                continue
            for (x, y) in stones:
                owner[y][x] = gi
                dq.append((x, y))
        if not dq:
            continue
        while dq:
            x, y = dq.popleft()
            for nx, ny in b._neighbors(x, y):
                if owner[ny][nx] == -1:
                    owner[ny][nx] = owner[y][x]
                    dq.append((nx, ny))
        for y in range(size):
            for x in range(size):
                o = own[y * size + x]
                cell = b.g[y][x]
                gi = owner[y][x]
                if gi < 0:
                    continue
                if color == 1 and o > 0 and cell != 1:
                    pts[gi] += o
                elif color == 2 and o < 0 and cell != 2:
                    pts[gi] += -o
    out = []
    for gi, (c, stones) in enumerate(groups):
        cxm = sum(s[0] for s in stones) / len(stones)
        cym = sum(s[1] for s in stones) / len(stones)
        rx, ry = min(stones, key=lambda s: (s[0] - cxm) ** 2 + (s[1] - cym) ** 2)
        out.append({"color": c, "stones": stones,
                    "points": round(pts[gi], 1), "repr": (rx, ry)})
    return out


def diagram_svg(game, m, board=None, margin=5, cell=28):
    size = game.get("board_size", 19)
    played = gtp_to_xy(m.get("played"), size)
    ai = gtp_to_xy(m.get("best"), size)
    pv = [gtp_to_xy(c, size) for c in (m.get("best_pv", "") or "").split()]
    pv = [q for q in pv if q is not None]
    if played is None or (ai is None and not pv):
        return None
    if ai is None and pv:
        ai = pv[0]
    b = board if board is not None else board_before(game, m["move_number"])

    # Crop around your move and KataGo's reply (keep it a local position).
    pts = [played, ai]
    x0 = max(0, min(p[0] for p in pts) - margin)
    x1 = min(size - 1, max(p[0] for p in pts) + margin)
    y0 = max(0, min(p[1] for p in pts) - margin)
    y1 = min(size - 1, max(p[1] for p in pts) + margin)
    cols, rows = x1 - x0 + 1, y1 - y0 + 1
    pad = 16
    W = pad * 2 + (cols - 1) * cell
    H = pad * 2 + (rows - 1) * cell

    def sx(x):
        return pad + (x - x0) * cell

    def sy(y):
        return pad + (y - y0) * cell

    def in_box(q):
        return q is not None and x0 <= q[0] <= x1 and y0 <= q[1] <= y1

    p = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
         f'style="background:#e9c483;border-radius:4px">']
    # grid
    for x in range(x0, x1 + 1):
        p.append(f'<line x1="{sx(x)}" y1="{sy(y0)}" x2="{sx(x)}" '
                 f'y2="{sy(y1)}" stroke="#5b4220" stroke-width="1"/>')
    for y in range(y0, y1 + 1):
        p.append(f'<line x1="{sx(x0)}" y1="{sy(y)}" x2="{sx(x1)}" '
                 f'y2="{sy(y)}" stroke="#5b4220" stroke-width="1"/>')
    # star points
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if x in HOSHI and y in HOSHI:
                p.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="3" '
                         f'fill="#5b4220"/>')
    # existing stones
    r = cell * 0.46
    pv_set = {q for q in pv if in_box(q)}
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            v = b.g[y][x]
            if v == 0 or (x, y) in pv_set:
                continue  # PV stones are drawn on top below
            fill = "#1c1c1c" if v == 1 else "#fbfbfb"
            stroke = "#000" if v == 2 else "none"
            p.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{r:.1f}" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    # KataGo's suggested line: numbered stones, alternating colours, #1 = best
    user = game.get("user_color", "B")
    opp = "W" if user == "B" else "B"
    fnum = cell * 0.42
    for i, q in enumerate(pv):
        if not in_box(q):
            continue
        col = user if i % 2 == 0 else opp
        fill = "#1c1c1c" if col == "B" else "#fbfbfb"
        tcol = "#fff" if col == "B" else "#1c1c1c"
        p.append(f'<circle cx="{sx(q[0])}" cy="{sy(q[1])}" r="{r:.1f}" '
                 f'fill="{fill}" stroke="#444" stroke-width="1"/>')
        p.append(f'<text x="{sx(q[0])}" y="{sy(q[1])}" font-size="{fnum:.0f}" '
                 f'font-weight="700" fill="{tcol}" text-anchor="middle" '
                 f'dominant-baseline="central">{i+1}</text>')
    # KataGo's move (#1): green ring
    if in_box(ai):
        p.append(f'<circle cx="{sx(ai[0])}" cy="{sy(ai[1])}" r="{r+2:.1f}" '
                 f'fill="none" stroke="#1f9d55" stroke-width="2.5"/>')
    # your move: red square (the point where you actually played)
    s = r * 1.7
    p.append(f'<rect x="{sx(played[0])-s/2:.1f}" y="{sy(played[1])-s/2:.1f}" '
             f'width="{s:.1f}" height="{s:.1f}" fill="none" stroke="#e02424" '
             f'stroke-width="3"/>')
    p.append("</svg>")
    return "".join(p)


def _chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _local_density(board, xy, radius=2):
    if xy is None or board is None:
        return 0
    cx, cy = xy
    n = 0
    for y in range(max(0, cy - radius), min(board.size, cy + radius + 1)):
        for x in range(max(0, cx - radius), min(board.size, cx + radius + 1)):
            if board.g[y][x] != 0:
                n += 1
    return n


def classify_blunder(game, m, board):
    """Heuristic label + advice for a blunder, from move data and the board.

    These are rules of thumb (not a second KataGo search), but they map the
    common amateur mistake types well enough to guide study.
    """
    size = game.get("board_size", 19)
    played = gtp_to_xy(m.get("played"), size)
    ai = gtp_to_xy(m.get("best"), size)
    phase = m.get("phase", "middlegame")
    pts = m.get("points_lost", 0)
    wr = m.get("winrate_lost", 0)
    dist = _chebyshev(played, ai) if (played and ai) else 0
    dens = max(_local_density(board, played), _local_density(board, ai))

    if wr >= 0.25 and dens >= 4:
        name = "Middlegame misread (fight read wrong)"
        tip = ("A close-quarters fight turned the game around. Before contact plays "
               "and crosscuts, count the liberties of both groups and read the "
               "capturing race out to the end instead of playing on feel.")
    elif dist >= 6:
        name = "Wrong direction / missed the big point"
        tip = ("KataGo wanted to play in a completely different part of the board. "
               "Before answering locally, scan the whole board and ask: is there a "
               "bigger open area, or a weaker group that needs attention first?")
    elif phase == "opening":
        name = "Slow fuseki move"
        tip = ("A slack or misdirected opening move. Take the open corners and big "
               "sides first, and do not play too close to your own thickness.")
    elif phase == "endgame":
        name = "Yose mistake"
        tip = ("Endgame points add up fast. Estimate the value of each endgame play, "
               "take your sente moves first, then the largest gote.")
    elif dist <= 2:
        name = "Shape / local technique"
        tip = ("There was a better move right next door. Look for the shape point "
               "that keeps you connected and leaves you the most liberties.")
    else:
        name = "Slow middlegame move (local loss)"
        tip = ("Compare your move with KataGo's -- the gap is usually efficiency or "
               "territory rather than one specific tesuji.")

    if pts >= PTS_BLUNDER and wr < 0.03:
        tip += (" (Note: the win rate barely moved -- the result was already "
                "decided, so this move cost points rather than the game. Still "
                "worth reviewing as pure technique.)")
    return name, tip


def full_board_svg(game, m, idp, cell=20):
    """Whole-board diagram. The move marker and the AI line are wrapped in
    toggleable <g> groups (ids '<idp>-mv' and '<idp>-ai')."""
    size = game.get("board_size", 19)
    played = gtp_to_xy(m.get("played"), size)
    ai = gtp_to_xy(m.get("best"), size)
    pv = [gtp_to_xy(c, size) for c in (m.get("best_pv", "") or "").split()]
    pv = [q for q in pv if q is not None]
    if ai is None and pv:
        ai = pv[0]
    b = board_before(game, m["move_number"])
    pad = 18
    W = H = pad * 2 + (size - 1) * cell

    def sx(x):
        return pad + x * cell

    def sy(y):
        return pad + y * cell

    r = cell * 0.46
    # Board snapshot embedded for the client-side "connect liberties" tool:
    # row-major string of 0/1/2 (empty/black/white) plus the geometry needed to
    # map a click back to a grid point.
    board_str = "".join(str(b.g[y][x]) for y in range(size) for x in range(size))
    p = [f'<svg viewBox="0 0 {W} {H}" data-n="{size}" data-pad="{pad}" '
         f'data-cell="{cell}" data-board="{board_str}" '
         f'style="max-width:440px;width:100%;'
         f'height:auto;background:#e9c483;border-radius:4px;margin-top:8px">']
    for i in range(size):
        p.append(f'<line x1="{sx(i)}" y1="{sy(0)}" x2="{sx(i)}" '
                 f'y2="{sy(size-1)}" stroke="#5b4220" stroke-width="1"/>')
        p.append(f'<line x1="{sx(0)}" y1="{sy(i)}" x2="{sx(size-1)}" '
                 f'y2="{sy(i)}" stroke="#5b4220" stroke-width="1"/>')
    if size == 19:
        for hx in (3, 9, 15):
            for hy in (3, 9, 15):
                p.append(f'<circle cx="{sx(hx)}" cy="{sy(hy)}" r="2.5" '
                         f'fill="#5b4220"/>')
    # KataGo territory estimate overlay (toggleable, hidden by default). Only
    # drawn on *empty* intersections (squares on stones just clutter the board),
    # each sized by |ownership| and coloured by who owns it, like Lizzie's
    # "display occupancy by square size". ownership is black-perspective,
    # row-major from the top-left.
    own = m.get("ownership")
    if own and len(own) == size * size:
        p.append(f'<g id="{idp}-est" style="display:none">')
        side_max = cell * 0.92
        for y in range(size):
            for x in range(size):
                if b.g[y][x] != 0:        # skip occupied points (no square on stones)
                    continue
                o = own[y * size + x]
                a = abs(o)
                if a < 0.10:
                    continue
                s = side_max * (a ** 0.5)
                if o > 0:
                    fill, stroke = "#111", "none"
                else:
                    fill, stroke = "#fafafa", "#9a8050"
                p.append(f'<rect x="{sx(x)-s/2:.1f}" y="{sy(y)-s/2:.1f}" '
                         f'width="{s:.1f}" height="{s:.1f}" fill="{fill}" '
                         f'stroke="{stroke}" stroke-width="0.5" '
                         f'fill-opacity="0.82"/>')
        p.append('</g>')
    pv_set = set(pv)
    for y in range(size):
        for x in range(size):
            v = b.g[y][x]
            if v == 0 or (x, y) in pv_set:
                continue
            fill = "#1c1c1c" if v == 1 else "#fbfbfb"
            stroke = "#000" if v == 2 else "none"
            p.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{r:.1f}" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    # Dead-stone marks (id '<idp>-dead'): hidden by default, shown together with
    # the AI-estimate squares. A stone whose point is controlled by the opponent
    # is dead — mark dead black stones with a white X, dead white with black X.
    if own and len(own) == size * size:
        xr = r * 0.58
        p.append(f'<g id="{idp}-dead" style="display:none">')
        for y in range(size):
            for x in range(size):
                v = b.g[y][x]
                if v == 0 or (x, y) in pv_set:
                    continue
                o = own[y * size + x]
                if not ((v == 1 and o < -0.4) or (v == 2 and o > 0.4)):
                    continue
                col = "#fafafa" if v == 1 else "#1c1c1c"
                cx, cy = sx(x), sy(y)
                p.append(f'<line x1="{cx-xr:.1f}" y1="{cy-xr:.1f}" '
                         f'x2="{cx+xr:.1f}" y2="{cy+xr:.1f}" stroke="{col}" '
                         f'stroke-width="1.8" stroke-linecap="round"/>')
                p.append(f'<line x1="{cx-xr:.1f}" y1="{cy+xr:.1f}" '
                         f'x2="{cx+xr:.1f}" y2="{cy-xr:.1f}" stroke="{col}" '
                         f'stroke-width="1.8" stroke-linecap="round"/>')
        p.append('</g>')
    # Per-group estimated territory (id '<idp>-estnum'): a number on each sizeable
    # group's representative stone, shown together with the AI-estimate squares.
    # Drawn *over* the stones (unlike the squares) so the figure stays readable.
    if own and len(own) == size * size:
        fb = cell * 0.46
        bbr = r + 2.5
        p.append(f'<g id="{idp}-estnum" style="display:none">')
        for grp in group_points(b, own):
            # Label every group whose estimate rounds to >=1 pt; hide ~0-pt groups.
            if round(grp["points"]) < 1:
                continue
            rx, ry = grp["repr"]
            if (rx, ry) in pv_set:
                continue
            cx, cy = sx(rx), sy(ry)
            badge = "#dd6b20" if grp["color"] == 1 else "#2b6cb0"
            p.append(f'<circle cx="{cx}" cy="{cy}" r="{bbr:.1f}" fill="{badge}" '
                     f'stroke="#fff" stroke-width="1.4"/>')
            p.append(f'<text x="{cx}" y="{cy}" font-size="{fb:.0f}" '
                     f'font-weight="800" fill="#fff" text-anchor="middle" '
                     f'dominant-baseline="central">{grp["points"]:.0f}</text>')
        p.append('</g>')
    # Liberty counts (id '<idp>-libs'): hidden by default. Every group gets its
    # true liberty count printed on a representative stone (the one nearest the
    # group's centre); "danger" groups are colour-coded with a halo so they pop
    # -- 1 liberty = red (atari), 2 = orange, 3 = yellow.  Many blunders come from
    # miscounting liberties, so groups involved in capturing races stand out.
    grp_libs = groups_with_liberties(b)
    if grp_libs:
        fl = cell * 0.5
        rb = r * 0.86
        DANGER = {1: "#e02424", 2: "#f76707", 3: "#f2b200"}
        p.append(f'<g id="{idp}-libs" style="display:none">')
        for color, stones, libs in grp_libs:
            cxm = sum(s[0] for s in stones) / len(stones)
            cym = sum(s[1] for s in stones) / len(stones)
            rx, ry = min(stones,
                         key=lambda s: (s[0] - cxm) ** 2 + (s[1] - cym) ** 2)
            cx, cy = sx(rx), sy(ry)
            if libs in DANGER:
                dc = DANGER[libs]
                p.append(f'<circle cx="{cx}" cy="{cy}" r="{rb:.1f}" '
                         f'fill="#fff" fill-opacity="0.92" stroke="{dc}" '
                         f'stroke-width="2"/>')
                p.append(f'<text x="{cx}" y="{cy}" font-size="{fl:.0f}" '
                         f'font-weight="800" fill="{dc}" text-anchor="middle" '
                         f'dominant-baseline="central">{libs}</text>')
            else:
                tc = "#fff" if color == 1 else "#1c1c1c"
                p.append(f'<text x="{cx}" y="{cy}" font-size="{fl*0.92:.0f}" '
                         f'font-weight="600" fill="{tc}" fill-opacity="0.8" '
                         f'text-anchor="middle" '
                         f'dominant-baseline="central">{libs}</text>')
        p.append('</g>')
    # AI suggested line (toggleable)
    user = game.get("user_color", "B")
    opp = "W" if user == "B" else "B"
    fnum = cell * 0.5
    p.append(f'<g id="{idp}-ai">')
    if ai is not None:
        p.append(f'<circle cx="{sx(ai[0])}" cy="{sy(ai[1])}" r="{r+2:.1f}" '
                 f'fill="none" stroke="#1f9d55" stroke-width="2.5"/>')
    for i, q in enumerate(pv):
        col = user if i % 2 == 0 else opp
        fill = "#1c1c1c" if col == "B" else "#fbfbfb"
        tcol = "#fff" if col == "B" else "#1c1c1c"
        p.append(f'<circle cx="{sx(q[0])}" cy="{sy(q[1])}" r="{r:.1f}" '
                 f'fill="{fill}" stroke="#444" stroke-width="1"/>')
        p.append(f'<text x="{sx(q[0])}" y="{sy(q[1])}" font-size="{fnum:.0f}" '
                 f'font-weight="700" fill="{tcol}" text-anchor="middle" '
                 f'dominant-baseline="central">{i+1}</text>')
    p.append('</g>')
    # your move (toggleable)
    p.append(f'<g id="{idp}-mv">')
    if played is not None:
        s = r * 1.7
        p.append(f'<rect x="{sx(played[0])-s/2:.1f}" '
                 f'y="{sy(played[1])-s/2:.1f}" width="{s:.1f}" height="{s:.1f}" '
                 f'fill="none" stroke="#e02424" stroke-width="3"/>')
    p.append('</g>')
    # Connect-liberties overlay (id '<idp>-conn'): empty, filled in by JS when the
    # user picks groups to test connecting.
    p.append(f'<g id="{idp}-conn"></g>')
    p.append('</svg>')
    return "".join(p)


# ---- "same mistake" similarity ---------------------------------------------
# What makes two blunders the *same lesson* is usually that you missed the same
# urgent move. So the signature is centred on KataGo's suggested move (the point
# you should have found), encoded from your own perspective (self / opponent /
# empty / off-board). The strongest signal is leaving the same (or an adjacent)
# urgent move on the board within one game; otherwise we fall back to matching
# the local shape around that point under the 8 board symmetries.

def local_pattern(game, m, board, radius=4):
    size = game.get("board_size", 19)
    c = gtp_to_xy(m.get("best"), size) or gtp_to_xy(m.get("played"), size)
    if c is None:
        return None
    cx, cy = c
    self_c = 1 if game.get("user_color", "B") == "B" else 2
    grid = []
    for dy in range(-radius, radius + 1):
        row = []
        for dx in range(-radius, radius + 1):
            x, y = cx + dx, cy + dy
            if not (0 <= x < size and 0 <= y < size):
                row.append(3)            # off-board (edge/corner context)
            else:
                v = board.g[y][x]
                row.append(0 if v == 0 else (1 if v == self_c else 2))
        grid.append(tuple(row))
    return tuple(grid)


def _rot90(g):
    n = len(g)
    return tuple(tuple(g[n - 1 - j][i] for j in range(n)) for i in range(n))


def _flip(g):
    return tuple(tuple(reversed(row)) for row in g)


def _dihedral(g):
    out, cur = [], g
    for _ in range(4):
        out.append(cur)
        out.append(_flip(cur))
        cur = _rot90(cur)
    return out


def _cell_w(v):
    return 1.0 if v in (1, 2) else (0.5 if v == 3 else 0.0)


def pattern_similarity(a, b):
    """Best fraction of weighted agreement over the 8 symmetries (0..1)."""
    best = 0.0
    for tb in _dihedral(b):
        agree = total = 0.0
        for ra, rb in zip(a, tb):
            for ca, cb in zip(ra, rb):
                w = max(_cell_w(ca), _cell_w(cb))
                if w == 0:
                    continue
                total += w
                if ca == cb:
                    agree += w
        if total > 0:
            best = max(best, agree / total)
    return best


def blunder_similarity(ei, ej, pat_i, pat_j):
    """How much two blunders are the *same mistake* (0..1).

    Strongest case: KataGo wanted the same point (or one right next to it) in
    the same game -- i.e. you left the same urgent move on the board more than
    once. Otherwise compare the local shape around that urgent point so a
    recurring shape is still caught across different games.
    """
    gi, mi = ei["g"], ei["m"]
    gj, mj = ej["g"], ej["m"]
    bi = gtp_to_xy(mi.get("best"), gi.get("board_size", 19))
    bj = gtp_to_xy(mj.get("best"), gj.get("board_size", 19))
    if gi.get("filename") == gj.get("filename") and bi and bj:
        d = max(abs(bi[0] - bj[0]), abs(bi[1] - bj[1]))
        if d == 0:
            return 1.0            # literally the same urgent move, left again
        if d == 1:
            return 0.82           # one point over -- effectively the same spot
    if pat_i is None or pat_j is None:
        return 0.0
    return pattern_similarity(pat_i, pat_j)


def _similarity_matrix(built, pats):
    """N x N matrix of blunder_similarity values.

    The pure-Python O(n^2) double loop with per-pair dihedral work gets too slow
    once every game contributes cards (hundreds of cards). When numpy is present
    we vectorise: encode each local pattern as an SxS grid, precompute its 8
    dihedral variants once, then score all pairs with array ops. The same-game
    "you left the same urgent move again" override is applied on top. Falls back
    to the original element-wise routine when numpy is unavailable so report.py
    keeps working with a bare Python install.
    """
    n = len(built)
    try:
        import numpy as np
    except Exception:
        np = None

    if np is None:
        mat = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                s = blunder_similarity(built[i], built[j], pats[i], pats[j])
                mat[i][j] = mat[j][i] = s
        return mat

    # Encode patterns. None patterns -> all-empty grid (weight 0 -> sim 0).
    S = None
    for p in pats:
        if p is not None:
            S = len(p)
            break
    if S is None:
        return [[0.0] * n for _ in range(n)]

    P = np.zeros((n, S, S), dtype=np.int8)
    for i, p in enumerate(pats):
        if p is not None:
            P[i] = np.array(p, dtype=np.int8)
    # cell weight: stones (1,2) -> 1.0, off-board (3) -> 0.5, empty (0) -> 0.0
    W = np.where((P == 1) | (P == 2), 1.0,
                 np.where(P == 3, 0.5, 0.0)).astype(np.float32)

    # 8 dihedral variants of the *second* operand (matches pattern_similarity,
    # which transforms b and keeps a fixed). The orbit under D4 is identical
    # regardless of rotation direction, so the per-pair max is unchanged.
    def variants(arr):
        out, cur = [], arr
        for _ in range(4):
            out.append(cur)
            out.append(cur[:, :, ::-1])          # horizontal flip
            cur = np.rot90(cur, k=-1, axes=(1, 2))
        return np.stack(out, axis=1)             # (n, 8, S, S)

    Pv = variants(P)                              # (n, 8, S, S)
    Wv = variants(W)                              # (n, 8, S, S)

    mat = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        a = P[i]                                  # (S, S)
        wa = W[i]                                 # (S, S)
        wmax = np.maximum(wa, Wv)                 # (n, 8, S, S)
        agree = (Pv == a) & (wmax > 0)
        num = (wmax * agree).sum(axis=(2, 3))     # (n, 8)
        den = wmax.sum(axis=(2, 3))               # (n, 8)
        with np.errstate(invalid="ignore", divide="ignore"):
            sim8 = np.where(den > 0, num / den, 0.0)
        mat[i] = sim8.max(axis=1)                  # (n,)

    out = mat.tolist()
    for i in range(n):
        out[i][i] = 0.0

    # Same-game override: same urgent point (or one over) left again.
    best_xy = []
    for e in built:
        g, m = e["g"], e["m"]
        best_xy.append((g.get("filename"),
                        gtp_to_xy(m.get("best"), g.get("board_size", 19))))
    by_file = {}
    for idx, (fn, _) in enumerate(best_xy):
        by_file.setdefault(fn, []).append(idx)
    for fn, idxs in by_file.items():
        for a_pos in range(len(idxs)):
            i = idxs[a_pos]
            bi = best_xy[i][1]
            if not bi:
                continue
            for b_pos in range(a_pos + 1, len(idxs)):
                j = idxs[b_pos]
                bj = best_xy[j][1]
                if not bj:
                    continue
                d = max(abs(bi[0] - bj[0]), abs(bi[1] - bj[1]))
                if d == 0:
                    out[i][j] = out[j][i] = 1.0
                elif d == 1:
                    out[i][j] = out[j][i] = 0.82
    return out


# ---- score graph (per game) ------------------------------------------------

def score_svg(g, width=720, height=176):
    """Per-game score-lead curve: where the game was won or lost.

    Accepts a game dict (preferred — enables user-perspective shading and
    blunder markers) or a bare timeline list. The line is KataGo's black-side
    score lead; the background is tinted green where *you* are ahead and red
    where you are behind, and your big mistakes are marked as red dots."""
    if isinstance(g, dict):
        timeline = g.get("timeline", [])
        user_color = g.get("user_color", "B")
        user_moves = g.get("all_user_moves", [])
    else:
        timeline, user_color, user_moves = g, "B", []
    if not timeline:
        return "<p class='sub'>(No score data.)</p>"
    xs = [p["move_number"] for p in timeline]
    ys = [p["black_score_lead"] for p in timeline]
    max_move = max(xs) or 1
    bound = max(10.0, max(abs(min(ys)), abs(max(ys))))
    pad = 22
    padb = 26  # bottom room for the move-number axis

    def px(mv):
        return pad + (mv / max_move) * (width - 2 * pad)

    def py(score):
        score = max(-bound, min(bound, score))
        return pad + (1 - (score + bound) / (2 * bound)) * (height - pad - padb)

    mid_y, top_y, bot_y = py(0), py(bound), py(-bound)
    # Shade by the user's perspective: green = you lead, red = you trail.
    # Black leads above the midline; for a white player the halves swap.
    if user_color == "B":
        ahead, behind = (top_y, mid_y), (mid_y, bot_y)
    else:
        ahead, behind = (mid_y, bot_y), (top_y, mid_y)
    w_in = width - 2 * pad
    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fafafa;border:1px solid #e3e3e3;border-radius:6px">',
         f'<rect x="{pad}" y="{ahead[0]:.1f}" width="{w_in}" '
         f'height="{abs(ahead[1]-ahead[0]):.1f}" fill="#38a169" fill-opacity="0.07"/>',
         f'<rect x="{pad}" y="{behind[0]:.1f}" width="{w_in}" '
         f'height="{abs(behind[1]-behind[0]):.1f}" fill="#e53e3e" fill-opacity="0.07"/>',
         f'<line x1="{pad}" y1="{mid_y:.1f}" x2="{width-pad}" '
         f'y2="{mid_y:.1f}" stroke="#bbb" stroke-dasharray="4 4"/>']
    # Move-number gridlines + labels along the bottom.
    step = 50 if max_move > 120 else (25 if max_move > 60 else 10)
    mk = step
    while mk < max_move:
        x = px(mk)
        p.append(f'<line x1="{x:.1f}" y1="{top_y:.1f}" x2="{x:.1f}" '
                 f'y2="{bot_y:.1f}" stroke="#ededed"/>')
        p.append(f'<text x="{x:.1f}" y="{height-padb+14:.0f}" font-size="9" '
                 f'fill="#999" text-anchor="middle">{mk}</text>')
        mk += step
    p.append(f'<text x="{width-pad:.0f}" y="{height-4:.0f}" font-size="9" '
             f'fill="#999" text-anchor="end">move &#8594;</text>')
    p.append(f'<text x="{pad}" y="14" font-size="10" fill="#666">'
             f'Black +{bound:.0f}</text>')
    p.append(f'<text x="{pad}" y="{bot_y+12:.0f}" font-size="10" fill="#666">'
             f'White +{bound:.0f}</text>')
    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys))
    p.append(f'<polyline fill="none" stroke="#2b6cb0" stroke-width="2" '
             f'points="{pts}"/>')
    # Mark the user's big mistakes on the curve (hover for details).
    for m in user_moves:
        if m.get("points_lost", 0) >= PTS_BLUNDER and \
                m.get("score_after_black") is not None:
            mv, sc = m["move_number"], m["score_after_black"]
            tip = (f"Move {mv}: you played {m.get('played')}, "
                   f"should have played {m.get('best')}, "
                   f"lost {m.get('points_lost')} pts "
                   f"(win rate -{m.get('winrate_lost',0)*100:.0f}%)")
            p.append(f'<circle class="pt" data-tip="{esc(tip)}" '
                     f'cx="{px(mv):.1f}" cy="{py(sc):.1f}" r="4.5" '
                     f'fill="#e53e3e" stroke="#fff" stroke-width="1.2"/>')
    p.append('</svg>')
    p.append("<p class='sub' style='margin-top:4px'>Score graph (the blue line is "
             "the point lead from Black's perspective): "
             "<b style='color:#38a169'>green band = you are ahead</b>, "
             "<b style='color:#e53e3e'>red band = you are behind</b>. "
             "<span style='color:#e53e3e'>&#9679;</span> Red dots are your blunders "
             "-- hover for detail. Wherever the line drops or jumps sharply is a "
             "turning point in the game.</p>")
    return "".join(p)


def _replay_board(game, n=None):
    """Rebuild the board after `n` moves (all moves if n is None)."""
    size = game.get("board_size", 19)
    b = GoBoard(size)
    for color, coord in game.get("setup", []):
        xy = gtp_to_xy(coord, size)
        if xy:
            b.play(color, xy[0], xy[1])
    moves = game.get("moves", [])
    n = len(moves) if n is None else max(0, min(n, len(moves)))
    for color, coord in moves[:n]:
        xy = gtp_to_xy(coord, size)
        if xy:
            b.play(color, xy[0], xy[1])
    return b


def final_score_board_svg(game, fs, idp="fs", cell=28, min_pts=4.0):
    """Full board at the scored position, with each group's representative
    stone badged by its estimated points. To stay legible, only groups worth at
    least `min_pts` are badged (the full breakdown is in the table below).

    The territory-estimate squares are wrapped in a group (id '<idp>-est') that
    is hidden by default and toggled by a button in final_score_html."""
    size = game.get("board_size", 19)
    if not game.get("moves"):
        return ""
    b = _replay_board(game, fs.get("moves_played"))
    pad = 18
    W = H = pad * 2 + (size - 1) * cell

    def sx(x):
        return pad + x * cell

    def sy(y):
        return pad + y * cell

    r = cell * 0.46
    p = [f'<svg viewBox="0 0 {W} {H}" style="max-width:460px;width:100%;'
         f'height:auto;background:#e9c483;border-radius:4px;margin:8px 0">']
    for i in range(size):
        p.append(f'<line x1="{sx(i)}" y1="{sy(0)}" x2="{sx(i)}" '
                 f'y2="{sy(size-1)}" stroke="#5b4220" stroke-width="1"/>')
        p.append(f'<line x1="{sx(0)}" y1="{sy(i)}" x2="{sx(size-1)}" '
                 f'y2="{sy(i)}" stroke="#5b4220" stroke-width="1"/>')
    if size == 19:
        for hx in (3, 9, 15):
            for hy in (3, 9, 15):
                p.append(f'<circle cx="{sx(hx)}" cy="{sy(hy)}" r="2.5" '
                         f'fill="#5b4220"/>')
    # KataGo territory-estimate overlay (the same square overlay used in the
    # blunder modal): each intersection gets a square sized by |ownership| and
    # coloured by who controls it. Drawn *under* the stones so they stay
    # readable. ownership is black-perspective, row-major from the top-left.
    own = fs.get("ownership")
    if own and len(own) == size * size:
        side_max = cell * 0.92
        # Estimate squares are drawn only on empty points and on dead stones.
        # Squares that would sit on a living stone (its point is owned by its own
        # colour) are skipped entirely — they add clutter without information.
        p.append(f'<g id="{idp}-est" style="display:none">')
        for y in range(size):
            for x in range(size):
                o = own[y * size + x]
                a = abs(o)
                if a < 0.10:
                    continue
                v = b.g[y][x]
                if (v == 1 and o > 0) or (v == 2 and o < 0):
                    continue                # skip squares on living stones
                s = side_max * (a ** 0.5)
                if o > 0:
                    fill, stroke = "#111", "none"
                else:
                    fill, stroke = "#fafafa", "#9a8050"
                p.append(f'<rect x="{sx(x)-s/2:.1f}" y="{sy(y)-s/2:.1f}" '
                         f'width="{s:.1f}" height="{s:.1f}" fill="{fill}" '
                         f'stroke="{stroke}" stroke-width="0.5" '
                         f'fill-opacity="0.82"/>')
        p.append('</g>')
    for y in range(size):
        for x in range(size):
            v = b.g[y][x]
            if v == 0:
                continue
            fill = "#1c1c1c" if v == 1 else "#fbfbfb"
            stroke = "#000" if v == 2 else "none"
            p.append(f'<circle cx="{sx(x)}" cy="{sy(y)}" r="{r:.1f}" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
    # Dead-stone marks: a stone whose final point is controlled by the opponent
    # is dead (ownership is black-perspective: o>0 = black controls). Mark dead
    # black stones with a white X, dead white stones with a black X. Wrapped in a
    # toggleable group (id '<idp>-dead'), shown by default.
    if own and len(own) == size * size:
        xr = r * 0.58
        p.append(f'<g id="{idp}-dead">')
        for y in range(size):
            for x in range(size):
                v = b.g[y][x]
                if v == 0:
                    continue
                o = own[y * size + x]
                if not ((v == 1 and o < -0.4) or (v == 2 and o > 0.4)):
                    continue
                col = "#fafafa" if v == 1 else "#1c1c1c"
                cx, cy = sx(x), sy(y)
                p.append(f'<line x1="{cx-xr:.1f}" y1="{cy-xr:.1f}" '
                         f'x2="{cx+xr:.1f}" y2="{cy+xr:.1f}" stroke="{col}" '
                         f'stroke-width="2" stroke-linecap="round"/>')
                p.append(f'<line x1="{cx-xr:.1f}" y1="{cy+xr:.1f}" '
                         f'x2="{cx+xr:.1f}" y2="{cy-xr:.1f}" stroke="{col}" '
                         f'stroke-width="2" stroke-linecap="round"/>')
        p.append('</g>')
    # Badge the representative stone of each group with its estimated TERRITORY
    # (territory-only, i.e. excluding that group's own stones) — synced with the
    # blunder board (full_board_svg). Every group that rounds to >=1 pt is
    # labelled; ~0-pt groups are skipped to keep the board readable.
    fnum = cell * 0.46
    br = r + 2.5
    # The badges are wrapped in two colour groups (id '<idp>-badge-B' /
    # '<idp>-badge-W') so each side can be toggled independently. Both shown by
    # default. color: 1=black -> "B", 2=white -> "W".
    grp_pts = group_points(b, own) if (own and len(own) == size * size) else []
    for col, cnum, gid in (("B", 1, f"{idp}-badge-B"), ("W", 2, f"{idp}-badge-W")):
        p.append(f'<g id="{gid}" style="display:none">')
        for grp in grp_pts:
            if grp["color"] != cnum or round(grp["points"]) < 1:
                continue
            rx, ry = grp["repr"]
            badge = "#dd6b20" if cnum == 1 else "#2b6cb0"
            val = f"{grp['points']:.0f}"
            p.append(f'<circle cx="{sx(rx)}" cy="{sy(ry)}" r="{br:.1f}" '
                     f'fill="{badge}" stroke="#fff" stroke-width="2"/>')
            p.append(f'<text x="{sx(rx)}" y="{sy(ry)}" '
                     f'font-size="{fnum:.0f}" '
                     f'font-weight="700" fill="#fff" text-anchor="middle" '
                     f'dominant-baseline="central">{val}</text>')
        p.append('</g>')
    p.append("</svg>")
    return "".join(p)


def final_score_html(g, idp="fs"):
    """Render the final-position score estimate stored by analyze.py."""
    fs = g.get("final_score")
    if not fs:
        return ""
    sb = fs.get("score_black")
    if sb is None:
        return ""
    if sb >= 0:
        lead = f"<b class='win'>Black leads by about {sb:.1f} pts</b> (komi included)"
    else:
        lead = f"<b class='loss'>White leads by about {-sb:.1f} pts</b> (komi included)"
    p = [f"<div class='score'><div class='scl'>Final position estimate</div>",
         f"<div class='scn'>{lead}</div>"]
    if "black_area" in fs:
        komi = fs.get("komi", 7.5)
        groups = fs.get("groups", [])
        board_svg = final_score_board_svg(g, fs, idp)
        b_area = fs.get("black_area")
        w_area = fs.get("white_area")
        if board_svg:
            # Toggle button for the dead-stone X marks (shown by default).
            if fs.get("ownership"):
                p.append(f"<button class='fbbtn' style='margin:6px 6px 6px 0' "
                         f"onclick=\"var e=document.getElementById('{idp}-dead');"
                         f"var s=e.style.display==='none';"
                         f"e.style.display=s?'':'none';"
                         f"this.textContent=s?'Hide dead-stone marks':"
                         f"'Show dead-stone marks';\">Hide dead-stone marks</button>")
            # Toggle button for the (default-hidden) AI ownership squares.
            # Like the blunder set: this single toggle also reveals the per-group
            # numbers (badge-B / badge-W) together with the squares.
            if fs.get("ownership"):
                p.append(f"<button class='fbbtn' style='margin:6px 6px 6px 0' "
                         f"onclick=\"var e=document.getElementById('{idp}-est');"
                         f"var s=e.style.display==='none';"
                         f"e.style.display=s?'':'none';"
                         f"var bb=document.getElementById('{idp}-badge-B'),"
                         f"bw=document.getElementById('{idp}-badge-W');"
                         f"if(bb)bb.style.display=s?'':'none';"
                         f"if(bw)bw.style.display=s?'':'none';"
                         f"this.textContent=s?'Hide AI territory estimate':"
                         f"'Show AI territory estimate';\">Show AI territory estimate</button>")
            p.append(board_svg)
            p.append("<p class='sub' style='margin-top:2px'>Use the button above to "
                     "overlay KataGo's ownership estimate: the bigger the square, the "
                     "more certain the ownership. "
                     "<b style='color:#1c1c1c'>&#9632; dark = Black</b>, "
                     "<b style='color:#9a8050'>&#9633; light = White</b>. The number on "
                     "each dot is that group's estimated points (stones excluded -- "
                     "only the empty space it controls; groups worth about 0 are not "
                     "labelled) (<b style='color:#2b6cb0'>&#9679; blue = White</b>, "
                     "<b style='color:#dd6b20'>&#9679; orange = Black</b>).</p>")
        # Both sides' point totals, plus a komi-adjusted tally the user can
        # verify by hand. (Per-group breakdown table removed — rarely needed.)
        if b_area is not None and w_area is not None:
            final = b_area - w_area - komi
            if final >= 0:
                res = f"<b class='win'>Black leads by about {final:.1f} pts</b>"
            else:
                res = f"<b class='loss'>White leads by about {-final:.1f} pts</b>"
            terr = None
            own = fs.get("ownership")
            size = fs.get("own_size") or g.get("board_size", 19)
            if own and len(own) == size * size:
                played = fs.get("moves_played")
                mv = (played + 1) if played is not None \
                    else len(g.get("moves", [])) + 1
                terr = territory_split(own, size, board_before(g, mv))
            sides = (f"Black ~ <b>{terr[0]:.1f}</b> pts, White ~ "
                     f"<b>{terr[1]:.1f}</b> pts (opponent's dead stones included); "
                     if terr else "")
            p.append(f"<p class='sub' style='margin-top:8px'>"
                     f"Territory estimate (your own live stones excluded, the "
                     f"opponent's dead stones included): {sides}"
                     f"after {komi} komi: {res} "
                     f"(a small discrepancy with KataGo's scoreLead above is normal "
                     f"-- point-by-point ownership is an approximation).</p>")
            bc, wc = count_captures(g)
            p.append(f"<p class='sub' style='margin-top:4px'>"
                     f"Captures during the game: Black took <b>{bc}</b> white stones, "
                     f"White took <b>{wc}</b> black stones (for reference only -- Fox "
                     f"uses area scoring, so captures are not added to the points "
                     f"above).</p>")
    p.append("</div>")
    return "".join(p)
