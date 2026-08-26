# ₿RS Signals — MCP Server

> **Model Context Protocol** wrapper for the BRS Signals API.
> Give AI agents real-time Bitcoin regime-switch detection *before* the price moves.

---

## What Is This?

The BRS Signals MCP server exposes **11 tools** to any MCP-compatible client (Claude Desktop, Cursor, Continue, etc.). Each tool wraps a live BRS Signals API endpoint, giving AI agents access to:

| Layer | What It Sees | Data Sources |
|-------|-------------|-------------|
| **Inner Eye (X-Ray)** | On-chain behavior | Mempool fee curves, miner flows, exchange reserves |
| **Outer Eye (SolarRay)** | Off-chain context | Funding divergence, ETF flows, macro correlations |
| **Invisible Eye (Shadow)** | Absence detection | Volume drops, volatility compression, silent accumulation |

These three independent engines converge into a **single directional bias** (bullish/bearish/WAIT) — verified at **>80% directional accuracy** on a public track record.

---

## Quick Start

> **Requires Python ≥3.10** — the `mcp` SDK depends on modern typing features.

### 1. Install

```bash
# From PyPI (once published):
pip install brs-signals-mcp

# Or from source:
git clone https://github.com/bernatferragut/BRS-Signals.git
cd BRS-Signals
pip install -e ".[mcp]"
```

### 2. Run

```bash
# stdio transport (Claude Desktop, Cursor, Continue)
python -m mcp_brs

# SSE/HTTP transport (remote agents, teams, self-hosting)
python -m mcp_brs --transport sse --port 8080

# With API key (Pro tier)
BRS_API_KEY=va_yourkey_here python -m mcp_brs

# Or via the installed script entry point:
brs-mcp
brs-mcp --transport sse --port 8080
```

### 3. Configure Your MCP Client

**Local (stdio) — Claude Desktop, Cursor, Continue:**

```json
{
  "mcpServers": {
    "brs-signals": {
      "command": "python3",
      "args": ["mcp_brs/server.py"],
      "cwd": "/path/to/4.BRS-Signals",
      "env": {
        "BRS_API_KEY": "va_yourkey_here"
      }
    }
  }
}
```

**Remote (SSE) — any MCP client over HTTP:**

```json
{
  "mcpServers": {
    "brs-signals": {
      "url": "http://your-server:8080/sse"
    }
  }
}
```

**Config file locations:**
Claude Desktop → `~/Library/Application Support/Claude/claude_desktop_config.json`
Cursor → `.cursor/mcp.json` in your project
Continue → `~/.continue/config.json`

---

## Tools Reference

### Three Eyes Architecture (Primary)

#### `get_convergence`
**Get the full Three Eyes convergence picture.**

Returns all three engine verdicts (X-Ray, SolarRay, Shadow), the convergence score (0.0–1.0), which meta-regime is dominant, whether a regime shift is brewing, gamma exposure data, and the system-wide entropy gradient.

| Field | Type | Description |
|-------|------|-------------|
| `xray` | object | Inner Eye verdict — on-chain regime assessment |
| `solarray` | object | Outer Eye verdict — off-chain context |
| `shadow` | object | Invisible Eye verdict — absence/anomaly detection |
| `convergence_score` | float | 0.0–1.0: how much the three engines agree |
| `shift_brewing` | bool | `true` if entropy is rising → regime change may be imminent |
| `entropy_gradient` | float | Rate of entropy change across all streams |
| `gamma` | object | Dealer gamma exposure + flip level |

**Use when:** You need the full market structure before making any directional decision.

---

#### `get_directional_bias`
**Get the current directional bias (bullish/bearish/WAIT) with confidence.**

| Field | Type | Description |
|-------|------|-------------|
| `side` | string | `bullish`, `bearish`, or `WAIT` |
| `confidence` | float | Adjusted confidence 0–100% |
| `raw_conviction` | float | Raw conviction before regime adjustment |
| `regime` | string | Meta-regime the signal was generated in |
| `zone` | string | Price zone: `low`, `mid`, or `high` |
| `reason` | string | Human-readable explanation |
| `suppressed` | bool | `true` if filtered by noise detector |
| `btc_price` | float | BTC price when signal was generated |
| `timestamp` | string | ISO 8601 timestamp |

> ⚠️ **WAIT means NO EDGE.** Do not force a trade when the system says WAIT.
> Suppressed signals were caught by the noise filter — ignore them.

**Use when:** You need a straightforward BUY/SELL/WAIT answer for BTC.

---

#### `get_signal_history`
**Get recent decoder decisions with ZLMA filtering.**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Number of signals (1–200) |

Returns a list of past signals, each with: `timestamp`, `side`, `confidence`, `regime`, `zone`, `reason`, `suppressed`, `btc_price`.

**Use when:** You want to see the signal track record or analyze patterns over time.

---

### Regime Detection

#### `get_regime_current`
**Get the current Bitcoin market regime with conviction.**

| Field | Type | Description |
|-------|------|-------------|
| `latest_event` | object | Most recent regime event |
| `latest_event.event_type` | string | `ACCUMULATION`, `DISTRIBUTION`, `SQUEEZE_IMMINENT`, etc. |
| `latest_event.conviction` | float | How confident the detector is (0.0–1.0) |
| `latest_event.direction` | string | `BULLISH`, `BEARISH`, `NEUTRAL` |
| `active_events` | object | All currently active regime events |

**Use when:** You need the broader market phase before interpreting individual signals.

---

### On-Chain Data Sources

#### `get_fee_histogram`
**Get the mempool fee curve shape and statistics.**

| Field | Type | Description |
|-------|------|-------------|
| `curve_type` | string | `FLAT_WIDE` (accumulation), `STEEP_TALL` (panic), `BIMODAL` (whale activity) |
| `actor_profile` | string | Inferred actor behavior from fee distribution |
| `skewness` | float | Statistical skew of fee distribution |
| `kurtosis` | float | "Peakedness" of fee distribution |
| `gini_coefficient` | float | Fee spending inequality (low = uniform, high = whales dominating) |
| `entropy` | float | Diversity of fee usage (high = diverse, low = single-actor) |
| `tx_count` | int | Number of transactions analyzed |

> **FLAT_WIDE** = whales being patient (accumulation).  
> **STEEP_TALL** = retail rushing transactions (panic/FOMO).

**Use when:** You want to detect whale vs. retail behavior in the mempool.

---

#### `get_funding_divergence`
**Get cross-exchange funding rate divergence and squeeze probability.**

| Field | Type | Description |
|-------|------|-------------|
| `squeeze_probability` | float | 0–100% chance of a funding squeeze |
| `divergence_direction` | string | `BULLISH`, `BEARISH`, or `NONE` |
| `max_spread` | float | Max spread between exchange funding rates |
| `spread_velocity` | float | How fast the spread is growing (%/min) |
| `binance_rate` | float | Binance funding rate |
| `bybit_rate` | float | Bybit funding rate |
| `okx_rate` | float | OKX funding rate |
| `hyperliquid_rate` | float | Hyperliquid funding rate |

> **High squeeze probability** = traders piling onto one side → the market usually reverses against them. This is a contrarian signal.

**Use when:** You want to gauge crowd positioning for contrarian entries.

---

#### `get_stablecoin_flows`
**Get stablecoin whale transfer flows (USDT on Tron, USDC on Solana).**

| Field | Type | Description |
|-------|------|-------------|
| `flow_regime` | string | `NORMAL`, `INFLOW_SURGE` (buying), `OUTFLOW_SURGE` (selling) |
| `total_net` | float | Net stablecoin flow (positive = accumulating) |

> Whale stablecoin flows detect intent BEFORE it reaches exchanges.  
> Large USDT inflows to exchange wallets = imminent buying pressure.

**Use when:** You want to see what whales are doing before they move markets.

---

#### `get_gamma_exposure`
**Get dealer gamma exposure and gamma flip level.**

| Field | Type | Description |
|-------|------|-------------|
| `dealer_net_gamma` | float | Net dealer gamma position |
| `gamma_flip_level` | float | Price where gamma flips (key S/R) |
| `put_gamma` | float | Put gamma |
| `call_gamma` | float | Call gamma |
| `gamma_regime` | string | Gamma regime interpretation |

> **Gamma flip levels act as magnetic price levels.** Above flip = dealers accelerate trends. Below flip = dealers dampen them. Large negative gamma = explosive potential.

**Use when:** You want key price levels from the options market.

---

### Dashboard & System

#### `get_dashboard`
**Get the full dashboard bundle in one call.**

Returns: `regime_meta`, `signal`, `funding`, `suppressed` signals, `cycle_context`, `options_context`.

**Use when:** You want everything in a single API call. This is the most comprehensive endpoint.

---

#### `get_system_health`
**Quick health check of the BRS Signals system.**

Returns component-by-component status (`ok`/`error`) for all data collectors and engines.

**Use when:** You want to verify the API is operational before relying on its signals.

---

#### `get_system_counters`
**Get live data counters.**

Returns: `signals_fired` (total), `data_points` (total), `days_collecting`.

**Use when:** You want to know how much data the system has processed.

---

#### `query_db`
**Run a read-only SQL query against the BRS database.**

Tables: `decoder_decision_records`, `engine_verdict_records`, `regime_event_records`, `vao_records`, `funding_records`, etc.

Args: `query` (SQL SELECT statement). Capped at 100 rows.

**Use when:** You need signal history, regime state, or system health without spawning sqlite3 CLI.

---

#### `get_mempool_fees`
**Live Bitcoin mempool fee rates from mempool.space.**

Returns: `fastestFee`, `halfHourFee`, `economyFee`, `minimumFee` (all in sat/vB).

**Use when:** Verifying X-Ray sensor readings against live on-chain fee data.

---

#### `get_mempool_stats`
**Live mempool stats: pending tx count, total size, total fees.**

Returns: `pending_tx`, `total_vsize`, `total_fee_btc`.

**Use when:** Checking on-chain congestion level.

---

#### `get_block_tip`
**Current Bitcoin block height from mempool.space.**

Returns: `block_height`.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BRS_API_KEY` | No | — | Your API key (Pro/Max tier). Free tier works without one. |
| `BRS_API_URL` | No | `https://brs-signals.com` | Override API base URL (for self-hosted instances). NOTE: `api.brs-signals.com` has no DNS record (verified Aug 15) — do not use it. |

---

## Tiers & Rate Limits

| Tier | Price | Rate Limit | Key Required |
|------|-------|-----------|-------------|
| **Free** | $0 | 5 req/min (5-min delayed) | No |
| **Per-call** | $0.01 / query | pay-as-you-go | Free key + `?tx_signature=` |
| **Pro** | $60/mo · $600/yr ($50/mo) | Unlimited (real-time) | Yes |

**Free tier** shows outputs only — convergence score, regime classification, track record. No raw collector data (fee curves, funding, stablecoins hidden). Delay: 5 minutes. Rate: 5 req/min. Proves the Three Eyes are real without exposing the secret sauce.

**Per-call** — the Pro bias one query at a time: `GET /api/v2/bias/per-call`
returns a 402 with an exact $0.01 USDC settlement (Solana); pay it, retry with
`?tx_signature=` + your free key. Capped at $50 per rolling 30 days and
converts to Pro at the cap — never more than $50 in any 30 days. Solana now,
Base next.

**Pro tier** unlocks everything: real-time raw streams, directional bias, full history, unlimited requests.

Get a key at [https://brs-signals.com](https://brs-signals.com).

---

## Architecture

```text
┌──────────────────────────────────────────────────────┐
│                   MCP Client                          │
│         (Claude Desktop / Cursor / Continue)          │
└──────────────────────┬───────────────────────────────┘
                       │ stdio / JSON-RPC
┌──────────────────────▼───────────────────────────────┐
│              mcp_brs/server.py                        │
│  ┌─────────────────────────────────────────────────┐ │
│  │  FastMCP("brs-signals")                         │ │
│  │                                                 │ │
│  │  Tools:                                         │ │
│  │  ├─ get_convergence()      ──┐                  │ │
│  │  ├─ get_directional_bias() ──┤                  │ │
│  │  ├─ get_signal_history()   ──┤                  │ │
│  │  ├─ get_regime_current()   ──┤                  │ │
│  │  ├─ get_fee_histogram()    ──┤  httpx.AsyncClient│ │
│  │  ├─ get_funding_divergence()──┤      │           │ │
│  │  ├─ get_stablecoin_flows() ──┤      │           │ │
│  │  ├─ get_gamma_exposure()   ──┤      │           │ │
│  │  ├─ get_dashboard()        ──┤      │           │ │
│  │  ├─ get_system_health()    ──┤      │           │ │
│  │  └─ get_system_counters()  ──┘      │           │ │
│  └──────────────────────────────────────┼──────────┘ │
└─────────────────────────────────────────┼────────────┘
                                          │ HTTPS
┌─────────────────────────────────────────▼────────────┐
│              brs-signals.com                          │
│  ┌─────────────────────────────────────────────────┐ │
│  │  Three Eyes Architecture                        │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐        │ │
│  │  │ X-Ray    │ │ SolarRay │ │ Shadow   │        │ │
│  │  │ On-chain │ │ Off-chain│ │ Absence  │        │ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘        │ │
│  │       └─────────────┼────────────┘              │ │
│  │               ┌─────▼─────┐                     │ │
│  │               │Convergence│                     │ │
│  │               │  Scorer   │                     │ │
│  │               └─────┬─────┘                     │ │
│  │                     ▼                           │ │
│  │              BUY / SELL / WAIT                  │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## CLI Reference

```
python mcp_brs/server.py [--transport {stdio,sse}] [--port PORT] [--host HOST]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--transport stdio` | ✓ | stdio transport (local agents — Claude Desktop, Cursor) |
| `--transport sse` | | SSE/HTTP transport (remote agents, team servers) |
| `--port` | `8000` | Port for SSE transport |
| `--host` | `127.0.0.1` | Bind address for SSE transport |

---

## Files

| File | Purpose |
|------|---------|
| [`mcp_brs/__init__.py`](../mcp_brs/__init__.py) | Package init with exports and MCP client config docs |
| [`mcp_brs/__main__.py`](../mcp_brs/__main__.py) | Entry point for `python -m mcp_brs` |
| [`mcp_brs/server.py`](../mcp_brs/server.py) | MCP server — 11 tools, ~220 lines |
| [`requirements.txt`](../requirements.txt) | Updated with `mcp>=1.0.0` |

---

## Testing

```bash
# Verify import and tool registration
python3 -c "from mcp_brs.server import mcp; print(mcp.name)"

# List all registered tools
python3 -c "
from mcp_brs.server import mcp
tools = mcp._tool_manager._tools
for name in tools:
    print(f'  {name}')
"

# Show CLI help
python3 mcp_brs/server.py --help

# Run (stdio — for MCP clients)
python3 mcp_brs/server.py

# Run (SSE — for remote agents, test with curl)
python3 mcp_brs/server.py --transport sse --port 8080
```

---

## Health probe — verify tools return DATA, not just a handshake

Aug 15 lesson: the public endpoint passed `initialize` (200) but every tool
returned "Cannot connect to https://api.brs-signals.com" — that subdomain
has no DNS record. The handshake proves routing, NOT that data flows. After
any launch/restart, call a real tool:

```python
# streamable-http flow: initialize -> notifications/initialized -> tools/call
import httpx
BASE = "https://brs-signals.com/mcp"
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
r = httpx.post(BASE, headers=H, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "probe", "version": "1.0"}}}, timeout=20)
sid = r.headers.get("mcpsessionid") or r.headers.get("mcp-session-id")
def call(m, p):
    h = dict(H); h["Mcp-Session-Id"] = sid
    return httpx.post(BASE, headers=h, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, timeout=20)
call("notifications/initialized", {})
print(call("tools/call", {"name": "get_convergence", "arguments": {}}).text[:200])        # EXPECT real JSON
print(call("tools/call", {"name": "get_directional_bias", "arguments": {}}).text[:200])   # EXPECT 402 x402
```

Expected: `get_convergence` / `get_regime_current` → real data (keyless
free tier); `get_directional_bias` / `get_signal_history` → the 402 x402
message (the gate works through the MCP). Anything else = upstream
misconfigured.

---

## Per-client key pass-through (Q58 Option C)

Clients may send their **own** `BRS_API_KEY` on the MCP HTTP requests to
unlock their own tier per-request (Pro tools, per-key rate attribution).
The server never holds the key and never logs it.

```
# send on every streamable-http request (initialize + each tools/call):
headers = {
  "Accept": "application/json, text/event-stream",
  "X-API-Key": "va_yourkey_here",            # or: Authorization: Bearer va_yourkey_here
}
```

- No key → free tier (unchanged; Pro tools return the 402 x402 message).
- Valid key → the caller's own tier (Pro data), attributed to their key.
- Invalid key → upstream 401 `Invalid or missing API key`.

> **Aug 17 — DEPLOYED (K3-approved).** Clients can now send their own key to
> unlock Pro per-request. Review brief:
> [`plans/Q58-OptionC_k3_review.md`](../plans/Q58-OptionC_k3_review.md).

---

## Related Docs

- [BRS Signals API Docs](https://brs-signals.com/docs)
- [Three Eyes Architecture](../plans/three_eyes_architecture.md)
- [LangChain Integration](../integrations/langchain_tool.py)
- [MCP Protocol Specification](https://modelcontextprotocol.io)
