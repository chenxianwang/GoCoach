"""The Blunder Set (practice) section."""

from .constants import PHASE_LABEL, PTS_BLUNDER, WR_BLUNDER
from .assets import BOARD_MODAL, FLOAT_REC, PRACTICE_CLEAR_JS, PRACTICE_JS, VOICE_JS, VOICE_PANEL
from .charts import game_wr_chart
from .data import date_key, esc, game_time, parse_date
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
    # Blunders per game *before* anything is deleted.  A game at 0 here is one
    # you played clean, which is a different fact from a game whose blunders you
    # have since worked through and removed -- the opponent row shows them
    # differently and must not confuse the two.
    game_blunders = {}
    for g in games:
        fn = g.get("filename", "")
        game_blunders.setdefault(fn, 0)
        for m in g.get("all_user_moves", []):
            if (m.get("points_lost", 0) >= PTS_BLUNDER or
                    m.get("winrate_lost", 0) >= WR_BLUNDER):
                total_blunders += 1     # counts every blunder (matches Overview)
                game_blunders[fn] += 1
                key = f"{fn}#{m.get('move_number')}"
                if key in hidden or cleared:
                    continue
                items.append((g, m))
    # In move order, not worst-first: reading the cards in the order the mistakes
    # happened lets you follow the game, and it lines them up left-to-right with
    # the win-rate curve shown above them once the filters leave one game.
    # Games are chronological so the grouping is stable; filename breaks a tie
    # between two games played on the same day.  "Show me the worst" is still one
    # click away on the Points lost row.
    items.sort(key=lambda t: (date_key(t[0]), t[0].get("filename", ""),
                              t[1].get("move_number") or 0))
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
    # Commonest first.  These used to fall out in first-appearance order, which
    # meant something only while the cards were sorted worst-first; now that they
    # are in move order that would put whichever type you happened to misplay on
    # move 12 at the head of the row.
    cat_count = {}
    for e in built:
        cat_count[e["name"]] = cat_count.get(e["name"], 0) + 1
    cats = sorted(cat_count, key=lambda c: (-cat_count[c], c.lower()))
    cat_slug = {c: f"c{i}" for i, c in enumerate(cats)}
    phases = [ph for ph in ("opening", "middlegame", "endgame")
              if any(e["phase"] == ph for e in built)]
    phase_count = {ph: sum(1 for e in built if e["phase"] == ph)
                   for ph in phases}

    # One chip per *game*, not per opponent.  Two games against the same person
    # are two different games -- you may have been crushed in one and comfortable
    # in the other -- and merging them made the row unable to say so: it had to
    # sum their blunders and give up on colouring a mixed record.  Splitting them
    # also lets the row cover games with *no* blunders, which have no cards at all
    # and so could never have contributed to a per-opponent tally.
    #
    # Every game listed here, in most-recently-played order, matching Game-by-game
    # and Trajectory -- the game you actually want after a session is at the left
    # end.  Filename breaks the tie if two games somehow land on the same second.
    order = sorted(games, key=lambda g: (-game_time(g), g.get("filename", "")))
    # Names come from the SGF, so they are arbitrary text (usually a Chinese
    # nickname) and the *filename* is slugged rather than either being used raw:
    # `recount` finds the counters with `i[data-co="<value>"]`, and a nickname
    # containing a quote or bracket would break that selector.  Same reason
    # `cat_slug` exists.
    opp_slug = {g.get("filename", ""): f"o{i}" for i, g in enumerate(order)}
    opp_name = {g.get("filename", ""): (g.get("opponent") or "").strip()
                or "(unknown)" for g in order}

    # `#1`, `#2` … only where a name repeats: numbering a one-off game would be
    # noise.  Numbered oldest-first, the way you would count them off yourself,
    # so #1 stays #1 when a later game against the same person is imported --
    # even though the row shows the newest of them first.
    played = {}
    for g in sorted(games, key=lambda g: (game_time(g), g.get("filename", ""))):
        played.setdefault(opp_name[g.get("filename", "")], []).append(
            g.get("filename", ""))
    nth = {fn: (i + 1, len(fns))
           for fns in played.values() for i, fn in enumerate(fns)}

    opp_count = {}
    for e in built:
        fn = e["g"].get("filename", "")
        e["oslug"] = opp_slug[fn]
        opp_count[fn] = opp_count.get(fn, 0) + 1

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
    # One game means there is nothing to choose between, so the row is only
    # worth its space when there are several.  Unlike every row above it this
    # one is multi-select: reviewing two or three games together is the
    # normal case, and picking them one at a time would defeat the point.
    if len(order) > 1:
        nav.append("<div class='navrow'><span class='navlbl' "
                   "title='One chip per game, most recently played first; "
                   "#1, #2 tell repeat meetings apart. Pick as many as you "
                   "like -- they combine. Green = you won it, red = you lost "
                   "it, blue = no blunders at all'>Opponent</span>")
        nav.append("<button class='navbtn on' data-fo='all' "
                   "title='Every game'>All "
                   f"<i data-co='all'>{len(built)}</i></button>")
        for g in order:
            fn = g.get("filename", "")
            slug, name = opp_slug[fn], opp_name[fn]
            n, of = nth[fn]
            # A game you played clean has no cards to filter to, so the point of
            # its chip is the fact itself -- it gets a colour of its own rather
            # than the win/loss green, which would make the one game worth
            # noticing look like all the others.
            clean = game_blunders.get(fn, 0) == 0
            won = bool(g.get("won"))
            tint = " wlc" if clean else (" wlw" if won else " wll")
            # Green/red carry the result, but a colour alone is not readable by
            # everyone (or in a screenshot), so the letter says it too.
            res = (f" <em class='wlres'>{'W' if won else 'L'}</em>"
                   if not clean else " <em class='wlres'>&#10003; clean</em>")
            label = esc(name) + (f" <em class='gno'>#{n}</em>" if of > 1 else "")
            tip = (f"No blunders in this game -- you played it clean"
                   if clean else
                   f"Blunders from this game -- you {'won' if won else 'lost'} it")
            nav.append(f"<button class='navbtn{tint}' data-fo='{slug}' "
                       f"data-gamefile=\"{esc(fn)}\" "
                       f"data-clean='{1 if clean else 0}' "
                       f"title='{tip}. Against {esc(name)}"
                       + (f", meeting #{n} of {of}" if of > 1 else "")
                       + f", played {esc(date_key(g))}."
                       f" Click more than one to combine them'>{label} "
                       f"<i data-co='{slug}'>{opp_count.get(fn, 0)}</i>"
                       f"{res}</button>")
        nav.append("</div>")
    nav.append("</div>")

    # Cards.  `marks` collects, per game, where its blunders sit on the win-rate
    # curve — filled in here because this is where a card gets the `bl<i>` id the
    # marker has to point back at.
    cards = []
    marks = {}
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
            f"data-opp='{e['oslug']}' "
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
        marks.setdefault(g.get("filename", ""), []).append(
            (m.get("move_number"), f"bl{i}",
             f"Move {m['move_number']}: you played {m.get('played')}, "
             f"-{m.get('points_lost')} pts (KataGo: {m.get('best')}). "
             f"Click to jump to it."))

    # One win-rate curve per game, all hidden.  The practice JS reveals the
    # matching one once the filters have narrowed the cards down to a single
    # game -- the point being the context a cropped diagram cannot give you:
    # whether a blunder threw the game or dented an already-won position.
    # Rendering them up front rather than fetching on demand keeps the report a
    # standalone file, which is the whole premise of the offline export.
    # Built from every game, not only the ones with cards: picking the chip for a
    # game you played clean would otherwise show nothing at all, when its curve is
    # exactly what there is to look at.
    wrboxes = []
    for g in order:
        fn = g.get("filename", "")
        svg = game_wr_chart(g, marks.get(fn, ()))
        if not svg:                    # no timeline (unanalysed import)
            continue
        res = g.get("result") or ""
        won = "you won" if g.get("won") else "you lost"
        head = (f"{esc(g.get('date',''))} vs <b>{esc(g.get('opponent',''))}</b>"
                f" &middot; {esc(won)}" + (f" ({esc(res)})" if res else ""))
        wrboxes.append(
            f"<div class='wrbox' data-game=\"{esc(fn)}\" hidden>"
            f"<div class='wrhd'>Win rate through this game "
            f"<span class='wrsub'>{head}</span></div>"
            f"{svg}"
            + (f"<div class='wrft'>Your win rate, move by move. "
               f"<span style='color:#e02424'>&#9632;</span> marks each blunder "
               f"<b>still shown below</b> — click one to jump to its card.</div>"
               if game_blunders.get(fn, 0) else
               "<div class='wrft'>Your win rate, move by move. "
               "Nothing in this game crossed the blunder line, so there are "
               "no markers on it.</div>")
            + "</div>")

    # Filterable practice cards + the board modal and JS.
    return ("<h2>Blunder Set</h2>"
            f"<p class='sub'>Every blunder across all your games (&ge;6 pts or win rate "
            f"&minus;15%; {total_blunders} in total, matching the Overview blunder count)"
            + (f"; {n_deleted} mastered ones have been deleted, leaving {len(items)} in the practice set" if n_deleted else "")
            + ", cropped down to the local shape for practice -- filter by phase, type, "
            "points lost, win-rate drop, status and opponent. "
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
            # Filtering down to nothing used to leave a blank strip below the
            # chips, which reads as broken rather than as an answer.  It became
            # worth fixing once the row could offer a game with no blunders at
            # all: an empty grid is the *right* result there and should say so.
            + "<div class='nobl' id='noblund' hidden></div>"
            + "".join(wrboxes)
            + f"<div class='diags'>{''.join(cards)}</div>"
            + BOARD_MODAL
            + FLOAT_REC
            + PRACTICE_JS
            + VOICE_JS
            + PRACTICE_CLEAR_JS)
