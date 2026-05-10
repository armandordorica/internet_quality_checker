"""CSV and PDF export helpers."""

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

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
from .labels import filename_label_from_network_name
from .metrics import rolling_ping_quality, summarize


def export_raw_csv(df=None, output_dir="internet_quality_results", label="internet_quality"):
    """Export raw collected samples to a timestamped CSV."""
    df = results_df() if df is None else df.copy()
    if df.empty:
        raise ValueError("No samples to export yet.")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = Path(output_dir) / f"{label}_raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(path, index=False)
    print(f"Saved raw CSV: {path}")
    return path


def _plot_report_charts(df, title="Internet quality report"):
    """Build the static report chart figure from a dataframe."""
    report_df = df.copy()
    if "time" not in report_df.columns:
        report_df["time"] = pd.to_datetime(report_df["ts"])

    ping_df = report_df[report_df["metric"] == "tcp_ping"].copy()
    speed_df = report_df[report_df["metric"].isin(["download", "upload"])].copy()

    fig, axes = plt.subplots(4, 1, figsize=(11, 14), sharex=True)
    fig.suptitle(title, fontsize=14, y=0.995)

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
    axes[0].set_title("Latency")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper left")

    for connection, group in ping_df.groupby("connection"):
        quality = rolling_ping_quality(group)
        axes[1].plot(quality.index, quality["jitter_ms"], linewidth=2, label=f"{connection} jitter")
        axes[2].plot(quality.index, quality["packet_loss_pct"], linewidth=2, label=f"{connection} packet loss")

    axes[1].axhline(MEET_GOOD_JITTER_MS, color="green", linestyle="--", alpha=0.45, label="Meet target: jitter < 30 ms")
    axes[1].axhline(MEET_OK_JITTER_MS, color="orange", linestyle="--", alpha=0.35, label="Caution: jitter < 50 ms")
    axes[1].set_ylabel("Jitter (ms)")
    axes[1].set_title("Packet timing consistency")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="upper left")

    axes[2].axhline(MEET_GOOD_LOSS_PCT, color="green", linestyle="--", alpha=0.45, label="Meet target: packet loss < 1%")
    axes[2].axhline(MEET_OK_LOSS_PCT, color="orange", linestyle="--", alpha=0.35, label="Caution: packet loss < 3%")
    axes[2].set_ylabel("Packet loss (%)")
    axes[2].set_title("Reliability")
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
    axes[3].set_title("Capacity probes")
    axes[3].grid(True, alpha=0.25)
    axes[3].legend(loc="upper left")

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def _summary_table_figure(meet_summary):
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.axis("off")
    ax.set_title("Google Meet Quality Summary", fontsize=14, pad=16)

    table_df = meet_summary.reset_index().copy()
    for column in table_df.columns:
        if pd.api.types.is_numeric_dtype(table_df[column]):
            table_df[column] = table_df[column].map(lambda value: "" if pd.isna(value) else f"{value:.2f}")

    table = ax.table(
        cellText=table_df.values,
        colLabels=table_df.columns,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.4)
    return fig


def export_pdf_report(df=None, output_dir="internet_quality_results", label="internet_quality"):
    """Export a PDF report with summary and charts for the collected samples."""
    df = results_df() if df is None else df.copy()
    if df.empty:
        raise ValueError("No samples to export yet.")
    if "time" not in df.columns:
        df["time"] = pd.to_datetime(df["ts"])

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = Path(output_dir) / f"{label}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    meet_summary, _, _ = summarize(df)
    connection_title = ", ".join(sorted(df["connection"].dropna().unique()))
    title = f"Internet quality report - {connection_title}"

    with PdfPages(path) as pdf:
        summary_fig = _summary_table_figure(meet_summary)
        pdf.savefig(summary_fig, bbox_inches="tight")
        plt.close(summary_fig)

        chart_fig = _plot_report_charts(df, title=title)
        pdf.savefig(chart_fig, bbox_inches="tight")
        plt.close(chart_fig)

    print(f"Saved PDF report: {path}")
    return path


def export_all_results(df=None, output_dir="internet_quality_results", label="internet_quality"):
    """Export both raw CSV and PDF report."""
    df = results_df() if df is None else df.copy()
    csv_path = export_raw_csv(df, output_dir=output_dir, label=label)
    pdf_path = export_pdf_report(df, output_dir=output_dir, label=label)
    return csv_path, pdf_path


def export_label_from_network_name(network_name):
    return filename_label_from_network_name(network_name)
