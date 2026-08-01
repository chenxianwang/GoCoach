"""Shared constants: thresholds, labels, colors, lookup tables."""

import os


HERE = os.path.dirname(os.path.abspath(__file__))


GTP_COLS = "ABCDEFGHJKLMNOPQRST"


PHASES = ["overall", "opening", "middlegame", "endgame"]


PHASE_LABEL = {"overall": "Overall", "opening": "Fuseki",
               "middlegame": "Middlegame", "endgame": "Yose"}


PHASE_COLOR = {"overall": "#1a202c", "opening": "#2b6cb0",
               "middlegame": "#d69e2e", "endgame": "#c53030"}


PTS_BLUNDER = 6.0      # points-lost threshold for a "blunder"


WR_BLUNDER = 0.15      # win-rate-drop threshold (15%)


HOSHI = {3, 9, 15}


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


LEAD_TH = 0.90   # win rate that counts as a "real, game-winning lead" for lead conversion


BEHIND_TH = 0.10   # win-rate that counts as "basically lost" (symmetric to 0.90)
