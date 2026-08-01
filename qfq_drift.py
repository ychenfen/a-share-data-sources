#!/usr/bin/env python3
"""Snapshot a fixed forward-adjusted window and detect when it changes.

Forward adjustment factors are anchored on the most recent bar, so every
dividend or split rewrites the whole history. This script makes that
observable: same symbol, same window, hashed on each run.

Append-only log at results/qfq_drift.csv:
    run_date, source, symbol, window, sha256_first16, changed_since_last
"""
