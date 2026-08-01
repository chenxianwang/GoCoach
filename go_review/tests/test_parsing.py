"""Self-contained unit tests for the SGF / LizzieYZY parsing core.

Run with:   python3 -m pytest go_review/tests      (or)   python3 go_review/tests/test_parsing.py

No network, no engine, no private data — everything is built from small inline
SGF strings, so these double as regression guards for the two bugs we fixed:
  * variation branches inflating the move count, and
  * the integer-per-ten-thousand winrate being misread as 100%.
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import sgfparse        # noqa: E402
import import_lizzie   # noqa: E402


# --- winrate normalisation (integer per-ten-thousand) ----------------------
def test_norm_winrate_scale():
    f = import_lizzie._norm_winrate
    assert abs(f("9998") - 0.9998) < 1e-9     # near-certain win
    assert abs(f("1") - 0.0001) < 1e-9        # ≈0%  (was misread as 1.0/100%)
    assert f("0") == 0.0
    assert abs(f("10000") - 1.0) < 1e-9
    assert abs(f("3546") - 0.3546) < 1e-9
    # decimal forms still understood
    assert abs(f("0.6236") - 0.6236) < 1e-9   # 0-1 fraction
    assert abs(f("62.36") - 0.6236) < 1e-9    # 0-100 percent
    # clamped into [0,1]
    assert 0.0 <= f("-5") <= 1.0


# --- main line only (ignore variation branches) ----------------------------
def _write(tmp, text):
    p = os.path.join(tmp, "g.sgf")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def test_main_line_ignores_variations():
    # Valid SGF: after W[dp] there are two variations — the FIRST is the main
    # line (B[qp];W[oq]); the second (W[dd];B[ee]) is an alternative and must
    # NOT be counted.  Main line = 4 moves.
    sgf = "(;FF[4]SZ[19];B[pd];W[dp](;B[qp];W[oq])(;W[dd];B[ee]))"
    g = sgfparse.parse_sgf(_write(tempfile.mkdtemp(), sgf))
    assert len(g["moves"]) == 4, g["moves"]
    colors = [c for c, _ in g["moves"]]
    assert colors == ["B", "W", "B", "W"], colors

    # A deeper, nested branch must also be ignored.
    sgf2 = ("(;FF[4]SZ[19];B[pd];W[dp];B[qp]"
            "(;W[oq];B[cc])(;W[cc];B[dd];W[ee]))")
    g2 = sgfparse.parse_sgf(_write(tempfile.mkdtemp(), sgf2))
    assert len(g2["moves"]) == 5, g2["moves"]


def test_no_variations_unchanged():
    sgf = "(;FF[4]SZ[19];B[pd];W[dp];B[qp])"
    g = sgfparse.parse_sgf(_write(tempfile.mkdtemp(), sgf))
    assert len(g["moves"]) == 3


# --- coordinate conversion --------------------------------------------------
def test_coord_conversion():
    assert sgfparse.sgf_coord_to_gtp("pd", 19) == "Q16"
    assert sgfparse.sgf_coord_to_gtp("", 19) == "pass"
    assert sgfparse.sgf_coord_to_gtp("tt", 19) == "pass"


# --- LZ candidate parsing ---------------------------------------------------
def test_parse_lz_candidate():
    block = ("ikatago 64.5 2040 -0.9 13.3 "
             "move R16 visits 2040 winrate 9998 prior 805 scoreMean -0.92 "
             "pv R16 D16 C4 info "
             "move Q4 visits 100 winrate 1 prior 10 scoreMean -5.0 pv Q4 D4")
    out = import_lizzie.parse_lz(block)
    cands = out["cands"]
    assert cands[0]["move"] == "R16"
    assert abs(cands[0]["winrate"] - 0.9998) < 1e-9
    assert abs(cands[1]["winrate"] - 0.0001) < 1e-9   # not 1.0!


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
