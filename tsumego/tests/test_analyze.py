"""Tests for the failure taxonomy, built from four real attempts.

The fixtures below are the actual payloads for run 8172383 (3级, 2026-08-02),
trimmed to the fields the classifier reads. They cover one instance of each
outcome, which is exactly what makes them worth keeping:

    Q1  played L18 -- a move outside the answer tree     -> off_book
    Q2  played P17 -- the popular losing move            -> trap
    Q3  played the first two correct moves, then erred   -> depth
    Q4  solved                                            -> correct

Run with:  python3 -m tsumego.tests.test_analyze   (from the repo root)
       or: python3 -m pytest tsumego/tests
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tsumego import analyze          # noqa: E402
from tsumego.api import pt_to_gtp    # noqa: E402


def _n(i, pt, num, s, pid=0, subs=()):
    return {"id": i, "pt": pt, "num": num, "s": s, "pid": pid, "subs": list(subs)}


# -- Q1: Tesuji, I played kb (L18); nobody's answer tree contains it ---------
Q1 = {
    "n": 1, "qid": 534062, "publicid": 479068, "levelname": "3K",
    "qtypename": "Tesuji", "result": 2, "costtime": 12, "at": 1785656084,
    "moves": ["kb"], "yes": 393, "no": 774, "vote": 5,
}
D1 = {str(d["id"]): d for d in [
    _n(0, "", 1158, "c", subs=[1, 2, 6, 42, 43]),
    _n(1, "kb", 71, "c", 0),
    _n(2, "nf", 556, "f", 0, [3]),
    _n(3, "me", 556, "f", 2),
    _n(6, "mf", 456, "o", 0, [7]),
    _n(7, "me", 456, "o", 6),
    _n(42, "ma", 16, "c", 0),
    _n(43, "mg", 17, "c", 0),
]}

# -- Q2: Life & Death, I played oc -- a known losing move, 24% of players ----
Q2 = {
    "n": 2, "qid": 169631, "publicid": 151242, "levelname": "3K",
    "qtypename": "Life & Death", "result": 2, "costtime": 15, "at": 1785656115,
    "moves": ["oc", "pb", "oa", "pd"], "yes": 3118, "no": 3531, "vote": 4.5,
}
D2 = {str(d["id"]): d for d in [
    _n(0, "", 6595, "c", subs=[1, 2, 11, 12]),
    _n(1, "oa", 1380, "f", 0),
    _n(2, "pb", 3212, "o", 0, [3]),
    _n(3, "oc", 3205, "o", 2),
    _n(11, "oc", 1606, "f", 0, [19]),
    _n(19, "pb", 1532, "f", 11, [22]),
    _n(22, "oa", 1213, "f", 19, [23]),
    _n(23, "pd", 1213, "f", 22),
    _n(12, "pd", 259, "c", 0),
]}

# -- Q3: Fight, correct for two moves then wrong on my third ----------------
Q3 = {
    "n": 3, "qid": 231059, "publicid": 200919, "levelname": "3K",
    "qtypename": "Fight", "result": 2, "costtime": 38, "at": 1785656171,
    "moves": ["nc", "mc", "nb", "mb", "oa", "ra", "ma"],
    "yes": 2011, "no": 4043, "vote": 4.4,
}
D3 = {str(d["id"]): d for d in [
    _n(0, "", 6034, "c", subs=[1, 8, 15]),
    _n(1, "nc", 5637, "o", 0, [2]),
    _n(2, "mc", 5628, "o", 1, [3]),
    _n(3, "nb", 4891, "o", 2, [4]),
    _n(4, "mb", 4887, "o", 3, [5, 9]),
    _n(5, "ma", 2344, "o", 4),
    _n(9, "oa", 1851, "f", 4, [25]),
    _n(25, "ra", 1815, "f", 9, [32]),
    _n(32, "ma", 550, "c", 25),
    _n(8, "nb", 169, "c", 0),
    _n(15, "mb", 74, "c", 0),
]}

# -- Q4: solved -------------------------------------------------------------
Q4 = {
    "n": 4, "qid": 376189, "publicid": 337068, "levelname": "3K",
    "qtypename": "Fight", "result": 1, "costtime": 16, "at": 1785656208,
    "moves": ["ne", "me", "mf", "oe", "mg", "pg", "qf"],
    "yes": 2826, "no": 2553, "vote": 5,
}
D4 = {str(d["id"]): d for d in [
    _n(0, "", 5353, "c", subs=[3, 4, 6]),
    _n(3, "me", 106, "c", 0),
    _n(4, "mf", 639, "f", 0),
    _n(6, "ne", 4497, "o", 0, [7]),
    _n(7, "me", 4496, "o", 6),
]}

FIXTURES = [(Q1, D1), (Q2, D2), (Q3, D3), (Q4, D4)]


def test_coordinates():
    # the site encodes column-then-row from the top-left; display counts rows up
    assert pt_to_gtp("mf") == "N14"      # the answer to Q1
    assert pt_to_gtp("kb") == "L18"      # what I actually played
    assert pt_to_gtp("nf") == "O14"      # the popular trap
    assert pt_to_gtp("aa") == "A19"
    assert pt_to_gtp("ss") == "T1"
    assert pt_to_gtp("") == ""


def test_off_book_is_not_confused_with_a_trap():
    a = analyze.classify(Q1, D1)
    assert a["kind"] == "off_book"
    assert a["my_first"] == "L18"
    assert a["my_first_status"] == "c"
    assert a["best_move"] == "N14"
    # the most-played first move here is wrong -- the majority falls for it
    assert a["top_move"] == "O14"
    assert round(a["top_share"], 2) == 0.48
    assert a["diverge_at"] == 0


def test_trap_is_detected_from_the_crowd_tree():
    a = analyze.classify(Q2, D2)
    assert a["kind"] == "trap"
    assert a["my_first"] == "P17"
    assert a["my_first_status"] == "f"
    assert a["best_move"] == "Q18"
    assert 0.24 < a["my_first_share"] < 0.25   # 1606 / 6595
    assert a["diverge_at"] == 0


def test_depth_failure_reports_where_the_reading_ran_out():
    a = analyze.classify(Q3, D3)
    assert a["kind"] == "depth"
    # my 1st and 2nd moves were on the correct line; the 3rd was not
    assert a["diverge_at"] == 2
    assert a["my_first_status"] == "o"


def test_correct_attempt():
    a = analyze.classify(Q4, D4)
    assert a["kind"] == "correct"
    assert a["diverge_at"] is None


def test_first_move_distribution_is_sorted_and_normalised():
    dist = analyze.first_move_distribution(D1)
    assert [d["gtp"] for d in dist][:3] == ["O14", "N14", "L18"]
    assert abs(sum(d["share"] for d in dist) - 1116 / 1158) < 1e-9
    assert [d["status"] for d in dist][:3] == ["f", "o", "c"]


def test_analyse_rolls_everything_up():
    run = {"guanid": 8172383, "number": 13, "t": 1785656486,
           "totaltime": 288, "questions": [Q1, Q2, Q3, Q4]}
    dias = {q["qid"]: d for q, d in FIXTURES}
    agg = analyze.analyse([run], lambda qid: dias.get(qid))
    assert agg["n"] == 4
    assert agg["accuracy"] == 0.25
    assert agg["kinds"] == {"off_book": 1, "trap": 1, "depth": 1}
    assert agg["levels"][0]["label"] == "3级"
    # 12s and 15s on the two I got wrong outright, 16s on the one I solved
    assert agg["median_time_wrong"] == 15
    types = {t["name"]: t for t in agg["types"]}
    assert types["Fight"]["n"] == 2 and types["Fight"]["accuracy"] == 0.5


def test_pass_probability_is_a_binomial_tail():
    # the test is not sudden-death: answer `total`, need `need` right
    assert analyze.pass_probability(1.0, 8, 10) == 1.0
    assert analyze.pass_probability(0.0, 8, 10) == 0.0
    low = analyze.pass_probability(0.33, 8, 10)
    high = analyze.pass_probability(0.60, 8, 10)
    assert low < 0.01 < high          # why accuracy, not retries, is the lever
    assert high < analyze.pass_probability(0.80, 8, 10)


def test_traps_are_grouped_by_problem_not_listed_once_per_miss():
    """Falling for the same trap repeatedly is one lesson, not N rows -- and the
    repeat count is the signal worth surfacing."""
    run = {"guanid": 1, "number": 13, "t": 1785656486,
           "questions": [dict(Q2, n=i) for i in range(1, 6)]}
    agg = analyze.analyse([run], lambda qid: {Q2["qid"]: D2}.get(qid))
    assert len(agg["traps"]) == 1
    assert agg["traps"][0]["times"] == 5
    assert agg["traps"][0]["my_first"] == "P17"
    assert agg["traps"][0]["best_move"] == "Q18"


def test_missing_crowd_tree_is_admitted_not_guessed():
    """A miss with no diagram fetched must not be reported as off_book -- that
    would invent a diagnosis from absent data."""
    a = analyze.classify(Q1, {})
    assert a["kind"] == "unclassified"
    assert a["diverge_at"] is None
    # a solved question needs no tree to be known correct
    assert analyze.classify(Q4, {})["kind"] == "correct"


def test_run_walk_stops_at_totaltime():
    """totaltime equals the sum of costtime, so the walk must stop on the last
    real question instead of probing a non-existent one -- that extra request
    is the one most likely to be throttled."""
    from tsumego import crawl
    calls = []

    class FakeClient:
        delay = 6.0
        def question(self, number, guanid, n):
            calls.append(n)
            if n > 3:
                raise AssertionError("walked past the end of the run")
            return {"qid": 100 + n, "qtypename": "Tesuji", "lu": 19,
                    "myan": {"st": 2, "result": 1, "costtime": 10,
                             "pts": [{"p": "mf"}]},
                    "taskresult": {}}

    import tempfile, os
    old = crawl.RUNS
    with tempfile.TemporaryDirectory() as d:
        crawl.RUNS = d
        try:
            out = crawl.fetch_run(FakeClient(),
                                  {"guanid": 1, "number": 13, "totaltime": 30},
                                  log=lambda *a: None)
        finally:
            crawl.RUNS = old
    assert calls == [1, 2, 3]
    assert len(out["questions"]) == 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
