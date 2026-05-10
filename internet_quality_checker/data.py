"""Shared in-memory sample storage."""

import pandas as pd

samples = []


def results_df():
    """Return collected samples as a DataFrame with a parsed time column."""
    if not samples:
        return pd.DataFrame()

    df = pd.DataFrame(samples)
    df["time"] = pd.to_datetime(df["ts"])
    return df
