"""Pairwise close-price agreement between sources.

The single most informative number this repo produces is not the mismatch count
— it is whether the disagreement is explained by a different adjustment
convention or by the underlying data genuinely differing. Those need completely
different fixes, and a bare "the sources disagree on 12 days" tells you which
one you have exactly never.

How the split is made: take the ratio a/b day by day. Two sources holding the
same data under different adjustment conventions produce a ratio that is *flat*
between corporate actions and *steps* on the day of one. Two sources holding
different data produce a ratio that wanders.

  ratio steps a few times, flat in between  -> adjustment convention differs
  ratio never steps but sits off by a margin -> the data itself differs
  ratio wanders inside a segment            -> both, or a broken series

A first implementation tried to spot ex-dividend days by flagging close-to-close
moves more than 6 rolling standard deviations from normal. That is wrong in a
way worth recording: on a smooth series the rolling standard deviation goes to
zero, so every trivial move clears a 6-sigma bar and the detector flags every
day. tests/test_agreement.py pins the corrected behaviour.

Limitation: this infers corporate actions from price behaviour instead of
reading an official calendar, so it cannot name the action. A real dividend that
leaves the ratio unchanged (both sources adjusted identically) is invisible
here, which is fine — that is not a disagreement.
"""
import itertools

import pandas as pd

TOL = 1e-4        # relative; anything larger is a genuine disagreement
STEP_TOL = 1e-3   # day-over-day change in the a/b ratio that counts as a step
# Corporate actions are rare — a handful per symbol per year. If a "step" shows
# up on more than this fraction of days, the ratio is wandering, not stepping,
# and calling it an adjustment difference would be wrong. Without this guard a
# ratio that drifts every single day scores one step per day, every segment has
# length 1, and the flat-between-steps check passes vacuously.
MAX_STEP_RATE = 0.05


def run(srcs, symbols, args) -> pd.DataFrame:
    series = {}
    for src in srcs:
        for sym in symbols:
            try:
                res = src.daily(sym, args.start, args.end, adjust=args.adjust)
                series[(src.name, sym)] = res.df.set_index("date")["close"]
            except Exception:
                continue

    rows = []
    for a, b in itertools.combinations([s.name for s in srcs], 2):
        compared = mism = steps = 0
        flat_between = True
        for sym in symbols:
            sa, sb = series.get((a, sym)), series.get((b, sym))
            if sa is None or sb is None:
                continue
            joined = pd.concat([sa, sb], axis=1, join="inner",
                               keys=["a", "b"]).dropna()
            if joined.empty:
                continue
            compared += len(joined)
            ratio = joined["a"] / joined["b"]
            mism += int(((joined["a"] - joined["b"]).abs()
                         / joined["b"].abs() > TOL).sum())

            step_mask = ((ratio / ratio.shift(1) - 1).abs() > STEP_TOL).fillna(False)
            steps += int(step_mask.sum())
            # Within each run bounded by steps the ratio should be constant. If
            # it drifts, an adjustment convention alone cannot explain the gap.
            for _, chunk in ratio.groupby(step_mask.cumsum()):
                if len(chunk) > 1 and float(chunk.max() / chunk.min() - 1) > STEP_TOL:
                    flat_between = False

        sparse = bool(compared and steps and steps / compared <= MAX_STEP_RATE)
        rows.append({
            "pair": f"{a} vs {b}",
            "days_compared": compared,
            "mismatch_days": mism,
            "adjustment_steps": steps,
            "explained_by_adjustment": bool(mism and sparse and flat_between),
            "mismatch_rate": round(mism / compared, 5) if compared else None,
        })
    return pd.DataFrame(rows)
