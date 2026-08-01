import concurrent.futures as cf, time
import pandas as pd
from sources.base import FetchError

LADDER = (1, 2, 4, 8, 16)
COOLDOWN_S = 30


def run(srcs, symbol, args) -> pd.DataFrame:
    rows = []
    for src in srcs:
        last_ok, first_fail = 0, None
        for c in LADDER:
            ok = _burst(src, symbol, c, args)
            if ok:
                last_ok = c
                time.sleep(COOLDOWN_S)
            else:
                first_fail = c
                break
        rows.append({"source": src.name,
                     "max_ok_concurrency": last_ok,
                     "first_failing_concurrency": first_fail,
                     "note": "observed lower bound, not a documented limit"})
        time.sleep(COOLDOWN_S)          # always cool down before the next source
    return pd.DataFrame(rows)


def _burst(src, symbol, c, args) -> bool:
    with cf.ThreadPoolExecutor(max_workers=c) as ex:
        futs = [ex.submit(src.daily, symbol, args.start, args.end)
                for _ in range(c * 3)]
        for f in cf.as_completed(futs):
            try:
                r = f.result()
            except FetchError:
                return False
            if r.n_rows == 0:           # HTTP 200 with nothing in it
                return False
    return True
