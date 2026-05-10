"""Network probing and monitor orchestration."""

import asyncio
import math
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from .config import (
    LATENCY_ENDPOINTS,
    PING_INTERVAL_SECONDS,
    SPEED_DOWNLOAD_URL,
    SPEED_INTERVAL_SECONDS,
    SPEED_UPLOAD_URL,
    TCP_TIMEOUT_SECONDS,
    UPLOAD_BYTES,
)
from .data import results_df, samples
from .labels import filename_label_from_network_name


def _stop_requested(stop_signal):
    return bool(stop_signal and stop_signal.is_set())


def wifi_interfaces():
    """Return macOS device names for Wi-Fi hardware, such as en0 or en1."""
    try:
        result = subprocess.run(
            ["/usr/sbin/networksetup", "-listallhardwareports"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []

    interfaces = []
    current_port_is_wifi = False
    for line in result.stdout.splitlines():
        if line.startswith("Hardware Port:"):
            current_port_is_wifi = "Wi-Fi" in line or "AirPort" in line
        elif current_port_is_wifi and line.startswith("Device:"):
            interfaces.append(line.split(":", 1)[1].strip())
            current_port_is_wifi = False
    return interfaces


def current_wifi_ssid():
    """Return the current macOS Wi-Fi SSID, or None if it cannot be detected."""
    for interface in wifi_interfaces() or ["en0", "en1", "en2"]:
        result = subprocess.run(
            ["/usr/sbin/networksetup", "-getairportnetwork", interface],
            check=False,
            capture_output=True,
            text=True,
        )
        output = (result.stdout or result.stderr).strip()
        prefix = "Current Wi-Fi Network: "
        if output.startswith(prefix):
            return output[len(prefix):]
    return None


def _connection_name(connection):
    name = connection.get("name") or current_wifi_ssid()
    if not name:
        raise ValueError(
            "Could not auto-detect the Wi-Fi SSID from macOS. "
            "Set the connection name manually, for example: "
            "{'name': 'Peanut Butter', 'source_ip': None}."
        )
    return name


def prepare_connections(connections):
    prepared = []
    for connection in connections:
        prepared_connection = dict(connection)
        prepared_connection["name"] = _connection_name(prepared_connection)
        prepared.append(prepared_connection)
    return prepared


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _local_addr(source_ip):
    return (source_ip, 0) if source_ip else None


def _connector(source_ip):
    family = socket.AF_INET if source_ip and "." in source_ip else 0
    return aiohttp.TCPConnector(
        local_addr=_local_addr(source_ip),
        family=family,
        ttl_dns_cache=300,
    )


async def tcp_ping_once(connection, endpoint):
    host, port, endpoint_name = endpoint
    started = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                host,
                port,
                local_addr=_local_addr(connection.get("source_ip")),
            ),
            timeout=TCP_TIMEOUT_SECONDS,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        writer.close()
        await writer.wait_closed()
        error = None
        ok = True
    except Exception as exc:
        latency_ms = math.nan
        error = type(exc).__name__
        ok = False

    return {
        "ts": _now_iso(),
        "unix_ts": time.time(),
        "connection": connection["name"],
        "source_ip": connection.get("source_ip"),
        "metric": "tcp_ping",
        "endpoint": endpoint_name,
        "latency_ms": latency_ms,
        "ok": ok,
        "error": error,
        "mbps": math.nan,
    }


async def measure_download_mbps(connection):
    started = time.perf_counter()
    total = 0
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=_connector(connection.get("source_ip")), timeout=timeout) as session:
        async with session.get(SPEED_DOWNLOAD_URL) as response:
            response.raise_for_status()
            async for chunk in response.content.iter_chunked(256 * 1024):
                total += len(chunk)
    elapsed = time.perf_counter() - started
    return (total * 8) / elapsed / 1_000_000


async def measure_upload_mbps(connection):
    payload = b"0" * UPLOAD_BYTES
    started = time.perf_counter()
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=_connector(connection.get("source_ip")), timeout=timeout) as session:
        async with session.post(SPEED_UPLOAD_URL, data=payload) as response:
            response.raise_for_status()
            await response.read()
    elapsed = time.perf_counter() - started
    return (UPLOAD_BYTES * 8) / elapsed / 1_000_000


async def ping_loop(connection, stop_at, stop_signal=None):
    i = 0
    while time.time() < stop_at and not _stop_requested(stop_signal):
        loop_started = time.perf_counter()
        endpoint = LATENCY_ENDPOINTS[i % len(LATENCY_ENDPOINTS)]
        samples.append(await tcp_ping_once(connection, endpoint))
        i += 1
        elapsed = time.perf_counter() - loop_started
        await asyncio.sleep(max(0, PING_INTERVAL_SECONDS - elapsed))


async def speed_loop(connection, stop_at, stop_signal=None):
    await asyncio.sleep(3)
    while time.time() < stop_at and not _stop_requested(stop_signal):
        for direction, measure in (("download", measure_download_mbps), ("upload", measure_upload_mbps)):
            if _stop_requested(stop_signal):
                break
            row = {
                "ts": _now_iso(),
                "unix_ts": time.time(),
                "connection": connection["name"],
                "source_ip": connection.get("source_ip"),
                "metric": direction,
                "endpoint": "cloudflare_speed",
                "latency_ms": math.nan,
                "ok": True,
                "error": None,
                "mbps": math.nan,
            }
            try:
                row["mbps"] = await measure(connection)
            except Exception as exc:
                row["ok"] = False
                row["error"] = type(exc).__name__
            samples.append(row)
        sleep_until = time.time() + SPEED_INTERVAL_SECONDS
        while time.time() < sleep_until and not _stop_requested(stop_signal):
            await asyncio.sleep(min(1, sleep_until - time.time()))


async def run_monitor(
    connections,
    duration_seconds=300,
    output_dir="internet_quality_results",
    reset_samples=True,
    stop_signal=None,
):
    """Run latency and speed probes, live-plot results, and save a CSV at the end."""
    from .plotting import plot_loop

    if reset_samples:
        samples.clear()

    connections = prepare_connections(connections)
    print("Testing:", ", ".join(connection["name"] for connection in connections))

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    stop_at = time.time() + duration_seconds

    if stop_signal:
        stop_signal.clear()

    tasks = [asyncio.create_task(plot_loop(stop_at, stop_signal=stop_signal))]
    for connection in connections:
        tasks.append(asyncio.create_task(ping_loop(connection, stop_at, stop_signal=stop_signal)))
        tasks.append(asyncio.create_task(speed_loop(connection, stop_at, stop_signal=stop_signal)))

    await asyncio.gather(*tasks)

    df = results_df()
    raw_label = "_".join(connection["name"] for connection in connections)
    run_label = filename_label_from_network_name(raw_label)
    path = Path(output_dir) / f"{run_label}_auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(path, index=False)
    print(f"Saved {len(df):,} rows to {path}")
    return df
