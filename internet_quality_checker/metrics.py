"""Metric calculations and Google Meet quality classification."""

import math

import pandas as pd

from .config import (
    MEET_CAUTION_LATENCY_MS,
    MEET_GOOD_JITTER_MS,
    MEET_GOOD_LOSS_PCT,
    MEET_OK_JITTER_MS,
    MEET_OK_LOSS_PCT,
    MEET_TARGET_DOWNLOAD_MBPS,
    MEET_TARGET_LATENCY_MS,
    MEET_TARGET_UPLOAD_MBPS,
)
from .data import results_df


SEMAPHORE_COLORS = {
    "green": "#2ca02c",
    "yellow": "#ffbf00",
    "red": "#d62728",
    "waiting": "#9e9e9e",
}


def rolling_ping_quality(group, window="30s"):
    """Return rolling packet loss and endpoint-normalized jitter for one connection.

    This is a proxy for packet timing consistency, not true RTP/WebRTC jitter.
    It avoids mixing paths by comparing latency changes only within the same endpoint.
    """
    ordered = group.sort_values("time").set_index("time")
    loss_pct = (1 - ordered["ok"].rolling(window).mean()) * 100

    successful = ordered[ordered["ok"]].copy()
    if successful.empty:
        jitter_ms = pd.Series(index=ordered.index, dtype="float64")
    else:
        if "endpoint" in successful.columns:
            latency_delta = successful.groupby("endpoint")["latency_ms"].diff().abs()
        else:
            latency_delta = successful["latency_ms"].diff().abs()
        jitter_ms = latency_delta.rolling(window, min_periods=2).quantile(0.95)
        jitter_ms = jitter_ms.reindex(ordered.index).ffill()

    return pd.DataFrame({"packet_loss_pct": loss_pct, "jitter_ms": jitter_ms})


def _status_for_max_metric(value, green_max, yellow_max):
    if pd.isna(value):
        return "waiting"
    if value <= green_max:
        return "green"
    if value <= yellow_max:
        return "yellow"
    return "red"


def _status_for_min_metric(value, green_min, yellow_min):
    if pd.isna(value):
        return "waiting"
    if value >= green_min:
        return "green"
    if value >= yellow_min:
        return "yellow"
    return "red"


def current_metric_statuses(ping_df, speed_df, window_seconds=60):
    """Return current green/yellow/red status badges by connection and metric."""
    import time

    statuses = []
    now = time.time()
    connections = sorted(set(ping_df["connection"].dropna()) | set(speed_df["connection"].dropna()))
    recent_ping = ping_df[ping_df["unix_ts"] >= now - window_seconds]

    speed_values = {}
    ok_speed = speed_df[speed_df["ok"]]
    for (connection, metric), group in ok_speed.groupby(["connection", "metric"]):
        speed_values[(connection, metric)] = group.sort_values("time").tail(3)["mbps"].median()

    for connection in connections:
        group = recent_ping[recent_ping["connection"] == connection]
        if group.empty:
            median_ms = math.nan
            jitter_ms = math.nan
            loss_pct = math.nan
        else:
            ok_latency = group.loc[group["ok"], "latency_ms"]
            median_ms = ok_latency.median()
            quality = rolling_ping_quality(group, window=f"{window_seconds}s")
            jitter_series = quality["jitter_ms"].dropna()
            jitter_ms = jitter_series.iloc[-1] if not jitter_series.empty else math.nan
            loss_pct = 100 * (1 - group["ok"].mean())

        statuses.extend([
            {
                "connection": connection,
                "metric": "latency",
                "value": median_ms,
                "unit": "ms",
                "status": _status_for_max_metric(median_ms, MEET_TARGET_LATENCY_MS, MEET_CAUTION_LATENCY_MS),
            },
            {
                "connection": connection,
                "metric": "jitter",
                "value": jitter_ms,
                "unit": "ms",
                "status": _status_for_max_metric(jitter_ms, MEET_GOOD_JITTER_MS, MEET_OK_JITTER_MS),
            },
            {
                "connection": connection,
                "metric": "loss",
                "value": loss_pct,
                "unit": "%",
                "status": _status_for_max_metric(loss_pct, MEET_GOOD_LOSS_PCT, MEET_OK_LOSS_PCT),
            },
        ])

        for metric, target in (("download", MEET_TARGET_DOWNLOAD_MBPS), ("upload", MEET_TARGET_UPLOAD_MBPS)):
            value = speed_values.get((connection, metric), math.nan)
            statuses.append({
                "connection": connection,
                "metric": metric,
                "value": value,
                "unit": "Mbps",
                "status": _status_for_min_metric(value, target, target * 0.75),
            })

    return statuses


def _meet_status(row):
    if (
        row["packet_loss_pct"] <= MEET_GOOD_LOSS_PCT
        and row["median_latency_ms"] <= MEET_TARGET_LATENCY_MS
        and row["jitter_ms"] <= MEET_GOOD_JITTER_MS
        and row.get("download_median_mbps", math.inf) >= MEET_TARGET_DOWNLOAD_MBPS
        and row.get("upload_median_mbps", math.inf) >= MEET_TARGET_UPLOAD_MBPS
    ):
        return "good"
    if (
        row["packet_loss_pct"] <= MEET_OK_LOSS_PCT
        and row["median_latency_ms"] <= MEET_CAUTION_LATENCY_MS
        and row["jitter_ms"] <= MEET_OK_JITTER_MS
        and row.get("download_median_mbps", math.inf) >= MEET_TARGET_DOWNLOAD_MBPS * 0.75
        and row.get("upload_median_mbps", math.inf) >= MEET_TARGET_UPLOAD_MBPS * 0.75
    ):
        return "usable_with_risk"
    return "likely_sluggish"


def summarize(df=None):
    df = results_df() if df is None else df
    if df.empty:
        return pd.DataFrame()

    ping_df = df[df["metric"] == "tcp_ping"].copy()
    speed_df = df[df["metric"].isin(["download", "upload"])].copy()

    latency_summary = ping_df.groupby("connection").agg(
        samples=("ok", "size"),
        success_rate=("ok", "mean"),
        median_latency_ms=("latency_ms", "median"),
        p95_latency_ms=("latency_ms", lambda s: s.dropna().quantile(0.95)),
        max_latency_ms=("latency_ms", "max"),
    )
    latency_summary["packet_loss_pct"] = (1 - latency_summary["success_rate"]) * 100

    jitter_by_connection = {}
    for connection, group in ping_df.groupby("connection"):
        quality = rolling_ping_quality(group, window="60s")
        jitter_series = quality["jitter_ms"].dropna()
        jitter_by_connection[connection] = jitter_series.median() if not jitter_series.empty else math.nan
    latency_summary["jitter_ms"] = pd.Series(jitter_by_connection)

    speed_summary = speed_df[speed_df["ok"]].groupby(["connection", "metric"]).agg(
        probes=("mbps", "size"),
        median_mbps=("mbps", "median"),
        min_mbps=("mbps", "min"),
        max_mbps=("mbps", "max"),
    )

    meet_summary = latency_summary[[
        "packet_loss_pct",
        "median_latency_ms",
        "jitter_ms",
        "p95_latency_ms",
    ]].copy()

    if not speed_summary.empty:
        speed_wide = speed_summary["median_mbps"].unstack("metric")
        meet_summary["download_median_mbps"] = speed_wide.get("download")
        meet_summary["upload_median_mbps"] = speed_wide.get("upload")

    meet_summary["meet_status"] = meet_summary.apply(_meet_status, axis=1)
    return meet_summary, latency_summary, speed_summary
