"""Tests for the per-problem coaching brief.

The claim `explain` makes is a strong one -- "the problem is decided at move N"
-- so the arithmetic behind it is worth pinning down. The share at each turn is
taken out of the players who *reached that turn*, not out of everyone who
attempted the problem; otherwise the numbers shrink down the line and two turns
stop being comparable, which is the only thing they are for.

Run with:  python3 -m tsumego.tests.test_explain   (from the repo root)
       or: python3 -m pytest tsumego/tests
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tsumego import explain                        # noqa: E402
from tsumego.tests.test_analyze import Q1, D1, Q3, D3   # noqa: E402

RUN = {"guanid": 8100001, "number": 13, "t": 1785656100}


def _runs(question):
    return [dict(RUN, questions=[question])]


def test_main_line_follows_the_most_played_correct_branch():
    line = [m["gtp"] for m in explain.main_line(D3)]
    assert line == ["O17", "N17", "O18", "N18", "N19"]


def test_main_line_survives_a_tree_with_no_correct_child():
    assert explain.main_line({}) == []


def test_decision_points_are_my_turns_only():
    pts = explain.decision_points(D3)
    assert [p["ply"] for p in pts] == [1, 2, 3]
    assert [p["answer"] for p in pts] == ["O17", "O18", "N19"]


def test_share_is_out_of_the_players_who_got_this_far():
    pts = {p["ply"]: p for p in explain.decision_points(D3)}
    # move 1: 5637 of the 5637+169+74 who played anything
    assert round(pts[1]["found"], 3) == round(5637 / 5880, 3)
    # move 3: 2344 of the 2344+1851 still on the line, NOT of 5880
    assert round(pts[3]["found"], 3) == round(2344 / 4195, 3)


def test_a_turn_with_one_reply_is_reported_as_forced_not_as_100_percent():
    """'Everyone found it' and 'there was nothing else to find' are different
    facts, and only the first one is a compliment."""
    pts = {p["ply"]: p for p in explain.decision_points(D3)}
    assert pts[2]["forced"] is True
    assert pts[1]["forced"] is False


def test_crux_is_the_hardest_real_choice():
    c = explain.crux(explain.decision_points(D3))
    assert c["ply"] == 3 and c["answer"] == "N19"   # 56% find it, vs 96% at move 1


def test_crux_ignores_forced_moves():
    forced_only = {"0": {"id": 0, "pt": "", "num": 9, "s": "c", "subs": [1]},
                   "1": {"id": 1, "pt": "nc", "num": 9, "s": "o", "subs": []}}
    assert explain.crux(explain.decision_points(forced_only)) is None


def test_explain_finds_the_attempt_and_locates_the_first_wrong_move():
    e = explain.explain(_runs(Q3), lambda qid: D3, Q3["publicid"])
    assert e["qid"] == Q3["qid"]
    assert e["crowd_rate"] == 2011 / (2011 + 4043)
    t = e["attempts"][0]
    assert t["solved"] is False
    assert t["wrong_at"] == 3        # my 3rd move; the first two were correct
    assert t["got_right"] == 2


def test_explain_can_be_asked_by_qid_instead():
    e = explain.explain(_runs(Q3), lambda qid: D3, Q3["qid"], by_qid=True)
    assert e is not None and e["publicid"] == Q3["publicid"]


def test_a_problem_never_attempted_is_none_not_an_empty_brief():
    assert explain.explain(_runs(Q3), lambda qid: D3, 999999) is None


def test_a_timeout_with_no_move_claims_no_misread():
    """Nothing was played, so there is no first-wrong-move to report -- saying
    'wrong at move 1' would invent one."""
    expired = dict(Q3, moves=[], expired=True, costtime=46, result=2)
    e = explain.explain(_runs(expired), lambda qid: D3, expired["publicid"])
    t = e["attempts"][0]
    assert t["wrong_at"] is None and t["got_right"] == 0
    assert "no misread to diagnose" in explain.to_text(e)


def test_a_missing_crowd_tree_is_admitted_not_faked():
    e = explain.explain(_runs(Q1), lambda qid: {}, Q1["publicid"])
    assert e["has_diagram"] is False and e["line"] == []
    assert "No crowd tree cached" in explain.to_text(e)


def test_to_text_renders_without_blowing_up():
    text = explain.to_text(explain.explain(_runs(Q3), lambda qid: D3, Q3["publicid"]))
    assert "ANSWER   B O17 W N17 B O18 W N18 B N19" in text
    assert "the problem is move 3 (N19)" in text
    assert f"Q-{Q3['publicid']}" in text


def _main():
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as e:
                fails += 1
                print(f"  FAIL {name}: {e}")
    print(f"\n{fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(_main())
