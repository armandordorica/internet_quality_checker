"""Side-by-side comparison helpers for saved raw test runs."""

import math
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import display

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
from .metrics import rolling_ping_quality, summarize


def meet_comparison_metric_specs():
    return [
        {
            "key": "latency_ms",
            "title": "Latency / RTT proxy distribution",
            "unit": "ms",
            "target": MEET_TARGET_LATENCY_MS,
            "caution": MEET_CAUTION_LATENCY_MS,
            "better": "lower",
        },
        {
            "key": "jitter_ms",
            "title": "Packet timing consistency / jitter distribution",
            "unit": "ms",
            "target": MEET_GOOD_JITTER_MS,
            "caution": MEET_OK_JITTER_MS,
            "better": "lower",
        },
        {
            "key": "packet_loss_pct",
            "title": "Rolling packet loss distribution",
            "unit": "%",
            "target": MEET_GOOD_LOSS_PCT,
            "caution": MEET_OK_LOSS_PCT,
            "better": "lower",
        },
        {
            "key": "download_mbps",
            "title": "Download probe distribution",
            "unit": "Mbps",
            "target": MEET_TARGET_DOWNLOAD_MBPS,
            "caution": MEET_TARGET_DOWNLOAD_MBPS * 0.75,
            "better": "higher",
        },
        {
            "key": "upload_mbps",
            "title": "Upload probe distribution",
            "unit": "Mbps",
            "target": MEET_TARGET_UPLOAD_MBPS,
            "caution": MEET_TARGET_UPLOAD_MBPS * 0.75,
            "better": "higher",
        },
    ]


def latest_raw_result_paths(result_dir="internet_quality_results"):
    result_dir = Path(result_dir)
    raw_paths = sorted(result_dir.glob("*_raw_*.csv"))
    if not raw_paths:
        return pd.DataFrame(columns=["network_label", "path", "modified_at"])

    file_index = pd.DataFrame([
        {
            "network_label": path.name.split("_raw_", 1)[0],
            "path": path,
            "modified_at": path.stat().st_mtime,
        }
        for path in raw_paths
    ])
    latest_idx = file_index.groupby("network_label")["modified_at"].idxmax()
    return file_index.loc[latest_idx].sort_values("network_label").reset_index(drop=True)


def load_latest_raw_runs(result_dir="internet_quality_results"):
    latest_paths = latest_raw_result_paths(result_dir)
    if latest_paths.empty:
        return pd.DataFrame(), latest_paths

    runs = []
    for _, row in latest_paths.iterrows():
        run_df = pd.read_csv(row["path"])
        run_df["network_label"] = row["network_label"]
        run_df["source_file"] = row["path"].name
        runs.append(run_df)

    combined = pd.concat(runs, ignore_index=True)
    combined["time"] = pd.to_datetime(combined["ts"])
    return combined, latest_paths


def build_meet_comparison_summary(combined):
    comparison_rows = []
    for network_label, run_df in combined.groupby("network_label"):
        meet_summary, _, _ = summarize(run_df)
        row = meet_summary.reset_index().iloc[0].to_dict()
        row["network_label"] = network_label
        row["source_file"] = run_df["source_file"].iloc[0]
        comparison_rows.append(row)

    if not comparison_rows:
        return pd.DataFrame()
    return pd.DataFrame(comparison_rows).set_index("network_label")


def build_metric_distributions(combined, metric_specs=None):
    metric_specs = metric_specs or meet_comparison_metric_specs()
    distributions = {spec["key"]: {} for spec in metric_specs}

    for network_label, run_df in combined.groupby("network_label"):
        ping_df = run_df[run_df["metric"] == "tcp_ping"].copy()
        speed_df = run_df[run_df["metric"].isin(["download", "upload"])].copy()

        distributions["latency_ms"][network_label] = ping_df.loc[ping_df["ok"], "latency_ms"].dropna()

        quality_parts = [
            rolling_ping_quality(connection_ping_df, window="30s")
            for _, connection_ping_df in ping_df.groupby("connection")
        ]
        if quality_parts:
            quality_df = pd.concat(quality_parts)
            distributions["jitter_ms"][network_label] = quality_df["jitter_ms"].dropna()
            distributions["packet_loss_pct"][network_label] = quality_df["packet_loss_pct"].dropna()
        else:
            distributions["jitter_ms"][network_label] = pd.Series(dtype="float64")
            distributions["packet_loss_pct"][network_label] = pd.Series(dtype="float64")

        distributions["download_mbps"][network_label] = speed_df.loc[
            (speed_df["metric"] == "download") & speed_df["ok"], "mbps"
        ].dropna()
        distributions["upload_mbps"][network_label] = speed_df.loc[
            (speed_df["metric"] == "upload") & speed_df["ok"], "mbps"
        ].dropna()

    return distributions


def plot_metric_distribution_boxplots(distributions, metric_specs=None):
    metric_specs = metric_specs or meet_comparison_metric_specs()
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    axes = axes.ravel()

    for ax, spec in zip(axes, metric_specs):
        metric_distribution = distributions[spec["key"]]
        labels = [label for label, values in metric_distribution.items() if not values.empty]
        values = [metric_distribution[label].values for label in labels]

        if values:
            box = ax.boxplot(values, labels=labels, patch_artist=True, showmeans=True)
            for patch, color in zip(box["boxes"], plt.cm.Set2(range(len(values)))):
                patch.set_facecolor(color)
                patch.set_alpha(0.75)
        else:
            ax.text(0.5, 0.5, "No samples", ha="center", va="center", transform=ax.transAxes)

        ax.set_title(spec["title"])
        ax.set_ylabel(spec["unit"])
        ax.grid(True, axis="y", alpha=0.25)
        ax.tick_params(axis="x", rotation=25)

        target_label = f"target {'<' if spec['better'] == 'lower' else '>='} {spec['target']:.1f} {spec['unit']}"
        caution_label = f"caution {'<' if spec['better'] == 'lower' else '>='} {spec['caution']:.1f} {spec['unit']}"
        ax.axhline(spec["target"], color="green", linestyle="--", alpha=0.6, label=target_label)
        ax.axhline(spec["caution"], color="orange", linestyle="--", alpha=0.45, label=caution_label)
        ax.legend(fontsize=8)

    for ax in axes[len(metric_specs):]:
        ax.axis("off")

    fig.suptitle("Internet Connection Distribution Comparison for Google Meet", fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    return fig


def summarize_metric_distributions(distributions, metric_specs=None):
    metric_specs = metric_specs or meet_comparison_metric_specs()
    rows = []
    for spec in metric_specs:
        for network_label, values in distributions[spec["key"]].items():
            rows.append({
                "metric": spec["key"],
                "network_label": network_label,
                "samples": len(values),
                "median": values.median() if len(values) else math.nan,
                "p25": values.quantile(0.25) if len(values) else math.nan,
                "p75": values.quantile(0.75) if len(values) else math.nan,
                "p95": values.quantile(0.95) if len(values) else math.nan,
            })
    return pd.DataFrame(rows)


def display_meet_connection_comparison(result_dir="internet_quality_results"):
    combined, latest_paths = load_latest_raw_runs(result_dir)
    if combined.empty:
        print("No raw CSVs found yet. Export each run first.")
        return None

    comparison = build_meet_comparison_summary(combined)
    display_columns = [
        "connection",
        "meet_status",
        "packet_loss_pct",
        "median_latency_ms",
        "jitter_ms",
        "p95_latency_ms",
        "download_median_mbps",
        "upload_median_mbps",
        "source_file",
    ]
    display(comparison[[column for column in display_columns if column in comparison.columns]])

    metric_specs = meet_comparison_metric_specs()
    distributions = build_metric_distributions(combined, metric_specs)
    fig = plot_metric_distribution_boxplots(distributions, metric_specs)
    display(fig)
    plt.close(fig)

    display(summarize_metric_distributions(distributions, metric_specs))

    numeric_columns = [
        "packet_loss_pct",
        "median_latency_ms",
        "jitter_ms",
        "p95_latency_ms",
        "download_median_mbps",
        "upload_median_mbps",
    ]
    side_by_side = comparison[[column for column in numeric_columns if column in comparison.columns]].T
    display(side_by_side)
    display(latest_paths[["network_label", "path"]])

    return {
        "combined": combined,
        "latest_paths": latest_paths,
        "comparison": comparison,
        "distributions": distributions,
    }
