"""Estimate territory / score for a Go position with ikatago (KataGo).

What you get:
  * total    -- KataGo's scoreLead (expected final score difference, komi
                included). This is the authoritative number.
  * per side -- each side's total estimated territory, from KataGo's per-point
                ownership map.
  * per group -- an *approximate* per-group breakdown. KataGo only reports
                per-point ownership, not per-group scores, so each point is
                attributed to the nearest stone group of the colour that owns
                it. Treat these as estimates, not exact counts.

Usage:
  python3 estimate_score.py PATH.sgf [MOVE_NUMBER]
      Analyse the position after MOVE_NUMBER moves (default: the whole game).

  python3 estimate_score.py --selfcheck PATH.sgf [MOVE_NUMBER]
      Just rebuild and print the board (no engine contacted) -- handy offline.

The ikatago command is read from config.json (same as analyze.py).
"""

import os
import sys
import json
import collections

import sgfparse
from gtp_engine import IkatagoEngine, GtpError


HERE = os.path.dirname(os.path.abspath(__file__))
GTP_COLS = "ABCDEFGHJKLMNOPQRST"


def load_config(path=None):
    import appconfig
    return appconfig.load_config(path)


# ---- coordinates -----------------------------------------------------------
def gtp_to_xy(coord, size):
    """'Q16' -> (col, row_from_top). None for pass/invalid."""
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


def xy_to_gtp(x, y, size):
    return f"{GTP_COLS[x]}{size - y}"


# ---- a board that handles captures -----------------------------------------
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
        grp, libs = self._group(x, y)
        if libs == 0:
            for gx, gy in grp:
                self.g[gy][gx] = 0


def replay(game, move_number):
    """Rebuild the board after `move_number` moves. Returns (board, stm).

    stm = the colour to move next ('B'/'W'), taken from the SGF when possible.
    """
    size = game.get("board_size", 19)
    b = GoBoard(size)
    for color, coord in game.get("setup", []):
        xy = gtp_to_xy(coord, size)
        if xy:
            b.play(color, xy[0], xy[1])
    moves = game.get("moves", [])
    n = len(moves) if move_number is None else max(0, min(move_number, len(moves)))
    last = None
    for color, coord in moves[:n]:
        last = color
        xy = gtp_to_xy(coord, size)
        if xy:
            b.play(color, xy[0], xy[1])
    # Whose turn is it now? Prefer the colour of the next move recorded in the
    # SGF; otherwise alternate from the last move.
    if n < len(moves):
        stm = moves[n][0]
    elif last is not None:
        stm = "W" if last == "B" else "B"
    else:
        stm = "B"
    return b, stm, n


# ---- group extraction ------------------------------------------------------
def find_groups(board):
    """Return a list of groups: {id, color('B'/'W'), stones:[(x,y)...]}."""
    size = board.size
    seen = [[False] * size for _ in range(size)]
    groups = []
    for y in range(size):
        for x in range(size):
            if board.g[y][x] == 0 or seen[y][x]:
                continue
            c = board.g[y][x]
            stack = [(x, y)]
            seen[y][x] = True
            stones = []
            while stack:
                cx, cy = stack.pop()
                stones.append((cx, cy))
                for nx, ny in board._neighbors(cx, cy):
                    if not seen[ny][nx] and board.g[ny][nx] == c:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            groups.append({"id": len(groups),
                           "color": "B" if c == 1 else "W",
                           "stones": stones})
    return groups


def nearest_group_map(board, groups):
    """Multi-source BFS: assign each EMPTY point to the nearest group id."""
    size = board.size
    owner = [[-1] * size for _ in range(size)]
    dq = collections.deque()
    for grp in groups:
        for (x, y) in grp["stones"]:
            owner[y][x] = grp["id"]
            dq.append((x, y))
    while dq:
        x, y = dq.popleft()
        for nx, ny in board._neighbors(x, y):
            if owner[ny][nx] == -1 and board.g[ny][nx] == 0:
                owner[ny][nx] = owner[y][x]
                dq.append((nx, ny))
    return owner


def color_nearest_map(board, groups, color):
    """Multi-source BFS seeded from one colour's groups, spreading over EVERY
    point on the board (through stones and empties alike).

    Unlike nearest_group_map this ignores stone colour while spreading, so every
    point gets assigned to the nearest same-colour group. That lets us credit a
    point that `color` *owns* (including dead enemy stones sitting in its area)
    to one of its groups -- which is what makes the per-group totals add up to
    that colour's full area.
    """
    size = board.size
    owner = [[-1] * size for _ in range(size)]
    dq = collections.deque()
    for grp in groups:
        if grp["color"] != color:
            continue
        for (x, y) in grp["stones"]:
            owner[y][x] = grp["id"]
            dq.append((x, y))
    while dq:
        x, y = dq.popleft()
        for nx, ny in board._neighbors(x, y):
            if owner[ny][nx] == -1:
                owner[ny][nx] = owner[y][x]
                dq.append((nx, ny))
    return owner


# ---- scoring from the ownership map ----------------------------------------
def score_from_ownership(board, own_black, groups, komi):
    """own_black: list length size*size, black perspective, row-major top-left.

    Returns a dict with totals and a per-group list.
    """
    size = board.size
    # Two colour-restricted nearest-group maps. A point owned by Black is
    # credited to the nearest BLACK group; owned by White, to the nearest WHITE
    # group. This way every owned point lands on a group of the right colour and
    # the per-group totals sum to each side's full area.
    black_owner = color_nearest_map(board, groups, "B")
    white_owner = color_nearest_map(board, groups, "W")
    grp_pts = {g["id"]: 0.0 for g in groups}

    black_area = white_area = neutral = 0.0
    for y in range(size):
        for x in range(size):
            o = own_black[y * size + x]
            if o >= 0:
                black_area += o
            else:
                white_area += -o
            if abs(o) < 0.15:
                neutral += 1 - abs(o)
            if o > 0:
                gid = black_owner[y][x]
                if gid >= 0:
                    grp_pts[gid] += o
            elif o < 0:
                gid = white_owner[y][x]
                if gid >= 0:
                    grp_pts[gid] += -o

    net_area = black_area - white_area          # board area difference
    final_area = net_area - komi                # Chinese/area: komi favours W
    per_group = []
    for g in groups:
        per_group.append({
            "color": g["color"],
            "label": _group_label(g, size),
            "stones": len(g["stones"]),
            "points": round(grp_pts[g["id"]], 1),
        })
    per_group.sort(key=lambda r: r["points"], reverse=True)
    return {
        "black_area": round(black_area, 1),
        "white_area": round(white_area, 1),
        "net_area": round(net_area, 1),
        "komi": komi,
        "final_area": round(final_area, 1),
        "neutral_points": round(neutral, 1),
        "groups": per_group,
    }


def _group_label(g, size):
    # Representative point: the top-left-most stone.
    x, y = sorted(g["stones"], key=lambda p: (p[1], p[0]))[0]
    return xy_to_gtp(x, y, size)


# ---- board printing --------------------------------------------------------
def print_board(board):
    size = board.size
    glyph = {0: ".", 1: "X", 2: "O"}
    for y in range(size):
        row = " ".join(glyph[board.g[y][x]] for x in range(size))
        print(f"  {size - y:>2} {row}")
    cols = " ".join(GTP_COLS[:size])
    print(f"     {cols}")
    print("     (X = Black, O = White)")


# ---- main ------------------------------------------------------------------
def main(argv):
    selfcheck = "--selfcheck" in argv
    args = [a for a in argv if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 1
    sgf_path = os.path.expanduser(args[0])
    move_number = int(args[1]) if len(args) > 1 else None

    game = sgfparse.parse_sgf(sgf_path)
    size = game.get("board_size", 19)
    komi = float(game.get("komi", 7.5))
    board, stm, n = replay(game, move_number)

    print(f"\nGame record: {os.path.basename(sgf_path)}")
    print(f"Position: after move {n}  ·  "
          f"{'Black' if stm == 'B' else 'White'} to play"
          f"  ·  komi {komi}\n")
    print_board(board)

    if selfcheck:
        groups = find_groups(board)
        nb = sum(1 for g in groups if g["color"] == "B")
        nw = len(groups) - nb
        print(f"\nSelf-check complete (no engine contacted): found {len(groups)} "
              f"groups ({nb} black, {nw} white).")
        return 0

    cfg = load_config()
    engine = IkatagoEngine(cfg["ikatago_command"],
                           ready_timeout=cfg.get("ready_timeout", 120),
                           verbose=True)
    engine.start()
    try:
        engine.send("clear_board")
        engine.send(f"boardsize {size}")
        engine.send(f"komi {komi}")
        for color, coord in game.get("setup", []):
            if coord != "pass":
                engine.send(f"play {color} {coord}")
        played = 0
        for color, coord in game.get("moves", [])[:n]:
            try:
                engine.send(f"play {color} {'pass' if coord == 'pass' else coord}")
            except GtpError as e:
                print(f"(Move {played + 1} {color} {coord} was rejected as illegal "
                      f"by the engine; stopping the replay and estimating from the "
                      f"current position): {e}")
                break
            played += 1
        # If the engine stopped early (illegal/superko), re-sync the local board
        # and side-to-move to the position the engine actually reached, so the
        # ownership map lines up with our group extraction.
        if played < n:
            board, stm, n = replay(game, played)
        visits = cfg.get("score_visits", 600)
        mtime = cfg.get("score_max_time", 15.0)
        infos, own = engine.analyze_with_ownership(max_visits=visits,
                                                   max_time=mtime)
        if not infos:
            print("(The ownership analysis came back empty; falling back to the "
                  "total score only.)")
            infos = engine.analyze(max_visits=visits, max_time=mtime)
            own = None
    finally:
        engine.close()

    if not infos:
        print("\nThe engine returned no analysis.")
        return 1

    # scoreLead is in the side-to-move perspective -> convert to Black.
    score_lead_stm = infos[0].get("scoreLead", 0.0)
    score_black = score_lead_stm if stm == "B" else -score_lead_stm

    print("\n========== KataGo position assessment ==========")
    if score_black >= 0:
        print(f"Total: Black leads by about {score_black:+.1f} pts (komi included)")
    else:
        print(f"Total: White leads by about {-score_black:+.1f} pts (komi included)")

    if not own or len(own) != size * size:
        print("(The engine returned no per-point ownership, so per-group points "
              "cannot be shown.)")
        return 0

    # ownership is also side-to-move perspective -> convert to Black.
    own_black = own if stm == "B" else [-v for v in own]
    res = score_from_ownership(board, own_black, find_groups(board), komi)

    print(f"\nFrom per-point ownership (board only, before komi):")
    print(f"  Black controls ~ {res['black_area']} pts")
    print(f"  White controls ~ {res['white_area']} pts")
    print(f"  Net on the board ~ {res['net_area']:+.1f} pts (Black - White)")
    print(f"  After {res['komi']} komi ~ {res['final_area']:+.1f} pts "
          f"(should roughly match the scoreLead above)")

    print(f"\nEstimated points per group (the stones plus the space they control; "
          f"approximate):")
    print(f"  {'Colour':<8}{'Point':<7}{'Stones':>7}{'Est. pts':>10}")
    for r in res["groups"]:
        if r["points"] < 0.5 and r["stones"] <= 1:
            continue  # skip negligible single stones
        col = "Black" if r["color"] == "B" else "White"
        print(f"  {col:<4}{r['label']:<7}{r['stones']:>4}{r['points']:>9.1f}")

    print("\nNote: per-group points are an approximation, obtained by assigning "
          "each point's ownership to the nearest group. KataGo itself only reports "
          "per-point ownership, not per-group points.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
