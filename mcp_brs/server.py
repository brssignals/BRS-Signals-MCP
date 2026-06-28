"""
₿RS Signals — MCP Server
========================
Exposes the BRS Signals API as MCP tools for AI agents.

Endpoints wrapped:
  /api/v2/convergence          → get_convergence        (Three Eyes architecture: all 3 engines + convergence score)
  /api/v2/signal/current       → get_directional_bias   (bullish/bearish/WAIT with confidence)
  /api/v2/signal/history       → get_signal_history     (Recent decoder decisions)
  /api/v2/regime/current       → get_regime_current     (Market regime + active events)
  /api/v2/fee-histogram/current → get_fee_histogram     (Mempool fee curve shape)
  /api/v2/funding-divergence/current → get_funding_divergence (Cross-exchange funding squeeze)
  /api/v2/stablecoin-flow/current → get_stablecoin_flows (Whale stablecoin transfers)
  /api/v2/gamma                → get_gamma_exposure     (Dealer gamma + flip level)
  /api/v2/dashboard            → get_dashboard          (Bundled regime + signal + funding)
  /api/v2/system/counters      → get_system_counters    (Live data counters)
  /api/v1/system/health        → get_system_health      (Quick health check)

Auth: Set BRS_API_KEY env var for paid tiers (Pro/Max).
      Free tier works without a key (rate-limited).
"""

from __future__ import annotations

import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

# ── Configuration ──────────────────────────────────────────────────

BASE_URL = os.environ.get("BRS_API_URL", "https://api.brs-signals.com")
API_KEY = os.environ.get("BRS_API_KEY")

mcp = FastMCP(
    "brs-signals",
    instructions="₿RS Signals — Bitcoin regime-switch detection before price moves. "
    "Three Eyes architecture: on-chain (fee curves), off-chain (funding divergence), "
    "and absence detection (shadow). Real-time bullish/bearish/WAIT signals for AI agents.",
)

# ── Shared HTTP Client ─────────────────────────────────────────────

def _headers() -> dict:
    """Build request headers. Free tier: no key. Pro/Max: X-API-Key."""
    h = {}
    if API_KEY:
        h["X-API-Key"] = API_KEY
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
                    "amount": "$60/month (Pro tier)",
                    "how_to_pay": (
                        "Send USDC via Solana Pay or sign up at "
                        "https://brs-signals.com"
                    ),
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
    """Get the full Three Eyes convergence picture.

    Returns:
        - All three engine verdicts (X-Ray inner eye, SolarRay outer eye, Shadow invisible eye)
        - Convergence score (0.0–1.0): how much the engines agree
        - Which meta-regime is dominant (TRENDING_UP, TRENDING_DOWN, RANGE_ACCUMULATION, RANGE_DISTRIBUTION)
        - shift_brewing: True if entropy is rising (regime change may be imminent)
        - Gamma exposure data
        - System-wide entropy gradient

    Use this to understand the overall market structure before making directional decisions.
    """
    return _fmt(await _get("/api/v2/convergence"))


@mcp.tool()
async def get_directional_bias() -> str:
    """Get the current directional bias (bullish/bearish/WAIT) with confidence.

    Returns:
        - side: bullish, bearish, or WAIT (when no clear edge)
        - confidence: Adjusted confidence 0–100%
        - raw_conviction: Raw conviction before regime adjustment
        - regime: Meta-regime the signal was generated in
        - zone: Price zone (low/mid/high)
        - reason: Human-readable explanation of the signal
        - suppressed: True if signal was suppressed (noise filter)
        - btc_price: BTC price when signal was generated
        - timestamp: When the signal was generated

    The WAIT side means the system sees no edge — do NOT force a trade.
    Suppressed signals were filtered by the noise detector.
    """
    return _fmt(await _get("/api/v2/signal/current"))


@mcp.tool()
async def get_signal_history(limit: int = 20) -> str:
    """Get recent decoder decisions (bullish/bearish/WAIT with ZLMA filtering).

    Args:
        limit: Number of recent signals to return (1–200, default 20)

    Returns list of signals with: timestamp, side, confidence, regime, zone, reason.
    """
    return _fmt(await _get(f"/api/v2/signal/history?limit={min(limit, 200)}"))


# ═══════════════════════════════════════════════════════════════════
# Tools — Regime Detection
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_regime_current() -> str:
    """Get the current Bitcoin market regime with conviction.

    Returns:
        - latest_event: Most recent regime event (event_type, conviction, direction, etc.)
        - active_events: All currently active regime events

    Regime types include: ACCUMULATION, DISTRIBUTION, SQUEEZE_IMMINENT, TRENDING, etc.
    Use this to understand the broader market phase before interpreting individual signals.
    """
    return _fmt(await _get("/api/v2/regime/current"))


# ═══════════════════════════════════════════════════════════════════
# Tools — On-Chain Data Sources (the ingredients)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_fee_histogram() -> str:
    """Get the current mempool fee curve shape and statistics.

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
    return _fmt(await _get("/api/v2/fee-histogram/current"))


@mcp.tool()
async def get_funding_divergence() -> str:
    """Get cross-exchange funding rate divergence and squeeze probability.

    Returns:
        - squeeze_probability: 0–100% chance of a funding squeeze
        - divergence_direction: Which direction the divergence points (BULLISH/BEARISH/NONE)
        - max_spread: Maximum spread between exchange funding rates
        - spread_velocity: How fast the spread is growing (%/min)
        - Per-exchange rates: Binance, Bybit, OKX, Hyperliquid

    High squeeze probability means traders are piling onto one side —
    the market usually reverses against them. This is a contrarian signal.
    """
    return _fmt(await _get("/api/v2/funding-divergence/current"))


@mcp.tool()
async def get_stablecoin_flows() -> str:
    """Get stablecoin whale transfer flows (USDT on Tron, USDC on Solana).

    Returns:
        - flow_regime: NORMAL, INFLOW_SURGE (buying pressure), OUTFLOW_SURGE (selling pressure)
        - total_net: Net stablecoin flow (positive = accumulating, negative = distributing)
        - Recent significant transfers over $1M

    Whale stablecoin flows detect buying/selling intent BEFORE it reaches exchanges.
    Large USDT inflows to exchange wallets = imminent buying pressure.
    Large USDT outflows from exchange wallets = whales cashing out.
    """
    return _fmt(await _get("/api/v2/stablecoin-flow/current"))


@mcp.tool()
async def get_gamma_exposure() -> str:
    """Get dealer gamma exposure and gamma flip level.

    Returns:
        - dealer_net_gamma: Net dealer gamma position
        - gamma_flip_level: Price level where gamma flips (key support/resistance)
        - put_gamma, call_gamma: Put and call gamma separately
        - gamma_regime: Current gamma regime interpretation

    Gamma flip levels act as magnetic price levels. Above flip = dealers hedge
    with the trend (accelerating). Below flip = dealers hedge against the trend
    (dampening). Large negative gamma = explosive potential.
    """
    return _fmt(await _get("/api/v2/gamma"))


# ═══════════════════════════════════════════════════════════════════
# Tools — Dashboard & System
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_dashboard() -> str:
    """Get the full dashboard bundle: regime + signal + funding + suppressed signals.

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
    """Quick health check of the BRS Signals system.

    Returns component status (ok/error) for all data collectors and engines.
    Use this to verify the API is operational before relying on its signals.
    """
    return _fmt(await _get("/api/v1/system/health"))


@mcp.tool()
async def get_system_counters() -> str:
    """Get live data counters: total signals fired, data points collected, days tracking.

    Returns:
        - signals_fired: Total number of trade signals generated
        - data_points: Total on-chain data points collected
        - days_collecting: How many days the system has been running
    """
    return _fmt(await _get("/api/v2/system/counters"))


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

def main():
    """Run the MCP server. Supports stdio (default) and SSE/HTTP transports."""
    import argparse

    parser = argparse.ArgumentParser(
        description="₿RS Signals MCP Server — Bitcoin regime-switch detection for AI agents",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol: stdio (local agents) or sse (remote agents over HTTP)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE/HTTP transport (default: 8000)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE/HTTP transport (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
