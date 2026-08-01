"""The Blunder Set (practice) section."""

from .constants import PHASE_LABEL, PTS_BLUNDER, WR_BLUNDER
from .assets import BOARD_MODAL, FLOAT_REC, PRACTICE_CLEAR_JS, PRACTICE_JS, VOICE_JS, VOICE_PANEL
from .data import esc, parse_date
from .board import _similarity_matrix, board_before, classify_blunder, diagram_svg, local_pattern, territory_split


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
