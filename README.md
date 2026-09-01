# ₿RS Signals — MCP Server

`mcp-name: io.github.brssignals/brs-signals-mcp`

Live Bitcoin market regime for AI agents: three independent sensors read
pre-price data — fee curves, funding velocity, whale flows, absence — every
30s and reject almost everything. When they converge, you get a directional
call with the evidence attached. The data doesn't exist in history; it exists
right now and can't be reconstructed. **Provable silence:** the public
rejection funnel shows exactly how many reads died at each gate, so your
agent can audit the silence, not just the signals. MCP + REST + x402. Free
tier, no card.

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

**OpenClaw** — run in your terminal:

```bash
openclaw mcp add brs-signals --transport streamable-http --url https://brs-signals.com/mcp
```

(or OpenClaw Web UI → `/settings/mcp` → add an HTTP/SSE endpoint at that URL)

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

**OpenClaw (stdio)**:

```bash
openclaw mcp add brs-signals --command python3 --arg -m --arg mcp_brs
```

## Don't trust us — query us

The full public track record is an endpoint, not a PDF. Point your agent at
it and let it reach its own conclusion:

```
"BRS Signals claims it rejects almost every read. Pull its public track
record (get_signal_history) and today's rejection funnel
(get_rejection_funnel), and tell me: does the data support the claim,
and what happened after each call at +4h and +24h?"
```

## What You Get

Three independent sensors running every 30 seconds, fused into one convergence score:

| Sensor | Domain | What It Detects |
|--------|--------|-----------------|
| **X-Ray** | On-chain | Bitcoin's internal structure — fee curves, capital movement, network health |
| **Pulse** | Off-chain | Derivatives positioning and macro — funding velocity, whale flows, squeeze probability |
| **Shadow** | Absence | What has *stopped* happening — the silence when a normally busy channel goes quiet |

When all three agree → conviction. When they disagree → silence.

## MCP Tools

**16 tools.** What each tier can call:

| Tool | Keyless | Free key | Pro |
|------|:---:|:---:|:---:|
| `get_convergence` | ✅ | ✅ | ✅ |
| `get_regime_current` | ✅ | ✅ | ✅ |
| `get_system_health` | ✅ | ✅ | ✅ |
| `get_system_counters` | ✅ | ✅ | ✅ |
| `get_rejection_funnel` | ✅ | ✅ | ✅ |
| `get_fee_histogram` | — | ✅ | ✅ |
| `get_funding_divergence` | — | ✅ | ✅ |
| `get_dashboard` | — | ✅ | ✅ |
| `get_directional_bias` | — | — | ✅ |
| `get_signal_history` | — | — | ✅ |
| `get_stablecoin_flows` | — | — | ✅ |
| `get_gamma_exposure` | — | — | ✅ |

**No BRS API** — `query_db` (read-only SQLite on the server) and the three
`get_mempool_*` / `get_block_tip` tools (live mempool.space) need no key.

**Regime & direction**
- `get_convergence` — All three engine verdicts + convergence score
- `get_regime_current` — Market regime + active events
- `get_directional_bias` — bullish/bearish/WAIT with confidence (Pro)
- `get_signal_history` — Recent decisions (Pro)

**Underlying streams**
- `get_fee_histogram` — Mempool fee curve shape analysis (free key)
- `get_funding_divergence` — Cross-exchange funding squeeze (free key)
- `get_stablecoin_flows` — Whale stablecoin transfers (Pro)
- `get_gamma_exposure` — Dealer gamma + flip level (Pro)
- `get_dashboard` — Bundled regime + signal + funding (free key)

**System & audit**
- `get_system_health` — Component-by-component health check
- `get_system_counters` — Signals sent, data points, days collecting
- `get_rejection_funnel` — Per-gate cycle counts: why no signal
- `query_db` — Read-only SQL against the BRS database

**Bitcoin network · live** (mempool.space)
- `get_mempool_fees` — Recommended fee rates (sat/vB)
- `get_mempool_stats` — Pending tx count, vsize, total fees
- `get_block_tip` — Current block height

## Pricing

- **Free tier** — Regime classification + convergence score (5 req/min). No card.
- **Pro tier ($50/mo)** — Full directional bias + raw streams + unlimited requests
- **Per-call ($0.01/query)** — Pro bias, pay-as-you-go via x402 (USDC on
  Solana or Base): hit `/api/v2/bias/per-call`, pay the 402, retry with
  `?tx_signature=` + your free key. Capped at $50 per rolling 30 days, then
  converts to Pro — never more than $50 in any 30 days. Solana + Base.
- **x402** — Agents with wallets pay per access in USDC; no signup, no human
- **Founding rate** — Use code `FOUNDING50` at checkout: $30/mo for 3 months (first 50 subscribers only)

Get your API key at [brs-signals.com](https://brs-signals.com).

## Links

- [Website](https://brs-signals.com)
- [API Docs](https://brs-signals.com/docs/guide)
- [GitHub](https://github.com/brssignals/BRS-Signals-MCP)
- [X (Twitter)](https://x.com/brssignals)
