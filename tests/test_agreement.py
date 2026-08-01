"""Verifies the one piece of logic in this repo that is easy to get wrong.

agreement.py claims it can tell "the two sources use different adjustment
conventions" apart from "the two sources hold different data". That claim is
the repo's main output, so it gets a test with a constructed series where the
right answer is known. No network involved.

Run: python -m pytest tests/ -q      (or: python tests/test_agreement.py)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from metrics import agreement  # noqa: E402
from sources.base import FetchResult  # noqa: E402


def _frame(closes, start="2024-01-01"):
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({
        "date": dates, "open": closes, "high": closes,
        "low": closes, "close": closes, "volume": [1000] * len(closes),
    })


class FakeSource:
    needs_token = False

    def __init__(self, name, closes):
        self.name = name
        self._df = _frame(closes)

    def available(self):
        return True

    def daily(self, symbol, start, end, adjust="hfq"):
        return FetchResult(df=self._df.copy(), elapsed_s=0.0,
                           n_rows=len(self._df), raw_fields=list(self._df.columns))


class Args:
    start = "20240101"
    end = "20241231"
    adjust = "hfq"
    sleep = 0


def test_identical_sources_report_zero_mismatch():
    closes = [10 + i * 0.01 for i in range(120)]
    a, b = FakeSource("a", closes), FakeSource("b", list(closes))
    out = agreement.run([a, b], ["000001"], Args()).iloc[0]
    assert out["mismatch_days"] == 0, out.to_dict()
    assert out["days_compared"] == 120


def test_adjustment_step_is_recognised_as_such():
    """One source is adjusted, the other is not. Exactly one ratio step, flat
    either side -> explained by adjustment.

    The step is *multiplicative*, because that is how adjustment actually works:
    an adjusted series is the raw series times a cumulative factor, so the ratio
    between adjusted and raw is piecewise constant. Modelling it as a subtractive
    offset (raw = base - 1.5) makes the ratio drift within the segment, and the
    detector correctly refuses to call that an adjustment — which is the point of
    the flat-between-steps check."""
    base = [10 + i * 0.01 for i in range(120)]
    raw = list(base)
    raw[90:] = [c / 1.15 for c in raw[90:]]  # factor step at day 90
    out = agreement.run([FakeSource("adjusted", base), FakeSource("raw", raw)],
                        ["000001"], Args()).iloc[0]
    assert out["mismatch_days"] == 30, out.to_dict()
    assert out["adjustment_steps"] == 1, (
        f"expected exactly one ratio step, got {out.to_dict()}")
    assert bool(out["explained_by_adjustment"]) is True, out.to_dict()


def test_constant_offset_is_a_data_difference_not_an_adjustment():
    """A persistent proportional difference with no step is a data difference.

    This is the case the first (rolling-sigma) implementation got wrong: with a
    smooth series its rolling std collapsed and it flagged every day as a gap."""
    base = [10 + i * 0.01 for i in range(120)]
    drift = [c * 1.001 for c in base]        # 0.1% everywhere, no step
    out = agreement.run([FakeSource("x", base), FakeSource("y", drift)],
                        ["000001"], Args()).iloc[0]
    assert out["mismatch_days"] == 120, out.to_dict()
    assert out["adjustment_steps"] == 0, out.to_dict()
    assert bool(out["explained_by_adjustment"]) is False, out.to_dict()


def test_wandering_ratio_is_not_explained_by_adjustment():
    """Ratio that drifts inside a segment must not be blamed on a corporate action."""
    base = [10 + i * 0.01 for i in range(120)]
    noisy = [c * (1 + 0.002 * ((i % 7) - 3)) for i, c in enumerate(base)]
    out = agreement.run([FakeSource("x", base), FakeSource("y", noisy)],
                        ["000001"], Args()).iloc[0]
    assert out["mismatch_days"] > 0, out.to_dict()
    assert bool(out["explained_by_adjustment"]) is False, out.to_dict()


if __name__ == "__main__":
    for fn in [test_identical_sources_report_zero_mismatch,
               test_adjustment_step_is_recognised_as_such,
               test_constant_offset_is_a_data_difference_not_an_adjustment,
               test_wandering_ratio_is_not_explained_by_adjustment]:
        fn()
        print(f"  PASS  {fn.__name__}")
    print("\n4 passed")
