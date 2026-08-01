"""Report generation: turns per-game analysis JSON into the review_report.html
dashboard. Split into submodules by concern; this file just wires the public
API back together so `import report; report.build_html(...)` etc. keep working
exactly as before the split.
"""

# noqa: F401 throughout -- these are re-exports, not used in this file itself.
from .constants import HERE, GTP_COLS, PHASES, PHASE_LABEL, PHASE_COLOR, PTS_BLUNDER, WR_BLUNDER, HOSHI, NOTE_CATS, NOTE_CAUSES, NOTE_MAXIMS, TRAJ_TYPES, TRAJ_LABEL, TRAJ_CLASS, LEAD_TH, BEHIND_TH  # noqa: F401
from .assets import PRACTICE_CLEAR_JS, TRENDS_JS, VOICE_PANEL, FLOAT_REC, VOICE_JS, BOARD_MODAL, PRACTICE_JS, CSS, GAMES_JS, TOOLTIP_JS, NAV_JS, TRAJ_JS, SUMMARY_SECT_JS  # noqa: F401
from .data import load_config, load_games, load_hidden, practice_cleared, _enrich_from_sgf, esc, parse_date, date_key, date_label, blunder_count, game_metrics, aggregate, recommendations, phase_label, source_label_from_path  # noqa: F401
from .board import gtp_to_xy, GoBoard, board_before, count_captures, groups_with_liberties, territory_split, group_points, diagram_svg, _chebyshev, _local_density, classify_blunder, full_board_svg, local_pattern, _rot90, _flip, _dihedral, _cell_w, pattern_similarity, blunder_similarity, _similarity_matrix, score_svg, _replay_board, final_score_board_svg, final_score_html  # noqa: F401
from .charts import _games_data_js, _date_filter_bar, trend_chart, _flush_segment, moves_hist_svg, metric_hist_svg, _date_filter_js, _traj_spark  # noqa: F401
from .trends import trends_section, _window_apl, improvement_metric, _improve_banner_html  # noqa: F401
from .trajectory import _user_wr_curve, classify_trajectory, _shape_html, _wr_at, _lead_flags, _behind_flags, trajectory_section  # noqa: F401
from .practice import practice_section  # noqa: F401
from .summary import summary_section  # noqa: F401
from .pages import _home_page, _moves_hist_section, _game_recency_key, _games_page  # noqa: F401
from .legacy import coach_review, _recs_page, _blunders_page  # noqa: F401
from .core import build_html, main  # noqa: F401
