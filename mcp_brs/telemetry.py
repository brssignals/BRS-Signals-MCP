"""
BRS-018 — minimal, non-PII MCP telemetry.

Emit append-only usage events (tool call, tier, outcome, latency) so the
marketing recap can track the audit §11.1 north-star metrics without touching
anything identifying:

  - never records API keys, tx signatures, or raw request content
  - client identity is a one-way truncated sha256 fingerprint (or "anon")
  - best-effort: recording can never break a tool call
  - opt-out via ``BRS_MCP_TELEMETRY=0``
  - path override via ``BRS_MCP_TELEMETRY_FILE`` (default data/telemetry/mcp_events.jsonl)

Each line is one JSON object::

  {"ts": "…", "tool": "brs_market_state", "tier": "free",
   "outcome": "ok", "error_code": null, "duration_ms": 12, "client": "anon"}
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_DEFAULT_FILE = "data/telemetry/mcp_events.jsonl"
_WRITE_LOCK = threading.Lock()


def _enabled() -> bool:
    """Telemetry is ON by default; set BRS_MCP_TELEMETRY=0 to opt out."""
    return os.environ.get("BRS_MCP_TELEMETRY", "1") != "0"


def _file_path() -> str:
    return os.environ.get("BRS_MCP_TELEMETRY_FILE", _DEFAULT_FILE)


def _fingerprint(client_id: Optional[str], client_key: str) -> str:
    """A stable, non-reversible identifier for a caller.

    Prefers the MCP request's own ``client_id`` (already anonymous metadata);
    otherwise a truncated sha256 of the forwarded per-client key. Never stores
    the key itself. Returns "anon" when neither is present.
    """
    if client_id:
        return "cid:" + hashlib.sha256(str(client_id).encode()).hexdigest()[:12]
    if client_key:
        return "key:" + hashlib.sha256(client_key.encode()).hexdigest()[:12]
    return "anon"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def record(
    tool: str,
    tier: str = "free",
    outcome: str = "ok",
    error_code: Optional[str] = None,
    duration_ms: Optional[int] = None,
    client_id: Optional[str] = None,
    client_key: str = "",
) -> None:
    """Append one telemetry event. Never raises — telemetry must not break a call."""
    if not _enabled():
        return
    event = {
        "ts": _iso_now(),
        "tool": tool,
        "tier": tier,
        "outcome": outcome,
        "error_code": error_code,
        "duration_ms": duration_ms,
        "client": _fingerprint(client_id, client_key),
    }
    try:
        path = Path(_file_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, separators=(",", ":")) + "\n")
    except Exception:
        # Best-effort only: a full disk / read-only FS must not surface to agents.
        return


def _load(path: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return events


def summarize(path: str | None = None) -> dict[str, Any]:
    """Aggregate the feed into the north-star metrics (audit §11.1).

    Returns counts that a marketing recap can render directly: total calls,
    per-tool/per-tier/per-outcome breakdowns, distinct caller fingerprints,
    and (where timestamps are present) 7-day and 30-day returning counts.
    """
    events = _load(path or _file_path())

    per_tool: dict[str, int] = {}
    per_tier: dict[str, int] = {}
    per_outcome: dict[str, int] = {}
    clients: set[str] = set()
    client_days: dict[str, set[str]] = {}
    errors: dict[str, int] = {}

    now = datetime.now(timezone.utc)
    for ev in events:
        tool = str(ev.get("tool", "?"))
        tier = str(ev.get("tier", "free"))
        outcome = str(ev.get("outcome", "ok"))
        client = str(ev.get("client", "anon"))
        per_tool[tool] = per_tool.get(tool, 0) + 1
        per_tier[tier] = per_tier.get(tier, 0) + 1
        per_outcome[outcome] = per_outcome.get(outcome, 0) + 1
        clients.add(client)
        if ev.get("error_code"):
            errors[str(ev["error_code"])] = errors.get(str(ev["error_code"]), 0) + 1

        ts = ev.get("ts")
        if ts:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except Exception:
                continue
            days = (now - dt).days
            if 0 <= days < 30:
                client_days.setdefault(client, set()).add(str(dt.date()))

    seven_day_returnees = sum(
        1 for days in client_days.values() if len(days) >= 2
    )
    return {
        "total_calls": len(events),
        "distinct_clients": len(clients),
        "per_tool": per_tool,
        "per_tier": per_tier,
        "per_outcome": per_outcome,
        "error_codes": errors,
        "clients_seen_last_30d": len(client_days),
        "clients_active_2plus_days_30d": seven_day_returnees,
    }
