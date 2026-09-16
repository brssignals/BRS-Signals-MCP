# ₿RS Signals — MCP Server

> **Model Context Protocol** wrapper for the BRS Signals API.
> Give AI agents real-time Bitcoin regime-switch detection *before* the price moves.

---

## What Is This?

The BRS Signals MCP server exposes **7 tools** to any MCP-compatible client
(Claude Desktop, Cursor, Continue, etc.). Each tool wraps a live BRS Signals
API endpoint.

| Layer | What It Sees | Data Sources |
|-------|-------------|-------------|
| **Inner Eye (X-Ray)** | On-chain behavior | Mempool fee curves, miner flows, exchange reserves |
| **Outer Eye (SolarRay)** | Off-chain context | Funding divergence, whale flows, macro correlations |
| **Invisible Eye (Shadow)** | Absence detection | Volume drops, volatility compression, silent accumulation |

These three independent engines converge into a **single directional posture**
(bullish / bearish / WAIT) — the most common answer is **WAIT**, because the
system rejects almost every read. The gate-by-gate rejection funnel and the
full track record are public, so agents can audit the silence rather than take
the claim on faith.

---

## Don't trust us — query us

Before you trust a single signal, verify the system with two **keyless** tools:

```
"BRS Signals claims it rejects almost every read. Pull its public track
record (brs_audit_track_record) and today's rejection funnel
(brs_rejection_funnel), and tell me: does the data support the claim,
and what happened after each call at +4h and +24h?"
```

No API key, no payment, no signup. The honesty surface is open by design.

---

## Quick Start

> **Requires Python ≥3.10** — the `mcp` SDK depends on modern typing features.

### 1. Install

```bash
# From PyPI:
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

# With API key (unlocks the full 7-tool surface)
BRS_API_KEY=va_yourkey_here python -m mcp_brs

# Or via the installed script entry point:
brs-mcp
```

For remote use, do not self-host — point your client at the public
streamable-http endpoint `https://brs-signals.com/mcp` (see below).

### 3. Configure Your MCP Client

**Remote (streamable-http) — zero install, keyless free tier:**

```json
{
  "mcpServers": {
    "brs-signals": {
      "type": "http",
      "url": "https://brs-signals.com/mcp"
    }
  }
}
```

**Local (stdio) — Claude Desktop, Cursor, Continue:**

```json
{
  "mcpServers": {
    "brs-signals": {
      "command": "python3",
      "args": ["-m", "mcp_brs"],
      "env": {
        "BRS_API_KEY": "va_yourkey_here"
      }
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

Discovery is **authorization-scoped** (BRS-013): keyless callers see only the
4 Free tools; a caller presenting a key sees all 7. The upstream API still
enforces Pro on call — no Pro tool serves data keyless.

> **Find the paid tool:** `brs_market_state` (free) shows regime, convergence,
> and health first. Directional posture is payable **per-call via x402** — call
> `brs_decision_context` with **no key**, read `error.payment` from the
> `PAYMENT_REQUIRED` result, pay the challenge, then re-call with the
> `tx_signature` to receive the posture. No signup required (BRS-017/BRS-021).

### Free — no key required

#### `brs_market_state`
**The canonical current market posture. Call this FIRST.**

Bundles three public, keyless reads into one call:

| Field | Description |
|-------|-------------|
| `market_structure` | The regime — which game the market is playing |
| `convergence` | How much the three sensors agree (0.0–1.0) |
| `system_health` | Whether the instrument is operational |

If any read is stale or a sensor is down, that changes what every other answer
means — check health before trusting a directional read.

**Use when:** You need the full market structure before making any directional
decision.

#### `brs_audit_track_record`
**The keyless public proof — every call BRS has made and what Bitcoin did next.**

| Field | Description |
|-------|-------------|
| `signals[]` | Past calls, most recent first |
| `signals[].ts` | Call timestamp |
| `signals[].dir` | `bullish` or `bearish` |
| `signals[].price` | BTC price at call time |
| `signals[].conf` | Confidence (0–100) |
| `signals[].regime` | Meta-regime at call time |
| `signals[].zone` | Price zone: `low`, `mid`, `high` |
| `signals[].r4` / `r24` | +4h / +24h return % (when resolved) |
| `signals[].mae` / `mfe` | Worst drawdown / best upside % |

Outcomes are fixed once written and never re-scored — this is auditable
evidence, not marketing. Parameter: `limit` (1–500, default 100).

**Use when:** You need to audit the system's real silence and hit rate before
trusting any signal.

#### `brs_rejection_funnel`
**Why no signal? The pipeline funnel in one glance.**

Every cycle that does not become a signal died at a specific gate. This returns
the cycle count at each gate in order, so an agent can draw a survival funnel
and see where reads are rejected. Parameters: `day` (YYYY-MM-DD), `days` (sum
over last N UTC days), `since` (`"launch"` or a YYYY-MM-DD).

**Use when:** Answering "BRS rejects almost everything — prove it."

#### `brs_system_status`
**Instrument health, SLO standing, and the sample size behind every reading.**

| Field | Description |
|-------|-------------|
| `health` | Collector/engine status and last-good timestamps |
| `counters` | Signals sent, data points collected, days collecting |
| `slo` | Status, measured `latency_ms`, and registry SLO fields |

The `slo` block (BRS-019/BRS-021d) is what registry listings report. It keeps
**configured targets** (promises) apart from **measured results** (observations):

| `slo.*` | Description |
|---------|-------------|
| `status` | `active` / `degraded` / `unavailable` |
| `status_detail` | Why — always names the stale/unhealthy part |
| `configured.compliance_pct` | 100 — generated from canonical metadata (drift-checked) |
| `configured.compliance_note` | **Scope of that %**: registry metadata checks only — NOT protocol conformance, NOT operational health |
| `measured.uptime_24h_pct` | `100.0` only when the current boot covers the full window |
| `measured.uptime_note` | States the boot-epoch convention (`None` ≠ 100 after a restart) |
| `measured.boot_epoch` | ISO start of the process's current life |
| `measured.uptime_seconds` | Seconds of the current boot |
| `measured.latency_ms` | Measured round-trip of this call |
| `measured.measured_at` | ISO timestamp of this measurement |
| `observation_window.uptime_window_hours` | 24 — the window the uptime % covers |
| `observation_window.covered` | `true` when the boot + loop cover that window |
| `observation_window.insufficient_history` | `true` when uptime is `None` (never fabricated) |

Call this when any reading looks stale, and to see exactly how small the sample
behind a claim is. Small samples cannot prove an edge.

### Freshness & expiry (every envelope)

Every result carries `as_of`, `freshness_seconds`, `valid_for_seconds`, and
`status`. `as_of` is the **underlying observation time** — not the request time.
`freshness_seconds` = `now − as_of`; once it exceeds `valid_for_seconds` (90 s)
the `status` flips `stale`. A stalled data source therefore ages a reading and
eventually reports `stale` or `unavailable`, so an agent can tell "old data"
apart from "quiet market". Ledger/aggregate tools (`brs_history`,
`brs_audit_track_record`, `brs_rejection_funnel`, `brs_system_status` counters)
carry no observation instant and report request-time `as_of` with
`freshness_seconds` 0. `unavailable` means **insufficient data to evaluate**
(e.g. the decoder's "no decisions yet"), distinct from a successfully computed
`WAIT`, which stays `ok`.

**Use when:** Verifying the API is operational before relying on its readings.

### Pro — key or x402 required

#### `brs_decision_context`
**Directional posture (bullish / bearish / WAIT) with evidence and caveats.**

| Field | Description |
|-------|-------------|
| `side` | `bullish`, `bearish`, or `WAIT` |
| `confidence` | Normalised against reachable evidence (sent calls ≈ 0.30–0.50) |
| `regime` / `zone` | The regime and price zone the read was made in |
| `reason` | Human-readable explanation |
| `suppressed` | `true` if filtered by the noise detector (shown, never hidden) |
| `btc_price` | BTC price at read time |
| `timestamp` | ISO 8601 timestamp |

> **WAIT means NO EDGE.** This is context, not an instruction to trade.
> Suppressed reads are shown (`suppressed=true`), never hidden.

**Payment (x402, per-call).** This is the metered Pro posture. Parameters:
`tx_signature` (empty on first call), `chain` (`solana` | `base`), `ref`
(attribution). A Pro key skips payment entirely.

1. Call with no `tx_signature`. If `status=error` and
   `error.code=PAYMENT_REQUIRED`, read `error.payment`: it carries the exact
   `amount`, `currency`, `asset`, `networks`, `recipient`, `resource`, `scheme`,
   `max_timeout_seconds`, and `request_digest` you need to build the payment.
2. Pay on an advertised rail (Solana or Base), then re-call with the
   `tx_signature` (and matching `chain`/`ref`) to get the metered result.
3. Retries are idempotent — the same `tx_signature` is never charged twice.
   Enforce your own max-per-call / max-per-day policy against `error.payment`
   before paying (spend cap: 3 re-calls per request).

**Use when:** You need the directional posture. Free alternative:
`brs_market_state`.

#### `brs_history`
**Recent calls and what Bitcoin did next.**

Each record carries timestamp, side, confidence, regime, zone, reason, plus
resolved outcomes where available (+4h/+24h returns, worst drawdown).
Outcomes are fixed once written and never re-scored. Parameter: `limit`
(1–200, default 20).

**Use when:** You want to verify rather than trust — inspect the signal history.

#### `brs_raw_stream`
**Raw pre-price stream for explicit decomposition.**

| `stream` value | What it returns |
|----------------|-----------------|
| `fees` | Mempool fee-curve shape (X-Ray's raw read) |
| `funding` | Cross-exchange funding spread and squeeze probability |
| `stablecoin` | Whale stablecoin transfers (USDT/USDC) |
| `gamma` | Dealer gamma exposure and flip level |

These are the ingredients behind the reads, not standalone trade signals.
Some streams require a Pro API key.

**Use when:** You want to decompose the signal into its raw inputs.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BRS_API_KEY` | No | — | Your API key (Pro tier). Free tier works without one. |
| `BRS_API_URL` | No | `https://brs-signals.com` | Override API base URL (for self-hosted instances). NOTE: `api.brs-signals.com` has no DNS record (verified Aug 15) — do not use it. |
| `BRS_MCP_TELEMETRY` | No | `1` | Set `0` to opt out of the anonymous usage feed (BRS-018). |
| `BRS_MCP_TELEMETRY_FILE` | No | `data/telemetry/mcp_events.jsonl` | Where the append-only usage feed is written. |

### Telemetry (BRS-018)

Every tool call appends one JSON line to the usage feed. It records **only**
what the marketing recap needs to track the north-star metrics — tool name,
tier, outcome, error code, latency, and a one-way fingerprint of the caller.
It never records your API key, a tx signature, or request content. The
fingerprint is a truncated SHA-256, so callers are counted without being
identified. Set `BRS_MCP_TELEMETRY=0` to disable it.

---

## Tiers & Rate Limits

| Tier | Price | Rate Limit | Key Required |
|------|-------|-----------|-------------|
| **Free** | $0 | 5 req/min | No |
| **Per-call** | $0.01 / query | pay-as-you-go | Free key + `?tx_signature=` |

**Free tier** shows outputs only — convergence score, regime classification,
track record, rejection funnel, system status. No raw collector data (fee
curves, funding, stablecoins hidden). Rate: 5 req/min.

**Per-call** — the full reading one query at a time: `GET /api/v2/bias/per-call`
returns a 402 with an exact $0.01 USDC settlement (Solana or Base); pay it,
retry with `?tx_signature=` + your free key. Capped at $50 per rolling 30 days
— never more than $50 in any 30 days.

Get a key at [https://brs-signals.com](https://brs-signals.com).

---

## Architecture

```text
┌──────────────────────────────────────────────────────┐
│                   MCP Client                         │
│         (Claude Desktop / Cursor / Continue)         │
└──────────────────────┬───────────────────────────────┘
                        │ stdio / streamable-http
┌──────────────────────▼───────────────────────────────┐
│              mcp_brs/server.py                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │  _TieredFastMCP("brs-signals")                  │ │
│  │                                                 │ │
│  │  Free (keyless):                                │ │
│  │  ├─ brs_market_state                            │ │
│  │  ├─ brs_audit_track_record                      │ │
│  │  ├─ brs_rejection_funnel                        │ │
│  │  └─ brs_system_status                           │ │
│  │  Pro (keyed / x402):                            │ │
│  │  ├─ brs_decision_context                        │ │
│  │  ├─ brs_history                                 │ │
│  │  └─ brs_raw_stream                              │ │
│  └───────────────────────┬─────────────────────────┘ │
│                          │ pooled httpx.AsyncClient  │
└──────────────────────────┼───────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼───────────────────────────┐
│              brs-signals.com                         │
│  ┌─────────────────────────────────────────────────┐ │
│  │  Three Eyes Architecture                        │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐         │ │
│  │  │ X-Ray    │ │ SolarRay │ │ Shadow   │         │ │
│  │  │ On-chain │ │ Off-chain│ │ Absence  │         │ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘         │ │
│  │       └─────────────┼────────────┘              │ │
│  │               ┌─────▼─────┐                     │ │
│  │               │Convergence│                     │ │
│  │               │  Scorer   │                     │ │
│  │               └─────┬─────┘                     │ │
│  │                     ▼                           │ │
│  │        bullish / bearish / WAIT (context)       │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## CLI Reference

```
python mcp_brs/server.py [--transport {stdio,streamable-http}] [--port PORT] [--host HOST] [--require-key]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--transport stdio` | ✓ | stdio transport (local agents — Claude Desktop, Cursor) |
| `--transport streamable-http` | | HTTP transport (remote agents, team servers) |
| `--port` | `8000` | Port for HTTP transport |
| `--host` | `127.0.0.1` | Bind address for HTTP transport |
| `--require-key` | off | Fail-closed gate: require `BRS_MCP_SERVER_KEY` on every request |

---

## Files

| File | Purpose |
|------|---------|
| [`mcp_brs/__init__.py`](../mcp_brs/__init__.py) | Package init with exports |
| [`mcp_brs/__main__.py`](../mcp_brs/__main__.py) | Entry point for `python -m mcp_brs` |
| [`mcp_brs/server.py`](../mcp_brs/server.py) | MCP server — 7 canonical tools |
| [`mcp_brs/metadata.py`](../mcp_brs/metadata.py) | Canonical product metadata (single source of truth) |
| [`scripts/refresh_registry_metadata.py`](../scripts/refresh_registry_metadata.py) | Registry generator (server-card, glama, MCPB manifest) |

---

## Testing

```bash
# Verify import and tool registration
python3 -c "from mcp_brs.server import mcp; print(mcp.name)"

# List all registered tools
python3 -c "
from mcp_brs.server import mcp
import asyncio
tools = asyncio.run(mcp.list_tools())
for t in tools:
    print(f'  {t.name}')
"

# Show CLI help
python3 mcp_brs/server.py --help

# Run (stdio — for MCP clients)
python3 mcp_brs/server.py
```

---

## Health probe — verify tools return DATA, not just a handshake

Aug 15 lesson: the public endpoint passed `initialize` (200) but every tool
returned "Cannot connect to https://api.brs-signals.com" — that subdomain
has no DNS record. The handshake proves routing, NOT that data flows. After
any launch/restart, call a real tool:

> **Dual-era server (mcp 2.x deployment).** One endpoint serves BOTH protocol
> generations: the modern stateless revision **2026-07-28** (`server/discover`,
> no session id, `MCP-Protocol-Version` header, per-request `_meta`) AND the
> legacy session flow (`initialize` + `Mcp-Session-Id`, `protocolVersion` ≤
> 2025-11-25). The legacy probe below stays valid for backward-compatible
> clients; a modern-only client probes `server/discover` instead.

```python
# LEGACY session flow: initialize -> notifications/initialized -> tools/call
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
print(call("tools/call", {"name": "brs_market_state", "arguments": {}}).text[:200])       # EXPECT real JSON
print(call("tools/call", {"name": "brs_decision_context", "arguments": {}}).text[:200])  # EXPECT 402 x402
```

Expected: `brs_market_state` → real data (keyless free tier);
`brs_decision_context` → the 402 x402 message (the gate works through the MCP).
Anything else = upstream misconfigured.

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

- No key → free tier (only the 4 Free tools are visible; Pro tools return the
  402 x402 message).
- Valid key → the caller's own tier (Pro data), attributed to their key.
- Invalid key → upstream 401 `Invalid or missing API key`.

---

## Related Docs

- [BRS Signals API Docs](https://brs-signals.com/docs)
- [Canonical metadata](../mcp_brs/metadata.py)
- [Registry generator](../scripts/refresh_registry_metadata.py)
- [MCP Protocol Specification](https://modelcontextprotocol.io)
