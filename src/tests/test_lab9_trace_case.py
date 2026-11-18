"""Regression test from docs/trace_case.md: seeded_regression C-002@11 (FM-03 ticket_trust).

First wrong step = event 3 `model_override {"delay_days": 5}` while event 2 shows DB delay_days 2.
The test must FAIL the buggy trial and PASS the same claim@seed on `fixed`.
"""
import pytest

pytestmark = pytest.mark.student


@pytest.fixture(autouse=True)
def _restore_shapes():
    """investigate() registers the lab9 variants into lab8.shapes.SHAPES; undo it so Lab 8's
    contract tests (exactly four shapes) still see the registry they expect."""
    from lab8.shapes import SHAPES

    before = dict(SHAPES)
    yield
    SHAPES.clear()
    SHAPES.update(before)


def _ctx(case):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="trace_case", inputs={}, metadata=None, expected_output=case["label"],
                            output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})


def _run(shape):
    from lab9.trace_case import investigate

    return investigate(shape, "C-002", 11)


def test_lab9_trace_case_c002_first_wrong_step_is_model_override():
    case = _run("seeded_regression")
    kinds = [e.get("kind") for e in case["trial"]["events"]]
    assert kinds[:3] == ["handoff", "investigator", "model_override"]
    db_delay = case["trial"]["events"][1]["payload"]["lookup_order"]["order"]["delay_days"]
    assert db_delay == 2 and case["trial"]["events"][2]["payload"] == {"delay_days": 5}


def test_lab9_trace_case_c002_graders_fail_buggy_and_pass_fixed():
    from lab9.graders import DbFactKept, RefundAmountCorrect, TrialPass

    bad, good = _ctx(_run("seeded_regression")), _ctx(_run("fixed"))
    assert DbFactKept().evaluate(bad).value is False
    assert RefundAmountCorrect().evaluate(bad).value is False      # ledger 20000, label 0
    assert TrialPass().evaluate(bad).value is False
    assert DbFactKept().evaluate(good).value is True
    assert RefundAmountCorrect().evaluate(good).value is True
    assert TrialPass().evaluate(good).value is True
