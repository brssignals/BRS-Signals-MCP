# ₿RS Signals — MCP Server

**Bitcoin regime-switch detection for AI agents.**

Three independent sensors — X-Ray (on-chain), Pulse (off-chain derivatives), Shadow (absence detection) — fused into a single convergence score. Your AI agent gets real-time Bitcoin regime data without needing to understand mempool fees, funding rates, or options flow.

## Quick Start

```bash
pip install brs-signals-mcp
```

### Claude Desktop

```json
{
  "mcpServers": {
    "brs-signals": {
      "command": "python3",
      "args": ["-m", "mcp_brs"],
      "env": {
        "BRS_API_KEY": "your-api-key"
      }
    }
  }
}
```

### Cursor / Continue

```json
{
  "mcpServers": {
    "brs-signals": {
      "command": "python3",
      "args": ["-m", "mcp_brs"],
      "env": {
        "BRS_API_KEY": "your-api-key"
      }
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `get_convergence` | Three-sensor convergence score (0.0–1.0) |
| `get_directional_bias` | Current BUY/SELL/WAIT bias |
| `get_signal_history` | Recent trade signals with confidence |
| `get_regime_current` | Current market regime |
| `get_fee_histogram` | Mempool fee distribution |
| `get_funding_divergence` | Exchange funding rate spread |
| `get_stablecoin_flows` | Stablecoin inflow/outflow |
| `get_gamma_exposure` | Dealer gamma exposure |
| `get_dashboard` | Full dashboard bundle |
| `get_system_health` | System status |
| `get_system_counters` | Data collection stats |

## API Keys

Get your API key at [brs-signals.com](https://brs-signals.com).

- **Free**: 5 req/min, convergence + regime only
- **Pro**: 60 req/min, all tools + real-time data

## License

MIT
