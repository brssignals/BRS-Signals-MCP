"""
₿RS Signals — canonical product metadata (BRS-003 single source of truth).

Every registry surface (`server-card.json`, `glama.json`, MCPB manifest) and,
eventually, every human surface must derive its facts from THIS block. If a
fact lives in two places, the second copy is a drift bug — that is exactly
the failure BRS-014 exists to eliminate.

Import safety: this module is PURE DATA — no `config`, `api`, `mcp`, or
database imports — so the registry generator and the CI drift-check can load
it with zero dependencies. It must stay importable on a bare Python install.

Version reconciliation (BRS-014): the live MCP package is published at
`mcp_brs/pyproject.toml` version 0.1.4, while the registry surfaces still
carried 0.1.1. The canonical VERSION below is 0.1.4; the generator rewrites
the registry surfaces to match.
"""

# ── Identity ────────────────────────────────────────────────────────
NAME = "brs-signals-mcp"
DISPLAY_NAME = "₿RS Signals — Pre-Price Three-Eye Bitcoin Signals"
REGISTRY_NAME = "io.github.brssignals/brs-signals-mcp"
VERSION = "0.1.4"
WEBSITE = "https://brs-signals.com"
DOCUMENTATION_URL = "https://brs-signals.com/docs/guide"
ICON_URL = "https://brs-signals.com/favicon.svg"
REPOSITORY_URL = "https://github.com/brssignals/BRS-Signals-MCP"
MAINTAINER_EMAIL = "brssignals@gmail.com"
AUTHOR_NAME = "BRS Signals"
AUTHOR_EMAIL = "hello@brs-signals.com"
LICENSE = "MIT"

# ── Transport ───────────────────────────────────────────────────────
STDIO_COMMAND = "python3"
STDIO_ARGS = ["-m", "mcp_brs"]
MCP_ENDPOINT_URL = "https://brs-signals.com/mcp"
MCPB_ENTRY_POINT = "server/server.py"
MCPB_ARGS = ["${__dirname}/server/server.py"]

# ── Signup URLs (per-surface referral tags are intentional) ─────────
SIGNUP_URL_OFFICIAL = "https://brs-signals.com/signup?ref=official"
SIGNUP_URL_MCPB = "https://brs-signals.com/signup?ref=mcpb"

# ── Tiers & pricing (single tier matrix) ────────────────────────────
FREE_RATE_LIMIT_PER_MIN = 5
PRO_RATE_LIMIT_PER_MIN = 60
PRO_PRICE_USDC_PER_MONTH = 50.0
PER_CALL_USD = 0.01
SPEND_CAP_USD_30D = 50.0

# ── Networks (single network statement) ─────────────────────────────
NETWORKS = ["Solana", "Base"]
ASSET = "USDC"

# ── Refund policy (single statement) ────────────────────────────────
REFUND_POLICY = "Payments are non-refundable. Cancelling stops future billing."

# ── Canonical tool surface (BRS-007 / BRS-013 tiers) ────────────────
FREE_TOOLS = [
    "brs_market_state",
    "brs_audit_track_record",
    "brs_rejection_funnel",
    "brs_system_status",
]
PRO_TOOLS = [
    "brs_decision_context",
    "brs_history",
    "brs_raw_stream",
]

# tool name -> tier, for programmatic lookups
TIERS = {t: "free" for t in FREE_TOOLS}
TIERS.update({t: "pro" for t in PRO_TOOLS})

# ── Copy (single description / pricing / instructions) ──────────────
DESCRIPTION_LONG = (
    "Three independent sensors read Bitcoin's market structure (mempool "
    "fee-curve shape, funding velocity, whale flows) every 30s and reject "
    "almost everything. The gate-by-gate rejection funnel is public — so you "
    "can audit the silence, not just the readings. This is the science behind "
    "the ORE Signals daily plate. Free tier, no card; pay-as-you-go at "
    "$0.01/query via x402 (USDC on Solana or Base)."
)

DESCRIPTION_SHORT = (
    "Live Bitcoin market-structure readings for agents: three independent "
    "sensors read the market every 30s and reject almost everything — the "
    "science behind the ORE Signals daily plate. The public rejection funnel "
    "lets your agent audit the silence. MCP + REST + x402. Free tier, no card."
)

PRICING_STRING = (
    "Free tier, no card. $0.01 per query via x402 (USDC, Solana or Base) — "
    "uncapped pay-as-you-go."
)

AUTH_INSTRUCTIONS = (
    f"Get your free API key at {SIGNUP_URL_OFFICIAL}. "
    "Set the BRS_API_KEY environment variable."
)

INSTALL_INSTRUCTIONS = (
    "Local: pip install brs-signals-mcp && python3 -m mcp_brs. "
    "Remote: point your MCP client at https://brs-signals.com/mcp "
    "(streamable-http)."
)

MCPB_API_KEY_DESCRIPTION = (
    f"Your BRS Signals API key. Get one free at {SIGNUP_URL_MCPB}"
)

CATEGORIES = ["finance", "cryptocurrency", "bitcoin", "trading", "market-data"]

# Fixed at first registry publication; not re-derived on each refresh.
REGISTRY_PUBLISHED_AT = "2026-08-03T19:27:12.155316Z"

# ── SLO / registry-listing facts (BRS-019) ─────────────────────────
# COMPLIANCE_PCT — scope of the "100" (what it covers, and what it does NOT):
#   Covered: every registry/listing surface is generated from THIS module
#   (server-card, glama.json, mcpb manifest — scripts/refresh_registry_metadata.py),
#   fixed at REGISTRY_PUBLISHED_AT ("2026-08-03T19:27:12.155316Z"); the CI
#   drift-check (scripts/refresh_registry_metadata.py --check) fails on any
#   mismatch; tests/test_status_slo.py pins the constant and the /system-status
#   surface. Supporting results: drift-check green + status-slo suite green.
#   Not covered / not measured: runtime availability, latency, freshness —
#   those are measured SLO fields, never fabricated. Measured-vs-configured
#   disclosure is tracked as BRS-021d. Note: a source comment alone does not
#   qualify a public field — every consumer-visible surface that emits
#   compliance_pct repeats this scope (mcp_brs/server.py brs_system_status →
#   compliance_note). It is distinct from protocol conformance (BRS-021f) and
#   from operational health (the measured fields).
REGISTRY_STATUS = "active"
COMPLIANCE_PCT = 100

# ── Registry schema / card constants ────────────────────────────────
SERVER_CARD_SCHEMA = "https://static.modelcontextprotocol.io/schemas/mcp-server-card/v1.json"
SERVER_CARD_VERSION = "1.0"
# PROTOCOL_VERSION — the MCP protocol revision advertised on the registry
# server-card ("protocolVersion"). BRS-021f Day 2 (mcp 2.x build): the server
# is now DUAL-ERA from one endpoint — it serves the modern stateless
# 2026-07-28 revision natively (`server/discover`, per-request `_meta`, no
# session id) AND retains the legacy session handshake (`initialize`) up to
# 2025-11-25. The server-card field is a single revision, so it advertises the
# MODERN ceiling ("2026-07-28") — the highest revision the server genuinely
# serves — not the legacy compatibility floor. Verified live: modern discover
# returns supported_versions == ["2026-07-28"] and a legacy client still
# completes initialize at 2025-11-25 (tests/test_real_transport.py
# test_modern_discover_serves_2026_07_28_with_legacy_fallback). The pure-data
# contract (module docstring — zero SDK import) only means the value cannot be
# auto-derived via runtime SDK introspection; it is a frozen fact refreshed here
# explicitly, and the CI drift-check (scripts/refresh_registry_metadata.py
# --check) fails if the generated server-card ever diverges.
PROTOCOL_VERSION = "2026-07-28"
GLAMA_SCHEMA = "https://glama.ai/mcp/schemas/connector.json"
MCPB_MANIFEST_VERSION = "0.4"
