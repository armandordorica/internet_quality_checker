"""Configuration defaults and Google Meet-oriented thresholds."""

PING_INTERVAL_SECONDS = 0.50
PLOT_REFRESH_SECONDS = 2.0
SPEED_INTERVAL_SECONDS = 45.0
TCP_TIMEOUT_SECONDS = 1.5

DOWNLOAD_BYTES = 4_000_000
UPLOAD_BYTES = 1_500_000

MEET_TARGET_DOWNLOAD_MBPS = 4.0
MEET_TARGET_UPLOAD_MBPS = 3.2
MEET_TARGET_LATENCY_MS = 150
MEET_CAUTION_LATENCY_MS = 200
MEET_GOOD_JITTER_MS = 30
MEET_OK_JITTER_MS = 50
MEET_GOOD_LOSS_PCT = 1.0
MEET_OK_LOSS_PCT = 3.0

LATENCY_ENDPOINTS = [
    ("meet.google.com", 443, "google_meet"),
    ("www.gstatic.com", 443, "google_static"),
    ("1.1.1.1", 443, "cloudflare"),
    ("8.8.8.8", 443, "google_dns"),
]

SPEED_DOWNLOAD_URL = f"https://speed.cloudflare.com/__down?bytes={DOWNLOAD_BYTES}"
SPEED_UPLOAD_URL = "https://speed.cloudflare.com/__up"
