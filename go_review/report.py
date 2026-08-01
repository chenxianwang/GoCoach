"""Build a self-contained HTML report from the JSON produced by analyze.py.

Sections:
  1. Summary cards.
  2. Trends over date: four charts (avg points lost, blunder rate by points,
     blunder rate by win-rate drop, total blunders); each chart shows four
     curves -- overall, opening, middle game, endgame.
  3. What to work on (data-driven recommendations).
  4. Blunder summary: cropped board diagrams of your worst positions, with your
     move and KataGo's suggested move marked.
  5. Biggest mistakes table + game-by-game score graphs.

No third-party dependencies: every chart and board is hand-rolled inline SVG.
"""

import os
import re
import sys
import json
import glob
import html
import datetime

try:
    import sgfparse  # sibling module; used to recover boards from raw SGF
except Exception:
    sgfparse = None


HERE = os.path.dirname(os.path.abspath(__file__))
GTP_COLS = "ABCDEFGHJKLMNOPQRST"

PHASES = ["overall", "opening", "middlegame", "endgame"]
PHASE_LABEL = {"overall": "Overall", "opening": "Fuseki",
               "middlegame": "Middlegame", "endgame": "Yose"}
PHASE_COLOR = {"overall": "#1a202c", "opening": "#2b6cb0",
               "middlegame": "#d69e2e", "endgame": "#c53030"}

PTS_BLUNDER = 6.0      # points-lost threshold for a "blunder"
WR_BLUNDER = 0.15      # win-rate-drop threshold (15%)


def load_config(path=None):
    import appconfig
    return appconfig.load_config(path)


def load_games(out_dir, games_dirs=None):
    games = []
    for p in sorted(glob.glob(os.path.join(out_dir, "*.json"))):
        if os.path.basename(p) in ("index.json", "notes.json", "practice_hidden.json"):
            continue
        with open(p, "r", encoding="utf-8") as f:
            g = json.load(f)
        _enrich_from_sgf(g, games_dirs or [])
        games.append(g)
    games.sort(key=lambda g: date_key(g), reverse=True)
    return games


def load_hidden(report_dir):
    """Set of blunder keys (filename#move) the user deleted from the practice
    set, read from <report_dir>/practice_hidden.json."""
    if not report_dir:
        return set()
    p = os.path.join(report_dir, "practice_hidden.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def practice_cleared(report_dir):
    """True if the user has 'cleared' this project's blunder set (a finished
    project they won't review move-by-move again).  Marked by an empty file
    <report_dir>/practice_cleared."""
    return bool(report_dir and
                os.path.exists(os.path.join(report_dir, "practice_cleared")))


PRACTICE_CLEAR_JS = r"""
<script>
(function(){
  function repRel(){ var m=location.pathname.match(/^\/r\/(.+)$/);
    return m?decodeURIComponent(m[1].replace(/\/$/,'')):null; }
  var REL=repRel();
  function setCleared(v){
    if(!REL){ alert('Open this report inside the app (local server) to do that.'); return; }
    if(v && !confirm("Delete all blunder positions in this project?\n"
      +"For a project you have finished reviewing: removes every blunder diagram "
      +"and its content, and shrinks the report file. You can Restore at any time.")) return;
    fetch('/api/practice_clear',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({report:REL,clear:v})}).then(function(r){return r.json();})
    .then(function(d){ if(d.error){ alert('Failed: '+d.error); return; } location.reload(); })
    .catch(function(e){ alert('Failed: '+e); });
  }
  window.practiceClear=function(){ setCleared(true); };
  window.practiceRestore=function(){ setCleared(false); };
})();
</script>
"""


def _enrich_from_sgf(game, games_dirs):
    """Older analysis JSON lacks moves/setup/board_size (needed to draw boards).
    Recover them by re-reading the original SGF, matched by filename."""
    if game.get("moves") or sgfparse is None:
        return game
    fn = game.get("filename")
    if not fn:
        return game
    safe_fn = glob.escape(fn)  # filenames contain [..] which are glob wildcards
    for d in games_dirs:
        d = os.path.expanduser(d)
        for cand in glob.glob(os.path.join(d, "**", safe_fn), recursive=True):
            try:
                src = sgfparse.parse_sgf(cand)
            except Exception:
                continue
            game["moves"] = src["moves"]
            game["setup"] = src["setup"]
            game.setdefault("board_size", src["board_size"])
            return game
    return game


def esc(x):
    return html.escape(str(x))


# ---- dates -----------------------------------------------------------------
def parse_date(g):
    for s in (g.get("date", ""), g.get("filename", "")):
        m = re.search(r"(20\d{2})[-/_.]?(\d{2})[-/_.]?(\d{2})", s or "")
        if m:
            try:
                return datetime.date(int(m.group(1)), int(m.group(2)),
                                     int(m.group(3)))
            except ValueError:
                continue
    return None


def date_key(g):
    d = parse_date(g)
    return d.isoformat() if d else "0000-00-00"


def date_label(g):
    d = parse_date(g)
    return d.strftime("%m-%d") if d else "?"


# ---- per-game metrics ------------------------------------------------------
def blunder_count(g):
    """Union blunder count for a game: a move counts if it lost >= PTS_BLUNDER
    points OR dropped win-rate by >= WR_BLUNDER.  Recomputed from the move list
    so the figure is correct regardless of when the game was analysed/imported."""
    return sum(1 for m in g.get("all_user_moves", [])
               if (m.get("points_lost", 0) or 0) >= PTS_BLUNDER
               or (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER)


def game_metrics(g):
    """Return {phase: {n, apl, br_pts, br_wr, blunders}} for one game."""
    moves = g.get("all_user_moves", [])
    out = {}
    for ph in PHASES:
        sub = moves if ph == "overall" else [m for m in moves
                                             if m.get("phase") == ph]
        n = len(sub)
        if n == 0:
            out[ph] = {"n": 0, "apl": None, "br_pts": None,
                       "br_wr": None, "blunders": 0}
            continue
        nb_pts = sum(1 for m in sub if m.get("points_lost", 0) >= PTS_BLUNDER)
        nb_wr = sum(1 for m in sub if m.get("winrate_lost", 0) >= WR_BLUNDER)
        nb_either = sum(1 for m in sub
                        if m.get("points_lost", 0) >= PTS_BLUNDER
                        or m.get("winrate_lost", 0) >= WR_BLUNDER)
        out[ph] = {
            "n": n,
            "apl": round(sum(m.get("points_lost", 0) for m in sub) / n, 2),
            "br_pts": round(nb_pts / n * 100, 1),
            "br_wr": round(nb_wr / n * 100, 1),
            "blunders": nb_either,
        }
    return out


# ---- per-game data embedded for the JS date-range filter --------------------
def _games_data_js(chron):
    """Compact per-game records (oldest->newest) the in-page JS uses to
    recompute the overview cards/charts/histogram for any date range.
    Each phase carries raw [n, sum_points_lost, n_blunders_pts, n_blunders_wr]
    so move-weighted pooled averages can be recomputed client-side."""
    rows = []
    for g in chron:
        d = parse_date(g)
        won = g.get("won")
        ph = {}
        allm = g.get("all_user_moves", [])
        for phase in PHASES:
            sub = allm if phase == "overall" else [
                m for m in allm if m.get("phase") == phase]
            n = len(sub)
            loss = sum((m.get("points_lost", 0) or 0) for m in sub)
            nbp = sum(1 for m in sub
                      if (m.get("points_lost", 0) or 0) >= PTS_BLUNDER)
            nbw = sum(1 for m in sub
                      if (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER)
            nbe = sum(1 for m in sub
                      if (m.get("points_lost", 0) or 0) >= PTS_BLUNDER
                      or (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER)
            ph[phase] = [n, round(loss, 3), nbp, nbw, nbe]
        # per-move [points_lost, winrate_lost%] for move-level distribution plots
        pm = [[round(m.get("points_lost", 0) or 0, 1),
               round((m.get("winrate_lost", 0) or 0) * 100, 1)]
              for m in allm]
        rows.append({
            "d": d.isoformat() if d else None,
            "w": 1 if won is True else (0 if won is False else -1),
            "mv": len(g.get("moves", [])),
            "p": ph,
            "pm": pm,
        })
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


def _date_filter_bar():
    """Shared date-range control inserted at the top of every module. All bars
    are kept in sync by the GR JS module (they share class names)."""
    return (
        "<div class='datebar'>"
        "<span class='navlbl' style='width:auto'>Date range</span>"
        "<input type='date' class='dffrom' "
        "onchange=\"GR.manual(this)\">"
        "<span class='dfsep'>—</span>"
        "<input type='date' class='dfto' "
        "onchange=\"GR.manual(this)\">"
        "<button class='navbtn dfp' data-days='30' "
        "onclick=\"GR.preset(30,this)\">Last 30 days</button>"
        "<button class='navbtn dfp' data-days='90' "
        "onclick=\"GR.preset(90,this)\">Last 90 days</button>"
        "<button class='navbtn dfp on dfreset' data-days='all' "
        "onclick=\"GR.preset(null,this)\">All</button>"
        "</div>")


# ---- trend chart (multi-series line) ---------------------------------------
def trend_chart(title, labels, series, ylabel, width=760, height=250,
                tip_labels=None, avg_overrides=None):
    """series: list of (name, color, [values aligned with labels, None=gap]).

    labels     -- short x-axis tick text (e.g. game number 1,2,3...).
    tip_labels -- richer text shown in the hover tooltip (e.g. "Game 3  06-18");
                  falls back to `labels` when not given.
    """
    tips = tip_labels or labels
    pad_l, pad_r, pad_t, pad_b = 46, 14, 54, 50
    n = len(labels)
    allv = [v for _, _, vals in series for v in vals if v is not None]
    ymax = max(allv) * 1.18 if allv and max(allv) > 0 else 1.0

    def px(i):
        if n <= 1:
            return (pad_l + width - pad_r) / 2
        return pad_l + i * (width - pad_l - pad_r) / (n - 1)

    def py(v):
        return pad_t + (1 - v / ymax) * (height - pad_t - pad_b)

    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" '
             f'fill="#1a202c">{esc(title)}</text>')

    # per-phase averages, in the title band (top-right) so each phase's typical
    # level reads at a glance without hovering. Laid out as one horizontal row,
    # above the plot, so it never overlaps the curves. Colour-matched.
    avgs = []
    for si, (sname, scolor, svals) in enumerate(series):
        if avg_overrides is not None and si < len(avg_overrides):
            # caller supplies the headline (move-weighted) figure as a string so
            # the chart's phase mean matches the overview cards exactly.
            txt = avg_overrides[si]
        else:
            nums = [v for v in svals if v is not None]
            av = (sum(nums) / len(nums)) if nums else 0.0
            txt = f"{av:.1f}"
        avgs.append((sname, scolor, txt))
    entry_w = 74
    row_w = 44 + entry_w * len(avgs)
    ax = max(pad_l, width - pad_r - row_w)
    ay = 20
    p.append(f'<text x="{ax:.1f}" y="{ay}" font-size="9.5" fill="#aaa" '
             f'font-weight="600">phase mean</text>')
    ax += 44
    for sname, scolor, txt in avgs:
        p.append(f'<circle cx="{ax+3:.1f}" cy="{ay-3:.1f}" r="3" '
                 f'fill="{scolor}"/>')
        p.append(f'<text x="{ax+11:.1f}" y="{ay}" font-size="10" '
                 f'fill="#444">{esc(sname)} {esc(txt)}</text>')
        ax += entry_w

    # y gridlines + labels
    for k in range(5):
        yval = ymax * k / 4
        y = py(yval)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" '
                 f'y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#888">{yval:.1f}</text>')
    p.append(f'<text x="12" y="{pad_t-30}" font-size="10" fill="#888">'
             f'{esc(ylabel)}</text>')

    # x ticks (sequence numbers are short -> render horizontally centered)
    step = max(1, n // 12)
    for i in range(0, n, step):
        x = px(i)
        p.append(f'<text x="{x:.1f}" y="{height-pad_b+16:.1f}" font-size="10" '
                 f'fill="#888" text-anchor="middle">{esc(labels[i])}</text>')

    # series (each wrapped in a toggleable group keyed by index)
    for si, (name, color, vals) in enumerate(series):
        p.append(f'<g class="tser" data-si="{si}">')
        seg = []
        for i, v in enumerate(vals):
            if v is None:
                _flush_segment(p, seg, color)
                seg = []
            else:
                seg.append((px(i), py(v)))
        _flush_segment(p, seg, color)
        for i, v in enumerate(vals):
            if v is not None:
                p.append(f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="2.6" '
                         f'fill="{color}"/>')
                # larger transparent hit area so the value is easy to hover;
                # data-tip is read by the floating tooltip script.
                tip = f"{name} &middot; {tips[i]}: {v}"
                p.append(f'<circle class="pt" cx="{px(i):.1f}" '
                         f'cy="{py(v):.1f}" r="9" fill="transparent" '
                         f'data-tip="{esc(tip)}"></circle>')
        p.append('</g>')

    # legend — click an entry to show/hide that series.
    lx = pad_l
    ly = height - 8
    for si, (name, color, _) in enumerate(series):
        w = 20 + len(name) * 6.6
        p.append(f'<g class="tleg" data-si="{si}" '
                 f'onclick="toggleSeries(this)" style="cursor:pointer">')
        p.append(f'<rect x="{lx-2:.1f}" y="{ly-11:.1f}" width="{w:.1f}" '
                 f'height="16" fill="transparent"/>')
        p.append(f'<line x1="{lx}" y1="{ly-4}" x2="{lx+16}" y2="{ly-4}" '
                 f'stroke="{color}" stroke-width="2.5"/>')
        p.append(f'<text x="{lx+20}" y="{ly}" font-size="10" fill="#444">'
                 f'{esc(name)}</text>')
        p.append('</g>')
        lx += 26 + len(name) * 6.4
    p.append("</svg>")
    return "".join(p)


def _flush_segment(parts, seg, color):
    if len(seg) >= 2:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in seg)
        parts.append(f'<polyline fill="none" stroke="{color}" '
                     f'stroke-width="2" points="{pts}"/>')


def trends_section(chron):
    """chron: games oldest->newest. Returns HTML with the 4 trend charts."""
    if not chron:
        return ""
    seq = [str(i + 1) for i in range(len(chron))]
    tips = [f"Game {i + 1}  {date_label(g)}" for i, g in enumerate(chron)]
    gms = [game_metrics(g) for g in chron]

    def series_for(key):
        return [(PHASE_LABEL[ph], PHASE_COLOR[ph],
                 [gms[i][ph][key] for i in range(len(chron))])
                for ph in PHASES]

    # Pooled per-phase figures, computed from every move (not the mean of the
    # per-game dots), so the "phase mean" shown on each chart matches the overview
    # cards exactly. The "Overall" row pools every move; each phase row pools only
    # the moves belonging to that phase.
    st = {ph: {"cnt": 0, "loss": 0.0, "nb_pts": 0, "nb_wr": 0, "nb_either": 0}
          for ph in PHASES}
    for g in chron:
        for m in g.get("all_user_moves", []):
            pl = m.get("points_lost", 0) or 0
            isb = pl >= PTS_BLUNDER
            isw = (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER
            for ph in ("overall", m.get("phase")):
                if ph not in st:
                    continue
                st[ph]["cnt"] += 1
                st[ph]["loss"] += pl
                if isb:
                    st[ph]["nb_pts"] += 1
                if isw:
                    st[ph]["nb_wr"] += 1
                if isb or isw:
                    st[ph]["nb_either"] += 1
    ng = max(1, len(chron))

    def ov(metric):
        out = []
        for ph in PHASES:
            s = st[ph]
            c = s["cnt"]
            if metric == "apl":
                out.append(f"{(s['loss']/c):.2f}" if c else "—")
            elif metric == "br_pts":
                out.append(f"{(s['nb_pts']/c*100):.1f}%" if c else "—")
            elif metric == "br_wr":
                out.append(f"{(s['nb_wr']/c*100):.1f}%" if c else "—")
            elif metric == "blunders":
                out.append(f"{(s['nb_either']/ng):.1f}")
        return out

    charts = [
        trend_chart("Average points lost per move", seq,
                    series_for("apl"), "pts/move", tip_labels=tips,
                    avg_overrides=ov("apl")),
        trend_chart("Blunder rate — lost >= 6 pts", seq,
                    series_for("br_pts"), "share %", tip_labels=tips,
                    avg_overrides=ov("br_pts")),
        trend_chart("Blunder rate — win-rate drop >= 15%", seq,
                    series_for("br_wr"), "share %", tip_labels=tips,
                    avg_overrides=ov("br_wr")),
        trend_chart("Blunders per game (>=6 pts or win-rate -15%)", seq,
                    series_for("blunders"), "count", tip_labels=tips,
                    avg_overrides=ov("blunders")),
    ]
    body = "".join(f"<div class='chart'>{c}</div>" for c in charts)
    return ("<h2>Trends over time</h2>"
            "<p class='sub'>Each chart is ordered oldest-to-newest; the x-axis is "
            "the game number (1 = earliest). The four curves are the phases of the "
            "game. Hover a dot to see which game it is, its date and its value; "
            "<b>click a legend entry to hide/show that curve</b>.</p>"
            "<p class='sub'>The <b>phase mean</b> in each chart's top-right corner "
            "pools every move from every game and averages per move (the same basis "
            "as the overview cards above, so it is a move-weighted average, not a "
            "plain average of the per-game dots).<br>"
            "<b>Phase split</b> (by move number): <b>Fuseki</b> = moves 1-40; "
            "<b>Yose</b> = the last 40 moves, or anything past ~72% of the game; "
            "<b>Middlegame</b> = everything in between; "
            "<b>Overall</b> = all moves combined.</p>"
            f"<div class='charts2' id='homeCharts'>{body}</div>"
            + TRENDS_JS)


TRENDS_JS = """
<script>
function toggleSeries(g){
  var svg=g.ownerSVGElement; if(!svg) return;
  var si=g.getAttribute('data-si');
  var ser=svg.querySelector('.tser[data-si=\"'+si+'\"]');
  if(!ser) return;
  var off=ser.style.display==='none';
  ser.style.display=off?'':'none';
  g.style.opacity=off?'1':'0.35';
}
</script>
"""


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


HOSHI = {3, 9, 15}


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


# ---- blunder notes (structured, saved to <report>/notes.json) --------------
NOTE_CATS = ["Wrong direction / missed the big point", "Slow middlegame move (local loss)",
             "Yose mistake", "Middlegame misread (fight read wrong)",
             "Shape / local technique", "Slow fuseki move", "Other"]
NOTE_CAUSES = ["Misread (life-and-death / ko count)", "Wrong direction",
               "Overplay / greed", "Slack / backing down", "Life and death unsettled",
               "Sente-gote / order of play", "Shape", "Joseki misremembered",
               "Careless / mental state", "Other"]
# Curated maxims -- tick instead of retype.  Ordered by how often they
# tend to matter; the user's own recurring maxims get merged in on top.
NOTE_MAXIMS = ["Play the vital point, not the dead stones",
               "Take absolute sente moves while they last",
               "Take sente endgame plays first",
               "When ahead, simplify and close the game out",
               "Keep lone stones connected",
               "Read basic life and death to the end -- no wishful thinking",
               "A big point beats a small endgame play",
               "Decide the direction first, then the exact move",
               "Work on judging endgame values",
               "Give up stones lightly -- do not cling to lone stones",
               "Thickness is for attacking, not for enclosing territory"]


VOICE_PANEL = (
    "<div class='vcpanel'>"
    "<div class='vcrow'>"
    "<button type='button' class='vcbtn' id='vcBtn' onclick='vcToggle()'>"
    "&#127908; Start voice review</button>"
    "<span class='vctimer' id='vcTimer'>00:00</span>"
    "<span class='vcstat sub' id='vcStat'></span></div>"
    "<p class='sub vchint'>One recording can cover many moves: scroll through the "
    "blunders below and talk through your thinking, your blind spots and what you "
    "learned. Hit <b>Stop &amp; transcribe</b> at the end and the whole take is turned "
    "into text and saved to this report, ready for <b>Review Summary</b> to turn into "
    "your weakness profile.</p>"
    "<div class='vcbar' id='vcBar'><i id='vcBarFill'></i></div>"
    "<textarea id='vcText' class='vctext' rows='4' "
    "placeholder='The transcript will appear here -- edit it freely...'></textarea>"
    "<div class='vcrow'><button type='button' class='vcsave' onclick='vcSave()'>"
    "Save text</button><span class='sub' style='margin-left:8px'>"
    "Saved automatically; you can also edit and save by hand.</span></div>"
    "</div>")


FLOAT_REC = (
    "<div id='vcFloat' class='vcfloat'><span class='vcdot'></span>"
    "Recording <span id='vcFloatT'>00:00</span>"
    "<button type='button' onclick='vcToggle()'>Stop &amp; transcribe</button></div>")


VOICE_JS = r"""
<script>
(function(){
  function repRel(){ var m=location.pathname.match(/^\/r\/(.+)$/);
    return m?decodeURIComponent(m[1].replace(/\/$/,'')):null; }
  var REL=repRel(), server=!!REL;
  var HKEY='ymhidden:'+(REL||location.pathname);
  var VKEY='ymvoice:'+(REL||location.pathname);
  function el(id){ return document.getElementById(id); }

  // ---- delete a blunder from the practice set (persists; shrinks on rebuild) ----
  function hideCard(nid){ document.querySelectorAll('.diag').forEach(function(d){
    if(d.dataset.key===nid) d.remove(); }); }
  function loadHidden(){
    if(server){
      fetch('/api/practice_hidden?report='+encodeURIComponent(REL)+'&t='+Date.now(),{cache:'no-store'})
      .then(function(r){return r.json();}).then(function(d){
        (d.hidden||[]).forEach(hideCard); document.dispatchEvent(new Event('ymnotes')); })
      .catch(function(){});
    } else {
      try{ JSON.parse(localStorage.getItem(HKEY)||'[]').forEach(hideCard); }catch(e){}
      document.dispatchEvent(new Event('ymnotes'));
    }
  }
  window.delBlunder=function(btn){
    var d=btn.closest('.diag'); if(!d) return; var nid=d.dataset.key;
    if(!confirm('Remove this position from the practice set?\n(The report file shrinks on the next rebuild; the move still counts in Overview > Total blunders.)')) return;
    if(server){
      fetch('/api/practice_hide',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({report:REL,id:nid})}).then(function(r){return r.json();})
      .then(function(res){ if(res.error){ alert('Delete failed: '+res.error); return; }
        d.remove(); document.dispatchEvent(new Event('ymnotes')); })
      .catch(function(e){ alert('Delete failed: '+e); });
    } else {
      try{ var s=JSON.parse(localStorage.getItem(HKEY)||'[]');
        if(s.indexOf(nid)<0) s.push(nid); localStorage.setItem(HKEY,JSON.stringify(s)); }catch(e){}
      d.remove(); document.dispatchEvent(new Event('ymnotes'));
    }
  };

  // ---- batch voice review: one continuous recording across many positions ----
  var _mr=null, _chunks=[], _recording=false, _t0=0, _timer=null;
  function fmt(s){ var m=Math.floor(s/60), x=s%60;
    return (m<10?'0':'')+m+':'+(x<10?'0':'')+x; }
  function tick(){ var s=Math.floor((Date.now()-_t0)/1000);
    var i=el('vcTimer'); if(i) i.textContent=fmt(s);
    var f=el('vcFloatT'); if(f) f.textContent=fmt(s); }
  function setFloat(on){ var f=el('vcFloat'); if(f) f.style.display=on?'flex':'none'; }

  // ---- transcription heartbeat -------------------------------------------
  // The POST blocks for the whole take, so poll the server for where it has
  // got to. faster-whisper yields segments as it decodes, so the percentage
  // is real progress through the audio rather than a spinner.
  var _prog=null;
  function bar(pct, on){
    var b=el('vcBar'), f=el('vcBarFill');
    if(!b||!f) return;
    b.style.display = on ? 'block' : 'none';
    f.style.width = (pct||0)+'%';
    f.className = (pct>0) ? '' : 'idle';
  }
  function pollStart(st){
    pollStop();
    bar(0, true);
    var misses=0;
    _prog=setInterval(function(){
      fetch('/api/transcribe_progress?t='+Date.now(),{cache:'no-store'})
      .then(function(r){return r.json();}).then(function(p){
        if(!p || !p.active){ misses++; return; }
        misses=0;
        st.textContent=p.label||'Working...';
        bar(p.pct||0, true);
      }).catch(function(){ misses++; });
      // If the server never reports activity, stop nagging it.
      if(misses>20) pollStop();
    }, 500);
  }
  function pollStop(){
    if(_prog){ clearInterval(_prog); _prog=null; }
    bar(0, false);
  }
  function loadVoice(){
    if(server){
      fetch('/api/voice?report='+encodeURIComponent(REL)+'&t='+Date.now(),{cache:'no-store'})
      .then(function(r){return r.json();}).then(function(d){
        var t=el('vcText'); if(t) t.value=d.text||''; }).catch(function(){});
    } else { try{ var t=el('vcText'); if(t) t.value=localStorage.getItem(VKEY)||''; }catch(e){} }
  }
  function saveVoice(text, cb){
    if(server){
      fetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({report:REL,text:text})})
      .then(function(r){return r.json();}).then(function(res){ cb&&cb(!res.error,res.error); })
      .catch(function(e){ cb&&cb(false,''+e); });
    } else { try{ localStorage.setItem(VKEY,text); cb&&cb(true); }catch(e){ cb&&cb(false,''+e); } }
  }
  window.vcSave=function(){ var st=el('vcStat'); st.textContent='Saving...';
    saveVoice(el('vcText').value, function(ok,err){
      st.textContent=ok?'Saved \u2713':'Save failed: '+(err||''); }); };
  window.vcToggle=function(){
    var btn=el('vcBtn'), st=el('vcStat');
    if(!server){ alert('Voice transcription needs the app running (start the local server first).'); return; }
    if(!navigator.mediaDevices || !window.MediaRecorder){ alert('This browser does not support recording.'); return; }
    if(!_recording){
      navigator.mediaDevices.getUserMedia({audio:true}).then(function(stream){
        _chunks=[]; _mr=new MediaRecorder(stream);
        _mr.ondataavailable=function(e){ if(e.data && e.data.size) _chunks.push(e.data); };
        _mr.onstop=function(){
          stream.getTracks().forEach(function(t){ t.stop(); });
          clearInterval(_timer); setFloat(false);
          btn.innerHTML='\uD83C\uDFA4 Start voice review'; btn.classList.remove('on');
          st.textContent='Uploading the recording...';
          pollStart(st);
          var blob=new Blob(_chunks,{type:'audio/webm'});
          // Pass the report so the server can name the kept .webm after it.
          fetch('/api/transcribe?report='+encodeURIComponent(REL||''),
            {method:'POST',headers:{'Content-Type':'audio/webm'},body:blob})
          .then(function(r){return r.json();}).then(function(d){
            pollStop();
            if(d.error){
              // The audio is saved before transcription, so a Whisper failure
              // still leaves the take on disk \u2014 tell the user where it went.
              st.textContent='Transcription failed: '+d.error;
              return;
            }
            var t=el('vcText');
            var stamp='['+new Date().toLocaleString()+']';
            if(d.audio) stamp+='  recording: '+d.audio;
            t.value=(t.value?t.value.replace(/\s+$/,'')+'\n\n':'')+stamp+'\n'+(d.text||'');
            saveVoice(t.value, function(){
              st.textContent=d.text
                ? ('Transcribed and saved \u2713'+(d.audio?' \u00b7 filed under "'+d.audio+'"':'')+' (edit below)')
                : '(Nothing recognised in the audio.)'; });
          }).catch(function(e){ pollStop(); st.textContent='Transcription failed: '+e; });
        };
        _mr.start(); _recording=true; _t0=Date.now(); tick(); _timer=setInterval(tick,1000);
        setFloat(true);
        btn.innerHTML='\u23F9 Stop &amp; transcribe'; btn.classList.add('on');
        st.textContent='Recording... scroll through as many blunders as you like and keep talking; hit stop to transcribe the whole take.';
      }).catch(function(e){ alert('Cannot access the microphone: '+e); });
    } else { _recording=false; if(_mr) _mr.stop(); }
  };

  loadHidden();
  loadVoice();
})();
</script>
"""


def practice_section(games, hidden=None, cleared=False):
    """`hidden` is the set of blunder keys the user has deleted (individually or
    via delete-all).  Deleting is per position, never a blanket switch: a game
    imported later has keys nobody has deleted, so its blunders show up
    normally.  `cleared` is the retired sticky marker, honoured only so an old
    report folder still renders sensibly before it is migrated."""
    hidden = set(hidden or ())
    items = []
    total_blunders = 0
    for g in games:
        for m in g.get("all_user_moves", []):
            if (m.get("points_lost", 0) >= PTS_BLUNDER or
                    m.get("winrate_lost", 0) >= WR_BLUNDER):
                total_blunders += 1     # counts every blunder (matches Overview)
                key = f"{g.get('filename','')}#{m.get('move_number')}"
                if key in hidden or cleared:
                    continue
                items.append((g, m))
    items.sort(key=lambda t: t[1].get("points_lost", 0), reverse=True)
    n_deleted = total_blunders - len(items)

    restore_btn = (
        "<button type='button' class='vcsave' onclick='practiceRestore()' "
        f"title='Brings back all {n_deleted} deleted position(s)'>"
        f"&#8635; Restore {n_deleted} deleted</button>" if n_deleted else "")

    # Nothing left to practise, but the page must stay: the heading and the
    # voice-review panel are independent of the diagrams, and returning ""
    # would make build_html drop the Blunders page (and its nav entry) whole.
    if not items:
        return ("<h2>Blunder Set</h2>"
                "<p class='sub'>"
                + (f"All {n_deleted} blunder position(s) in this project have been "
                   "deleted, which keeps the report small once you have finished "
                   "reviewing them. Your <b>voice review below is untouched</b>, and "
                   "<b>Restore</b> brings them back. <b>Games you analyse from now on "
                   "will show their blunders here as usual.</b>"
                   if n_deleted else
                   "No blunders in this project — nothing lost 6 points or more, and "
                   "no move dropped the win rate by 15%.")
                + "</p>"
                + VOICE_PANEL
                + (f"<div class='flrow'><div class='flcount'>{n_deleted} deleted"
                   f"</div>{restore_btn}</div>" if n_deleted else "")
                + FLOAT_REC
                + VOICE_JS
                + PRACTICE_CLEAR_JS)

    # Build each card, recording its phase and classification for the navigator.
    built = []
    for g, m in items:
        board = board_before(g, m["move_number"])
        svg = diagram_svg(g, m, board=board)
        if svg is None:
            continue
        name, tip = classify_blunder(g, m, board)
        built.append({"g": g, "m": m, "svg": svg, "name": name,
                      "tip": tip, "phase": m.get("phase", "middlegame"),
                      "board": board})
    if not built:
        return ""

    # Group each blunder with every other "same mistake" (recurring missed move
    # or recurring local shape), best match first.
    SIM_T = 0.6
    pats = [local_pattern(e["g"], e["m"], e["board"]) for e in built]
    sim_mat = _similarity_matrix(built, pats)
    for i, e in enumerate(built):
        sims = []
        row = sim_mat[i]
        for j in range(len(built)):
            if j == i:
                continue
            s = row[j]
            if s >= SIM_T:
                sims.append((s, j))
        sims.sort(reverse=True)
        e["sims"] = [j for _, j in sims]
        e["sim_best"] = sims[0][0] if sims else 0.0

    # Categories (position classifications) and phases present, with counts.
    cats = []
    for e in built:
        if e["name"] not in cats:
            cats.append(e["name"])
    cat_slug = {c: f"c{i}" for i, c in enumerate(cats)}
    cat_count = {c: sum(1 for e in built if e["name"] == c) for c in cats}
    phases = [ph for ph in ("opening", "middlegame", "endgame")
              if any(e["phase"] == ph for e in built)]
    phase_count = {ph: sum(1 for e in built if e["phase"] == ph)
                   for ph in phases}

    # Navigator (clickable folders): phase row + position-type row.
    nav = ["<div class='navbar'>"]
    nav.append("<div class='navrow'><span class='navlbl'>Phase</span>")
    nav.append(f"<button class='navbtn on' data-fp='all'>All "
               f"<i data-cp='all'>{len(built)}</i></button>")
    for ph in phases:
        nav.append(f"<button class='navbtn' data-fp='{ph}'>"
                   f"{esc(PHASE_LABEL.get(ph, ph))} "
                   f"<i data-cp='{ph}'>{phase_count[ph]}</i></button>")
    nav.append("</div>")
    nav.append("<div class='navrow'><span class='navlbl'>Type</span>")
    nav.append("<button class='navbtn on' data-fc='all'>All "
               f"<i data-cc='all'>{len(built)}</i></button>")
    for c in cats:
        nav.append(f"<button class='navbtn' data-fc='{cat_slug[c]}'>"
                   f"{esc(c)} <i data-cc='{cat_slug[c]}'>{cat_count[c]}</i></button>")
    nav.append("</div>")
    nav.append("<div class='navrow'><span class='navlbl'>Points lost</span>"
               "<button class='navbtn on' data-fpts='0'>All</button>"
               "<button class='navbtn' data-fpts='6'>&ge; 6</button>"
               "<button class='navbtn' data-fpts='10'>&ge; 10</button>"
               "<button class='navbtn' data-fpts='15'>&ge; 15</button></div>")
    nav.append("<div class='navrow'><span class='navlbl'>Win-rate drop</span>"
               "<button class='navbtn on' data-fwr='0'>All</button>"
               "<button class='navbtn' data-fwr='15'>&ge; 15%</button>"
               "<button class='navbtn' data-fwr='30'>&ge; 30%</button>"
               "<button class='navbtn' data-fwr='50'>&ge; 50%</button></div>")
    nav.append("<div class='navrow'><span class='navlbl'>Status</span>"
               "<button class='navbtn on' data-fst='all'>All</button>"
               "<button class='navbtn' data-fst='todo'>To review "
               "<i id='cnt-todo'>0</i></button>"
               "<button class='navbtn' data-fst='done'>Mastered "
               "<i id='cnt-done'>0</i></button></div>")
    nav.append("</div>")

    # Cards.
    cards = []
    for i, e in enumerate(built):
        g, m = e["g"], e["m"]
        color = "Black" if g["user_color"] == "B" else "White"
        ph = PHASE_LABEL.get(e["phase"], e["phase"])
        wr = m.get("winrate_lost", 0) * 100
        line = esc(m.get("best_pv", "") or "")
        cap = (f"Move {m['move_number']} &middot; you ({color})"
               f"<span class='pill'>{esc(ph)}</span><br>"
               f"You played <b>{esc(m.get('played'))}</b> "
               f"(&minus;{m.get('points_lost')} pts, win rate &minus;{wr:.0f}%) &middot; "
               f"KataGo: <b>{esc(m.get('best'))}</b>")
        sub = f"{esc(g.get('date',''))} vs {esc(g.get('opponent',''))}"
        line_html = (f"<div class='dline'><b>AI line:</b> {line}</div>"
                     if line else "")
        if e["sims"]:
            ids = ",".join(f"bl{j}" for j in e["sims"])
            n = len(e["sims"])
            kind = ("Same move missed" if e["sim_best"] >= 0.78
                    else "Similar shape")
            label = kind + (f" ({n})" if n > 1 else "")
            btn = (f"<button class='simbtn' data-sims='{ids}' data-i='0' "
                   f"onclick='goSim(this)'>&#8631; {label} &rarr;</button>")
        else:
            btn = ""
        # Stable key (game + move) so the mastered state survives report rebuilds.
        key = esc(f"{g.get('filename','')}#{m.get('move_number')}")
        msbtn = ("<button class='msbtn' onclick='toggleMaster(this)'>"
                 "&#10003; Mark as mastered</button>")
        notebtn = ""
        delbtn = ("<button class='delbtn' type='button' onclick='delBlunder(this)' "
                  "title='Mastered -- remove from the practice set (smaller file after rebuild)'>&#128465; Delete</button>")
        # Click-to-expand: a full-board diagram (hidden) shown in a modal, plus a
        # plain-text title/info line (no quotes, safe inside attributes).
        title = esc(f"Move {m['move_number']} - you ({color}) - {ph}")
        info = esc(f"You played {m.get('played')} (-{m.get('points_lost')} pts, "
                   f"win rate -{wr:.0f}%). KataGo recommends: {m.get('best')}. "
                   f"AI line: {m.get('best_pv','') or '-'}")
        # Whether this position has a stored KataGo ownership map (only present
        # if the game was analysed with the ownership-capture pass).
        has_est = bool(m.get("ownership"))
        est = ""
        bp, wp = m.get("own_black_pts"), m.get("own_white_pts")
        if has_est and bp is not None and wp is not None:
            komi = float(g.get("komi", 7.5) or 7.5)
            lead = bp - wp - komi  # Black's perspective, area scoring incl. komi
            who = "Black leads by" if lead >= 0 else "White leads by"
            own = m.get("ownership")
            size = m.get("own_size") or g.get("board_size", 19)
            sides = ""
            if own and len(own) == size * size:
                bt, wt = territory_split(own, size, e["board"])
                sides = f"Black ~ {bt:.1f} pts, White ~ {wt:.1f} pts; "
            est = esc(f"AI territory estimate (stones excluded): {sides}"
                      f"after {komi:g} komi: {who} {abs(lead):.1f} pts")
        # The full board is fetched lazily on click (keeps the file small) —
        # see openBoard / /api/board.
        fbfull = ""
        if g.get("moves"):
            img = (f"<div class='dimg' onclick='openBoard(this)' "
                   f"title='Click for the full board'>{e['svg']}</div>"
                   f"<div class='dhint'>Click the board to enlarge it and see the full variation</div>")
        else:
            img = e["svg"]
        _gd = parse_date(g)
        _gd = _gd.isoformat() if _gd else ""
        cards.append(
            f"<div class='diag' id='bl{i}' data-key=\"{key}\" "
            f"data-date='{_gd}' "
            f"data-phase='{e['phase']}' "
            f"data-cat='{cat_slug[e['name']]}' "
            f"data-pts='{m.get('points_lost', 0)}' data-wr='{wr:.1f}' "
            f"data-est='{1 if has_est else 0}' data-estline=\"{est}\" "
            f"data-played=\"{esc(m.get('played') or '')}\" "
            f"data-best=\"{esc(m.get('best') or '')}\" "
            f"data-catname=\"{esc(e['name'])}\" "
            f"data-game=\"{esc(g.get('filename',''))}\" "
            f"data-move='{m.get('move_number')}' "
            f"data-title=\"{title}\" data-info=\"{info}\">{img}"
            f"<div class='dcap'>{cap}</div>"
            f"{line_html}"
            f"<div class='dsub'>{sub}</div>{btn}{msbtn}{notebtn}{delbtn}{fbfull}</div>")

    # Filterable practice cards + the board modal and JS.
    return ("<h2>Blunder Set</h2>"
            f"<p class='sub'>Every blunder across all your games (&ge;6 pts or win rate "
            f"&minus;15%; {total_blunders} in total, matching the Overview blunder count)"
            + (f"; {n_deleted} mastered ones have been deleted, leaving {len(items)} in the practice set" if n_deleted else "")
            + ", cropped down to the local shape for practice -- filter by phase, type, "
            "points lost and more. "
            "<span style='color:#e02424'>&#9632; The red square</span> = the move you "
            "actually played; <b>the numbered stones</b> are KataGo's recommended "
            "variation (<span style='color:#1f9d55'>&#9679; number 1 = its move</span>). "
            "Cover the markers first and try to read the sequence out yourself.</p>"
            + VOICE_PANEL
            + "".join(nav)
            # The count line doubles as the home for the bulk actions: it sits
            # right under the filters, where you end up once you have worked
            # through the set.
            + "<div class='flrow'><div class='flcount' id='flcount'></div>"
              "<button type='button' class='clrbtn' onclick='practiceClear()' "
              "title='Deletes the positions listed here. Reversible, and blunders "
              "from games you analyse later still appear.'>"
              "&#128465; Delete all blunder positions</button>"
            + restore_btn
            + "</div>"
            + f"<div class='diags'>{''.join(cards)}</div>"
            + BOARD_MODAL
            + FLOAT_REC
            + PRACTICE_JS
            + VOICE_JS
            + PRACTICE_CLEAR_JS)


BOARD_MODAL = """
<div id='bd-modal' class='bdmask'>
  <div class='bdbox'>
    <button class='bdclose' onclick='closeBoard()'>&times;</button>
    <div class='bdtitle' id='bd-title'></div>
    <div class='bdtogs'>
      <label><input type='checkbox' id='bd-mv' checked>
        <span style='color:#e02424'>&#9632;</span> Move played</label>
      <label><input type='checkbox' id='bd-ai' checked>
        <span style='color:#1f9d55'>&#9679;</span> AI recommendation (numbered continuation)</label>
      <label id='bd-est-lbl' style='display:none'><input type='checkbox' id='bd-est'>
        <span style='color:#111'>&#9632;</span>/<span style='color:#bbb'>&#9633;</span>
        AI territory estimate (square size = ownership confidence, dead stones marked; circled number = that group's approximate points)</label>
      <label><input type='checkbox' id='bd-libs'>
        <span style='color:#e02424'>&#9312;</span> Liberties per group (coloured at &le;3: <span style='color:#e02424'>red 1</span>/<span style='color:#f76707'>orange 2</span>/<span style='color:#f2b200'>yellow 3</span>)</label>
      <label><input type='checkbox' id='bd-conn'>
        <span style='color:#2b6cb0'>&#9741;</span> Combined liberties (switch on, then click several <b>same-colour</b> groups to see their liberties once linked)</label>
    </div>
    <div class='bdest' id='bd-est-line'></div>
    <div class='bdconn' id='bd-conn-line'></div>
    <div class='bdbody' id='bd-body'></div>
    <div class='bdinfo' id='bd-info'></div>
  </div>
</div>
"""


PRACTICE_JS = """
<script>
(function(){
  var fp='all', fc='all', fpts=0, fwr=0, fst='all';

  // Mastered positions persist in the browser, keyed by game+move so the state
  // survives regenerating the report.
  var STORE='go_review_mastered';
  function load(){
    try{ return new Set(JSON.parse(localStorage.getItem(STORE)||'[]')); }
    catch(e){ return new Set(); }
  }
  function save(set){
    try{ localStorage.setItem(STORE, JSON.stringify(Array.from(set))); }
    catch(e){}
  }
  var mastered = load();

  function refreshCard(d){
    var done = mastered.has(d.getAttribute('data-key'));
    d.classList.toggle('done', done);
    var b = d.querySelector('.msbtn');
    if(b) b.innerHTML = done ? '&#8617; Move back to review' : '&#10003; Mark as mastered';
  }
  // Recompute EVERY filter-button count from the cards actually present in the
  // DOM (so deleting positions updates all the tallies, not just the filtered count).
  function setI(attr,val,n){
    var el=document.querySelector('i['+attr+'="'+val+'"]'); if(el) el.textContent=n; }
  function recount(){
    var byPhase={}, byCat={}, total=0, todo=0, done=0;
    document.querySelectorAll('.diag').forEach(function(d){
      total++;
      var ph=d.getAttribute('data-phase'); byPhase[ph]=(byPhase[ph]||0)+1;
      var cat=d.getAttribute('data-cat'); byCat[cat]=(byCat[cat]||0)+1;
      if(mastered.has(d.getAttribute('data-key'))) done++; else todo++;
    });
    setI('data-cp','all',total); setI('data-cc','all',total);
    document.querySelectorAll('i[data-cp]').forEach(function(el){
      var v=el.getAttribute('data-cp'); if(v!=='all') el.textContent=byPhase[v]||0; });
    document.querySelectorAll('i[data-cc]').forEach(function(el){
      var v=el.getAttribute('data-cc'); if(v!=='all') el.textContent=byCat[v]||0; });
    var ct=document.getElementById('cnt-todo'); if(ct) ct.textContent=todo;
    var cd=document.getElementById('cnt-done'); if(cd) cd.textContent=done;
  }
  window.toggleMaster = function(btn){
    var d = btn.closest('.diag');
    var k = d.getAttribute('data-key');
    if(mastered.has(k)) mastered.delete(k); else mastered.add(k);
    save(mastered);
    refreshCard(d);
    recount();
    apply();
  };

  function apply(){
    var shown=0, gms={};
    document.querySelectorAll('.diag').forEach(function(d){
      var okp = fp==='all' || d.getAttribute('data-phase')===fp;
      var okc = fc==='all' || d.getAttribute('data-cat')===fc;
      var okpts = parseFloat(d.getAttribute('data-pts')) >= fpts;
      var okwr = parseFloat(d.getAttribute('data-wr')) >= fwr;
      var done = mastered.has(d.getAttribute('data-key'));
      var okst = fst==='all' || (fst==='done'?done:!done);
      var okdt = (window.GR ? GR.inRange(d.getAttribute('data-date')) : true);
      var vis = okp && okc && okpts && okwr && okst && okdt;
      d.style.display = vis ? '' : 'none';
      if(vis){ shown++; gms[(d.getAttribute('data-key')||'').split('#')[0]]=1; }
    });
    var fl=document.getElementById('flcount');
    if(fl) fl.textContent=shown+' shown \u00B7 from '+
      Object.keys(gms).length+' game(s)';
  }
  function wire(attr, set){
    document.querySelectorAll('.navbtn['+attr+']').forEach(function(b){
      b.addEventListener('click', function(){
        set(b.getAttribute(attr));
        document.querySelectorAll('.navbtn['+attr+']').forEach(function(x){
          x.classList.toggle('on', x===b);});
        apply();
      });
    });
  }
  wire('data-fp', function(v){ fp=v; });
  wire('data-fc', function(v){ fc=v; });
  wire('data-fpts', function(v){ fpts=parseFloat(v); });
  wire('data-fwr', function(v){ fwr=parseFloat(v); });
  wire('data-fst', function(v){ fst=v; });

  document.querySelectorAll('.diag').forEach(refreshCard);
  recount();
  apply();
  document.addEventListener('grdate', apply);
  // notes load / change, or a blunder is deleted -> recount all + re-filter
  document.addEventListener('ymnotes', function(){ recount(); apply(); });

  // Full-board modal: click a card's diagram to see the whole board at that
  // position, with the actual move and KataGo's line toggleable.
  var modal=document.getElementById('bd-modal');
  var bdBody=document.getElementById('bd-body');
  function applyTogs(){
    if(!bdBody) return;
    var mv=bdBody.querySelector("[id$='-mv']");
    var ai=bdBody.querySelector("[id$='-ai']");
    var est=bdBody.querySelector("[id$='-est']");
    var estnum=bdBody.querySelector("[id$='-estnum']");
    var dead=bdBody.querySelector("[id$='-dead']");
    var libs=bdBody.querySelector("[id$='-libs']");
    var cmv=document.getElementById('bd-mv'), cai=document.getElementById('bd-ai');
    var ce=document.getElementById('bd-est');
    var cl=document.getElementById('bd-libs');
    if(mv) mv.style.display=(cmv&&cmv.checked)?'':'none';
    if(ai) ai.style.display=(cai&&cai.checked)?'':'none';
    if(est) est.style.display=(ce&&ce.checked)?'':'none';
    // Dead-stone X marks and per-group point numbers follow the AI-estimate toggle.
    if(dead) dead.style.display=(ce&&ce.checked)?'':'none';
    if(estnum) estnum.style.display=(ce&&ce.checked)?'':'none';
    if(libs) libs.style.display=(cl&&cl.checked)?'':'none';
    // The numeric result always shows (whenever the position has ownership data);
    // it is not hidden by the square overlay toggle.
  }
  function bdRepRel(){ var m=location.pathname.match(/^\/r\/(.+)$/);
    return m?decodeURIComponent(m[1].replace(/\/$/,'')):null; }
  function bdSetup(d){
    document.getElementById('bd-title').textContent=d.getAttribute('data-title')||'';
    document.getElementById('bd-info').textContent=d.getAttribute('data-info')||'';
    var cmv=document.getElementById('bd-mv'), cai=document.getElementById('bd-ai');
    if(cmv) cmv.checked=true; if(cai) cai.checked=true;
    var cl=document.getElementById('bd-libs'); if(cl) cl.checked=false;
    var cc=document.getElementById('bd-conn'); if(cc) cc.checked=false;
    connReset(false);
    var hasEst=d.getAttribute('data-est')==='1';
    var lbl=document.getElementById('bd-est-lbl');
    var ce=document.getElementById('bd-est');
    var line=document.getElementById('bd-est-line');
    if(lbl) lbl.style.display=hasEst?'':'none';
    if(ce) ce.checked=false;
    if(line){ var t=d.getAttribute('data-estline')||'';
              line.textContent=t; line.style.display=(hasEst&&t)?'':'none'; }
  }
  window.openBoard=function(el){
    var d=el.closest('.diag'); if(!d||!modal) return;
    bdSetup(d);
    modal.classList.add('open');
    var rel=bdRepRel();
    if(!rel){  // offline (file://): no server to render the full board
      bdBody.innerHTML="<p style='padding:24px;color:#8a7d6b'>The full board cannot be enlarged in offline viewing mode. "+
        "Open the report inside the app (double-click Mirror of Go.command) to zoom in and see the full variation.</p>";
      return;
    }
    bdBody.innerHTML="<p style='padding:24px;color:#8a7d6b'>Loading the full board...</p>";
    fetch('/api/board?report='+encodeURIComponent(rel)+
      '&game='+encodeURIComponent(d.getAttribute('data-game')||'')+
      '&move='+encodeURIComponent(d.getAttribute('data-move')||'')+'&t='+Date.now(),
      {cache:'no-store'})
    .then(function(r){ return r.ok?r.text():Promise.reject('HTTP '+r.status); })
    .then(function(svg){ bdBody.innerHTML=svg; applyTogs(); })
    .catch(function(e){ bdBody.innerHTML="<p style='padding:24px;color:#c53030'>"+
      "Load failed: "+e+"</p>"; });
  };
  window.closeBoard=function(){
    if(!modal) return; modal.classList.remove('open'); bdBody.innerHTML='';
  };
  var cmv=document.getElementById('bd-mv'); if(cmv) cmv.addEventListener('change', applyTogs);
  var cai=document.getElementById('bd-ai'); if(cai) cai.addEventListener('change', applyTogs);
  var cest=document.getElementById('bd-est'); if(cest) cest.addEventListener('change', applyTogs);
  var clib=document.getElementById('bd-libs'); if(clib) clib.addEventListener('change', applyTogs);
  if(modal) modal.addEventListener('click', function(e){ if(e.target===modal) closeBoard(); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeBoard(); });

  // ---- Connect-liberties tool ----------------------------------------------
  // Pick several same-colour groups and see how many liberties they'd have once
  // joined; warn when they can't actually be connected. The board snapshot is
  // read from the SVG's data-board attribute so everything runs client-side.
  var connOn=false, connSel={};            // group key -> {color, stones[], key}
  var connLine=document.getElementById('bd-conn-line');
  var connHint='Combined liberties: click same-colour groups on the board (as many as you like); click again to deselect.';

  function connSvg(){ return bdBody ? bdBody.querySelector('svg') : null; }
  function connLayer(){ return bdBody ? bdBody.querySelector("[id$='-conn']") : null; }
  function boardOf(svg){
    return {n:parseInt(svg.getAttribute('data-n'),10),
            pad:parseFloat(svg.getAttribute('data-pad')),
            cell:parseFloat(svg.getAttribute('data-cell')),
            s:svg.getAttribute('data-board')||''};
  }
  function connClear(){
    connSel={};
    var g=connLayer(); if(g) g.innerHTML='';
    if(connLine){ connLine.innerHTML=''; connLine.style.display='none'; }
  }
  function connReset(on){
    connOn=on; connClear();
    if(bdBody) bdBody.classList.toggle('connmode', on);
    if(on && connLine){ connLine.style.display=''; connLine.innerHTML=connHint; }
  }
  function clickGrid(svg, b, evt){
    var pt=svg.createSVGPoint(); pt.x=evt.clientX; pt.y=evt.clientY;
    var ctm=svg.getScreenCTM(); if(!ctm) return null;
    var loc=pt.matrixTransform(ctm.inverse());
    var x=Math.round((loc.x-b.pad)/b.cell), y=Math.round((loc.y-b.pad)/b.cell);
    if(x<0||x>=b.n||y<0||y>=b.n) return null;
    if(Math.abs(loc.x-(b.pad+x*b.cell))>b.cell*0.5) return null;
    if(Math.abs(loc.y-(b.pad+y*b.cell))>b.cell*0.5) return null;
    return {x:x,y:y};
  }
  function groupAt(b,x,y){
    var c=b.s.charAt(y*b.n+x); if(c==='0'||c==='') return null;
    var seen={}, st=[[x,y]], stones=[]; seen[y*b.n+x]=1;
    while(st.length){
      var p=st.pop(); stones.push(p);
      var nb=[[p[0]+1,p[1]],[p[0]-1,p[1]],[p[0],p[1]+1],[p[0],p[1]-1]];
      for(var k=0;k<4;k++){
        var qx=nb[k][0], qy=nb[k][1];
        if(qx<0||qx>=b.n||qy<0||qy>=b.n) continue;
        var idx=qy*b.n+qx;
        if(b.s.charAt(idx)===c && !seen[idx]){ seen[idx]=1; st.push([qx,qy]); }
      }
    }
    stones.sort(function(a,c2){ return (a[1]*b.n+a[0])-(c2[1]*b.n+c2[0]); });
    return {color:c, stones:stones, key:stones[0][0]+','+stones[0][1]};
  }
  function libsOf(b, stoneSet){
    var libs={};
    Object.keys(stoneSet).forEach(function(k){
      var xy=k.split(','), x=+xy[0], y=+xy[1];
      var nb=[[x+1,y],[x-1,y],[x,y+1],[x,y-1]];
      nb.forEach(function(q){
        if(q[0]<0||q[0]>=b.n||q[1]<0||q[1]>=b.n) return;
        var kk=q[0]+','+q[1];
        if(stoneSet[kk]) return;
        if(b.s.charAt(q[1]*b.n+q[0])==='0') libs[kk]=1;
      });
    });
    return libs;
  }
  function draw(b, rings, libKeys, connectors){
    var layer=connLayer(); if(!layer) return;
    function SX(x){ return (b.pad+x*b.cell); }
    function SY(y){ return (b.pad+y*b.cell); }
    var out=[];
    rings.forEach(function(s){
      out.push('<circle cx="'+SX(s[0])+'" cy="'+SY(s[1])+'" r="'+(b.cell*0.5).toFixed(1)
        +'" fill="none" stroke="#2b6cb0" stroke-width="2"/>');
    });
    (libKeys||[]).forEach(function(k){
      var xy=k.split(',');
      out.push('<circle cx="'+SX(+xy[0])+'" cy="'+SY(+xy[1])+'" r="'+(b.cell*0.16).toFixed(1)
        +'" fill="#17b3c4"/>');
    });
    (connectors||[]).forEach(function(k){
      var xy=k.split(','), cx=SX(+xy[0]), cy=SY(+xy[1]), s=b.cell*0.34;
      out.push('<rect x="'+(cx-s/2).toFixed(1)+'" y="'+(cy-s/2).toFixed(1)+'" width="'
        +s.toFixed(1)+'" height="'+s.toFixed(1)+'" fill="#2f9e44" stroke="#fff" '
        +'stroke-width="1" transform="rotate(45 '+cx+' '+cy+')"/>');
    });
    layer.innerHTML=out.join('');
  }
  function recompute(b){
    var groups=Object.keys(connSel).map(function(k){ return connSel[k]; });
    var rings=[];
    groups.forEach(function(g){ g.stones.forEach(function(s){ rings.push(s); }); });
    if(!groups.length){
      draw(b, rings, [], []);
      if(connLine){ connLine.style.display=''; connLine.innerHTML=connHint; }
      return;
    }
    var selColor=null, mixed=false;
    groups.forEach(function(g){
      if(selColor===null) selColor=g.color; else if(selColor!==g.color) mixed=true;
    });
    if(mixed){
      draw(b, rings, [], []);
      if(connLine){ connLine.style.display='';
        connLine.innerHTML='<span class="bad">Cannot link: the selected groups are different colours</span> (only same-colour groups can be linked).'; }
      return;
    }
    var stoneSet={};
    groups.forEach(function(g){ g.stones.forEach(function(s){ stoneSet[s[0]+','+s[1]]=1; }); });
    if(groups.length===1){
      var lk1=Object.keys(libsOf(b, stoneSet));
      draw(b, rings, lk1, []);
      if(connLine){ connLine.style.display='';
        connLine.innerHTML='This group has <b>'+lk1.length+'</b> liberties.'; }
      return;
    }
    // connectors: empty points orthogonally adjacent to >=2 selected groups.
    var adj={};
    groups.forEach(function(g,gi){
      g.stones.forEach(function(s){
        var nb=[[s[0]+1,s[1]],[s[0]-1,s[1]],[s[0],s[1]+1],[s[0],s[1]-1]];
        nb.forEach(function(q){
          if(q[0]<0||q[0]>=b.n||q[1]<0||q[1]>=b.n) return;
          if(b.s.charAt(q[1]*b.n+q[0])!=='0') return;
          var kk=q[0]+','+q[1]; (adj[kk]=adj[kk]||{})[gi]=1;
        });
      });
    });
    var parent=groups.map(function(_,i){ return i; });
    function find(i){ while(parent[i]!==i){ parent[i]=parent[parent[i]]; i=parent[i]; } return i; }
    var connectors=[];
    Object.keys(adj).forEach(function(kk){
      var gs=Object.keys(adj[kk]).map(Number);
      if(gs.length>=2){ connectors.push(kk);
        for(var t=1;t<gs.length;t++) parent[find(gs[0])]=find(gs[t]); }
    });
    var root=find(0), allConn=groups.every(function(_,i){ return find(i)===root; });
    if(!allConn){
      draw(b, rings, [], []);
      if(connLine){ connLine.style.display='';
        connLine.innerHTML='<span class="bad">Cannot link: these groups share no point that connects them directly</span>'
          +' (too far apart -- it would take several moves, so it is not counted here).'; }
      return;
    }
    var merged={};
    Object.keys(stoneSet).forEach(function(k){ merged[k]=1; });
    connectors.forEach(function(k){ merged[k]=1; });
    var lk=Object.keys(libsOf(b, merged));
    draw(b, rings, lk, connectors);
    if(connLine){ connLine.style.display='';
      connLine.innerHTML='Linking <b>'+groups.length+'</b> groups \u2192 <b>'+lk.length+'</b> liberties in total'
        +' (requires playing the <b>'+connectors.length+'</b> connecting points, shown as green squares; light blue dots are liberties).'; }
  }
  if(bdBody) bdBody.addEventListener('click', function(evt){
    if(!connOn) return;
    var svg=connSvg(); if(!svg) return;
    var b=boardOf(svg);
    var gp=clickGrid(svg,b,evt); if(!gp) return;
    var g=groupAt(b, gp.x, gp.y); if(!g) return;
    if(connSel[g.key]) delete connSel[g.key]; else connSel[g.key]=g;
    recompute(b);
  });
  var cconn=document.getElementById('bd-conn');
  if(cconn) cconn.addEventListener('change', function(){ connReset(cconn.checked); });

  // Cycle through this blunder's similar positions. Clear filters first so the
  // target is visible, then scroll to it and flash a highlight.
  window.goSim = function(btn){
    var ids=(btn.getAttribute('data-sims')||'').split(',').filter(Boolean);
    if(!ids.length) return;
    var k=parseInt(btn.getAttribute('data-i')||'0',10) % ids.length;
    btn.setAttribute('data-i', k+1);
    ["[data-fp='all']","[data-fc='all']","[data-fpts='0']","[data-fwr='0']",
     "[data-fst='all']"]
      .forEach(function(sel){
        var b=document.querySelector('.navbtn'+sel); if(b) b.click();
      });
    var el=document.getElementById(ids[k]);
    if(el){
      el.scrollIntoView({behavior:'smooth', block:'center'});
      el.classList.add('hl');
      setTimeout(function(){ el.classList.remove('hl'); }, 1600);
    }
  };
})();
</script>
"""


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


# ---- aggregate + recommendations -------------------------------------------
def aggregate(games):
    all_moves = []
    for g in games:
        for m in g.get("all_user_moves", []):
            mm = dict(m)
            mm["game"] = g["filename"]
            mm["opponent"] = g.get("opponent", "")
            mm["date"] = g.get("date", "")
            all_moves.append(mm)

    def avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    phase_vals = {"opening": [], "middlegame": [], "endgame": []}
    for m in all_moves:
        phase_vals.setdefault(m["phase"], []).append(m["points_lost"])

    blunders = sorted((m for m in all_moves
                       if m["points_lost"] >= PTS_BLUNDER
                       or (m.get("winrate_lost", 0) or 0) >= WR_BLUNDER),
                      key=lambda m: m["points_lost"], reverse=True)

    by_date = sorted(games, key=date_key)
    half = len(by_date) // 2 or 1

    def mean_apl(gs):
        v = [g["avg_points_lost"] for g in gs if g.get("n_user_moves")]
        return round(sum(v) / len(v), 2) if v else 0.0

    return {
        "n": len(games),
        "wins": sum(1 for g in games if g.get("won") is True),
        "losses": sum(1 for g in games if g.get("won") is False),
        "avg_points_lost": avg([m["points_lost"] for m in all_moves]),
        "phase_avg": {k: avg(v) for k, v in phase_vals.items()},
        "n_blunders": len(blunders),
        "blunder_rate": round(len(blunders) / max(1, len(all_moves)) * 100, 1),
        "top_blunders": blunders[:15],
        "trend_older": mean_apl(by_date[:half]),
        "trend_newer": mean_apl(by_date[half:]),
        "n_user_moves": len(all_moves),
        "avg_moves": (round(sum(len(g.get("moves", [])) for g in games)
                            / len(games)) if games else 0),
        "moves_counts": [len(g.get("moves", [])) for g in games],
    }


def recommendations(agg):
    recs = []
    pa = agg["phase_avg"]
    if agg["n_user_moves"] == 0:
        return ["No analysed moves yet."]
    phase_cn = {"opening": "the fuseki",
                "middlegame": "the middlegame",
                "endgame": "the yose"}
    if any(pa.values()):
        worst = max(pa, key=lambda k: pa[k])
        recs.append(
            f"Your biggest average loss is in {phase_cn[worst]} "
            f"(about {pa[worst]} pts/move) -- that is where study pays off most, "
            f"so work on it first.")
    if agg["blunder_rate"] > 4:
        recs.append(
            f"{agg['blunder_rate']}% of your moves are blunders (&ge;6 pts or win "
            f"rate &minus;15%). Cutting out obvious blunders raises your strength "
            f"faster than polishing good moves -- slow down in the positions below.")
    if pa.get("endgame", 0) >= 1.5:
        recs.append(
            "Your yose losses are noticeable. Getting into the habit of counting "
            "and taking the largest endgame plays first is a cheap, repeatable win.")
    if agg["trend_newer"] and agg["trend_older"]:
        if agg["trend_newer"] < agg["trend_older"]:
            recs.append(
                f"You are improving: recent games lose {agg['trend_newer']} pts per "
                f"move versus {agg['trend_older']} pts earlier on.")
        elif agg["trend_newer"] > agg["trend_older"] * 1.1:
            recs.append(
                f"Recent games ({agg['trend_newer']} pts/move) are slightly worse "
                f"than earlier ones ({agg['trend_older']} pts/move) -- tougher "
                f"opponents, or are you playing too fast?")
    recs.append(
        "Review with the practice diagrams below, then open the same move number in "
        "Lizzie to study KataGo's full variation.")
    return recs


# ---- coach's qualitative review --------------------------------------------
def coach_review(games, agg):
    """A written, data-driven diagnosis: the player's main weakness, the Go
    principles they may be misunderstanding, and concrete suggestions.

    The numbers (worst phase, the point KataGo kept recommending, how often a
    winning game was thrown away) are computed from the data so the text stays
    honest as more games are analysed; the framing is the coaching layer."""
    moves = [m for g in games for m in g.get("all_user_moves", [])]
    if not moves:
        return ""
    pa = agg.get("phase_avg", {}) or {}
    worst = max(pa, key=lambda k: pa.get(k, 0)) if any(pa.values()) else "middlegame"
    worst_lbl = PHASE_LABEL.get(worst, worst)
    best_phase = min(pa, key=lambda k: pa.get(k, 0)) if any(pa.values()) else "opening"
    best_lbl = PHASE_LABEL.get(best_phase, best_phase)

    # The single point KataGo kept recommending while you played elsewhere.
    miss_cnt, miss_pts = {}, {}
    for m in moves:
        best, played = m.get("best"), m.get("played")
        if not best or best == played:
            continue
        if m.get("points_lost", 0) >= 1.5 or m.get("winrate_lost", 0) >= 0.08:
            miss_cnt[best] = miss_cnt.get(best, 0) + 1
            miss_pts[best] = miss_pts.get(best, 0.0) + m.get("points_lost", 0)
    top_pt, top_n, top_pts = "", 0, 0.0
    if miss_cnt:
        top_pt = max(miss_cnt, key=lambda k: (miss_cnt[k], miss_pts[k]))
        top_n = miss_cnt[top_pt]
        top_pts = miss_pts[top_pt]

    big_swings = sum(1 for m in moves if m.get("winrate_lost", 0) >= 0.30)
    decided_leaks = sum(1 for m in moves
                        if m.get("points_lost", 0) >= 6
                        and m.get("winrate_lost", 0) < 0.03)

    paras = []

    # 1. Overall diagnosis.
    paras.append(
        f"<p>Your <b>opening fundamentals are solid</b> -- in the {best_lbl} phase "
        f"you lose only {pa.get(best_phase, 0)} pts per move on average, and your "
        f"joseki and big-point choices are broadly right. Where you actually bleed "
        f"points is <b>{worst_lbl}</b> ({pa.get(worst, 0)} pts per move) -- the phase "
        f"where the board opens up and you have to judge the whole board yourself. In "
        f"other words: <b>what you have memorised is enough, but your live whole-board "
        f"judgement has not caught up</b>.</p>")

    # 2. Core weakness — the recurring missed big point.
    if top_n >= 4:
        paras.append(
            f"<p><b>The core problem: you keep missing the biggest move on the "
            f"board.</b> Across these games KataGo marked the area around "
            f"<b>{esc(top_pt)}</b> as best as many as <b>{top_n} times</b> "
            f"(costing roughly {top_pts:.0f} pts in total), and you almost never "
            f"took it -- instead you kept patching the area you had just been "
            f"fighting in, reinforcing a group that was already alive, or playing "
            f"small local moves. This is the classic combination of "
            f"<b>clinging to stones / refusing to play tenuki</b> and a "
            f"<b>weak feel for big points</b>.</p>")
    elif top_n >= 2:
        paras.append(
            f"<p><b>Core problem: finding the biggest point on the board.</b> "
            f"KataGo repeatedly ({top_n} times around {esc(top_pt)}) pointed at the "
            f"same big point you were slow to take, which means you often choose "
            f"wrongly between <b>answering locally</b> and <b>turning away to take "
            f"the big point</b>.</p>")
    else:
        paras.append(
            "<p><b>Your core problem is whole-board judgement in the middlegame.</b> "
            "Most of your mistakes are not reading errors -- they are choosing the "
            "wrong area to play in.</p>")

    if big_swings:
        paras.append(
            f"<p>Worse, playing in the unimportant place threw away a <b>game you "
            f"were leading or level in</b> on <b>{big_swings} occasions</b> (a single "
            f"move dropping the win rate by 30% or more). You do not lose the margin "
            f"gradually -- you hand it over all at once on a few critical moves.</p>")
    if decided_leaks >= 2:
        paras.append(
            f"<p>Another <b>{decided_leaks}</b> blunders came in already-decided "
            f"positions (they cost points without changing the result). That points "
            f"to <b>loose endgame and life-and-death finishing</b>: you relax when "
            f"winning and get flustered when losing.</p>")

    # 3. Go theory the player may be misunderstanding.
    paras.append(
        "<p><b>Go principles you may be misreading or ignoring:</b></p>"
        "<ul>"
        "<li><b>Vital points and big points (the largest move):</b> before every "
        "move, ask where the biggest area on the board is and compare two or three "
        "candidate big points, instead of reflexively answering next to your "
        "opponent's last stone.</li>"
        "<li><b>Once a group is alive, play tenuki:</b> if a group is unconditionally "
        "alive or already settled, another reinforcing move creates almost no value. "
        "Save the tesuji and the reinforcement for when you actually need them; when "
        "it is time to turn away, turn away.</li>"
        "<li><b>Direction of play:</b> attack and expand so that you drive your "
        "opponent towards your own thickness and lead your development towards the "
        "largest open area -- rather than pushing from behind in a small corner of "
        "the board.</li>"
        "<li><b>When behind, look for the biggest exchange:</b> in a bad position, "
        "look for a large group or a genuine game-turning move that wins back ten "
        "points at once, instead of patching with a series of small plays -- that "
        "only locks the deficit in.</li>"
        "</ul>")

    # 4. Concrete suggestions.
    sug = [
        f"Force yourself to do a whole-board scan before every move: find the "
        f"largest open area or the weakest group, and weigh it against the local "
        f"move you want to play -- especially the kind of big point you keep "
        f"missing around {esc(top_pt) if top_pt else 'the biggest open area'}.",
        "Practise the tenuki decision: every time a local exchange comes to a rest, "
        "pause and ask yourself, 'Does this group still need a move? Is there "
        "anything bigger elsewhere on the board?'",
        "Roughly count the score around moves 50, 100 and 150 to build the habit of "
        "positional judgement -- knowing whether you are ahead or behind is what "
        "tells you whether to play safe or to fight.",
        "Drill endgame value comparison and life-and-death finishing, so you close "
        "won games out cleanly and stop leaking points.",
        "Your opening is already decent: the biggest lever is not memorising more "
        "joseki but whole-board judgement in the middlegame -- focus your reviews on "
        "direction of play and big points.",
    ]
    paras.append("<p><b>What to do about it:</b></p><ol>"
                 + "".join(f"<li>{s}</li>" for s in sug) + "</ol>")

    return ("<h2>Coach's review (overall diagnosis)</h2>"
            "<div class='coach'>" + "".join(paras) + "</div>")


# ---- HTML shell ------------------------------------------------------------
CSS = """
:root{
 --paper:#f6f1e8; --card:#fffdf9; --line:#e9dfce; --line-soft:#f1ead9;
 --ink:#3d352e; --ink-soft:#6f6357; --muted:#9a8d7b;
 --espresso:#2a241f; --espresso-2:#37302a; --espresso-line:#3f382f;
 --on-dark:#e7ddce; --on-dark-soft:#b0a18d;
 --amber:#b7791f; --amber-ink:#8a5a12; --amber-soft:#f6ecd6; --amber-line:#e6d3ab;}
body{font-family:-apple-system,"PingFang SC",Segoe UI,Helvetica,Arial,sans-serif;
 margin:0;color:var(--ink);line-height:1.5;background:var(--paper)}
.layout{display:flex;align-items:flex-start;min-height:100vh}
.sidebar{position:sticky;top:0;align-self:flex-start;height:100vh;width:212px;
 flex:none;box-sizing:border-box;background:var(--espresso);color:var(--on-dark);
 padding:22px 14px;overflow-y:auto}
.brand{font-size:18px;font-weight:700;color:#fff;line-height:1.25}
.brand span{display:block;font-size:10.5px;font-weight:500;color:var(--amber);
 letter-spacing:1.5px;margin-top:3px}
.sidebar nav{display:flex;flex-direction:column;gap:3px;margin-top:24px}
.navlink{font:inherit;font-size:14px;text-align:left;cursor:pointer;border:none;
 background:transparent;color:var(--on-dark);border-radius:8px;padding:9px 12px;
 display:flex;align-items:center;gap:8px;transition:background .12s}
.navlink:hover{background:var(--espresso-2)}
.navlink.active{background:var(--amber);color:#fff;font-weight:600}
.navlink .dot{width:7px;height:7px;border-radius:50%;background:#6b5e4a;flex:none}
.navlink.active .dot{background:#ffe9bf}
.sidebar .meta{font-size:11px;color:var(--on-dark-soft);margin-top:26px;
 line-height:1.6;border-top:1px solid var(--espresso-line);padding-top:14px}
.content{flex:1;min-width:0;max-width:1000px;margin:0 auto;
 padding:30px 34px;box-sizing:border-box;background:var(--card);min-height:100vh}
.page{display:none}.page.active{display:block}
.page>h1:first-child,.page>h2:first-child{margin-top:0}
@media(max-width:760px){
 .layout{flex-direction:column}
 .sidebar{position:static;height:auto;width:auto}
 .sidebar nav{flex-direction:row;flex-wrap:wrap;margin-top:14px;gap:6px}
 .navlink{font-size:13px;padding:7px 11px}
 .content{padding:20px 16px}
}
h1{font-size:24px;margin-bottom:4px}h2{font-size:19px;margin-top:34px;
 border-bottom:2px solid var(--line);padding-bottom:6px}
h3{font-size:16px;margin-bottom:4px}
.sub{color:var(--ink-soft);font-size:13px;margin-top:0}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}
.card{flex:1;min-width:130px;background:var(--card);border:1px solid var(--line);
 border-radius:8px;padding:14px 16px}
.card .v{font-size:26px;font-weight:800;letter-spacing:-.01em;
 font-variant-numeric:tabular-nums}.card .l{font-size:12px;color:var(--ink-soft)}
.ovctl{margin:10px 0 0}
.ovctl .exw{display:inline-flex;align-items:center;gap:6px;font-size:13px;
 color:#4a5568;cursor:pointer;user-select:none}
.ovctl .exw input{cursor:pointer}
.ovctl .exwnote{margin-left:10px;font-size:12px;color:#a0aec0}
.improve{margin:6px 0 16px;padding:14px 16px;border-radius:12px;
 border:1px solid #e2e8f0;background:#f7fafc}
.improve .impl{font-size:11px;letter-spacing:.08em;color:#718096;font-weight:700}
.improve .impv{font-size:22px;font-weight:800;margin:3px 0 5px;
 display:flex;align-items:baseline;gap:8px}
.improve .impv .ar{font-size:18px}
.improve .impv .pct{font-size:14px;font-weight:700;opacity:.85}
.improve .impd{font-size:13px;color:#4a5568;line-height:1.55}
.imp-good{background:#f0fff4;border-color:#9ae6b4}.imp-good .impv{color:#276749}
.imp-bad{background:#fff5f5;border-color:#feb2b2}.imp-bad .impv{color:#c53030}
.imp-flat{background:#f7fafc;border-color:#e2e8f0}.imp-flat .impv{color:#4a5568}
.imp-na .impv{color:#718096;font-size:16px}
.charts2{display:grid;grid-template-columns:1fr;gap:14px}
.chart{min-width:0}
.chart .pt{cursor:pointer}.chart .pt:hover{fill:rgba(0,0,0,.06)}
#tipbox{position:fixed;z-index:9999;pointer-events:none;display:none;
 background:#1a202c;color:#fff;font-size:12px;line-height:1.3;padding:5px 9px;
 border-radius:6px;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.25)}
@media(max-width:760px){.charts2{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{border-bottom:1px solid #edf2f7;padding:6px 8px;text-align:left}
th{color:#718096;font-weight:600}
.rec{background:#ebf8ff;border-left:4px solid #3182ce;padding:10px 14px;
 border-radius:4px;margin:8px 0;font-size:14px}
.coach{background:#fffaf0;border:1px solid #f6e0b5;border-left:4px solid #dd6b20;
 border-radius:8px;padding:6px 18px;font-size:14px;line-height:1.7}
.coach ul,.coach ol{margin:6px 0 12px;padding-left:22px}
.coach li{margin:4px 0}.coach b{color:#9c4221}
.game{border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin:16px 0}
.win{color:#2f855a;font-weight:600}.loss{color:#c53030;font-weight:600}
.score{background:#f7fafc;border:1px solid #e2e8f0;border-radius:8px;
 padding:10px 14px;margin-top:12px}
.score .scl{font-size:12px;font-weight:700;color:#718096;margin-bottom:2px}
.score .scn{font-size:16px;margin-bottom:2px}
.score table{margin-top:6px}
.pill{display:inline-block;background:var(--amber-soft);color:var(--amber-ink);
 border-radius:12px;padding:1px 9px;font-size:12px;margin-left:6px}
.mv{font-variant-numeric:tabular-nums}.big{color:#c53030;font-weight:600}
.diags{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
 gap:16px}
/* ---- game trajectory ---- */
.cvbox{display:flex;flex-wrap:wrap;align-items:stretch;gap:14px 22px;margin:14px 0;
 padding:14px 18px;background:var(--card);border:1px solid var(--line);border-radius:12px}
.cvgrp{display:flex;gap:22px}
.cvstat{min-width:130px}
.cvstat .cvv{font-size:30px;font-weight:800;line-height:1.1;font-variant-numeric:tabular-nums;
 color:var(--ink)}
.cvstat .cvv.cv-good{color:#2f855a}.cvstat .cvv.cv-mid{color:var(--amber-ink)}
.cvstat .cvv.cv-bad{color:#c53030}
.cvstat .cvl{font-size:12.5px;color:var(--ink-soft);font-weight:700;margin-top:2px}
.cvstat .cvl span{display:block;font-size:11px;color:var(--muted);font-weight:400;margin-top:1px}
.cvnote{flex:1;min-width:220px;align-self:center;font-size:12px;color:var(--muted);
 line-height:1.6;border-left:1px solid var(--line);padding-left:14px}
.tjsum{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.tjchip{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;
 border-radius:16px;padding:4px 12px;border:1px solid var(--line);cursor:pointer;
 user-select:none;transition:box-shadow .1s,filter .1s}
.tjchip:hover{filter:brightness(.97)}
.tjchip.on{box-shadow:inset 0 0 0 2px currentColor}
.tjchip.tjall{background:#efe9df;color:var(--ink-soft)}
.tjchip b{font-variant-numeric:tabular-nums}
.tjchip.t-win{background:#eaf6ee;border-color:#bfe3cb;color:#276749}
.tjchip.t-come{background:var(--amber-soft);border-color:var(--amber-line);color:var(--amber-ink)}
.tjchip.t-loss{background:#f3f0eb;border-color:var(--line);color:#7a6f62}
.tjchip.t-bad{background:#fdecec;border-color:#f3c0c0;color:#b03535}
.tjchip.t-crash{background:#fbe3e3;border-color:#eba9a9;color:#a02020}
.tjins{margin:6px 0 14px;padding-left:20px;font-size:13px;line-height:1.7;color:var(--ink-soft)}
.tjins b{color:var(--ink)}
.trajgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.trajcard{border:1px solid var(--line);border-radius:10px;padding:12px 12px 10px;
 background:var(--card)}
.tjhead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}
.tjbadge{font-size:12px;font-weight:700;border-radius:8px;padding:2px 9px}
.tjbadge.t-win{background:#eaf6ee;color:#276749}
.tjbadge.t-come{background:var(--amber-soft);color:var(--amber-ink)}
.tjbadge.t-loss{background:#f3f0eb;color:#7a6f62}
.tjbadge.t-bad{background:#fdecec;color:#b03535}
.tjbadge.t-crash{background:#fbe3e3;color:#a02020}
.tjshape{font-size:14px;letter-spacing:1px}
.tjspark{border:1px solid var(--line-soft);border-radius:7px;overflow:hidden;background:#fff}
.tjmeta{font-size:11.5px;color:var(--muted);margin-top:7px;line-height:1.4}
.diag{position:relative;border:1px solid #e2e8f0;border-radius:8px;padding:10px;
 text-align:center}
.diag.done{opacity:.6}
.diag.done::after{content:'Mastered';position:absolute;top:8px;right:8px;
 background:#276749;color:#fff;font-size:10px;font-weight:700;border-radius:10px;
 padding:2px 8px}
.msbtn{display:inline-block;font:inherit;font-size:11.5px;cursor:pointer;
 border:1px solid #9ae6b4;background:#f0fff4;color:#276749;border-radius:6px;
 padding:4px 9px;margin-top:8px;margin-left:6px}
.msbtn:hover{background:#c6f6d5}
.diag.done .msbtn{border-color:#cbd5e0;background:#edf2f7;color:#4a5568}
.diag svg{max-width:100%;height:auto}
.dcap{font-size:12px;margin-top:6px;text-align:left;line-height:1.45}
.dline{font-size:11.5px;color:#2d3748;text-align:left;margin-top:5px;
 font-variant-numeric:tabular-nums;background:#f7fafc;border-radius:4px;
 padding:3px 6px}
.dname{font-size:12px;font-weight:700;color:#c05621;text-align:left;
 margin-top:8px}
.dtip{font-size:11.5px;color:#4a5568;text-align:left;margin-top:3px;
 line-height:1.45}
.dsub{font-size:11px;color:#718096;text-align:left;margin-top:6px}
.navbar{margin:10px 0 16px}
.navrow{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:6px 0}
.navlbl{font-size:12px;font-weight:700;color:#718096;width:46px;flex:none}
.navbtn{font:inherit;font-size:12px;cursor:pointer;border:1px solid var(--line);
 background:var(--card);color:var(--ink);border-radius:14px;padding:4px 11px}
.navbtn:hover{background:var(--amber-soft);border-color:var(--amber-line)}
.navbtn.on{background:var(--amber);border-color:var(--amber);color:#fff}
.navbtn i{font-style:normal;opacity:.7;font-size:11px;margin-left:3px}
.navbtn.on i{opacity:.9}
.datebar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:10px 0 14px;
 padding:9px 12px;background:var(--line-soft);border:1px solid var(--line);
 border-radius:10px}
.datebar input[type=date]{font:inherit;font-size:12.5px;border:1px solid #cbd5e0;
 border-radius:8px;padding:3px 7px;color:#2d3748;background:#fff}
.datebar .dfsep{color:#a0aec0;font-size:13px}
.datebar .dfreset{margin-left:auto}
.simbtn{display:inline-block;font:inherit;font-size:11.5px;cursor:pointer;
 border:1px solid #b794f4;background:#faf5ff;color:#6b46c1;border-radius:6px;
 padding:4px 9px;margin-top:8px}
.simbtn:hover{background:#e9d8fd}
.diag.hl{box-shadow:0 0 0 3px #6b46c1}
.delbtn{margin-top:6px;margin-left:6px;border:1px solid #f0c8c0;background:#fff;
 color:#b5462f;border-radius:7px;padding:5px 10px;font-size:12.5px;cursor:pointer}
.delbtn:hover{background:#fbeae6;border-color:#e08a75}
.notebtn{margin-top:6px;margin-left:6px;border:1px solid #cbd5e0;background:#fff;
 color:#4a5568;border-radius:7px;padding:5px 10px;font-size:12.5px;cursor:pointer}
.notebtn:hover{background:#f7fafc;border-color:#6b46c1;color:#6b46c1}
.diag.hasnote{box-shadow:0 0 0 2px #d6bcfa}
.diag.hasnote .notebtn{background:#f3effc;border-color:#9f7aea;color:#6b46c1}
.ndot{color:#6b46c1;font-weight:700}
.notectl{margin:6px 0 14px}
.notectl button{border:1px solid #cbd5e0;background:#fff;border-radius:8px;
 padding:7px 12px;font-size:13px;cursor:pointer;color:#4a5568}
.notectl button:hover{border-color:#6b46c1;color:#6b46c1}
.nmodal{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:1000;display:none;
 align-items:center;justify-content:center;padding:16px}
.nmodal.open{display:flex}
.nbox{background:#fff;border-radius:12px;max-width:560px;width:100%;max-height:88vh;
 overflow-y:auto;box-shadow:0 12px 40px rgba(0,0,0,.3)}
.nhd{position:sticky;top:0;background:#1a202c;color:#fff;padding:12px 16px;display:flex;
 align-items:center;gap:8px;border-radius:12px 12px 0 0}
.nhd .nmt{font-size:12px;color:#cbd5e1;flex:1;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
.nhd .nx{background:none;border:none;color:#fff;font-size:22px;cursor:pointer;line-height:1}
.nbd{padding:14px 16px}
.nbd label{display:block;font-size:12px;color:#718096;font-weight:600;margin:12px 0 4px}
.nbd select,.nbd input,.nbd textarea{width:100%;box-sizing:border-box;padding:8px 9px;
 border:1px solid #cdd3da;border-radius:8px;font-size:13.5px;font-family:inherit}
.nmeta{font-size:12.5px;color:#4a5568;background:#f7fafc;border-radius:8px;padding:8px 10px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips .chip{display:inline-flex;align-items:center;gap:4px;border:1px solid #cdd3da;
 border-radius:16px;padding:4px 10px;font-size:12.5px;color:#4a5568;cursor:pointer;margin:0}
.chips .chip input{width:auto;margin:0}
.chips .chip:has(input:checked){background:var(--amber-soft);border-color:var(--amber);
 color:var(--amber-ink);font-weight:600}
.vcpanel{margin:10px 0 14px;padding:14px 16px;border:1px solid var(--amber-line);
 background:var(--amber-soft);border-radius:12px}
.vcrow{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.vcbtn{border:1px solid var(--amber);background:var(--amber);color:#fff;
 border-radius:9px;padding:9px 16px;font-size:14px;font-weight:700;cursor:pointer}
.vcbtn:hover{filter:brightness(1.05)}
.vcbtn.on{background:#c0392b;border-color:#a5281b;animation:recpulse 1s infinite}
.vctimer{font-variant-numeric:tabular-nums;font-weight:700;color:var(--espresso);
 font-size:14px}
.vcstat{font-size:12.5px}
/* transcription heartbeat: real progress through the audio, not a spinner */
.vcbar{display:none;height:6px;border-radius:999px;background:#eadfc6;
 overflow:hidden;margin:0 0 8px}
.vcbar>i{display:block;height:100%;width:0;border-radius:999px;
 background:var(--amber,#b7791f);transition:width .35s ease}
.vcbar>i.idle{width:35%;animation:vcslide 1.1s ease-in-out infinite;
 background:#d8b075}
@keyframes vcslide{0%{margin-left:-35%}100%{margin-left:100%}}
.vchint{margin:8px 0 8px;line-height:1.6}
.vctext{width:100%;box-sizing:border-box;border:1px solid var(--amber-line);
 border-radius:8px;padding:9px 11px;font-size:13.5px;line-height:1.65;
 background:#fff;color:var(--ink);resize:vertical}
.vcsave{border:1px solid var(--amber-line);background:#fff;color:var(--amber-ink);
 border-radius:8px;padding:7px 14px;font-size:13px;font-weight:600;cursor:pointer}
.vcsave:hover{background:#efe0bf}
.clrbtn{border:1px solid #e2c9a0;background:#fff;color:#9a6a2a;border-radius:8px;
 padding:6px 12px;font-size:12.5px;font-weight:600;cursor:pointer}
.clrbtn:hover{background:#fbefd9;border-color:#d8b075}
.vcfloat{display:none;position:fixed;right:18px;bottom:18px;z-index:9999;
 align-items:center;gap:10px;background:#c0392b;color:#fff;border-radius:999px;
 padding:10px 16px;font-size:13.5px;font-weight:700;
 box-shadow:0 6px 20px rgba(0,0,0,.25)}
.vcfloat button{border:0;background:rgba(255,255,255,.22);color:#fff;
 border-radius:999px;padding:6px 12px;font-size:12.5px;font-weight:700;cursor:pointer}
.vcfloat button:hover{background:rgba(255,255,255,.35)}
.vcdot{width:10px;height:10px;border-radius:50%;background:#fff;
 animation:recpulse 1s infinite}
.smdbox{font-size:14.5px;line-height:1.75;color:var(--ink);max-width:920px}
.smdbox h1{font-size:21px;margin:6px 0 12px}
.smdbox h2{font-size:17.5px;margin:20px 0 8px;padding-top:6px;
 border-top:1px solid var(--amber-line)}
.smdbox h3{font-size:15px;margin:14px 0 6px;color:var(--espresso)}
.smdbox h4{font-size:13.5px;margin:10px 0 4px;color:var(--muted)}
.smdbox p{margin:8px 0}
.smdbox ul,.smdbox ol{margin:8px 0;padding-left:22px}
.smdbox li{margin:3px 0}
.smdbox blockquote{margin:10px 0;padding:8px 14px;border-left:3px solid var(--amber);
 background:var(--amber-soft);color:var(--espresso);border-radius:0 8px 8px 0}
.smdbox hr{border:0;border-top:1px solid var(--amber-line);margin:16px 0}
.smdbox code{background:var(--amber-soft);padding:1px 5px;border-radius:4px;font-size:13px}
.smdbox table.smd{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
.smdbox table.smd th,.smdbox table.smd td{border:1px solid var(--amber-line);
 padding:7px 9px;text-align:left;vertical-align:top}
.smdbox table.smd thead th{background:var(--amber-soft);color:var(--espresso);font-weight:700}
.smdbox table.smd tbody tr:nth-child(even){background:#fbf7ef}
.recrow{display:flex;gap:10px;align-items:center;margin:2px 0 6px}
.recbtn{border:1px solid var(--amber-line);background:var(--amber-soft);
 color:var(--amber-ink);border-radius:8px;padding:6px 12px;font-size:12.5px;
 font-weight:600;cursor:pointer}
.recbtn:hover{background:#efe0bf}
.recbtn.on{background:#fbe3e3;border-color:#eba9a9;color:#a02020;
 animation:recpulse 1s infinite}
@keyframes recpulse{50%{opacity:.55}}
.addrow{display:flex;gap:8px;margin-top:8px}
.addrow input{flex:1}
.addbtn{flex:none;white-space:nowrap;border:1px solid var(--amber-line);
 background:var(--amber-soft);color:var(--amber-ink);border-radius:8px;
 padding:8px 12px;font-size:12.5px;font-weight:600;cursor:pointer}
.addbtn:hover{background:#efe0bf}
.nbtns{margin-top:14px;display:flex;align-items:center;gap:10px}
.nbtns .nsave{background:#6b46c1;color:#fff;border:none;border-radius:8px;padding:9px 20px;
 font-weight:700;cursor:pointer}
.nbtns .ndel{background:#fff;color:#c53030;border:1px solid #fbb6b6;border-radius:8px;
 padding:9px 14px;cursor:pointer}
.nstat{font-size:12.5px;color:#718096}
.nsg{margin:10px 0}.nsg ul{margin:6px 0 0;padding-left:20px}.nsg li{font-size:13px;margin:2px 0}
.fbbtn{font:inherit;font-size:12px;cursor:pointer;border:1px solid #cbd5e0;
 background:#fff;border-radius:6px;padding:3px 9px}
.fbbtn:hover{background:#f7fafc}
.fbpanel{padding:6px 2px}
.fbtogs{display:flex;gap:14px;margin-bottom:4px}
.fbtog{font-size:12px;color:#4a5568;cursor:pointer;user-select:none}
.fbtog input{vertical-align:middle;margin-right:4px}
.flcount{font-size:12.5px;color:#4a5568;font-weight:600;margin:2px 0 14px}
.flrow{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:2px 0 14px}
.flrow .flcount{margin:0}
/* review-summary history: older versions kept, collapsed under the latest */
.sumexp{border:1px solid var(--amber-line);background:var(--card);
 color:var(--amber-ink);border-radius:8px;padding:7px 14px;font-size:12.5px;
 font-weight:600;cursor:pointer;text-decoration:none;white-space:nowrap}
.sumexp:hover{background:var(--amber-soft)}
.sumhist{margin-top:26px;padding-top:16px;border-top:1px solid var(--line)}
.sumhist-h{font-size:13px;font-weight:700;color:var(--ink-soft);
 margin-bottom:8px;display:flex;align-items:center;gap:8px}
.sumhist-h .nstat{font-weight:600;color:var(--muted);font-size:12px}
.sumver{border:1px solid var(--line);border-radius:10px;margin-bottom:8px;
 background:var(--card)}
.sumver>summary{cursor:pointer;padding:9px 13px;font-size:13px;font-weight:600;
 color:var(--ink-soft);list-style:none}
.sumver>summary::-webkit-details-marker{display:none}
.sumver>summary::before{content:'\25B8';margin-right:8px;color:var(--muted)}
.sumver[open]>summary::before{content:'\25BE'}
.sumver>summary:hover{color:var(--amber-ink)}
.sumver[open]>summary{border-bottom:1px solid var(--line-soft)}
.sumver .smdbox{padding:4px 16px 14px}
.dimg{cursor:zoom-in;display:block}
.dimg svg{display:block}
.dhint{font-size:10.5px;color:#a0aec0;margin-top:3px}
.bdmask{display:none;position:fixed;inset:0;z-index:10000;
 background:rgba(0,0,0,.55);align-items:center;justify-content:center;padding:18px}
.bdmask.open{display:flex}
.bdbox{background:#fff;border-radius:12px;max-width:640px;width:100%;
 max-height:92vh;overflow:auto;padding:18px 20px;position:relative;
 box-shadow:0 10px 40px rgba(0,0,0,.3)}
.bdclose{position:absolute;top:8px;right:12px;border:none;background:transparent;
 font-size:26px;line-height:1;cursor:pointer;color:#718096}
.bdtitle{font-size:15px;font-weight:700;margin:0 30px 8px 0}
.bdtogs{display:flex;gap:16px;margin-bottom:8px;flex-wrap:wrap}
.bdtogs label{font-size:13px;color:#4a5568;cursor:pointer;user-select:none}
.bdtogs input{vertical-align:middle;margin-right:5px}
.bdbody{text-align:center}
.bdbody svg{max-width:560px !important;width:100% !important;height:auto}
.bdinfo{font-size:12.5px;color:#2d3748;margin-top:10px;line-height:1.55;
 background:#f7fafc;border-radius:6px;padding:8px 10px;text-align:left}
.bdest{display:none;font-size:13px;font-weight:600;color:#1a202c;
 margin:2px 0 8px;text-align:center}
.bdconn{display:none;font-size:13.5px;color:#1a202c;margin:2px 0 8px;
 text-align:center;background:#ebf3fb;border:1px solid #cfe0f2;
 border-radius:6px;padding:7px 10px;line-height:1.5}
.bdconn b{color:#2b6cb0}
.bdconn .bad{color:#c53030;font-weight:700}
.bdbody.connmode svg{cursor:pointer}
"""


def phase_label(k):
    return {"opening": "Fuseki", "middlegame": "Middlegame",
            "endgame": "Yose"}[k]


def source_label_from_path(path):
    """Derive a human-readable player/source label from the output folder name,
    e.g. '.../yehu_3d' -> 'Fox 3 dan', '.../fox_5k' -> 'Fox 5 kyu'."""
    base = os.path.basename((path or "").rstrip("/"))
    plat = "Fox" if re.search(r"yehu|fox|\u91ce\u72d0", base, re.I) else ""
    m = re.search(r"(\d+)\s*d\b", base, re.I)
    rank = f"{m.group(1)} dan" if m else ""
    if not rank:
        m = re.search(r"(\d+)\s*k\b", base, re.I)
        rank = f"{m.group(1)} kyu" if m else ""
    return " ".join(x for x in (plat, rank) if x)


def moves_hist_svg(counts, width=760, height=260, bin_size=20):
    """Histogram of game length (total moves), binned into 20-move buckets."""
    counts = [c for c in counts if c and c > 0]
    if not counts:
        return ""
    pad_l, pad_r, pad_t, pad_b = 46, 14, 40, 46
    lo = (min(counts) // bin_size) * bin_size
    hi = ((max(counts) // bin_size) + 1) * bin_size
    nbins = max(1, (hi - lo) // bin_size)
    bins = [0] * nbins
    for c in counts:
        idx = min(nbins - 1, (c - lo) // bin_size)
        bins[idx] += 1
    ymax = max(bins) if bins else 1
    yscale = (ymax * 1.18) or 1
    avg = sum(counts) / len(counts)

    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bw = plot_w / nbins

    def py(v):
        return pad_t + (1 - v / yscale) * plot_h

    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" '
             f'fill="#1a202c">Game length distribution</text>')
    # y gridlines + labels
    for k in range(5):
        yval = yscale * k / 4
        y = py(yval)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" '
                 f'y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#888">{yval:.0f}</text>')
    p.append(f'<text x="12" y="{pad_t-18}" font-size="10" fill="#888">games</text>')
    # bars
    for i, c in enumerate(bins):
        x = pad_l + i * bw
        y = py(c)
        h = (pad_t + plot_h) - y
        b0 = lo + i * bin_size
        b1 = b0 + bin_size
        tip = f"{b0}-{b1} moves: {c} game(s)"
        p.append(f'<rect x="{x+1.5:.1f}" y="{y:.1f}" width="{bw-3:.1f}" '
                 f'height="{max(0,h):.1f}" fill="#4c6ef5" fill-opacity="0.82" '
                 f'rx="2" data-tip="{esc(tip)}"></rect>')
        if c > 0:
            p.append(f'<text x="{x+bw/2:.1f}" y="{y-4:.1f}" font-size="10" '
                     f'fill="#444" text-anchor="middle">{c}</text>')
        # x tick at left edge of each bar
        p.append(f'<text x="{x:.1f}" y="{height-pad_b+15:.1f}" font-size="9.5" '
                 f'fill="#888" text-anchor="middle">{b0}</text>')
    # final right edge tick
    p.append(f'<text x="{pad_l+plot_w:.1f}" y="{height-pad_b+15:.1f}" '
             f'font-size="9.5" fill="#888" text-anchor="middle">{hi}</text>')
    # average line
    ax = pad_l + ((avg - lo) / (hi - lo)) * plot_w
    ax = max(pad_l, min(pad_l + plot_w, ax))
    p.append(f'<line x1="{ax:.1f}" y1="{pad_t:.1f}" x2="{ax:.1f}" '
             f'y2="{pad_t+plot_h:.1f}" stroke="#e8590c" stroke-width="1.6" '
             f'stroke-dasharray="5 4"/>')
    p.append(f'<text x="{ax+4:.1f}" y="{pad_t+12:.1f}" font-size="10" '
             f'fill="#e8590c" font-weight="700">mean {avg:.0f}</text>')
    p.append(f'<text x="{pad_l}" y="{height-8}" font-size="10" fill="#888">'
             f'x-axis: total moves per game ({bin_size} moves per bin)</text>')
    p.append("</svg>")
    return "".join(p)


def metric_hist_svg(values, title, bin_size, x_note, thresh=None,
                    thresh_label=None, cap=None, pct=False, color="#4c6ef5",
                    width=760, height=260):
    """Move-level distribution histogram of a float metric (points lost / winrate
    drop) across every analysed move.  `cap` clamps a long tail into an overflow
    bin; `thresh` draws the blunder threshold line.  y-axis counts moves."""
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    mean = sum(vals) / len(vals)
    if cap is not None:
        vals = [min(v, cap) for v in vals]
        hi = cap
    else:
        hi = (int(max(vals) / bin_size) + 1) * bin_size
    lo = 0.0
    nbins = max(1, int((hi - lo) / bin_size + 0.5))
    bins = [0] * nbins
    for v in vals:
        idx = int((v - lo) / bin_size)
        if idx < 0:
            idx = 0
        if idx >= nbins:
            idx = nbins - 1
        bins[idx] += 1
    ymax = max(bins) or 1
    yscale = ymax * 1.18 or 1
    pad_l, pad_r, pad_t, pad_b = 46, 14, 40, 46
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    bw = plot_w / nbins

    def fmt(v):
        s = f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}"
        return s + ("%" if pct else "")

    def py(v):
        return pad_t + (1 - v / yscale) * plot_h

    def px(v):  # value -> x
        x = pad_l + ((v - lo) / (hi - lo)) * plot_w
        return max(pad_l, min(pad_l + plot_w, x))

    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="xMidYMid meet" '
         f'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">']
    p.append(f'<text x="{pad_l}" y="20" font-size="14" font-weight="700" '
             f'fill="#1a202c">{esc(title)}</text>')
    for k in range(5):
        yval = yscale * k / 4
        y = py(yval)
        p.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" '
                 f'y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{pad_l-6}" y="{y+3:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#888">{yval:.0f}</text>')
    p.append(f'<text x="12" y="{pad_t-18}" font-size="10" fill="#888">moves</text>')
    # frequency-polygon / area curve through the bin centres
    base = pad_t + plot_h
    pts = [(pad_l + (i + 0.5) * bw, py(bins[i])) for i in range(nbins)]
    area = (f"M {pts[0][0]:.1f},{base:.1f} "
            + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts)
            + f" L {pts[-1][0]:.1f},{base:.1f} Z")
    p.append(f'<path d="{area}" fill="{color}" fill-opacity="0.16"/>')
    p.append('<path d="M ' + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
             + f'" fill="none" stroke="{color}" stroke-width="2" '
             f'stroke-linejoin="round"/>')
    # x ticks
    step = max(1, nbins // 10)
    for i in range(0, nbins + 1, step):
        xx = pad_l + i * bw
        p.append(f'<text x="{xx:.1f}" y="{height-pad_b+15:.1f}" font-size="9" '
                 f'fill="#888" text-anchor="middle">{fmt(lo + i * bin_size)}</text>')
    p.append(f'<text x="{pad_l+plot_w:.1f}" y="{height-pad_b+15:.1f}" '
             f'font-size="9" fill="#888" text-anchor="middle">'
             f'{fmt(hi)}{"+" if cap is not None else ""}</text>')
    # threshold line (the blunder line)
    if thresh is not None and lo <= thresh <= hi:
        tx = px(thresh)
        p.append(f'<line x1="{tx:.1f}" y1="{pad_t:.1f}" x2="{tx:.1f}" '
                 f'y2="{pad_t+plot_h:.1f}" stroke="#e03131" stroke-width="1.4" '
                 f'stroke-dasharray="4 3"/>')
        if thresh_label:
            p.append(f'<text x="{tx+4:.1f}" y="{pad_t+24:.1f}" font-size="10" '
                     f'fill="#e03131" font-weight="700">{esc(thresh_label)}</text>')
    # mean line
    mx = px(mean)
    p.append(f'<line x1="{mx:.1f}" y1="{pad_t:.1f}" x2="{mx:.1f}" '
             f'y2="{pad_t+plot_h:.1f}" stroke="#e8590c" stroke-width="1.6" '
             f'stroke-dasharray="5 4"/>')
    p.append(f'<text x="{mx+4:.1f}" y="{pad_t+12:.1f}" font-size="10" '
             f'fill="#e8590c" font-weight="700">mean {fmt(mean)}</text>')
    p.append(f'<text x="{pad_l}" y="{height-8}" font-size="10" fill="#888">'
             f'{esc(x_note)}</text>')
    p.append("</svg>")
    return "".join(p)


# ---- improvement metric ----------------------------------------------------
def _window_apl(games):
    """Pooled average points lost per user move over a set of games."""
    loss, cnt = 0.0, 0
    for g in games:
        for m in g.get("all_user_moves", []):
            cnt += 1
            loss += (m.get("points_lost", 0) or 0)
    return (loss / cnt) if cnt else None


def improvement_metric(chron):
    """Compare the most-recent block of games to the block before it on points
    lost per move (lower = stronger). chron is oldest->newest. Returns a dict
    or None when there are too few games / moves."""
    g = len(chron)
    if g < 6:
        return None
    n = min(10, g // 2)
    recent = chron[-n:]
    earlier = chron[-2 * n:-n]
    r = _window_apl(recent)
    e = _window_apl(earlier)
    if r is None or e is None or e == 0:
        return None
    delta = r - e
    pct = delta / e * 100
    if pct <= -10:
        verdict = "good"
    elif pct >= 10:
        verdict = "bad"
    else:
        verdict = "flat"
    return {"n": n, "recent": r, "earlier": e, "delta": delta,
            "pct": pct, "verdict": verdict}


def _improve_banner_html(chron):
    m = improvement_metric(chron)
    if not m:
        return ("<div class='improve imp-na' id='homeImprove'>"
                "<div class='impl'>Improvement trend</div>"
                "<div class='impv'>Too few games to judge yet</div>"
                "<div class='impd'>Once you have 6 or more games, this compares the "
                "average points lost per move in your recent games against the "
                "batch before them, and calls it improving / flat / slipping."
                "</div></div>")
    cls = {"good": "imp-good", "bad": "imp-bad", "flat": "imp-flat"}[m["verdict"]]
    title = {"good": "Improving", "bad": "Slipping",
             "flat": "Roughly flat"}[m["verdict"]]
    ar = {"good": "▼", "bad": "▲", "flat": "→"}[m["verdict"]]
    direction = "down" if m["delta"] < 0 else ("up" if m["delta"] > 0 else "flat")
    less_more = "losing" if m["delta"] < 0 else "losing an extra"
    pcttxt = f"{abs(m['pct']):.0f}%"
    desc = (f"Your last {m['n']} games lose <b>{m['recent']:.2f}</b> pts per move, "
            f"{direction} {pcttxt} from <b>{m['earlier']:.2f}</b> pts in the "
            f"{m['n']} games before them ({less_more} {abs(m['delta']):.2f} "
            f"pts/move). The lower the loss per move, the steadier your play.")
    return (f"<div class='improve {cls}' id='homeImprove'>"
            f"<div class='impl'>Improvement trend &middot; avg points lost per move</div>"
            f"<div class='impv'><span class='ar'>{ar}</span>{title}"
            f"<span class='pct'>{pcttxt}</span></div>"
            f"<div class='impd'>{desc}</div></div>")


def _home_page(agg, chron=None):
    record = f"{agg['wins']}–{agg['losses']}"
    src = agg.get("source_label", "")
    src_html = (f" &middot; project <b>{esc(src)}</b>" if src else "")
    p = [f"<h1>KataGo Game Review</h1>",
         f"<p class='sub'>Generated {esc(datetime.date.today().isoformat())} "
         f"&middot; {agg['n']} games &middot; {agg['n_user_moves']} of your moves analysed"
         f"{src_html}</p>",
         "<div class='ovctl'><label class='exw'>"
         "<input type='checkbox' id='exWorst'> Exclude the worst game (outlier)"
         "</label><span class='exwnote' id='exWorstNote'></span></div>",
         "<div class='cards' id='homeCards'>"]
    for v, l in ((record, "Win - Loss"),
                 (agg["avg_points_lost"], "Avg points lost per move"),
                 (f"{agg['blunder_rate']}%", "Blunder rate (&ge;6 pts or WR &minus;15%)"),
                 (agg["n_blunders"], "Total blunders"),
                 (agg.get("avg_moves", 0), "Avg moves per game")):
        p.append(f"<div class='card'><div class='v'>{v}</div>"
                 f"<div class='l'>{l}</div></div>")
    p.append("</div>")
    p.append("<p class='sub'>Use the sidebar to open the other sections: "
             "the blunder set and the game-by-game review.</p>")
    return "".join(p)


def _moves_hist_section(agg, games=None):
    games = games or []
    pl, wl = [], []
    for g in games:
        for m in g.get("all_user_moves", []):
            pl.append(m.get("points_lost", 0) or 0)
            wl.append((m.get("winrate_lost", 0) or 0) * 100)
    apl_hist = metric_hist_svg(
        pl, "Points lost per move (distribution)", 0.5,
        "x-axis: points lost on a single move (0.5-pt bins, 15+ pooled); "
        "the red dashed line is the 6-pt blunder line",
        thresh=6, thresh_label="blunder line 6 pts", cap=15, color="#4c6ef5")
    wl_hist = metric_hist_svg(
        wl, "Win-rate lost per move (distribution)", 2.5,
        "x-axis: win-rate drop on a single move (2.5% bins, 50%+ pooled); "
        "the red dashed line is the 15% blunder line",
        thresh=15, thresh_label="blunder line 15%", cap=50, pct=True, color="#7048e8")
    moves = moves_hist_svg(agg.get("moves_counts", []))
    # Wrapped with ids so the date-range filter / exclude-worst toggle can re-render.
    return ("<div class='chartbox' id='homeHistApl'>" + (apl_hist or "") + "</div>"
            "<div class='chartbox' id='homeHistWr'>" + (wl_hist or "") + "</div>"
            "<div class='chartbox' id='homeHist'>" + (moves or "") + "</div>")


def _recs_page(recs):
    p = ["<h2>What to work on</h2>"]
    for r in recs:
        p.append(f"<div class='rec'>{esc(r)}</div>")
    return "".join(p)


def _blunders_page(games, agg):
    gmap = {g["filename"]: g for g in games}
    p = ["<h2>Biggest mistakes across all games</h2>",
         "<table><tr><th>Points lost</th><th>Move</th><th>You played</th>"
         "<th>KataGo</th><th>Phase</th><th>Game</th><th>Board</th></tr>"]
    for k, m in enumerate(agg["top_blunders"]):
        p.append(f"<tr><td class='big'>{m['points_lost']}</td>"
                 f"<td class='mv'>#{m['move_number']}</td>"
                 f"<td class='mv'>{esc(m['played'])}</td>"
                 f"<td class='mv'>{esc(m.get('best'))}</td>"
                 f"<td>{esc(PHASE_LABEL.get(m['phase'], m['phase']))}</td>"
                 f"<td>{esc(m.get('date',''))} vs "
                 f"{esc(m.get('opponent',''))}</td>"
                 f"<td><button class='fbbtn' onclick=\"var r="
                 f"document.getElementById('fbrow-{k}');"
                 f"var s=r.style.display==='none';"
                 f"r.style.display=s?'':'none';"
                 f"this.textContent=s?'Hide':'Show full board';\">"
                 f"Show full board</button></td></tr>")
        g = gmap.get(m.get("game"))
        if g is not None and g.get("moves"):
            board_svg = full_board_svg(g, m, f"fb{k}")
            mvcb = (f"<label class='fbtog'><input type='checkbox' checked "
                    f"onchange=\"document.getElementById('fb{k}-mv')"
                    f".style.display=this.checked?'':'none'\"> Your move</label>")
            aicb = (f"<label class='fbtog'><input type='checkbox' checked "
                    f"onchange=\"document.getElementById('fb{k}-ai')"
                    f".style.display=this.checked?'':'none'\"> AI recommended line</label>")
            panel = (f"<div class='fbpanel'><div class='fbtogs'>"
                     f"{mvcb}{aicb}</div>{board_svg}</div>")
        else:
            panel = ("<div class='fbpanel'>(Cannot show the full board -- "
                     "re-run the analysis.)</div>")
        p.append(f"<tr class='fbrow' id='fbrow-{k}' style='display:none'>"
                 f"<td colspan='7'>{panel}</td></tr>")
    p.append("</table>")
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


def _game_recency_key(g):
    """Sort key for "newest first": the trailing chess-id in the SGF filename
    (a globally increasing number on Fox) is the most reliable recency signal;
    fall back to the parsed date when no id is present."""
    fn = g.get("filename", "") or ""
    nums = re.findall(r"\d{6,}", fn)
    cid = int(nums[-1]) if nums else 0
    return (date_key(g), cid)


def _games_page(games):
    p = ["<h2>Game by game</h2>",
         "<p class='sub'>Newest game first. Use the filters below to narrow it down.</p>",
         "<div class='navbar'>",
         "<div class='navrow'><span class='navlbl'>Result</span>"
         "<button class='navbtn on' data-fr='all'>All</button>"
         "<button class='navbtn' data-fr='win'>Win</button>"
         "<button class='navbtn' data-fr='loss'>Loss</button></div>",
         "<div class='navrow'><span class='navlbl'>Colour</span>"
         "<button class='navbtn on' data-fc='all'>All</button>"
         "<button class='navbtn' data-fc='B'>Black</button>"
         "<button class='navbtn' data-fc='W'>White</button></div>",
         "<div class='navrow'><span class='navlbl'>Blunders</span>"
         "<button class='navbtn on' data-fb='0'>All</button>"
         "<button class='navbtn' data-fb='1'>&ge; 1</button>"
         "<button class='navbtn' data-fb='3'>&ge; 3</button>"
         "<button class='navbtn' data-fb='5'>&ge; 5</button></div>",
         "<div class='navrow'><span class='navlbl'>Avg loss</span>"
         "<button class='navbtn on' data-fa='0'>All</button>"
         "<button class='navbtn' data-fa='2'>&ge; 2 pts</button>"
         "<button class='navbtn' data-fa='3'>&ge; 3 pts</button>"
         "<button class='navbtn' data-fa='4'>&ge; 4 pts</button></div>",
         "</div>",
         "<div class='flcount' id='gmcount'></div>"]
    fbk = 0  # page-wide unique id for the expandable full-board rows
    for gi, g in enumerate(sorted(games, key=_game_recency_key, reverse=True)):
        wl = g.get("won")
        wl_html = ("<span class='win'>Win</span>" if wl is True else
                   "<span class='loss'>Loss</span>" if wl is False else "")
        res = "win" if wl is True else "loss" if wl is False else "na"
        try:
            avg = float(g.get("avg_points_lost") or 0)
        except (TypeError, ValueError):
            avg = 0.0
        _gd = parse_date(g)
        _gd = _gd.isoformat() if _gd else ""
        p.append(f"<div class='game' data-result='{res}' "
                 f"data-date='{_gd}' "
                 f"data-color='{g.get('user_color','')}' "
                 f"data-blunders='{blunder_count(g)}' "
                 f"data-avg='{avg:.2f}'>")
        p.append(f"<h3>{esc(g.get('date',''))} &mdash; vs {esc(g.get('opponent',''))} "
                 f"{wl_html} <span class='pill'>You: "
                 f"{'Black' if g['user_color']=='B' else 'White'}</span> "
                 f"<span class='pill'>{esc(g.get('result',''))}</span></h3>")
        pa = g.get("avg_points_lost_by_phase", {})
        p.append(f"<p class='sub'>Avg points lost per move: "
                 f"{g.get('avg_points_lost')} (fuseki {pa.get('opening',0)}, "
                 f"middlegame {pa.get('middlegame',0)}, yose "
                 f"{pa.get('endgame',0)}) &middot; {blunder_count(g)} blunders</p>")
        p.append(score_svg(g))
        p.append(final_score_html(g, f"fs{gi}"))
        mistakes = g.get("biggest_mistakes", [])
        if mistakes:
            p.append("<table><tr><th>Points lost</th><th>Move</th>"
                     "<th>You played</th><th>KataGo played</th>"
                     "<th>Recommended line</th><th></th></tr>")
            for m in mistakes:
                cls = "big" if m["points_lost"] >= PTS_BLUNDER else ""
                k = fbk
                fbk += 1
                btn = (f"<button class='fbbtn' onclick=\"var r="
                       f"document.getElementById('gmrow-{k}');"
                       f"var s=r.style.display==='none';"
                       f"r.style.display=s?'':'none';"
                       f"this.textContent=s?'Hide full position':'View full position';\">"
                       f"View full position</button>")
                p.append(f"<tr><td class='{cls}'>{m['points_lost']}</td>"
                         f"<td class='mv'>#{m['move_number']}</td>"
                         f"<td class='mv'>{esc(m['played'])}</td>"
                         f"<td class='mv'>{esc(m.get('best'))}</td>"
                         f"<td class='mv'>{esc(m.get('best_pv',''))}</td>"
                         f"<td>{btn}</td></tr>")
                # Expandable full-board row: actual move + AI line, toggleable.
                if g.get("moves"):
                    bsvg = full_board_svg(g, m, f"gm{k}")
                    mvcb = (f"<label class='fbtog'><input type='checkbox' checked "
                            f"onchange=\"document.getElementById('gm{k}-mv')"
                            f".style.display=this.checked?'':'none'\"> "
                            f"<span style='color:#e02424'>&#9632;</span> "
                            f"The move you played</label>")
                    aicb = (f"<label class='fbtog'><input type='checkbox' checked "
                            f"onchange=\"document.getElementById('gm{k}-ai')"
                            f".style.display=this.checked?'':'none'\"> "
                            f"<span style='color:#1f9d55'>&#9679;</span> "
                            f"AI recommendation (numbered continuation)</label>")
                    panel = (f"<div class='fbpanel'><div class='fbtogs'>"
                             f"{mvcb}{aicb}</div>{bsvg}</div>")
                else:
                    panel = ("<div class='fbpanel'>(Cannot show the full board -- "
                             "re-run the analysis.)</div>")
                p.append(f"<tr class='fbrow' id='gmrow-{k}' style='display:none'>"
                         f"<td colspan='6'>{panel}</td></tr>")
            p.append("</table>")
        p.append("</div>")
    p.append(GAMES_JS)
    return "".join(p)


GAMES_JS = """
<script>
(function(){
  var fr='all', fc='all', fb=0, fa=0;
  function apply(){
    var shown=0;
    document.querySelectorAll('#page-games .game').forEach(function(d){
      var okr = fr==='all' || d.getAttribute('data-result')===fr;
      var okc = fc==='all' || d.getAttribute('data-color')===fc;
      var okb = parseInt(d.getAttribute('data-blunders')||'0',10) >= fb;
      var oka = parseFloat(d.getAttribute('data-avg')||'0') >= fa;
      var okdt = (window.GR ? GR.inRange(d.getAttribute('data-date')) : true);
      var vis = okr && okc && okb && oka && okdt;
      d.style.display = vis ? '' : 'none';
      if(vis) shown++;
    });
    var el=document.getElementById('gmcount');
    if(el) el.textContent='Showing '+shown+' game(s)';
  }
  function wire(attr, set){
    document.querySelectorAll('#page-games .navbtn['+attr+']').forEach(function(b){
      b.addEventListener('click', function(){
        set(b.getAttribute(attr));
        document.querySelectorAll('#page-games .navbtn['+attr+']').forEach(
          function(x){ x.classList.toggle('on', x===b); });
        apply();
      });
    });
  }
  wire('data-fr', function(v){ fr=v; });
  wire('data-fc', function(v){ fc=v; });
  wire('data-fb', function(v){ fb=parseInt(v,10); });
  wire('data-fa', function(v){ fa=parseFloat(v); });
  apply();
  document.addEventListener('grdate', apply);
})();
</script>
"""


TOOLTIP_JS = """
<div id="tipbox"></div>
<script>
(function(){
  var box=document.getElementById('tipbox');
  function move(e){
    box.style.left=(e.clientX+12)+'px';
    box.style.top=(e.clientY+12)+'px';
  }
  document.addEventListener('mouseover', function(e){
    var t=e.target;
    if(t && t.classList && t.classList.contains('pt')){
      box.textContent=t.getAttribute('data-tip')||'';
      box.style.display='block';
      move(e);
    }
  });
  document.addEventListener('mousemove', function(e){
    if(box.style.display==='block') move(e);
  });
  document.addEventListener('mouseout', function(e){
    if(e.target && e.target.classList && e.target.classList.contains('pt')){
      box.style.display='none';
    }
  });
})();
</script>
"""


def _date_filter_js(chron):
    """The global GR module: shared date-range state, synced date bars, and a
    full client-side recompute of the overview cards / 4 trend charts /
    histogram for the selected range (JS ports of trend_chart & moves_hist)."""
    data = _games_data_js(chron)
    meta = json.dumps({
        "phases": PHASES,
        "labels": [PHASE_LABEL[p] for p in PHASES],
        "colors": [PHASE_COLOR[p] for p in PHASES],
    }, ensure_ascii=False, separators=(",", ":"))
    js = r"""
<script>
(function(){
  var GAMES = __GAMES__;       // oldest -> newest
  var META  = __META__;
  var GR = window.GR = window.GR || {};
  GR.games = GAMES;
  GR.range = {from:null, to:null};

  function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

  GR.inRange = function(d){
    if(!d) return !(GR.range.from || GR.range.to);   // undated: only when "All"
    if(GR.range.from && d < GR.range.from) return false;
    if(GR.range.to   && d > GR.range.to)   return false;
    return true;
  };
  function syncInputs(){
    document.querySelectorAll('.dffrom').forEach(function(e){
      e.value = GR.range.from || '';});
    document.querySelectorAll('.dfto').forEach(function(e){
      e.value = GR.range.to || '';});
  }
  function markPreset(days){
    document.querySelectorAll('.dfp').forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-days') === days);});
  }
  function fire(){ document.dispatchEvent(new CustomEvent('grdate')); }

  GR.setRange = function(f,t){
    GR.range.from = f || null; GR.range.to = t || null;
    syncInputs(); fire();
  };
  GR.manual = function(el){
    var bar = el.closest('.datebar');
    var f = bar.querySelector('.dffrom').value;
    var t = bar.querySelector('.dfto').value;
    GR.range.from = f || null; GR.range.to = t || null;
    syncInputs();
    markPreset(null);                       // manual edit clears preset highlight
    fire();
  };
  GR.preset = function(days, btn){
    if(days === null){ GR.range.from = null; GR.range.to = null; markPreset('all'); }
    else {
      var to = new Date();
      var from = new Date(); from.setDate(from.getDate() - days);
      function iso(x){ return x.toISOString().slice(0,10); }
      GR.range.from = iso(from); GR.range.to = iso(to);
      markPreset(String(days));
    }
    syncInputs(); fire();
  };
  GR.filtered = function(){
    return GAMES.filter(function(g){ return GR.inRange(g.d); });
  };

  // ---- overview recompute (cards + charts + histogram) ---------------------
  function pooled(fg){
    var st = {}; META.phases.forEach(function(p){
      st[p] = {cnt:0, loss:0, nbp:0, nbw:0, nbe:0}; });
    fg.forEach(function(g){
      META.phases.forEach(function(p){
        var a = g.p[p]; st[p].cnt += a[0]; st[p].loss += a[1];
        st[p].nbp += a[2]; st[p].nbw += a[3]; st[p].nbe += (a[4]||0);
      });
    });
    return st;
  }
  function renderCards(fg){
    var el = document.getElementById('homeCards'); if(!el) return;
    var wins=0, losses=0;
    fg.forEach(function(g){ if(g.w===1) wins++; else if(g.w===0) losses++; });
    var o = pooled(fg).overall;
    var apl = o.cnt ? (o.loss/o.cnt) : 0;
    var brate = o.cnt ? (o.nbe/o.cnt*100) : 0;
    var mvSum=0, mvCnt=0;
    fg.forEach(function(g){ mvSum += g.mv; mvCnt++; });
    var amoves = mvCnt ? Math.round(mvSum/mvCnt) : 0;
    var rows = [
      [wins+'\u2013'+losses, 'Win \u2013 Loss'],
      [apl.toFixed(2), 'Avg points lost per move'],
      [brate.toFixed(1)+'%', 'Blunder rate (\u22656 pts or WR \u221215%)'],
      [String(o.nbe), 'Total blunders'],
      [String(amoves), 'Avg moves per game'],
    ];
    el.innerHTML = rows.map(function(r){
      return "<div class='card'><div class='v'>"+esc(r[0])+
             "</div><div class='l'>"+esc(r[1])+"</div></div>"; }).join('');
  }

  function trendChartSVG(title, labels, series, ylabel, tips, avgOv){
    var W=760, H=250, pl=46, pr=14, pt=54, pb=50;
    var n=labels.length;
    var allv=[]; series.forEach(function(s){ s[2].forEach(function(v){
      if(v!==null && v!==undefined) allv.push(v); }); });
    var mx = allv.length ? Math.max.apply(null, allv) : 0;
    var ymax = (allv.length && mx>0) ? mx*1.18 : 1.0;
    function px(i){ return n<=1 ? (pl+W-pr)/2 : pl + i*(W-pl-pr)/(n-1); }
    function py(v){ return pt + (1 - v/ymax)*(H-pt-pb); }
    var p=['<svg viewBox="0 0 '+W+' '+H+'" width="100%" '+
      'preserveAspectRatio="xMidYMid meet" '+
      'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">'];
    p.push('<text x="'+pl+'" y="20" font-size="14" font-weight="700" '+
      'fill="#1a202c">'+esc(title)+'</text>');
    // phase-mean row (top-right)
    var entryW=74, rowW=44+entryW*series.length;
    var ax=Math.max(pl, W-pr-rowW), ay=20;
    p.push('<text x="'+ax.toFixed(1)+'" y="'+ay+'" font-size="9.5" fill="#aaa" '+
      'font-weight="600">phase mean</text>');
    ax+=44;
    series.forEach(function(s,si){
      p.push('<circle cx="'+(ax+3).toFixed(1)+'" cy="'+(ay-3).toFixed(1)+
        '" r="3" fill="'+s[1]+'"/>');
      p.push('<text x="'+(ax+11).toFixed(1)+'" y="'+ay+'" font-size="10" '+
        'fill="#444">'+esc(s[0])+' '+esc(avgOv[si])+'</text>');
      ax+=entryW;
    });
    for(var k=0;k<5;k++){
      var yval=ymax*k/4, y=py(yval);
      p.push('<line x1="'+pl+'" y1="'+y.toFixed(1)+'" x2="'+(W-pr)+'" y2="'+
        y.toFixed(1)+'" stroke="#eee"/>');
      p.push('<text x="'+(pl-6)+'" y="'+(y+3).toFixed(1)+'" font-size="10" '+
        'text-anchor="end" fill="#888">'+yval.toFixed(1)+'</text>');
    }
    p.push('<text x="12" y="'+(pt-30)+'" font-size="10" fill="#888">'+
      esc(ylabel)+'</text>');
    var step=Math.max(1, Math.floor(n/12));
    for(var i=0;i<n;i+=step){
      p.push('<text x="'+px(i).toFixed(1)+'" y="'+(H-pb+16).toFixed(1)+
        '" font-size="10" fill="#888" text-anchor="middle">'+esc(labels[i])+
        '</text>');
    }
    series.forEach(function(s,si){
      p.push('<g class="tser" data-si="'+si+'">');
      var seg=[];
      function flush(){ if(seg.length>=2){
        p.push('<polyline fill="none" stroke="'+s[1]+'" stroke-width="2" '+
          'points="'+seg.map(function(q){return q[0].toFixed(1)+','+
          q[1].toFixed(1);}).join(' ')+'"/>'); } seg=[]; }
      s[2].forEach(function(v,ii){
        if(v===null||v===undefined){ flush(); } else { seg.push([px(ii),py(v)]); }
      });
      flush();
      s[2].forEach(function(v,ii){
        if(v===null||v===undefined) return;
        p.push('<circle cx="'+px(ii).toFixed(1)+'" cy="'+py(v).toFixed(1)+
          '" r="2.6" fill="'+s[1]+'"/>');
        var tip=s[0]+' \u00b7 '+tips[ii]+': '+v;
        p.push('<circle class="pt" cx="'+px(ii).toFixed(1)+'" cy="'+
          py(v).toFixed(1)+'" r="9" fill="transparent" data-tip="'+esc(tip)+
          '"></circle>');
      });
      p.push('</g>');
    });
    var lx=pl, ly=H-8;
    series.forEach(function(s,si){
      var w=20+s[0].length*6.6;
      p.push('<g class="tleg" data-si="'+si+'" onclick="toggleSeries(this)" '+
        'style="cursor:pointer">');
      p.push('<rect x="'+(lx-2).toFixed(1)+'" y="'+(ly-11).toFixed(1)+
        '" width="'+w.toFixed(1)+'" height="16" fill="transparent"/>');
      p.push('<line x1="'+lx+'" y1="'+(ly-4)+'" x2="'+(lx+16)+'" y2="'+(ly-4)+
        '" stroke="'+s[1]+'" stroke-width="2.5"/>');
      p.push('<text x="'+(lx+20)+'" y="'+ly+'" font-size="10" fill="#444">'+
        esc(s[0])+'</text>');
      p.push('</g>');
      lx += 26 + s[0].length*6.4;
    });
    p.push('</svg>');
    return p.join('');
  }

  function movesHistSVG(counts){
    counts = counts.filter(function(c){ return c && c>0; });
    if(!counts.length) return '';
    var W=760,H=260,bin=20,pl=46,pr=14,pt=40,pb=46;
    var mn=Math.min.apply(null,counts), mxc=Math.max.apply(null,counts);
    var lo=Math.floor(mn/bin)*bin, hi=(Math.floor(mxc/bin)+1)*bin;
    var nbins=Math.max(1,Math.floor((hi-lo)/bin));
    var bins=[]; for(var b=0;b<nbins;b++) bins.push(0);
    counts.forEach(function(c){
      var idx=Math.min(nbins-1, Math.floor((c-lo)/bin)); bins[idx]++; });
    var ymax=Math.max.apply(null,bins)||1, yscale=(ymax*1.18)||1;
    var avg=counts.reduce(function(a,b){return a+b;},0)/counts.length;
    var plotW=W-pl-pr, plotH=H-pt-pb, bw=plotW/nbins;
    function py(v){ return pt + (1 - v/yscale)*plotH; }
    var p=['<svg viewBox="0 0 '+W+' '+H+'" width="100%" '+
      'preserveAspectRatio="xMidYMid meet" '+
      'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">'];
    p.push('<text x="'+pl+'" y="20" font-size="14" font-weight="700" '+
      'fill="#1a202c">Game length distribution</text>');
    for(var k=0;k<5;k++){
      var yval=yscale*k/4, y=py(yval);
      p.push('<line x1="'+pl+'" y1="'+y.toFixed(1)+'" x2="'+(W-pr)+'" y2="'+
        y.toFixed(1)+'" stroke="#eee"/>');
      p.push('<text x="'+(pl-6)+'" y="'+(y+3).toFixed(1)+'" font-size="10" '+
        'text-anchor="end" fill="#888">'+yval.toFixed(0)+'</text>');
    }
    p.push('<text x="12" y="'+(pt-18)+'" font-size="10" fill="#888">games</text>');
    bins.forEach(function(c,i){
      var x=pl+i*bw, y=py(c), h=(pt+plotH)-y, b0=lo+i*bin, b1=b0+bin;
      var tip=b0+'\u2013'+b1+' moves: '+c+' game(s)';
      p.push('<rect x="'+(x+1.5).toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+
        (bw-3).toFixed(1)+'" height="'+Math.max(0,h).toFixed(1)+
        '" fill="#4c6ef5" fill-opacity="0.82" rx="2" data-tip="'+esc(tip)+
        '"></rect>');
      if(c>0) p.push('<text x="'+(x+bw/2).toFixed(1)+'" y="'+(y-4).toFixed(1)+
        '" font-size="10" fill="#444" text-anchor="middle">'+c+'</text>');
      p.push('<text x="'+x.toFixed(1)+'" y="'+(H-pb+15).toFixed(1)+
        '" font-size="9.5" fill="#888" text-anchor="middle">'+b0+'</text>');
    });
    p.push('<text x="'+(pl+plotW).toFixed(1)+'" y="'+(H-pb+15).toFixed(1)+
      '" font-size="9.5" fill="#888" text-anchor="middle">'+hi+'</text>');
    var axp=pl+((avg-lo)/(hi-lo))*plotW;
    axp=Math.max(pl, Math.min(pl+plotW, axp));
    p.push('<line x1="'+axp.toFixed(1)+'" y1="'+pt.toFixed(1)+'" x2="'+
      axp.toFixed(1)+'" y2="'+(pt+plotH).toFixed(1)+
      '" stroke="#e8590c" stroke-width="1.6" stroke-dasharray="5 4"/>');
    p.push('<text x="'+(axp+4).toFixed(1)+'" y="'+(pt+12).toFixed(1)+
      '" font-size="10" fill="#e8590c" font-weight="700">mean '+
      avg.toFixed(0)+'</text>');
    p.push('<text x="'+pl+'" y="'+(H-8)+'" font-size="10" fill="#888">'+
      'x-axis: total moves per game ('+
      bin+' moves per bin)</text>');
    p.push('</svg>');
    return p.join('');
  }

  function distHistSVG(values, title, bin, xNote, thresh, threshLabel, cap, pct, color){
    var vals=values.filter(function(v){return v!==null&&v!==undefined;});
    if(!vals.length) return '';
    var mean=vals.reduce(function(a,b){return a+b;},0)/vals.length;
    var hi;
    if(cap!=null){ vals=vals.map(function(v){return Math.min(v,cap);}); hi=cap; }
    else { hi=(Math.floor(Math.max.apply(null,vals)/bin)+1)*bin; }
    var lo=0, nbins=Math.max(1, Math.round((hi-lo)/bin));
    var bins=[]; for(var b=0;b<nbins;b++) bins.push(0);
    vals.forEach(function(v){ var idx=Math.floor((v-lo)/bin);
      if(idx<0)idx=0; if(idx>=nbins)idx=nbins-1; bins[idx]++; });
    var ymax=Math.max.apply(null,bins)||1, yscale=ymax*1.18||1;
    var W=760,H=260,pl=46,pr=14,pt=40,pb=46;
    var plotW=W-pl-pr, plotH=H-pt-pb, bw=plotW/nbins;
    function fmt(v){ var s=(Math.abs(v-Math.round(v))<1e-9)?v.toFixed(0):v.toFixed(1);
      return s+(pct?'%':''); }
    function py(v){ return pt+(1-v/yscale)*plotH; }
    function px(v){ var x=pl+((v-lo)/(hi-lo))*plotW; return Math.max(pl,Math.min(pl+plotW,x)); }
    var p=['<svg viewBox="0 0 '+W+' '+H+'" width="100%" '+
      'preserveAspectRatio="xMidYMid meet" '+
      'style="background:#fff;border:1px solid #e3e3e3;border-radius:8px">'];
    p.push('<text x="'+pl+'" y="20" font-size="14" font-weight="700" '+
      'fill="#1a202c">'+esc(title)+'</text>');
    for(var k=0;k<5;k++){ var yv=yscale*k/4, y=py(yv);
      p.push('<line x1="'+pl+'" y1="'+y.toFixed(1)+'" x2="'+(W-pr)+'" y2="'+
        y.toFixed(1)+'" stroke="#eee"/>');
      p.push('<text x="'+(pl-6)+'" y="'+(y+3).toFixed(1)+'" font-size="10" '+
        'text-anchor="end" fill="#888">'+yv.toFixed(0)+'</text>'); }
    p.push('<text x="12" y="'+(pt-18)+'" font-size="10" fill="#888">moves</text>');
    var base=pt+plotH;
    var pts=bins.map(function(c,i){ return [pl+(i+0.5)*bw, py(c)]; });
    var area='M '+pts[0][0].toFixed(1)+','+base.toFixed(1)+' '+
      pts.map(function(q){return 'L '+q[0].toFixed(1)+','+q[1].toFixed(1);}).join(' ')+
      ' L '+pts[pts.length-1][0].toFixed(1)+','+base.toFixed(1)+' Z';
    p.push('<path d="'+area+'" fill="'+color+'" fill-opacity="0.16"/>');
    p.push('<path d="M '+pts.map(function(q){return q[0].toFixed(1)+','+q[1].toFixed(1);}).join(' L ')+
      '" fill="none" stroke="'+color+'" stroke-width="2" stroke-linejoin="round"/>');
    var step=Math.max(1, Math.floor(nbins/10));
    for(var t=0;t<=nbins;t+=step){
      p.push('<text x="'+(pl+t*bw).toFixed(1)+'" y="'+(H-pb+15).toFixed(1)+
        '" font-size="9" fill="#888" text-anchor="middle">'+fmt(lo+t*bin)+'</text>'); }
    p.push('<text x="'+(pl+plotW).toFixed(1)+'" y="'+(H-pb+15).toFixed(1)+
      '" font-size="9" fill="#888" text-anchor="middle">'+fmt(hi)+((cap!=null)?'+':'')+'</text>');
    if(thresh!=null && thresh>=lo && thresh<=hi){ var tx=px(thresh);
      p.push('<line x1="'+tx.toFixed(1)+'" y1="'+pt.toFixed(1)+'" x2="'+tx.toFixed(1)+
        '" y2="'+(pt+plotH).toFixed(1)+'" stroke="#e03131" stroke-width="1.4" stroke-dasharray="4 3"/>');
      if(threshLabel) p.push('<text x="'+(tx+4).toFixed(1)+'" y="'+(pt+24).toFixed(1)+
        '" font-size="10" fill="#e03131" font-weight="700">'+esc(threshLabel)+'</text>'); }
    var mx=px(mean);
    p.push('<line x1="'+mx.toFixed(1)+'" y1="'+pt.toFixed(1)+'" x2="'+mx.toFixed(1)+
      '" y2="'+(pt+plotH).toFixed(1)+'" stroke="#e8590c" stroke-width="1.6" stroke-dasharray="5 4"/>');
    p.push('<text x="'+(mx+4).toFixed(1)+'" y="'+(pt+12).toFixed(1)+
      '" font-size="10" fill="#e8590c" font-weight="700">mean '+fmt(mean)+'</text>');
    p.push('<text x="'+pl+'" y="'+(H-8)+'" font-size="10" fill="#888">'+esc(xNote)+'</text>');
    p.push('</svg>');
    return p.join('');
  }

  function renderCharts(fg){
    var box=document.getElementById('homeCharts');
    if(box){
      if(!fg.length){
        box.innerHTML="<p class='sub'>No games in this date range.</p>";
      } else {
        var seq=fg.map(function(_,i){return String(i+1);});
        var tips=fg.map(function(g,i){
          return 'Game '+(i+1)+'  '+(g.d?g.d.slice(5):'?'); });
        function seriesFor(key){
          return META.phases.map(function(p,pi){
            return [META.labels[pi], META.colors[pi],
              fg.map(function(g){
                var a=g.p[p], nn=a[0];
                if(key==='apl')    return nn? (a[1]/nn) : null;
                if(key==='br_pts') return nn? (a[2]/nn*100) : null;
                if(key==='br_wr')  return nn? (a[3]/nn*100) : null;
                if(key==='blunders') return (a[4]||0);
                return null;
              })];
          });
        }
        var st=pooled(fg), ng=Math.max(1,fg.length);
        function ov(metric){
          return META.phases.map(function(p){
            var s=st[p], c=s.cnt;
            if(metric==='apl')    return c? (s.loss/c).toFixed(2) : '—';
            if(metric==='br_pts') return c? (s.nbp/c*100).toFixed(1)+'%' : '—';
            if(metric==='br_wr')  return c? (s.nbw/c*100).toFixed(1)+'%' : '—';
            if(metric==='blunders') return (s.nbe/ng).toFixed(1);
            return '';
          });
        }
        var charts=[
          trendChartSVG('Average points lost per move',
            seq, seriesFor('apl'), 'pts/move', tips, ov('apl')),
          trendChartSVG('Blunder rate \u2014 lost \u2265 6 pts',
            seq, seriesFor('br_pts'), 'share %', tips, ov('br_pts')),
          trendChartSVG('Blunder rate \u2014 win-rate drop \u2265 15%',
            seq, seriesFor('br_wr'), 'share %', tips, ov('br_wr')),
          trendChartSVG('Blunders per game (\u22656 pts or WR \u221215%)',
            seq, seriesFor('blunders'), 'count', tips, ov('blunders')),
        ];
        box.innerHTML=charts.map(function(c){
          return "<div class='chart'>"+c+"</div>"; }).join('');
      }
    }
    var emptyMsg="<p class='sub'>No games to summarise in this date range.</p>";
    // move-level distributions (points lost / winrate drop across every move)
    var plAll=[], wlAll=[];
    fg.forEach(function(g){ (g.pm||[]).forEach(function(m){
      plAll.push(m[0]); wlAll.push(m[1]); }); });
    var hboxA=document.getElementById('homeHistApl');
    if(hboxA) hboxA.innerHTML = distHistSVG(plAll,'Points lost per move (distribution)',0.5,
      'x-axis: points lost on a single move (0.5-pt bins, 15+ pooled); the red dashed line is the 6-pt blunder line',
      6,'blunder line 6 pts',15,false,'#4c6ef5') || emptyMsg;
    var hboxW=document.getElementById('homeHistWr');
    if(hboxW) hboxW.innerHTML = distHistSVG(wlAll,'Win-rate lost per move (distribution)',2.5,
      'x-axis: win-rate drop on a single move (2.5% bins, 50%+ pooled); the red dashed line is the 15% blunder line',
      15,'blunder line 15%',50,true,'#7048e8') || emptyMsg;
    var hbox=document.getElementById('homeHist');
    if(hbox){
      var hist=movesHistSVG(fg.map(function(g){return g.mv;}));
      hbox.innerHTML = hist || emptyMsg;
    }
  }

  // ---- improvement banner recompute (avg points lost per move, recent vs earlier) ----
  function windowApl(games){
    var loss=0, cnt=0;
    games.forEach(function(g){ var o=g.p.overall; cnt+=o[0]; loss+=o[1]; });
    return cnt ? (loss/cnt) : null;
  }
  function renderImprove(fg){
    var el=document.getElementById('homeImprove'); if(!el) return;
    var G=fg.length, m=null;
    if(G>=6){
      var n=Math.min(10, Math.floor(G/2));
      var recent=fg.slice(G-n), earlier=fg.slice(G-2*n, G-n);
      var r=windowApl(recent), e=windowApl(earlier);
      if(r!==null && e!==null && e!==0){
        var delta=r-e, pct=delta/e*100, verdict;
        if(pct<=-10) verdict='good'; else if(pct>=10) verdict='bad';
        else verdict='flat';
        m={n:n, recent:r, earlier:e, delta:delta, pct:pct, verdict:verdict};
      }
    }
    if(!m){
      el.className='improve imp-na';
      el.innerHTML="<div class='impl'>Improvement trend</div>"+
        "<div class='impv'>Too few games to judge yet</div>"+
        "<div class='impd'>Once you have 6 or more games, this compares the average "+
        "points lost per move in your recent games against the batch before them, "+
        "and calls it improving / flat / slipping.</div>";
      return;
    }
    var clsMap={good:'imp-good',bad:'imp-bad',flat:'imp-flat'};
    var titleMap={good:'Improving',bad:'Slipping',flat:'Roughly flat'};
    var arMap={good:'▼',bad:'▲',flat:'→'};
    var direction = m.delta<0 ? 'down' : (m.delta>0 ? 'up' : 'flat');
    var lessMore = m.delta<0 ? 'losing' : 'losing an extra';
    var pcttxt = Math.abs(m.pct).toFixed(0)+'%';
    var desc = 'Your last '+m.n+' games lose <b>'+m.recent.toFixed(2)+'</b> pts per move, '+
      direction+' '+pcttxt+' from <b>'+m.earlier.toFixed(2)+'</b> pts in the '+m.n+
      ' games before them ('+lessMore+' '+Math.abs(m.delta).toFixed(2)+
      ' pts/move). The lower the loss per move, the steadier your play.';
    el.className='improve '+clsMap[m.verdict];
    el.innerHTML="<div class='impl'>Improvement trend \u00B7 avg points lost per move</div>"+
      "<div class='impv'><span class='ar'>"+arMap[m.verdict]+"</span>"+
      titleMap[m.verdict]+"<span class='pct'>"+pcttxt+"</span></div>"+
      "<div class='impd'>"+desc+"</div>";
  }

  // Drop the "worst game" -- the one with the highest avg points lost per move --
  // so a single collapse does not drag the averages up.
  function gApl(g){ var o=g.p.overall; return o[0] ? (o[1]/o[0]) : 0; }
  function dropWorst(fg){
    if(fg.length<=1) return {list:fg, dropped:null};
    var wi=0, wv=-1;
    fg.forEach(function(g,i){ var a=gApl(g); if(a>wv){ wv=a; wi=i; } });
    var kept=fg.slice(0,wi).concat(fg.slice(wi+1));
    return {list:kept, dropped:fg[wi], apl:wv};
  }
  GR.renderHome = function(){
    var fg=GR.filtered();
    var ex=document.getElementById('exWorst');
    var note=document.getElementById('exWorstNote');
    if(ex && ex.checked){
      var d=dropWorst(fg); fg=d.list;
      if(note) note.textContent = d.dropped
        ? ('Worst game excluded: '+(d.dropped.d||'?')+' ('+d.apl.toFixed(2)+' pts lost per move)')
        : '(Too few games -- nothing excluded.)';
    } else if(note){ note.textContent=''; }
    renderCards(fg);
    renderCharts(fg);
  };
  document.addEventListener('grdate', GR.renderHome);
  (function attachEx(){
    var ex=document.getElementById('exWorst');
    if(ex){ ex.addEventListener('change', GR.renderHome); }
    else { document.addEventListener('DOMContentLoaded', attachEx); }
  })();
})();
</script>
"""
    return js.replace("__GAMES__", data).replace("__META__", meta)


NAV_JS = """
<script>
(function(){
  var links=document.querySelectorAll('.navlink');
  function show(id){
    document.querySelectorAll('.page').forEach(function(s){
      s.classList.toggle('active', s.id==='page-'+id);
    });
    links.forEach(function(l){
      l.classList.toggle('active', l.getAttribute('data-page')===id);
    });
    window.scrollTo(0,0);
    if(location.hash!=='#'+id) history.replaceState(null,'','#'+id);
  }
  links.forEach(function(l){
    l.addEventListener('click', function(){ show(l.getAttribute('data-page')); });
  });
  var h=(location.hash||'').replace('#','');
  if(h && document.getElementById('page-'+h)) show(h);
})();
</script>
"""


# ---- game trajectory (win-rate curve shape) --------------------------------
def _user_wr_curve(g):
    """The user's win-rate over the game (0..1), flipped to their colour."""
    uc = g.get("user_color")
    out = []
    for t in g.get("timeline", []):
        bw = t.get("black_winrate")
        if bw is None:
            continue
        out.append(bw if uc == "B" else 1.0 - bw)
    return out


# type id -> (label, css-class, is_problem, insight-or-None)
TRAJ_TYPES = [
    ("wire_win",   "Led throughout \u00b7 solid win", "t-win",   False, None),
    ("comeback",   "Comeback win \u00b7 behind then ahead", "t-come",  False,
     "Comeback wins: you have fighting spirit and yose resilience -- but they also "
     "mean you are often behind in the opening or middlegame. Steadying the first "
     "half of the game would cost you far less effort."),
    ("seesaw_win", "Seesaw \u00b7 narrow win", "t-win",   False, None),
    ("wire_loss",  "Behind throughout", "t-loss",  True,
     "Behind throughout: you were already being suppressed in the opening or "
     "middlegame -- direction of play and joseki choice are the priority."),
    ("blew_lead",  "Lead thrown away", "t-bad",   True,
     "Lead thrown away: you relax or back down once ahead -- when leading, play "
     "safe, simplify, and do not overplay."),
    ("collapse",   "Endgame collapse \u00b7 one step short", "t-crash", True,
     "Endgame collapse: ahead all the way into the yose and still derailed -- work "
     "on endgame order, simplification, and not chasing dead stones."),
    ("narrow_loss", "Seesaw \u00b7 narrow loss", "t-loss",  True, None),
]
TRAJ_LABEL = {t[0]: t[1] for t in TRAJ_TYPES}
TRAJ_CLASS = {t[0]: t[2] for t in TRAJ_TYPES}


def classify_trajectory(g):
    """Classify a game by the shape of the user's win-rate curve."""
    w = _user_wr_curve(g)
    if len(w) < 6:
        return None
    won = bool(g.get("won"))
    n = len(w)
    seg = lambda a, b: (sum(w[a:b]) / len(w[a:b])) if w[a:b] else 0.5
    o, m, e = seg(0, n // 3), seg(n // 3, 2 * n // 3), seg(2 * n // 3, n)
    mx, mn, final = max(w), min(w), w[-1]
    AH, BE = 0.60, 0.40
    # fraction of the game spent clearly ahead / behind (robust to blips)
    frac_ahead = sum(1 for v in w if v >= AH) / n
    frac_behind = sum(1 for v in w if v <= BE) / n
    eg = w[2 * n // 3:] or w[-1:]
    eg_ahead = sum(1 for v in eg if v >= AH) / len(eg)

    def mark(v):
        return "▲" if v >= AH else ("▼" if v <= BE else "●")
    shape = mark(o) + mark(m) + mark(e)
    if won:
        if frac_behind < 0.12:
            tid = "wire_win"              # rarely behind → led throughout
        elif frac_behind >= 0.25:
            tid = "comeback"              # behind a good chunk, then won
        else:
            tid = "seesaw_win"
    else:
        if eg_ahead >= 0.4 and final < 0.5:
            tid = "collapse"             # led most of the endgame, still lost
        elif frac_ahead >= 0.25:
            tid = "blew_lead"            # substantially ahead at some point
        elif frac_ahead < 0.12:
            tid = "wire_loss"            # barely ever ahead
        else:
            tid = "narrow_loss"
    return {"type": tid, "shape": shape, "curve": w, "won": won,
            "o": o, "m": m, "e": e, "mx": mx, "mn": mn, "final": final,
            "frac_ahead": frac_ahead, "frac_behind": frac_behind}


def _traj_spark(w, won, width=200, height=54):
    """Small win-rate sparkline (user perspective, 0..1) with a 50% guide."""
    if not w:
        return ""
    pl, pr, pt, pb = 4, 4, 6, 6
    pw, ph = width - pl - pr, height - pt - pb
    n = len(w)
    col = "#2f855a" if won else "#c53030"

    def px(i):
        return pl + (i / (n - 1) * pw if n > 1 else pw / 2)

    def py(v):
        return pt + (1 - v) * ph
    pts = [(px(i), py(v)) for i, v in enumerate(w)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"M {pts[0][0]:.1f},{pt+ph:.1f} "
            + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts)
            + f" L {pts[-1][0]:.1f},{pt+ph:.1f} Z")
    mid = py(0.5)
    p = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
         f'preserveAspectRatio="none" style="display:block">']
    p.append(f'<rect x="0" y="{pt:.1f}" width="{width}" height="{ph/2:.1f}" '
             f'fill="#2f855a" fill-opacity="0.05"/>')
    p.append(f'<rect x="0" y="{mid:.1f}" width="{width}" height="{ph/2:.1f}" '
             f'fill="#c53030" fill-opacity="0.05"/>')
    p.append(f'<line x1="0" y1="{mid:.1f}" x2="{width}" y2="{mid:.1f}" '
             f'stroke="#b7a98f" stroke-width="1" stroke-dasharray="3 3"/>')
    p.append(f'<path d="{area}" fill="{col}" fill-opacity="0.10"/>')
    p.append(f'<polyline fill="none" stroke="{col}" stroke-width="1.8" '
             f'points="{line}"/>')
    p.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.6" '
             f'fill="{col}"/>')
    p.append("</svg>")
    return "".join(p)


def _shape_html(shape):
    cmap = {"▲": "#2f855a", "●": "#a08a6a", "▼": "#c53030"}
    return "".join(f"<span style='color:{cmap[c]}'>{c}</span>" for c in shape)


LEAD_TH = 0.90   # win rate that counts as a "real, game-winning lead" for lead conversion


def _wr_at(w, frac):
    """Smoothed win-rate at a fraction of the game (small window)."""
    if not w:
        return 0.5
    i = int(round(frac * (len(w) - 1)))
    seg = w[max(0, i - 2):i + 3]
    return sum(seg) / len(seg) if seg else 0.5


def _lead_flags(w):
    """(led_entering_middle, led_entering_endgame) at LEAD_TH."""
    return (_wr_at(w, 1 / 3) >= LEAD_TH, _wr_at(w, 2 / 3) >= LEAD_TH)


BEHIND_TH = 0.10   # win-rate that counts as "basically lost" (symmetric to 0.90)


def _behind_flags(w):
    """(behind_entering_middle, behind_entering_endgame) at BEHIND_TH."""
    return (_wr_at(w, 1 / 3) <= BEHIND_TH, _wr_at(w, 2 / 3) <= BEHIND_TH)


def trajectory_section(games):
    rows = []
    for g in games:
        c = classify_trajectory(g)
        if c:
            rows.append((g, c))
    if not rows:
        return ""
    rows.sort(key=lambda gc: date_key(gc[0]), reverse=True)
    counts = {}
    for _, c in rows:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    # summary chips (server-side; JS recomputes for the date filter)
    chips = []
    for tid, label, cls, prob, _ in TRAJ_TYPES:
        n = counts.get(tid, 0)
        if n:
            chips.append(f"<span class='tjchip {cls}' data-t='{tid}'>"
                         f"{esc(label)} <b>{n}</b></span>")
    # insights for the problem types that actually occurred, most common first
    insights = []
    for tid, label, cls, prob, tip in sorted(
            TRAJ_TYPES, key=lambda t: counts.get(t[0], 0), reverse=True):
        if prob and tip and counts.get(tid, 0):
            insights.append(f"<li><b>{esc(label)} ({counts[tid]} games):</b> "
                            f"{esc(tip)}</li>")
    ins_html = (f"<ul class='tjins'>{''.join(insights)}</ul>" if insights else "")

    # Lead conversion & comeback rate: of games led / behind entering
    # a phase, win %.
    lm = lmw = le = lew = 0          # led entering middle / endgame -> won
    bm = bmw = be = bew = 0          # behind entering middle / endgame -> won
    cards = []
    for g, c in rows:
        won = c["won"]
        led_mid, led_end = _lead_flags(c["curve"])
        beh_mid, beh_end = _behind_flags(c["curve"])
        if led_mid:
            lm += 1
            lmw += 1 if won else 0
        if led_end:
            le += 1
            lew += 1 if won else 0
        if beh_mid:
            bm += 1
            bmw += 1 if won else 0
        if beh_end:
            be += 1
            bew += 1 if won else 0
        res = ("<span class='win'>Win</span>" if won
               else "<span class='loss'>Loss</span>")
        _gd = parse_date(g)
        _gd = _gd.isoformat() if _gd else ""
        cards.append(
            f"<div class='trajcard' data-type='{c['type']}' data-date='{_gd}' "
            f"data-won='{1 if won else 0}' data-ledmid='{1 if led_mid else 0}' "
            f"data-ledend='{1 if led_end else 0}' "
            f"data-behmid='{1 if beh_mid else 0}' "
            f"data-behend='{1 if beh_end else 0}'>"
            f"<div class='tjhead'><span class='tjbadge {TRAJ_CLASS[c['type']]}'>"
            f"{esc(TRAJ_LABEL[c['type']])}</span>"
            f"<span class='tjshape' title='Fuseki / middlegame / yose: ahead (up), level (dot), behind (down)'>"
            f"{_shape_html(c['shape'])}</span></div>"
            f"<div class='tjspark'>{_traj_spark(c['curve'], won)}</div>"
            f"<div class='tjmeta'>{esc(g.get('date',''))} vs "
            f"{esc(g.get('opponent',''))} · {res} · "
            f"peak {c['mx']*100:.0f}% / trough {c['mn']*100:.0f}%</div></div>")

    def pct(a, b):
        return f"{round(a / b * 100)}%" if b else "—"
    conv = (
        "<div class='cvbox'>"
        "<div class='cvgrp'>"
        "<div class='cvstat'><div class='cvv' id='cvMid'>" + pct(lmw, lm) + "</div>"
        "<div class='cvl'>Middlegame lead conversion<span id='cvMidN'>" +
        (f"led into middlegame {lm} &middot; held {lmw}" if lm else "&mdash;") + "</span></div></div>"
        "<div class='cvstat'><div class='cvv' id='cvEnd'>" + pct(lew, le) + "</div>"
        "<div class='cvl'>Yose lead conversion<span id='cvEndN'>" +
        (f"led into yose {le} &middot; held {lew}" if le else "&mdash;") + "</span></div></div>"
        "</div>"
        "<div class='cvgrp'>"
        "<div class='cvstat'><div class='cvv' id='cbMid'>" + pct(bmw, bm) + "</div>"
        "<div class='cvl'>Middlegame comeback rate<span id='cbMidN'>" +
        (f"behind into middlegame {bm} &middot; turned it around {bmw}" if bm else "&mdash;") + "</span></div></div>"
        "<div class='cvstat'><div class='cvv' id='cbEnd'>" + pct(bew, be) + "</div>"
        "<div class='cvl'>Yose comeback rate<span id='cbEndN'>" +
        (f"behind into yose {be} &middot; turned it around {bew}" if be else "&mdash;") + "</span></div></div>"
        "</div>"
        "<div class='cvnote'><b>Lead conversion</b> = of the games you entered this "
        "phase clearly winning (win rate &ge; 90%), the share you went on to win. "
        "<b>Comeback rate</b> = of the games you entered this phase clearly losing "
        "(&le; 10%), the share you still turned around. Read them together: low "
        "conversion plus a high comeback rate means you enjoy a brawl but cannot hold "
        "an advantage -- raising your lead conversion is the shortest route to the "
        "next rank.</div>"
        "</div>")

    return ("<h2>Game trajectory &middot; shape classification</h2>"
            "<p class='sub'>Every game sorted by the <b>shape of your win-rate "
            "curve</b> -- led throughout, comeback win, lead thrown away, endgame "
            "collapse. Above 50% means you are ahead. "
            "<b>&#9650;&#9679;&#9660;</b> = ahead / level / behind across the three "
            "phases (fuseki, middlegame, yose).</p>"
            + conv
            + f"<div class='tjsum' id='trajSummary'>{''.join(chips)}</div>"
            + ins_html
            + "<div class='flcount' id='tjcount'></div>"
            + f"<div class='trajgrid'>{''.join(cards)}</div>"
            + TRAJ_JS)


TRAJ_JS = r"""
<script>
(function(){
  var LABEL={wire_win:'Led throughout \u00b7 solid win',
    comeback:'Comeback win \u00b7 behind then ahead',
    seesaw_win:'Seesaw \u00b7 narrow win',wire_loss:'Behind throughout',
    blew_lead:'Lead thrown away',
    collapse:'Endgame collapse \u00b7 one step short',
    narrow_loss:'Seesaw \u00b7 narrow loss'};
  var CLS={wire_win:'t-win',comeback:'t-come',seesaw_win:'t-win',
    wire_loss:'t-loss',blew_lead:'t-bad',collapse:'t-crash',narrow_loss:'t-loss'};
  var ORDER=['wire_win','comeback','seesaw_win','wire_loss','blew_lead','collapse','narrow_loss'];
  var active=null;   // selected type, or null = all
  function apply(){
    // counts + lead conversion within the date range (independent of the type filter)
    var counts={}, total=0, lm=0,lmw=0,le=0,lew=0, bm=0,bmw=0,be=0,bew=0;
    document.querySelectorAll('.trajcard').forEach(function(d){
      var ok=(window.GR?GR.inRange(d.getAttribute('data-date')):true);
      if(ok){ counts[d.getAttribute('data-type')]=(counts[d.getAttribute('data-type')]||0)+1; total++;
        var won=d.getAttribute('data-won')==='1';
        if(d.getAttribute('data-ledmid')==='1'){ lm++; if(won) lmw++; }
        if(d.getAttribute('data-ledend')==='1'){ le++; if(won) lew++; }
        if(d.getAttribute('data-behmid')==='1'){ bm++; if(won) bmw++; }
        if(d.getAttribute('data-behend')==='1'){ be++; if(won) bew++; }
      }
    });
    function pct(a,b){ return b? Math.round(a/b*100)+'%':'—'; }
    function cvcolor(a,b){ if(!b) return ''; var r=a/b;
      return r>=0.7?'cv-good':(r<0.5?'cv-bad':'cv-mid'); }
    function set(id,txt){ var el=document.getElementById(id); if(el) el.textContent=txt; }
    function stat(vid,nid,a,b,ntxt){ var el=document.getElementById(vid);
      if(el){ el.textContent=pct(a,b); el.className='cvv '+cvcolor(a,b); } set(nid,b?ntxt:'—'); }
    stat('cvMid','cvMidN',lmw,lm,'led into middlegame '+lm+' \u00b7 held '+lmw);
    stat('cvEnd','cvEndN',lew,le,'led into yose '+le+' \u00b7 held '+lew);
    stat('cbMid','cbMidN',bmw,bm,'behind into middlegame '+bm+' \u00b7 turned it around '+bmw);
    stat('cbEnd','cbEndN',bew,be,'behind into yose '+be+' \u00b7 turned it around '+bew);
    if(active && !counts[active]) active=null;   // type vanished from range
    var sum=document.getElementById('trajSummary');
    if(sum){
      var html="<span class='tjchip tjall"+(active===null?' on':'')+"' data-t='__all__'>"+
        "All <b>"+total+"</b></span>";
      html+=ORDER.filter(function(t){return counts[t];}).map(function(t){
        return "<span class='tjchip "+CLS[t]+(active===t?' on':'')+"' data-t='"+t+
          "'>"+LABEL[t]+" <b>"+counts[t]+"</b></span>"; }).join('');
      sum.innerHTML=html;
    }
    // visibility = in date range AND (no type filter or matching type)
    var shown=0;
    document.querySelectorAll('.trajcard').forEach(function(d){
      var okDate=(window.GR?GR.inRange(d.getAttribute('data-date')):true);
      var okType=(active===null || d.getAttribute('data-type')===active);
      var vis=okDate&&okType; d.style.display=vis?'':'none'; if(vis) shown++;
    });
    var c=document.getElementById('tjcount');
    if(c) c.textContent=(active?'Filtered: ':'Total: ')+shown+' game(s)'+(active?' ('+LABEL[active]+')':'');
  }
  var sum=document.getElementById('trajSummary');
  if(sum) sum.addEventListener('click',function(e){
    var chip=e.target.closest('.tjchip'); if(!chip) return;
    var t=chip.getAttribute('data-t');
    active=(t==='__all__'||t===active)?null:t;
    apply();
  });
  apply();
  document.addEventListener('grdate', apply);
})();
</script>
"""


SUMMARY_SECT_JS = r"""
<script>
(function(){
  function repRel(){ var m=location.pathname.match(/^\/r\/(.+)$/);
    return m?decodeURIComponent(m[1].replace(/\/$/,'')):null; }
  var REL=repRel();
  function setHist(h){
    var el=document.getElementById('rsHist');
    if(el) el.innerHTML=h||'';
  }
  function load(){
    if(!REL) return;
    fetch('/api/summary?report='+encodeURIComponent(REL)+'&t='+Date.now(),{cache:'no-store'})
    .then(function(r){return r.json();}).then(function(d){
      if(d && d.html){ document.getElementById('rsBody').innerHTML=d.html; }
      if(d) setHist(d.history);
    }).catch(function(){});
    var ex=document.getElementById('rsExp');
    if(ex) ex.href='/api/summary_export?report='+encodeURIComponent(REL);
  }
  window.rsGenerate=function(){
    if(!REL){ alert('Open this report inside the app (local server) to generate it.'); return; }
    var b=document.getElementById('rsBtn'), st=document.getElementById('rsStat');
    b.disabled=true; st.textContent='Generating... (DeepSeek analysis, about 20\u201360s -- please stay on this page)';
    fetch('/api/summary',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({report:REL})})
    .then(function(r){return r.json();}).then(function(d){
      b.disabled=false;
      if(d.error){ st.textContent='Failed: '+d.error; return; }
      document.getElementById('rsBody').innerHTML=d.html||'';
      // The version being replaced is archived, not lost \u2014 show it below.
      setHist(d.history);
      st.textContent='Updated \u2713 \u00b7 the previous one is kept below';
    }).catch(function(e){ b.disabled=false; st.textContent='Failed: '+e; });
  };
  load();
})();
</script>
"""


def summary_section():
    return (
        "<h2>Review summary &middot; diagnostic profile</h2>"
        "<p class='sub'>Built from the reviews you <b>spoke into the recorder</b> in "
        "the blunder set, plus this report's lead conversion, comeback rate and "
        "blunder distribution. DeepSeek <b>derives your own weakness categories "
        "straight from your notes</b> (not a fixed checklist) and diagnoses the root "
        "causes -- conclusions and training priorities only, no move-by-move list. "
        "The result is saved into this report, so next time it loads instantly.</p>"
        "<div class='vcrow' style='margin:12px 0'>"
        "<button type='button' class='vcbtn' id='rsBtn' onclick='rsGenerate()'>"
        "&#8635; Generate / refresh review summary</button>"
        "<a class='sumexp' id='rsExp' download href='#' "
        "title='Every version of this project&#39;s summary in one Markdown file'>"
        "&#8681; Export all versions</a>"
        "<span class='vcstat sub' id='rsStat'></span></div>"
        "<div id='rsBody' class='smdbox'>"
        "<p class='sub'>Nothing generated yet. Record a spoken review in the blunder "
        "set first, then press the button above.</p>"
        "</div>"
        "<div id='rsHist'></div>"
        + SUMMARY_SECT_JS)


def build_html(games, agg, recs, report_dir=None):
    chron = sorted(games, key=date_key)  # oldest -> newest for trends
    hidden = load_hidden(report_dir)

    # The project (report folder) name is the report's identity — show it as the
    # player/source label on the overview.
    if report_dir:
        agg["source_label"] = os.path.basename(str(report_dir).rstrip("/\\"))

    # Each module is one page. (id, sidebar label, html). Empty modules are
    # dropped so their nav entry doesn't appear.
    candidates = [
        ("home", "Overview",
         _home_page(agg, chron) + trends_section(chron)
         + _moves_hist_section(agg, games)),
        ("trajectory", "Trajectory", trajectory_section(games)),
        ("practice", "Blunders",
         practice_section(games, hidden, practice_cleared(report_dir))),
        ("summary", "Review summary", summary_section()),
        ("games", "Game by game", _games_page(games)),
    ]
    pages = [(pid, label, h) for pid, label, h in candidates if h]

    nav = ["<aside class='sidebar'>",
           "<div class='brand'>Mirror of Go<span>KATAGO REVIEW</span></div>",
           "<nav>"]
    sections = []
    for i, (pid, label, h) in enumerate(pages):
        active = " active" if i == 0 else ""
        nav.append(f"<button class='navlink{active}' data-page='{pid}'>"
                   f"<span class='dot'></span>{esc(label)}</button>")
        sections.append(f"<section class='page{active}' id='page-{pid}'>"
                        f"{_date_filter_bar()}{h}</section>")
    nav.append("</nav>")
    nav.append(f"<div class='meta'>Generated "
               f"{esc(datetime.date.today().isoformat())}<br>"
               f"{agg['n']} games &middot; {agg['n_user_moves']} moves analysed</div>")
    nav.append("</aside>")

    p = [f"<!doctype html><html lang='zh'><head><meta charset='utf-8'>"
         f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Mirror of Go &middot; KataGo Review</title>"
         f"<style>{CSS}</style></head><body>",
         "<div class='layout'>",
         "".join(nav),
         "<main class='content'>",
         "".join(sections),
         "</main></div>",
         TOOLTIP_JS,
         NAV_JS,
         _date_filter_js(chron),
         "</body></html>"]
    return "".join(p)


def main(argv):
    cfg = load_config()
    out_dir = os.path.expanduser(cfg["output_dir"])
    games = load_games(out_dir, cfg.get("games_dirs", []))
    if not games:
        print(f"No analysed games found in {out_dir}; run analyze.py first.")
        return 1
    agg = aggregate(games)
    agg["source_label"] = source_label_from_path(out_dir)
    recs = recommendations(agg)
    report_path = os.path.join(out_dir, "review_report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(build_html(games, agg, recs, report_dir=out_dir))
    print(f"Review report written: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
