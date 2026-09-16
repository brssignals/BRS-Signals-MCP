# ₿RS Signals — MCP Server

`mcp-name: io.github.brssignals/brs-signals-mcp`

Live Bitcoin market regime for AI agents: three independent sensors read
pre-price data — fee curves, funding velocity, whale flows, absence — every
30s and reject almost everything. When they converge, you get a directional
call with the evidence attached. The data can't be reconstructed from history.
**Provable silence:** the public rejection funnel shows exactly how many reads
died at each gate, so your agent can audit the silence, not just the signals.
MCP + REST + x402. Free tier, no card.

## Don't trust us — query us

The full public track record is an endpoint, not a PDF. Point your agent at
it and let it reach its own conclusion:

```
"BRS Signals claims it rejects almost every read. Pull its public track
record (brs_audit_track_record) and today's rejection funnel
(brs_rejection_funnel), and tell me: does the data support the claim,
and what happened after each call at +4h and +24h?"
```

Both of those tools are keyless — no API key, no payment, no signup. That is
the point: the honesty surface is open by design.

## Use it in 30 seconds — remote, no install

The public endpoint is live at **`https://brs-signals.com/mcp`**
(streamable-http · keyless free tier). Any MCP client can use it — no
package install, no local process.

**Cursor** (MCP requires Cursor's paid Pro tier) — Settings → Features →
MCP → + Add New MCP Server → Type `http`, URL `https://brs-signals.com/mcp`.
Or add `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "brs-signals": { "type": "http", "url": "https://brs-signals.com/mcp" }
  }
}
```

**Claude Desktop** (MCP is free) — Settings → Developer → Edit Config:

```json
{
  "mcpServers": {
    "brs-signals": { "type": "http", "url": "https://brs-signals.com/mcp" }
  }
}
```

Then just ask your agent: *"What's the current Bitcoin regime and convergence
score?"*

## Or install locally (stdio, self-host)

```bash
pip install brs-signals-mcp
export BRS_API_KEY=va_yourkey_here   # get one at https://brs-signals.com
brs-mcp                                # starts the MCP server (stdio)
```

**Claude Desktop (stdio)** — add to
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows), then restart:

```json
{
  "mcpServers": {
    "brs-signals": {
      "command": "brs-mcp",
      "env": { "BRS_API_KEY": "va_yourkey_here" }
    }
  }
}
```

**Cursor (stdio)** — Settings → Features → MCP → Add New MCP Server:
Type `command` · Command `python3 -m mcp_brs` · Env `BRS_API_KEY`.

## What You Get

Three independent sensors running every 30 seconds, fused into one convergence score:

| Sensor | Domain | What It Detects |
|--------|--------|-----------------|
| **X-Ray** | On-chain | Bitcoin's internal structure — fee curves, capital movement, network health |
| **Pulse** | Off-chain | Derivatives positioning and macro — funding velocity, whale flows, squeeze probability |
| **Shadow** | Absence | What has *stopped* happening — the silence when a normally busy channel goes quiet |

When all three agree → conviction. When they disagree → silence.

## MCP Tools

**7 tools.** Discovery is authorization-scoped: keyless callers see only the
4 Free tools; a caller presenting a key sees all 7. No paid tool serves data
keyless — the metered tool below surfaces its x402 payment challenge keyless,
but never data.

> **New to this server?** Call `brs_market_state` (free) first — it shows the
> current regime, three-eye convergence, and system health. Need the directional
> posture one time? Call `brs_decision_context` with **no key**, read
> `error.payment` from the `PAYMENT_REQUIRED` result, pay, and re-call with the
> `tx_signature`.

### Free — no key required

| Tool | What it returns |
|------|-----------------|
| `brs_market_state` | Regime structure + three-eye convergence + system health (call first) |
| `brs_audit_track_record` | Public proof — every call and what BTC did next (+4h/+24h) |
| `brs_rejection_funnel` | Per-gate cycle counts: why no signal came out |
| `brs_system_status` | Component health + sample size behind every reading |

### Paid — key or x402 required

| Tool | What it returns |
|------|-----------------|
| `brs_decision_context` | Directional posture (bullish / bearish / WAIT) with evidence |
| `brs_history` | Recent calls with resolved outcomes |
| `brs_raw_stream` | One raw stream: `fees`, `funding`, `stablecoin`, or `gamma` |

> **WAIT means no edge.** The system tells you which game the market is
> playing and how much the sensors agree — it is context, not an instruction
> to trade.

## Pricing

- **Free tier** — Regime + convergence + the public proof (5 req/min). No card.
- **Per-call ($0.01/query)** — the full reading one query at a time via x402
  (USDC on Solana or Base): hit `/api/v2/bias/per-call`, pay the 402, retry
  with `?tx_signature=` + your free key. Capped at $50 per rolling 30 days —
  never more than $50 in any 30 days.
- **x402** — Agents with wallets pay per access in USDC; no signup, no human.

Get your API key at [brs-signals.com](https://brs-signals.com).

## Links

- [Website](https://brs-signals.com)
- [API Docs](https://brs-signals.com/docs/guide)
- [GitHub](https://github.com/brssignals/BRS-Signals-MCP)
- [X (Twitter)](https://x.com/brssignals)
