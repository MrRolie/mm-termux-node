#!/usr/bin/env python3
"""Fetch TrendForce indicators in parallel (stdlib-only)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "https://datatrack-finwhale.trendforce.com:8000/api/v1"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

LOGGER = logging.getLogger("trendforce_fetch")


class ConfigError(ValueError):
    pass


def _parse_scalar(value: str):
    if not value:
        return ""
    if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def load_yaml_config(path: str) -> dict:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    data: dict = {}
    current_list_key: str | None = None

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue

            stripped = line.lstrip()
            if stripped.startswith("- "):
                if current_list_key is None:
                    raise ConfigError("List item found before a list key")
                item = stripped[2:].strip()
                data[current_list_key].append(_parse_scalar(item))
                continue

            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if not key:
                    raise ConfigError("Empty key in config")
                if value == "":
                    data[key] = []
                    current_list_key = key
                else:
                    data[key] = _parse_scalar(value)
                    current_list_key = None
                continue

            raise ConfigError(f"Invalid config line: {raw_line.strip()}")

    return data


def _build_url(base_url: str, indicator_id: str | int) -> str:
    params = urlencode({"fields": indicator_id})
    return f"{base_url.rstrip('/')}/data/column?{params}"


def _fetch_indicator(
    indicator_id: str | int,
    base_url: str,
    headers: dict,
    timeout: int,
    retries: int,
    backoff_base: float,
    insecure: bool,
):
    url = _build_url(base_url, indicator_id)
    request = Request(url, headers=headers)
    last_error: Exception | None = None
    context = ssl._create_unverified_context() if insecure else None

    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout, context=context) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except HTTPError as exc:
            last_error = exc
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries:
                delay = backoff_base * (2 ** attempt)
                LOGGER.warning("Retryable HTTP %s for %s (sleep %.1fs)", exc.code, indicator_id, delay)
                time.sleep(delay)
                continue
            raise
        except URLError as exc:
            last_error = exc
            if attempt < retries:
                delay = backoff_base * (2 ** attempt)
                LOGGER.warning("Network error for %s (sleep %.1fs)", indicator_id, delay)
                time.sleep(delay)
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unknown error")


def _parse_payload(payload: dict) -> tuple[list[dict], dict]:
    """Parse API response and return (rows, metadata)."""
    rows: list[dict] = []
    metadata: dict = {}

    if not isinstance(payload, dict):
        return rows, metadata

    for indicator_name, series in payload.items():
        if not isinstance(series, dict):
            continue
        data_points = series.get("data") or {}
        if not isinstance(data_points, dict):
            continue
        indicator_id = series.get("indicator_id")
        freq = series.get("freq")
        data_source = series.get("data_source")
        inferenced = series.get("inferenced")
        unit = series.get("unit")

        # Store metadata
        metadata = {
            "indicator_name": indicator_name,
            "unit": unit or "",
            "freq": freq or "",
        }

        for date_str, value in data_points.items():
            rows.append(
                {
                    "date": date_str,
                    "value": value,
                    "indicator_id": indicator_id,
                    "indicator_name": indicator_name,
                    "freq": freq,
                    "data_source": data_source,
                    "unit": unit,
                    "inferenced": inferenced,
                }
            )

    # Sort rows by date
    rows.sort(key=lambda r: r["date"])
    return rows, metadata


def load_env_file(path: str) -> dict:
    """Load environment variables from .env file (simple key=value format)."""
    if not os.path.exists(path):
        raise ConfigError(f"Environment file not found: {path}")
    env_vars = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()
    return env_vars


def load_state(path: str) -> dict:
    """Load state from JSON file, or return empty state if not exists."""
    if not os.path.exists(path):
        return {
            "version": 1,
            "indicators": {},
            "last_run": None
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, state: dict) -> None:
    """Atomically save state to JSON file."""
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, path)  # Atomic on POSIX


def get_new_datapoints(rows: list[dict], indicator_state: dict | None) -> list[dict]:
    """Return datapoints newer than last_check_date in state."""
    if not indicator_state or not indicator_state.get("last_check_date"):
        return []

    last_date = indicator_state["last_check_date"]
    new_rows = [row for row in rows if row["date"] > last_date]
    return new_rows


def calculate_growth(new_value: float, history: list[dict], n_periods: int) -> float | None:
    """Calculate relative growth rate difference: (r_t - r̄_n) / r̄_n × 100.

    This normalizes the difference by the historical average growth rate,
    making thresholds comparable across indicators with different volatility.

    Where:
    - r_t = log(P_t) - log(P_{t-1}) (current period's growth rate)
    - r̄_n = (1/n) × [log(P_{t-1}) - log(P_{t-n})] (average historical growth rate)
    - P_t = new_value (current price)
    - P_{t-1} = history[-1] (most recent historical price)
    - P_{t-n} = history[-n] (price from n periods ago)

    Returns None if insufficient history (need at least n values) or if r̄_n ≈ 0.
    """
    if len(history) < n_periods:
        return None

    # Get the required values
    P_t = new_value
    P_t_minus_1 = float(history[-1]["value"])
    P_t_minus_n = float(history[-n_periods]["value"])

    # Avoid log(0)
    if P_t <= 0 or P_t_minus_1 <= 0 or P_t_minus_n <= 0:
        return None

    import math

    # Calculate current period's growth rate
    r_t = math.log(P_t) - math.log(P_t_minus_1)

    # Calculate average historical growth rate
    r_bar_n = (1 / n_periods) * (math.log(P_t_minus_1) - math.log(P_t_minus_n))

    # Avoid division by zero or very small values
    if abs(r_bar_n) < 1e-10:
        # If historical average growth is essentially zero, return the absolute difference
        # This handles cases where prices have been stable
        return (r_t - r_bar_n) * 100

    # Calculate relative difference: (r_t - r̄_n) / r̄_n × 100
    relative_diff = ((r_t - r_bar_n) / r_bar_n) * 100

    return relative_diff


def send_pushover_notification(
    user_key: str,
    api_token: str,
    message: str,
    title: str,
    timeout: int = 30
) -> bool:
    """Send Pushover notification using stdlib urllib.

    Returns True if successful, False otherwise.
    """
    url = "https://api.pushover.net/1/messages.json"
    data = urlencode({
        "token": api_token,
        "user": user_key,
        "message": message,
        "title": title,
    }).encode("utf-8")

    request = Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("status") == 1
    except (HTTPError, URLError) as exc:
        LOGGER.error("Pushover notification failed: %s", exc)
        return False


def format_alert_message(
    indicator_name: str,
    growth_pct: float,
    threshold_pct: float,
    new_value: float,
    unit: str,
    date: str
) -> tuple[str, str]:
    """Format Pushover notification message and title.

    Returns (title, message) tuple.
    """
    direction = "increased" if growth_pct > 0 else "decreased"
    title = f"TrendForce Alert: {indicator_name}"
    message = (
        f"{indicator_name} {direction} by {abs(growth_pct):.1f}% "
        f"(threshold: {threshold_pct:.1f}%)\n\n"
        f"New value: {new_value:.3f} {unit}\n"
        f"Date: {date[:10]}"  # Just YYYY-MM-DD
    )
    return title, message


def update_indicator_state(
    state: dict,
    indicator_id: int,
    new_rows: list[dict],
    metadata: dict,
    max_history: int
) -> None:
    """Update state with new datapoints, maintaining history limit."""
    indicator_key = str(indicator_id)

    if indicator_key not in state["indicators"]:
        state["indicators"][indicator_key] = {
            "indicator_id": indicator_id,
            "indicator_name": metadata["indicator_name"],
            "unit": metadata["unit"],
            "freq": metadata["freq"],
            "last_check_date": None,
            "last_check_value": None,
            "history": []
        }

    ind_state = state["indicators"][indicator_key]

    # Add new rows to history
    for row in new_rows:
        ind_state["history"].append({
            "date": row["date"],
            "value": row["value"]
        })

    # Update last_check from most recent row
    if new_rows:
        latest = new_rows[-1]
        ind_state["last_check_date"] = latest["date"]
        ind_state["last_check_value"] = latest["value"]

    # Trim history to max_history
    if len(ind_state["history"]) > max_history:
        ind_state["history"] = ind_state["history"][-max_history:]


def initialize_indicator_state(
    state: dict,
    indicator_id: int,
    all_rows: list[dict],
    metadata: dict,
    n_periods: int
) -> None:
    """Initialize state for first run with last n_periods of historical data.

    Does NOT trigger alerts (initialization only).
    """
    indicator_key = str(indicator_id)

    # Sort rows by date (should already be sorted)
    sorted_rows = sorted(all_rows, key=lambda r: r["date"])

    # Take last n_periods + 1 (n_periods for history, +1 for last_check)
    relevant_rows = sorted_rows[-(n_periods + 1):] if len(sorted_rows) > n_periods else sorted_rows

    if not relevant_rows:
        return

    # Last row becomes last_check
    last_row = relevant_rows[-1]
    history_rows = relevant_rows[:-1] if len(relevant_rows) > 1 else []

    state["indicators"][indicator_key] = {
        "indicator_id": indicator_id,
        "indicator_name": metadata["indicator_name"],
        "unit": metadata["unit"],
        "freq": metadata["freq"],
        "last_check_date": last_row["date"],
        "last_check_value": last_row["value"],
        "history": [{"date": r["date"], "value": r["value"]} for r in history_rows]
    }

    LOGGER.info(
        "Initialized state for indicator %s: last_date=%s, history_size=%d",
        indicator_id,
        last_row["date"][:10],
        len(history_rows)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor TrendForce indicators and send alerts")
    parser.add_argument(
        "--config",
        default=os.path.join("config", "industry_ids.yaml"),
        help="Path to YAML config file",
    )
    parser.add_argument("--concurrency", type=int, default=None, help="Max parallel workers")
    parser.add_argument("--timeout", type=int, default=None, help="Request timeout seconds")
    parser.add_argument("--retries", type=int, default=None, help="Retry count")
    parser.add_argument("--backoff-base", type=float, default=None, help="Backoff base seconds")
    parser.add_argument("--base-url", default=None, help="API base URL override")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable SSL verification (use only if necessary)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip sending notifications (for testing)",
    )

    args = parser.parse_args()

    config = load_yaml_config(args.config)

    # Validate required fields
    indicator_ids = config.get("indicator_ids")
    if not indicator_ids:
        raise ConfigError("Config must include indicator_ids list")
    if not isinstance(indicator_ids, list):
        raise ConfigError("indicator_ids must be a list")

    # Get config values (with CLI overrides)
    concurrency = args.concurrency or int(config.get("concurrency") or 4)
    timeout = args.timeout or int(config.get("timeout") or 30)
    retries = args.retries if args.retries is not None else int(config.get("retries") or 3)
    backoff_base = args.backoff_base if args.backoff_base is not None else float(config.get("backoff_base") or 1.5)
    base_url = args.base_url or str(config.get("base_url") or DEFAULT_BASE_URL)
    insecure = args.insecure or bool(config.get("insecure") or False)

    default_threshold = float(config.get("default_threshold") or 10.0)
    default_n_periods = int(config.get("default_n_periods") or 3)

    # Per-indicator config (flattened approach)
    indicator_configs = {}
    for ind_id in indicator_ids:
        indicator_configs[ind_id] = {
            "threshold": float(config.get(f"indicator_{ind_id}_threshold") or default_threshold),
            "n_periods": int(config.get(f"indicator_{ind_id}_n_periods") or default_n_periods),
        }

    # Load environment variables
    env_file = config.get("env_file", ".env")
    if not os.path.isabs(env_file):
        config_dir = os.path.dirname(os.path.abspath(args.config))
        base_dir = os.path.abspath(os.path.join(config_dir, os.pardir))
        env_file = os.path.join(base_dir, env_file)

    try:
        env_vars = load_env_file(env_file)
    except ConfigError as exc:
        LOGGER.error("Failed to load environment: %s", exc)
        return 1

    pushover_user = env_vars.get("PUSHOVER_USER_KEY")
    pushover_token = env_vars.get("PUSHOVER_API_TOKEN")

    if not pushover_user or not pushover_token:
        LOGGER.error("PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN required in %s", env_file)
        return 1

    # Load state file
    state_file = config.get("state_file", "data/state.json")
    if not os.path.isabs(state_file):
        config_dir = os.path.dirname(os.path.abspath(args.config))
        base_dir = os.path.abspath(os.path.join(config_dir, os.pardir))
        state_file = os.path.join(base_dir, state_file)

    # Ensure data directory exists
    state_dir = os.path.dirname(state_file)
    if state_dir and not os.path.exists(state_dir):
        os.makedirs(state_dir, exist_ok=True)

    state = load_state(state_file)
    is_first_run = not state.get("indicators")

    LOGGER.info("Monitoring %d indicators with %d workers", len(indicator_ids), concurrency)
    if is_first_run:
        LOGGER.info("First run detected - will initialize state without sending alerts")
    if args.dry_run:
        LOGGER.info("DRY RUN MODE - notifications will not be sent")

    # Parallel fetch
    failures: list[str] = []
    new_datapoints_count = 0
    alerts_sent = 0

    max_history = max([cfg["n_periods"] for cfg in indicator_configs.values()]) + 5  # Buffer

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_map = {
            executor.submit(
                _fetch_indicator,
                indicator_id,
                base_url,
                DEFAULT_HEADERS,
                timeout,
                retries,
                backoff_base,
                insecure,
            ): indicator_id
            for indicator_id in indicator_ids
        }

        for future in as_completed(future_map):
            indicator_id = future_map[future]

            try:
                payload = future.result()
            except Exception as exc:  # noqa: BLE001
                LOGGER.error("Failed to fetch %s: %s", indicator_id, exc)
                failures.append(str(indicator_id))
                continue

            # Parse payload
            rows, metadata = _parse_payload(payload)
            if not rows:
                LOGGER.warning("No rows returned for %s", indicator_id)
                continue

            # Get indicator config
            ind_config = indicator_configs[indicator_id]
            threshold_pct = ind_config["threshold"]
            n_periods = ind_config["n_periods"]

            # Check if first run for this indicator
            indicator_key = str(indicator_id)
            if is_first_run or indicator_key not in state["indicators"]:
                initialize_indicator_state(state, indicator_id, rows, metadata, n_periods)
                continue

            # Get new datapoints
            ind_state = state["indicators"][indicator_key]
            new_rows = get_new_datapoints(rows, ind_state)

            if not new_rows:
                LOGGER.info("No new datapoints for %s", indicator_id)
                continue

            LOGGER.info("Found %d new datapoint(s) for %s", len(new_rows), indicator_id)
            new_datapoints_count += len(new_rows)

            # Process each new datapoint
            # Build temporary history for calculating growth across multiple new datapoints
            # Include last_check_value so we have P_{t-1} for the first new datapoint
            temp_history = list(ind_state["history"])
            if ind_state.get("last_check_value"):
                temp_history.append({
                    "date": ind_state["last_check_date"],
                    "value": ind_state["last_check_value"]
                })

            for new_row in new_rows:
                new_value = float(new_row["value"])

                # Calculate growth rate difference using temporary history
                growth_pct = calculate_growth(new_value, temp_history, n_periods)

                if growth_pct is None:
                    LOGGER.warning(
                        "Insufficient history for %s (need %d periods, have %d)",
                        indicator_id,
                        n_periods,
                        len(temp_history)
                    )
                else:
                    LOGGER.info(
                        "%s: new value %.3f %s (growth: %+.1f%%)",
                        metadata["indicator_name"],
                        new_value,
                        metadata["unit"],
                        growth_pct
                    )

                    # Check threshold
                    if abs(growth_pct) > threshold_pct:
                        title, message = format_alert_message(
                            metadata["indicator_name"],
                            growth_pct,
                            threshold_pct,
                            new_value,
                            metadata["unit"],
                            new_row["date"]
                        )

                        if args.dry_run:
                            LOGGER.info("[DRY RUN] Would send alert: %s", title)
                        else:
                            success = send_pushover_notification(
                                pushover_user,
                                pushover_token,
                                message,
                                title,
                                timeout
                            )
                            if success:
                                LOGGER.info("Alert sent for %s", indicator_id)
                                alerts_sent += 1
                            else:
                                LOGGER.error("Failed to send alert for %s", indicator_id)

                # Update temp history for next iteration (within same batch)
                temp_history.append({
                    "date": new_row["date"],
                    "value": new_row["value"]
                })
                if len(temp_history) > max_history:
                    temp_history = temp_history[-max_history:]

            # Update indicator state
            update_indicator_state(state, indicator_id, new_rows, metadata, max_history)

    # Save state
    try:
        save_state(state_file, state)
        LOGGER.info("State saved to %s", state_file)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to save state: %s", exc)
        return 1

    # Summary
    LOGGER.info(
        "Summary: %d new datapoints, %d alerts sent, %d failures",
        new_datapoints_count,
        alerts_sent,
        len(failures)
    )

    if failures:
        LOGGER.error("Failed indicators: %s", ", ".join(failures))
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    sys.exit(main())
