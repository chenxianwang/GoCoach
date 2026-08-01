"""Lazy full-board SVG rendering for the blunder-zoom API."""

import os

import report          # noqa: E402

from .listing import report_dir_from_rel
from .config_jobs import _safe_cfg


_BOARD_GAMES = {}   # (rdir, mtime) -> games list, so repeated zooms are fast


def render_board_svg(rel, game_file, move):
    """Regenerate one blunder's full-board SVG on demand (for the lazy zoom)."""
    rdir = report_dir_from_rel(rel or "")
    if not rdir:
        return None
    try:
        mvn = int(move)
    except (TypeError, ValueError):
        return None
    key = (rdir, os.path.getmtime(rdir))
    games = _BOARD_GAMES.get(key)
    if games is None:
        games = report.load_games(rdir, _safe_cfg().get("games_dirs", []))
        _BOARD_GAMES.clear()
        _BOARD_GAMES[key] = games
    g = next((x for x in games if x.get("filename") == game_file), None)
    if not g:
        return None
    m = next((x for x in g.get("all_user_moves", [])
              if x.get("move_number") == mvn), None)
    if not m:
        return None
    try:
        return report.full_board_svg(g, m, "bd")
    except Exception:
        return None
