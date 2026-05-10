"""Live plotting helpers."""

import asyncio
import math
import time

import matplotlib.pyplot as plt
from IPython.display import clear_output, display

from .config import (
    MEET_CAUTION_LATENCY_MS,
    MEET_GOOD_JITTER_MS,
    MEET_GOOD_LOSS_PCT,
    MEET_OK_JITTER_MS,
    MEET_OK_LOSS_PCT,
    MEET_TARGET_DOWNLOAD_MBPS,
    MEET_TARGET_LATENCY_MS,
    MEET_TARGET_UPLOAD_MBPS,
    PLOT_REFRESH_SECONDS,
)
from .data import results_df
from .metrics import SEMAPHORE_COLORS, current_metric_statuses, rolling_ping_quality


def _stop_requested(stop_signal):
    return bool(stop_signal and stop_signal.is_set())


def draw_status_badges(fig, statuses):
    if not statuses:
        fig.text(
            0.02,
            0.94,
            "Status: waiting for samples",
            fontsize=10,
            color="white",
            bbox={"facecolor": SEMAPHORE_COLORS["waiting"], "edgecolor": "none", "boxstyle": "round,pad=0.35"},
        )
        return

    x = 0.02
    y = 0.94
    for status in statuses[:10]:
        value = status["value"]
        value_text = "waiting" if value is None or math.isnan(value) else f"{value:.1f} {status['unit']}"
        label = f"{status['connection']} {status['metric']}: {status['status']} ({value_text})"
        fig.text(
            x,
            y,
            label,
            fontsize=9,
            color="black" if status["status"] == "yellow" else "white",
            bbox={
                "facecolor": SEMAPHORE_COLORS[status["status"]],
                "edgecolor": "none",
                "boxstyle": "round,pad=0.35",
            },
        )
        x += 0.19
        if x > 0.82:
            x = 0.02
            y -= 0.035


def plot_results():
    df = results_df()
    if df.empty:
        print("Waiting for samples...")
        return

    ping_df = df[df["metric"] == "tcp_ping"].copy()
    speed_df = df[df["metric"].isin(["download", "upload"])].copy()
    connection_title = ", ".join(sorted(df["connection"].dropna().unique()))

    fig, axes = plt.subplots(4, 1, figsize=(13, 12), sharex=True)
    draw_status_badges(fig, current_metric_statuses(ping_df, speed_df))

    for connection, group in ping_df.groupby("connection"):
        ok_group = group[group["ok"]].sort_values("time")
        if ok_group.empty:
            continue
        axes[0].plot(ok_group["time"], ok_group["latency_ms"], ".", alpha=0.25, markersize=3, label=f"{connection} raw")
        rolling = ok_group.set_index("time")["latency_ms"].rolling("10s").median()
        axes[0].plot(rolling.index, rolling.values, linewidth=2, label=f"{connection} 10s median")

    axes[0].axhline(MEET_TARGET_LATENCY_MS, color="green", linestyle="--", alpha=0.45, label="Meet target: RTT < 150 ms")
    axes[0].axhline(MEET_CAUTION_LATENCY_MS, color="orange", linestyle="--", alpha=0.35, label="Caution: RTT < 200 ms")
    axes[0].set_ylabel("Latency / RTT proxy (ms)")
    axes[0].set_title(f"Google Meet latency stability - {connection_title}")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper left")

    for connection, group in ping_df.groupby("connection"):
        quality = rolling_ping_quality(group)
        axes[1].plot(quality.index, quality["jitter_ms"], linewidth=2, label=f"{connection} 30s rolling jitter")
        axes[2].plot(quality.index, quality["packet_loss_pct"], linewidth=2, label=f"{connection} 30s rolling packet loss")

    axes[1].axhline(MEET_GOOD_JITTER_MS, color="green", linestyle="--", alpha=0.45, label="Meet target: jitter < 30 ms")
    axes[1].axhline(MEET_OK_JITTER_MS, color="orange", linestyle="--", alpha=0.35, label="Caution: jitter < 50 ms")
    axes[1].set_ylabel("Jitter (ms)")
    axes[1].set_title("Packet timing consistency")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="upper left")

    axes[2].axhline(MEET_GOOD_LOSS_PCT, color="green", linestyle="--", alpha=0.45, label="Meet target: packet loss < 1%")
    axes[2].axhline(MEET_OK_LOSS_PCT, color="orange", linestyle="--", alpha=0.35, label="Caution: packet loss < 3%")
    axes[2].set_ylabel("Packet loss (%)")
    axes[2].set_title("Connection reliability")
    axes[2].grid(True, alpha=0.25)
    axes[2].legend(loc="upper left")

    for (connection, metric), group in speed_df.groupby(["connection", "metric"]):
        ok_group = group[group["ok"]].sort_values("time")
        if ok_group.empty:
            continue
        axes[3].plot(ok_group["time"], ok_group["mbps"], marker="o", linewidth=1.5, label=f"{connection} {metric}")

    axes[3].axhline(MEET_TARGET_DOWNLOAD_MBPS, color="blue", linestyle="--", alpha=0.25, label="Meet download target")
    axes[3].axhline(MEET_TARGET_UPLOAD_MBPS, color="purple", linestyle="--", alpha=0.35, label="Meet HD upload target: 3.2 Mbps")
    axes[3].set_ylabel("Mbps")
    axes[3].set_title("Lightweight Meet capacity probes")
    axes[3].grid(True, alpha=0.25)
    axes[3].legend(loc="upper left")

    title_parts = [f"Network: {connection_title}"]
    recent = ping_df[ping_df["unix_ts"] >= time.time() - 60]
    if not recent.empty:
        summary = []
        for connection, group in recent.groupby("connection"):
            loss_pct = 100 * (1 - group["ok"].mean())
            median_ms = group.loc[group["ok"], "latency_ms"].median()
            quality = rolling_ping_quality(group, window="60s")
            jitter_series = quality["jitter_ms"].dropna()
            jitter_ms = jitter_series.iloc[-1] if not jitter_series.empty else math.nan
            summary.append(f"{connection}: loss {loss_pct:.1f}%, median {median_ms:.1f} ms, jitter {jitter_ms:.1f} ms")
        title_parts.append("Last 60s: " + " | ".join(summary))
    fig.suptitle("\n".join(title_parts), y=0.995)

    plt.tight_layout(rect=[0, 0, 1, 0.88])
    display(fig)
    plt.close(fig)


async def plot_loop(stop_at, stop_signal=None):
    while time.time() < stop_at and not _stop_requested(stop_signal):
        clear_output(wait=True)
        plot_results()
        await asyncio.sleep(PLOT_REFRESH_SECONDS)
    clear_output(wait=True)
    plot_results()
