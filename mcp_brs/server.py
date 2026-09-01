"""
₿RS Signals — MCP Server
========================
Exposes the BRS Signals API as MCP tools for AI agents.

Endpoints wrapped:
  /api/v2/confidence          → get_convergence        (Three Eyes: all 3 engines + convergence score)
  /api/v2/bias                → get_directional_bias   (bullish/bearish/WAIT with confidence)
  /api/v2/bias/history        → get_signal_history     (Recent decoder decisions)
  /api/v2/structure           → get_regime_current     (Market regime + active events)
  /api/v2/streams/fees        → get_fee_histogram      (Mempool fee curve shape)
  /api/v2/streams/funding     → get_funding_divergence (Cross-exchange funding squeeze)
  /api/v2/streams/stablecoin  → get_stablecoin_flows   (Whale stablecoin transfers)
  /api/v2/streams/gamma       → get_gamma_exposure     (Dealer gamma + flip level)
  /api/v2/dashboard           → get_dashboard          (Bundled regime + signal + funding)
  /api/v2/system/counters     → get_system_counters    (Live data counters)
  /api/v2/health/funnel       → get_rejection_funnel   (Per-gate cycle counts: why no signal)
  /api/v1/system/health       → get_system_health      (Quick health check)
  (no API)                    → query_db               (Read-only SQL against the BRS SQLite DB)
  (mempool.space)             → get_mempool_fees       (Recommended fee rates, sat/vB)
  (mempool.space)             → get_mempool_stats      (Pending tx count, vsize, total fees)
  (mempool.space)             → get_block_tip          (Current block height)

Auth: Set BRS_API_KEY env var for paid tiers (Pro/Max).
      Free tier works without a key (rate-limited).
"""

from __future__ import annotations

import contextvars
import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# ── Configuration ──────────────────────────────────────────────────

# api.brs-signals.com has no DNS record (verified Aug 15) — default to the
# working public host. Override via BRS_API_URL for self-host.
BASE_URL = os.environ.get("BRS_API_URL", "https://brs-signals.com")
API_KEY = os.environ.get("BRS_API_KEY")

# Q58 Option C — per-client key pass-through. An HTTP request may carry the
# caller's own BRS key (Authorization: Bearer <key> or X-API-Key: <key>); the
# streamable-http middleware stashes it here for the request's duration and
# _headers() forwards it verbatim upstream. The server holds no key material
# and never logs it. No key on the request => free tier (keyless proxy).
_client_key: contextvars.ContextVar[str] = contextvars.ContextVar(
    "brs_client_key", default=""
)

# DNS-rebinding protection stays ON; the public host (via cloudflared) is added
# to the allowlist so the forwarded `Host: brs-signals.com` is not rejected (421).
_ALLOWED_HOSTS = [
    "127.0.0.1:*", "localhost:*", "[::1]:*",
    "brs-signals.com", "www.brs-signals.com",
]

mcp = FastMCP(
    "brs-signals",
    instructions="₿RS Signals — Bitcoin regime-switch detection before price moves. "
    "Three Eyes architecture: on-chain (fee curves), off-chain (funding divergence), "
    "and absence detection (shadow). Real-time bullish/bearish/WAIT signals for AI agents.",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_ALLOWED_HOSTS,
    ),
)

# ── Shared HTTP Client ─────────────────────────────────────────────

def _headers() -> dict:
    """Build request headers. Per-client key (Q58 Option C) wins over the
    server env key; none => free tier (keyless). Never logged."""
    h = {}
    key = _client_key.get() or API_KEY or ""
    if key:
        h["X-API-Key"] = key
    return h


async def _get(endpoint: str, timeout: float = 15.0) -> dict:
    """Call the BRS Signals API. Returns dict (data or error info)."""
    url = f"{BASE_URL}{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=_headers())
            if r.status_code == 401:
                return {
                    "error": "Invalid or missing API key",
                    "how_to_fix": (
                        "Set BRS_API_KEY environment variable, "
                        "or get a free key at https://brs-signals.com"
                    ),
                }
            if r.status_code == 402:
                return {
                    "error": "Payment required (x402)",
                    "pro_required": True,
                    "amount": "$50/month (Pro tier)",
                    "how_to_pay": (
                        "Send USDC on Solana or Base (via x402) or sign up at "
                        "https://brs-signals.com"
                    ),
                    "upgrade_url": "https://brs-signals.com/signup",
                    "free_tier": "Get a free API key for regime data (5 req/min)",
                }
            if r.status_code == 429:
                return {
                    "error": "Rate limit exceeded",
                    "how_to_fix": "Wait 60 seconds or upgrade to Pro/Max tier",
                }
            r.raise_for_status()
            return r.json()
    except httpx.TimeoutException:
        return {"error": "BRS API timed out", "retry": "Try again in a few seconds"}
    except httpx.ConnectError:
        return {"error": f"Cannot connect to {BASE_URL}", "retry": "Check network or BRS_API_URL"}
    except Exception as e:
        return {"error": str(e)}


def _fmt(data: dict) -> str:
    """Pretty-print dict as JSON string for MCP text response."""
    return json.dumps(data, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════
# Tools — Three Eyes Architecture (Primary)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_convergence() -> str:
    """How much do the three independent sensors agree right now?

    Call this BEFORE trusting any directional read. Agreement is scored
    pairwise: 1.00 same meta-regime, 0.85 same direction, 0.60 one sensor
    silent, 0.25 open conflict, 0.00 unreadable. High agreement means
    conditions are worth acting on; low agreement means the sensors are
    looking at different markets and the honest answer is wait.

    Returns all three verdicts (X-Ray on-chain, Pulse off-chain, Shadow
    absence), the convergence score, the dominant meta-regime
    (TRENDING_UP, TRENDING_DOWN, RANGE_ACCUMULATION, RANGE_DISTRIBUTION),
    shift_brewing (entropy rising = regime change may be imminent), gamma
    exposure, and the system entropy gradient.
    """
    return _fmt(await _get("/api/v2/confidence"))


@mcp.tool()
async def get_directional_bias() -> str:
    """Should you be trading Bitcoin right now, and in which direction?

    Returns side (bullish / bearish / WAIT) with confidence, the regime
    and zone the call was made in, the reason, btc_price and timestamp.
    WAIT is the most common answer and means no edge exists — respect it;
    do not force a trade. Confidence is normalised against how much
    evidence was reachable: sent signals typically land 0.30–0.50, so
    compare against the distribution, not 1.0. Signals suppressed by the
    noise filter are shown (suppressed=true), never hidden.

    Requires a Pro API key or x402 payment. Free alternative:
    get_convergence.
    """
    return _fmt(await _get("/api/v2/bias"))


@mcp.tool()
async def get_signal_history(limit: int = 20) -> str:
    """Recent calls and what Bitcoin did next (Pro tier).

    Each record carries timestamp, side, confidence, regime, zone, reason,
    plus outcomes where resolved (+4h/+24h returns, worst drawdown). Use
    this to verify rather than trust: outcomes are never re-scored after
    the fact. The keyless public track record lives at the website's
    track-record page (also reachable via get_rejection_funnel's sibling
    REST endpoint /api/v2/signals/track-record).

    Args:
        limit: Number of recent signals to return (1–200, default 20)
    """
    return _fmt(await _get(f"/api/v2/bias/history?limit={min(limit, 200)}"))


# ═══════════════════════════════════════════════════════════════════
# Tools — Regime Detection
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_regime_current() -> str:
    """Which game is the market playing right now?

    Returns the current regime with conviction and how long it has held —
    accumulation, distribution, trending, reorganizing — as latest_event
    plus all active_events. Use it to pick the playbook (trend-following
    vs mean-reversion vs sit out) BEFORE interpreting any individual
    reading. Free tier, no key needed.
    """
    return _fmt(await _get("/api/v2/structure"))


# ═══════════════════════════════════════════════════════════════════
# Tools — On-Chain Data Sources (the ingredients)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_fee_histogram() -> str:
    """Who is transacting on-chain right now — X-Ray's raw read (free key).

    The mempool fee curve shape: FLAT_WIDE means patient accumulation,
    STEEP_TALL means urgency or panic, BIMODAL means whale activity.


    Returns:
        - curve_type: FLAT_WIDE (accumulation), STEEP_TALL (retail panic), BIMODAL (whale activity), etc.
        - actor_profile: Inferred actor behavior from fee distribution
        - skewness, kurtosis: Statistical shape of fee distribution
        - gini_coefficient: Inequality of fee spending (low = uniform, high = whales dominating)
        - entropy: Diversity of fee usage (high = diverse activity, low = single-actor dominance)
        - tx_count: Number of transactions analyzed

    FLAT_WIDE fee curves indicate accumulation (whales being patient).
    STEEP_TALL fee curves indicate urgency/panic (retail rushing transactions).
    """
    return _fmt(await _get("/api/v2/streams/fees"))


@mcp.tool()
async def get_funding_divergence() -> str:
    """Is positioning one-sided enough to squeeze? (free key)

    Cross-exchange funding spread, velocity, and squeeze probability.
    Contrarian by design: the market usually reverses against the crowded
    side.


    Returns:
        - squeeze_probability: 0–100% chance of a funding squeeze
        - divergence_direction: Which direction the divergence points (BULLISH/BEARISH/NONE)
        - max_spread: Maximum spread between exchange funding rates
        - spread_velocity: How fast the spread is growing (%/min)
        - Per-exchange rates: Binance, Bybit, OKX, Hyperliquid

    High squeeze probability means traders are piling onto one side —
    the market usually reverses against them. This is a contrarian signal.
    """
    return _fmt(await _get("/api/v2/streams/funding"))


@mcp.tool()
async def get_stablecoin_flows() -> str:
    """Whale buying or selling intent before it reaches exchanges (Pro).

    Large USDT (Tron) and USDC (Solana) movements: inflow surges precede
    buying pressure, outflow surges precede distribution.


    Returns:
        - flow_regime: NORMAL, INFLOW_SURGE (buying pressure), OUTFLOW_SURGE (selling pressure)
        - total_net: Net stablecoin flow (positive = accumulating, negative = distributing)
        - Recent significant transfers over $1M

    Whale stablecoin flows detect buying/selling intent BEFORE it reaches exchanges.
    Large USDT inflows to exchange wallets = imminent buying pressure.
    Large USDT outflows from exchange wallets = whales cashing out.
    """
    return _fmt(await _get("/api/v2/streams/stablecoin"))


@mcp.tool()
async def get_gamma_exposure() -> str:
    """Where does dealer hedging amplify or dampen the move? (Pro stream)

    Net dealer gamma and the flip level that acts as a price magnet.


    Returns:
        - dealer_net_gamma: Net dealer gamma position
        - gamma_flip_level: Price level where gamma flips (key support/resistance)
        - put_gamma, call_gamma: Put and call gamma separately
        - gamma_regime: Current gamma regime interpretation

    Gamma flip levels act as magnetic price levels. Above flip = dealers hedge
    with the trend (accelerating). Below flip = dealers hedge against the trend
    (dampening). Large negative gamma = explosive potential.
    """
    return _fmt(await _get("/api/v2/streams/gamma"))


# ═══════════════════════════════════════════════════════════════════
# Tools — Dashboard & System
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_dashboard() -> str:
    """The full picture in one call (free key). Use the individual tools when
    you want one answer cheaply; use this when you want everything at once.

    Bundle: regime + signal + funding + suppressed signals.

    Returns:
        - regime_meta: Full regime classification with confidence and range info
        - signal: Latest bullish/bearish/WAIT with confidence and reasoning
        - funding: Cross-exchange funding squeeze data
        - suppressed: Signals that were filtered by the noise detector
        - cycle_context: Time cycle analysis (if available)
        - options_context: Deribit options market context (if available)

    This is the most comprehensive single endpoint — use it when you want
    the full picture in one call.
    """
    return _fmt(await _get("/api/v2/dashboard"))


@mcp.tool()
async def get_system_health() -> str:
    """Is the instrument operational right now?

    Component-by-component status for all collectors and engines. Call
    this first if any reading looks stale or absent — a sensor being down
    changes what every other answer means.
    """
    return _fmt(await _get("/api/v1/system/health"))


@mcp.tool()
async def get_system_counters() -> str:
    """The sample size behind everything: signals sent, data points
    collected, days collecting. Small samples cannot prove an edge — this
    tells you exactly how small.


    Returns:
        - signals_fired: Total number of trade signals generated
        - data_points: Total on-chain data points collected
        - days_collecting: How many days the system has been running
    """
    return _fmt(await _get("/api/v2/system/counters"))


@mcp.tool()
async def get_rejection_funnel(day: str = "", days: int = 0,
                               since: str = "") -> str:
    """Why no signal? The pipeline funnel in one glance (public).

    Every cycle that does not become a signal died at a specific gate. This
    returns the cycle count at each gate in order, so your agent can draw a
    survival funnel and see where reads are being rejected — the direct
    answer to "BRS rejects almost everything, prove it."

    Args:
        day: A specific UTC day (YYYY-MM-DD). Empty = today.
        days: Sum over the last N UTC days (e.g. 30). Ignored if day set.
        since: "launch" for every day on record, or a YYYY-MM-DD start date.

    Returns:
        cycles_total, emitted, signals_sent, per-gate counts, gate_order.
    """
    params = ""
    if day:
        params = f"?day={day}"
    elif days:
        params = f"?days={days}"
    elif since:
        params = f"?since={since}"
    return _fmt(await _get(f"/api/v2/health/funnel{params}"))


# ═══════════════════════════════════════════════════════════════════
# Direct Database Tools (bypass API — faster, no auth)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def query_db(query: str) -> str:
    """Run a read-only SQL query against the BRS SQLite database.
    
    Tables: decoder_decision_records, engine_verdict_records,
    regime_event_records, vao_records, funding_records, etc.
    
    Use this to check signal history, regime state, or system health
    without spawning sqlite3 CLI commands.
    
    Args:
        query: SQL SELECT statement to execute
    
    Returns:
        JSON array of result rows
    """
    import sqlite3, json
    from pathlib import Path
    db = Path(__file__).parent.parent / "data" / "vao.db"
    if not db.exists():
        return json.dumps({"error": "Database not found"})
    # Safety: only allow SELECT
    q = query.strip()
    if not q.upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries allowed"})
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(q).fetchall()
        conn.close()
        result = [dict(r) for r in rows[:100]]  # cap at 100 rows
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════
# On-Chain Data Tools (Mempool.space — X-Ray sensor verification)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_mempool_fees() -> str:
    """Live Bitcoin mempool fee rates from mempool.space.
    
    Returns recommended fees in sat/vB: fastest, half-hour, economy, minimum.
    Fees above 50 = congestion, above 100 = extreme.
    Critical for X-Ray sensor verification.
    """
    import json, httpx
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get("https://mempool.space/api/v1/fees/recommended")
            if r.status_code == 200:
                d = r.json()
                return json.dumps({
                    "fastestFee": d.get("fastestFee"),
                    "halfHourFee": d.get("halfHourFee"),
                    "economyFee": d.get("economyFee"),
                    "minimumFee": d.get("minimumFee"),
                    "unit": "sat/vB",
                    "note": "Fees above 50 = congestion, above 100 = extreme"
                }, indent=2)
            return json.dumps({"error": f"HTTP {r.status_code}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_mempool_stats() -> str:
    """Live mempool stats: pending tx count, total size in vbytes, total fees in BTC.
    
    High pending count (>200K) = congestion. Low count (<50K) = quiet.
    """
    import json, httpx
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get("https://mempool.space/api/mempool")
            if r.status_code == 200:
                d = r.json()
                return json.dumps({
                    "pending_tx": d.get("count"),
                    "total_vsize": d.get("vsize"),
                    "total_fee_btc": d.get("total_fee"),
                    "note": f"{d.get('count', 0):,} pending tx"
                }, indent=2)
            return json.dumps({"error": f"HTTP {r.status_code}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_block_tip() -> str:
    """Current Bitcoin block height from mempool.space."""
    import json, httpx
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get("https://mempool.space/api/blocks/tip/height")
            if r.status_code == 200:
                return json.dumps({"block_height": int(r.text)}, indent=2)
            return json.dumps({"error": f"HTTP {r.status_code}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════

def _run_streamable_http(args) -> None:
    """Run the streamable-http transport, with an OPT-IN API-key gate.

    The public endpoint proxies to the BRS API, which already gates Pro
    endpoints and rate-limits the free tier. `--require-key` adds a second
    layer so the endpoint is not an open firehose: every request must present
    the server key via `Authorization: Bearer <BRS_MCP_SERVER_KEY>` or
    `X-API-Key: <BRS_MCP_SERVER_KEY>` (constant-time comparison). Default OFF
    so the free-tier UX is unchanged — the operator opts in at launch.
    """
    import uvicorn
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    app = mcp.streamable_http_app()

    # Q58 Option C — per-client key pass-through (always on, independent of the
    # --require-key gate). Capture the caller's own key from the request and
    # forward it verbatim upstream; server holds nothing, never logs. No key =>
    # free tier; a key => that caller's own tier (per-key rate attribution
    # preserved upstream). Visibility: logged as enabled at startup.
    class _ClientKeyPass(BaseHTTPMiddleware):
        def __init__(self, inner_app):
            super().__init__(inner_app)

        async def dispatch(self, request, call_next):
            auth = request.headers.get("authorization", "")
            key = ""
            if auth.lower().startswith("bearer "):
                key = auth[7:].strip()
            else:
                key = (request.headers.get("x-api-key") or "").strip()
            token = _client_key.set(key)
            try:
                return await call_next(request)
            finally:
                _client_key.reset(token)

    app.add_middleware(_ClientKeyPass)

    require = bool(args.require_key)
    expected = os.environ.get("BRS_MCP_SERVER_KEY", "") if require else ""
    if require and not expected:
        print("WARNING: --require-key set but BRS_MCP_SERVER_KEY is empty — "
              "auth DISABLED; set BRS_MCP_SERVER_KEY to enforce.")
        require = False

    # Q58 security ruling: the public /mcp must run KEYLESS (free-tier proxy).
    # A server BRS_API_KEY would turn /mcp into a free Pro firehose (no
    # revocation, no `?ref=` attribution). Log the tier at startup so the
    # exposure is visible before the endpoint serves.
    _server_key = os.environ.get("BRS_API_KEY", "")
    tier = ("KEYLESS (free-tier proxy)" if not _server_key
            else "KEYED — BRS_API_KEY set (REJECTED for public launch per Q58)")
    # flush=True: stdout is block-buffered to a file under pm2; the tier must
    # be visible in the pm2 log at startup (Q58 launch condition #1).
    print(f"[brs-mcp] startup tier: {tier}", flush=True)
    print(f"[brs-mcp] streamable-http {args.host}:{args.port}{args.mount_path} "
          f"· key gate={'ON' if require else 'OFF'}", flush=True)
    if _server_key:
        print("WARNING: BRS_API_KEY is set — per Q58 do NOT run the public "
              "/mcp keyed (free Pro firehose, no revocation). Remove it.",
              flush=True)

    if require:
        import hmac

        class _KeyAuth(BaseHTTPMiddleware):
            def __init__(self, app, expected_key: str = ""):
                super().__init__(app)
                self._expected = expected_key

            async def dispatch(self, request, call_next):
                auth = request.headers.get("authorization", "")
                key = request.headers.get("x-api-key", "")
                if auth.startswith("Bearer "):
                    key = auth[len("Bearer "):].strip()
                ok = bool(key) and hmac.compare_digest(key, self._expected)
                if not ok:
                    return JSONResponse(
                        {"error": "Unauthorized — set BRS_API_KEY "
                                  "(Authorization: Bearer <key> or X-API-Key)"},
                        status_code=401,
                    )
                return await call_next(request)

        app.add_middleware(_KeyAuth, expected_key=expected)

    config = uvicorn.Config(app, host=args.host, port=args.port,
                            log_level="info")
    uvicorn.Server(config).run()


def main():
    """Run the MCP server. stdio (default), sse, or streamable-http."""
    import argparse

    parser = argparse.ArgumentParser(
        description="₿RS Signals MCP Server — Bitcoin regime-switch detection for AI agents",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport: stdio (local) | sse (legacy HTTP) | "
             "streamable-http (modern MCP over HTTP, /mcp)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8123,
        help="Port for HTTP transports (default: 8123)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP transports (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--mount-path",
        default="/mcp",
        help="Streamable-HTTP mount path (default: /mcp)",
    )
    parser.add_argument(
        "--require-key",
        action="store_true",
        help="Require BRS_MCP_SERVER_KEY via Authorization/X-API-Key header "
             "(opt-in; default off so free tier is unchanged)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="sse")
    else:  # streamable-http
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.settings.streamable_http_path = args.mount_path
        _run_streamable_http(args)


if __name__ == "__main__":
    main()
