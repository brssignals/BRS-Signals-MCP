"""
₿RS Signals — MCP Server
========================
Exposes the BRS Signals API as MCP tools for AI agents.

Canonical tool surface (7 tools):
  brs_market_state        (Free)  → /api/v2/structure + /api/v2/confidence + /api/v1/system/health
  brs_decision_context    (Pro)   → /api/v2/bias/per-call (x402 metered)
  brs_history             (Pro)   → /api/v2/bias/history
  brs_audit_track_record  (Free)  → /api/v2/signals/track-record (public proof — keyless)
  brs_rejection_funnel    (Free)  → /api/v2/health/funnel
  brs_system_status       (Free)  → /api/v1/system/health (incl. SLO) + /api/v2/system/counters
  brs_raw_stream          (Pro)   → /api/v2/streams/{fees,funding,stablecoin,gamma}

Auth model (BRS-013, audit §5.5):
  - Per-client API key pass-through (Q58 Option C) is the metered identity
    layer: the caller's own key is forwarded verbatim upstream.
  - x402 challenges (carried as PAYMENT_REQUIRED by BRS-012) handle one-off
    paid calls — no signup required for metered agent context.
  - OAuth/scopes are reserved for persistent users long-term; a static shared
    server key is NOT a paid-user identity and is rejected for public launch.

Authorization-scoped discovery: keyless callers see the 4 Free tools PLUS the
metered posture (brs_decision_context) so its schema and payment instructions
are discoverable; a caller presenting a key sees the full 7-tool surface, and
the upstream BRS API still enforces Pro (401/402) on call — no Pro tool SERVES
DATA keyless. The metered tool (brs_decision_context) IS callable keyless by
design: a keyless call reaches /api/v2/bias/per-call and returns the x402
payment challenge in error.payment, which a caller pays and re-presents as
tx_signature to unlock that single request (BRS-017, BRS-021 policy row 1).

Telemetry (BRS-018): every tool call emits one append-only, non-PII event
(tool, tier, outcome, error_code, duration_ms, client fingerprint) to
data/telemetry/mcp_events.jsonl. Keys and tx signatures are never recorded.
Opt out with BRS_MCP_TELEMETRY=0.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import hmac
import importlib.metadata as _pkg
import json
import os
import time
import uuid
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal, Optional

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, Tool as MCPTool, ToolAnnotations
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Canonical product metadata (BRS-003 pure-data single source of truth). Safe to
# import at module level: metadata.py carries zero SDK/config imports, so there
# is no circular import with mcp_brs/__init__.
from mcp_brs import metadata

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

# ── Pooled HTTP client (BRS-011) ───────────────────────────────────

_HTTP_TIMEOUT = 15.0
_MAX_RETRIES = 3
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()


def _backoff(attempt: int) -> float:
    """Exponential backoff: 0.25s, 0.5s, 1s, ..."""
    return 0.25 * (2 ** attempt)


async def _get_client() -> httpx.AsyncClient:
    """Return the process-wide pooled AsyncClient, creating it lazily.

    One shared client gives connection reuse across all 7 tools instead of a
    fresh client (and socket) per call. The lifespan closes it on shutdown;
    the lazy path covers direct/test invocation without a lifespan.
    """
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is None:
            _client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    return _client


@asynccontextmanager
async def _lifespan(app: MCPServer) -> AsyncIterator[None]:
    """Create the pooled client on startup, close it on shutdown."""
    client = await _get_client()
    try:
        yield
    finally:
        await client.aclose()
        global _client
        _client = None


# ── Authorization-scoped tool discovery (BRS-013) ──────────────────
# Auth model decision (audit §5.5): per-client API key pass-through is the
# metered identity layer; x402 (carried by BRS-012) covers one-off paid calls;
# OAuth/scopes are reserved for persistent users long-term. A static shared
# server key is NOT a paid-user identity (Q58: rejected for public launch).
#
# Discovery reflects the caller's tier: keyless callers see the Free tools PLUS
# the metered posture (discoverable schema + payment instructions); a caller
# presenting a key sees the full surface, and the upstream BRS API still
# enforces Pro (401/402) on call — no Pro tool SERVES DATA keyless.
_FREE_TIER_META: dict[str, str] = {"tier": "free"}
_PRO_TIER_META: dict[str, str] = {"tier": "pro"}
# The metered posture stays visible to keyless callers BY DESIGN: discovery must
# advertise it (schema + payment instructions) so an agent can find and pay it
# without already knowing the name (BRS-021c keyless-discoverability gap).
_METERED_TOOL: str = "brs_decision_context"


def _has_key() -> bool:
    """True when the caller presents a key (Q58 per-client pass-through) or the
    server env key is set (self-host stdio). Mirrors _headers() precedence."""
    return bool(_client_key.get() or API_KEY)


class _TieredFastMCP(MCPServer):
    """MCPServer with authorization-scoped discovery (BRS-013) + telemetry (BRS-018)."""

    async def list_tools(self) -> list[MCPTool]:
        tools = await super().list_tools()
        if _has_key():
            return tools
        # Keyless discovery shows the 4 Free tools PLUS the metered posture so
        # its schema and payment instructions are discoverable (BRS-021c).
        return [
            t for t in tools
            if (t.meta or {}).get("tier") != "pro" or t.name == _METERED_TOOL
        ]

    @staticmethod
    def _outcome_of(result: Any) -> tuple[str, Optional[str]]:
        """Derive (outcome, error_code) from a tool result envelope.

        Handles v2 ``CallToolResult`` (structured_content), the legacy v1
        structured tuple (content + dict), and plain dicts. Never raises.
        """
        payload: dict[str, Any] = {}
        if isinstance(result, CallToolResult):
            if isinstance(result.structured_content, dict):
                payload = result.structured_content
        elif isinstance(result, tuple):
            for part in result:
                if isinstance(part, dict):
                    payload = part
                    break
        elif isinstance(result, dict):
            payload = result
        status = str(payload.get("status", "ok"))
        err = payload.get("error")
        code: Optional[str] = None
        if isinstance(err, dict):
            code = err.get("code")
        if status in ("ok", "degraded", "stale"):
            outcome = status
        elif status in ("unavailable", "error"):
            outcome = "error"
        else:
            outcome = status
        return outcome, code

    def _client_id(self, context: Any = None) -> Optional[str]:
        try:
            if context is None:
                return None
            meta = getattr(context.request_context, "meta", None)
            return (meta or {}).get("client_id")
        except Exception:
            return None

    @staticmethod
    def _normalize_error_result(result: Any) -> Any:
        """Signal failed execution with ``isError:true`` while PRESERVING the
        structured error envelope (and its payment challenge) for x402-aware
        clients (BRS-021c corrected isError ruling).

        A successfully calculated WAIT/abstention remains a successful result
        (``status`` is not ``"error"``) and passes through unchanged, so it
        stays ``isError`` unset/false. Only business/API failures — which ride
        the typed envelope with ``status:"error"`` — are re-marked at the MCP
        level, and their ``structuredContent`` is never nulled.
        """
        if isinstance(result, CallToolResult):
            sc = result.structured_content
            if isinstance(sc, dict) and sc.get("status") == "error":
                return CallToolResult(
                    content=result.content,
                    structured_content=sc,
                    is_error=True,
                )
            return result
        if isinstance(result, tuple) and len(result) == 2:
            content, structured = result
            if isinstance(structured, dict) and structured.get("status") == "error":
                return CallToolResult(
                    content=list(content),
                    structured_content=structured,
                    is_error=True,
                )
        return result

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context: Any = None
    ) -> Any:
        """Call a tool, then record one non-PII telemetry event (BRS-018).

        The event captures tool name, tier, outcome, error code and latency —
        the audit §11.1 north-star inputs — and nothing identifying: the
        caller is a truncated fingerprint, never a key or tx. Recording is
        best-effort and can never affect the tool result.
        """
        from mcp_brs import telemetry

        tier = "pro" if _has_key() else "free"
        started = time.monotonic()
        try:
            result = await super().call_tool(name, arguments, context)
        except Exception:
            telemetry.record(
                name, tier=tier, outcome="exception",
                error_code="INTERNAL_ERROR",
                duration_ms=int((time.monotonic() - started) * 1000),
                client_id=self._client_id(context), client_key=_client_key.get(),
            )
            raise
        outcome, code = self._outcome_of(result)
        telemetry.record(
            name, tier=tier, outcome=outcome, error_code=code,
            duration_ms=int((time.monotonic() - started) * 1000),
            client_id=self._client_id(context), client_key=_client_key.get(),
        )
        return self._normalize_error_result(result)


# Server identity (BRS-021f Day 2): serverInfo.version advertises the BRS
# package/release (metadata.VERSION = "0.1.4"), NOT the SDK version. The SDK
# version is recorded separately below for the evidence bundle.
_SDK_VERSION = _pkg.version("mcp")

mcp = _TieredFastMCP(
    "brs-signals",
    version=metadata.VERSION,
    lifespan=_lifespan,
    instructions="₿RS Signals — pre-price, three-eye Bitcoin signals. "
    "Three independent sensors read pre-price flows (mempool fee-curve shape, "
    "funding velocity, whale flows) every 30s and reject almost everything. "
    "Only when all three converge does a bullish/bearish/WAIT call come out, "
    "with evidence attached. The gate-by-gate rejection funnel is public — so "
    "you can audit the silence, not just the signals. "
    "Start with brs_market_state (free) for regime, convergence, and health. "
    "Directional posture is payable per-call via x402: call brs_decision_context "
    "with no key, read error.payment from the PAYMENT_REQUIRED response, pay the "
    "challenge, then re-call with the tx_signature to receive the posture.",
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


async def _get(endpoint: str, timeout: float = _HTTP_TIMEOUT) -> dict:
    """Call the BRS Signals API via the pooled client. Returns dict (data or
    error info). Retries transient failures (429/5xx, timeouts, connect errors)
    with exponential backoff; 401/402 are terminal and returned immediately."""
    url = f"{BASE_URL}{endpoint}"
    client = await _get_client()
    last: dict[str, Any] | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            r = await client.get(url, headers=_headers(), timeout=timeout)
        except httpx.TimeoutException:
            last = {
                "code": "UPSTREAM_TIMEOUT",
                "error": "BRS API timed out",
                "retry_after_seconds": 5,
                "how_to_fix": "Try again in a few seconds",
            }
        except httpx.ConnectError:
            last = {
                "code": "UPSTREAM_UNAVAILABLE",
                "error": f"Cannot connect to {BASE_URL}",
                "retry_after_seconds": 5,
                "how_to_fix": "Check network or BRS_API_URL",
            }
        except Exception as e:
            return {"code": "INTERNAL_ERROR", "error": str(e)}
        else:
            if r.status_code == 401:
                return {
                    "code": "AUTH_REQUIRED",
                    "error": "Invalid or missing API key",
                    "how_to_fix": (
                        "Set BRS_API_KEY environment variable, "
                        "or get a free key at https://brs-signals.com"
                    ),
                }
            if r.status_code == 402:
                # Carry the full upstream x402 challenge (v2 accepts[]/resource
                # or legacy payment{}), not a flattened "Pro required", so P2
                # (BRS-017) can construct the actual on-chain payment.
                try:
                    challenge = r.json()
                except Exception:
                    challenge = None
                return {
                    "code": "PAYMENT_REQUIRED",
                    "error": "Payment required (x402)",
                    "how_to_fix": (
                        "Pay the x402 challenge or upgrade at "
                        "https://brs-signals.com/signup"
                    ),
                    "payment": challenge,
                    "free_tier": "Get a free API key for regime data (5 req/min)",
                }
            if r.status_code == 429:
                last = {
                    "code": "RATE_LIMITED",
                    "error": "Rate limit exceeded",
                    "how_to_fix": "Wait 60 seconds or upgrade to Pro/Max tier",
                    "retry_after_seconds": 60,
                }
            elif r.status_code in _RETRYABLE_STATUSES:
                last = {
                    "code": "UPSTREAM_ERROR",
                    "error": f"BRS API returned HTTP {r.status_code}",
                    "retry_after_seconds": 5,
                    "how_to_fix": "Try again in a few seconds",
                }
            else:
                r.raise_for_status()
                return r.json()

        # Transient failure — retry with backoff if attempts remain.
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(_backoff(attempt))
            continue
        return last or {"code": "INTERNAL_ERROR", "error": "Unknown error"}

    return last or {"code": "INTERNAL_ERROR", "error": "Unknown error"}


# ── Result envelope (audit §4.2) ───────────────────────────────────

# All market-reading tools are read-only, non-destructive, idempotent for the
# same observation instant, and open-world (they access external/current data).
_READ_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

SCHEMA_VERSION = "1.0"
METHODOLOGY_VERSION = "2026.09"
DISCLAIMER = "Market-structure context; not an execution instruction."

# BRS-021d — Freshness. A LIVE reading is valid for _VALID_FOR_SECONDS after its
# observation instant (`as_of`). `freshness_seconds` = now - `as_of`; once it
# exceeds `valid_for_seconds` the envelope `status` becomes "stale". Ledger /
# aggregate tools (history, track-record, funnel, counters) carry no observation
# instant and report request-time `as_of` with `freshness_seconds` 0.
_VALID_FOR_SECONDS = 90


class ErrorInfo(BaseModel):
    """Structured error carried inside the envelope (audit §4.3 / BRS-012).

    Every failure maps to one stable ``code`` plus a ``retryable`` flag, an
    optional ``retry_after_seconds``, a human ``how_to_fix``, and — for
    ``PAYMENT_REQUIRED`` — a typed ``payment`` challenge that P2 (BRS-017)
    can act on directly.
    """

    code: str
    message: str
    retryable: bool = False
    retry_after_seconds: Optional[int] = None
    how_to_fix: Optional[str] = None
    payment: Optional["PaymentChallenge"] = None


class PaymentChallenge(BaseModel):
    """x402 payment challenge on a PAYMENT_REQUIRED error (audit §17.2).

    Carries exactly what P2 needs to construct the on-chain payment: amount,
    currency, accepted networks, recipient, and the submit URL where the
    signed tx is returned. ``raw`` preserves the full upstream 402 body so
    nothing the server advertised is dropped.

    Spend-safety fields (audit §6.2) ride alongside so a payment-aware bridge
    can enforce caps before signing: ``asset`` (what to pay with), ``scheme``
    (how the exact amount is matched), ``max_timeout_seconds`` (expiry),
    ``request_digest`` (a stable digest binding the payment to this exact
    request), and ``max_retries`` (the policy ceiling on re-calls — the
    per-call ledger already makes retries idempotent via ``already_processed``).
    """

    protocol: str = "x402"
    amount: Optional[str] = None
    currency: str = "USDC"
    networks: list[str] = Field(default_factory=list)
    recipient: Optional[str] = None
    resource: Optional[str] = None
    submit_url: Optional[str] = None
    scheme: Optional[str] = None
    asset: Optional[str] = None
    max_timeout_seconds: Optional[int] = None
    max_retries: int = 3
    request_digest: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class QualityInfo(BaseModel):
    """Best-effort evidence/quality summary for a reading."""

    sources_expected: int = 0
    sources_healthy: int = 0
    sample_size: Optional[int] = None


class ResultEnvelope(BaseModel):
    """Standard result envelope (audit §4.2) — success and error paths.

    Every tool returns this shape so an agent never has to guess whether
    "old data" means "quiet market" or "broken collector".
    """

    schema_version: str = SCHEMA_VERSION
    methodology_version: str = METHODOLOGY_VERSION
    as_of: str
    freshness_seconds: int = 0
    valid_for_seconds: int = _VALID_FOR_SECONDS
    status: Literal["ok", "degraded", "stale", "unavailable", "error"]
    tier: str = "free"
    data: Optional[dict[str, Any]] = None
    evidence: list[Any] = Field(default_factory=list)
    quality: Optional[QualityInfo] = None
    request_id: str
    disclaimer: str = DISCLAIMER
    error: Optional[ErrorInfo] = None


def _iso_now() -> str:
    """Current UTC time as ISO-8601 with a Z suffix (second precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_request_id() -> str:
    """Short, unique, non-sensitive correlation id for one envelope."""
    return f"brs_{uuid.uuid4().hex[:12]}"


# ── Freshness derivation (BRS-021d) ─────────────────────────────────
# `as_of` must be the UNDERLYING OBSERVATION time, not the request time. A
# stalled source (its observation timestamp stops advancing) therefore makes
# `freshness_seconds` grow and flips `status` to "stale". Tools whose upstream
# carries no observation instant (ledgers/aggregates) are excluded below.

def _parse_observation(value: Any) -> Optional[datetime]:
    """Parse an observation timestamp into an aware UTC datetime, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _observation_of(payload: Any) -> Optional[datetime]:
    """The observation instant of a LIVE reading, or None when the tool carries
    no observation concept (ledgers/aggregates). Only top-level observation
    keys are considered — list tools' per-record timestamps (signals[],
    history[]) are historical evidence, not a freshness signal."""
    if not isinstance(payload, dict):
        return None
    for key in ("as_of", "timestamp", "observed_at"):
        ts = _parse_observation(payload.get(key))
        if ts is not None:
            return ts
    latest = payload.get("latest_event")
    if isinstance(latest, dict):
        return _parse_observation(latest.get("timestamp"))
    return None


def _oldest_observation(observations: list[Optional[datetime]]) -> Optional[datetime]:
    """Oldest non-None observation — a bundle is as fresh as its stalest part."""
    present = [o for o in observations if o is not None]
    return min(present) if present else None


def _iso_of(dt: datetime) -> str:
    """ISO-8601 Z-suffix string for an aware datetime (second precision)."""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _freshness(observation: Optional[datetime], now: datetime) -> tuple[str, int]:
    """(status, freshness_seconds) for an observation instant vs `now`.

    No observation instant -> ("ok", 0): the tool class carries no freshness
    concept. A present-but-too-old instant -> ("stale", age)."""
    if observation is None:
        return "ok", 0
    age = (now - observation).total_seconds()
    freshness = max(0, int(age))
    if age > _VALID_FOR_SECONDS:
        return "stale", freshness
    return "ok", freshness


# ── Error model (audit §4.3 / BRS-012) ──────────────────────────────
# Stable, documented error codes. Every failure maps to exactly one code,
# a `retryable` flag, and (for PAYMENT_REQUIRED) a typed payment challenge:
#   AUTH_REQUIRED        → bad/missing key            (terminal)
#   PAYMENT_REQUIRED     → x402 challenge carried     (terminal; has .payment)
#   RATE_LIMITED         → 429                         (retryable)
#   UPSTREAM_TIMEOUT     → upstream slow               (retryable)
#   UPSTREAM_UNAVAILABLE → cannot connect              (retryable)
#   UPSTREAM_ERROR       → upstream 5xx                (retryable)
#   STALE_DATA           → data too old                (retryable)
#   SOURCE_DEGRADED      → sensor partial              (retryable)
#   INVALID_ARGUMENT     → caller input bad            (terminal)
#   INTERNAL_ERROR       → unexpected local error      (terminal)
_RETRYABLE_ERRORS = {
    "AUTH_REQUIRED": False,
    "PAYMENT_REQUIRED": False,
    "RATE_LIMITED": True,
    "UPSTREAM_TIMEOUT": True,
    "UPSTREAM_UNAVAILABLE": True,
    "UPSTREAM_ERROR": True,
    "STALE_DATA": True,
    "SOURCE_DEGRADED": True,
    "INVALID_ARGUMENT": False,
    "INTERNAL_ERROR": False,
}


def _short_chain(network: str) -> str:
    """CAIP-2 → short chain name for the challenge's networks list."""
    if network.startswith("eip155:"):
        return "base"
    if network.startswith("solana:"):
        return "solana"
    return network


def _challenge_digest(body: Any) -> str:
    """Deterministic digest binding a payment to this exact challenge.

    A payment-aware client can hash the challenge it received and present the
    digest when retrying, so a signed tx cannot be replayed against a
    different amount/recipient (audit §6.2 "request digest").
    """
    try:
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                               default=str)
    except Exception:
        canonical = str(body)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _per_call_endpoint(tx_signature: str = "", chain: str = "solana",
                       ref: str = "") -> str:
    """Build the metered per-call URL.

    First call (no ``tx_signature``) -> the bare endpoint, which returns the
    402 challenge. Retry (with a settlement signature) -> the settle/verify
    leg carrying ``chain`` and ``ref``. Query values are URL-encoded.
    """
    q: dict[str, str] = {}
    if tx_signature:
        q["tx_signature"] = tx_signature
        q["chain"] = chain
        if ref:
            q["ref"] = ref
    endpoint = "/api/v2/bias/per-call"
    if q:
        endpoint += "?" + urlencode(q)
    return endpoint


def _extract_payment_challenge(body: Any) -> dict[str, Any]:
    """Normalize a 402 body into ``PaymentChallenge`` kwargs.

    Tolerates both legacy ``{payment: {...}}`` and v2
    ``{accepts: [...], resource: {...}}`` shapes. Returns an empty-skeleton
    dict when nothing recognizable is present.
    """
    raw = body if isinstance(body, dict) else {}
    payment = raw.get("payment") if isinstance(raw.get("payment"), dict) else {}
    accepts = raw.get("accepts") or []

    networks: list[str] = []
    recipient = payment.get("recipient")
    amount = payment.get("amount")
    scheme = None
    asset = None
    max_timeout_seconds = None
    if isinstance(accepts, list):
        for acc in accepts:
            if isinstance(acc, dict):
                net = acc.get("network")
                if net:
                    networks.append(_short_chain(str(net)))
                recipient = recipient or acc.get("payTo")
                amount = amount if amount is not None else acc.get("amount")
                scheme = scheme or acc.get("scheme")
                asset = asset or acc.get("asset")
                if max_timeout_seconds is None and isinstance(acc.get("maxTimeoutSeconds"), int):
                    max_timeout_seconds = acc["maxTimeoutSeconds"]

    resource = raw.get("resource")
    resource_url = resource.get("url") if isinstance(resource, dict) else None

    return {
        "protocol": "x402",
        "amount": str(amount) if amount is not None else None,
        "currency": str(payment.get("currency") or "USDC"),
        "networks": networks or ["solana"],
        "recipient": recipient,
        "resource": resource_url,
        "submit_url": payment.get("submit_url"),
        "scheme": scheme,
        "asset": asset,
        "max_timeout_seconds": max_timeout_seconds,
        "request_digest": _challenge_digest(raw),
        "raw": raw,
    }


def _error_envelope(code: str, message: str, tier: str = "free",
                    retry_after_seconds: Optional[int] = None,
                    how_to_fix: Optional[str] = None,
                    payment: Optional[dict[str, Any]] = None) -> ResultEnvelope:
    """Build a failed envelope directly (for local validation errors)."""
    return ResultEnvelope(
        as_of=_iso_now(),
        status="error",
        tier=tier,
        request_id=_new_request_id(),
        error=ErrorInfo(
            code=code,
            message=message,
            retryable=_RETRYABLE_ERRORS.get(code, False),
            retry_after_seconds=retry_after_seconds,
            how_to_fix=how_to_fix,
            payment=PaymentChallenge(**_extract_payment_challenge(payment)) if payment else None,
        ),
    )


def _envelope(payload: dict[str, Any], tier: str = "free",
              observation: Any = None, unavailable: bool = False,
              quality: Optional[QualityInfo] = None) -> ResultEnvelope:
    """Wrap an upstream read in the standard envelope (BRS-021d freshness).

    Error path: an upstream/local error dict becomes `status="error"` with a
    typed `error` payload, so success and failure both honor one shape.

    Success path now derives freshness: `as_of` is the upstream OBSERVATION
    instant (``observation`` or the payload's own timestamp — never the request
    time), `freshness_seconds` is its age, and `status` becomes "stale" once
    the reading is older than `valid_for_seconds`. A tool with no observation
    instant reports request-time `as_of` with `freshness_seconds` 0.

    ``unavailable=True`` marks INSUFFICIENT DATA to evaluate (abstention — the
    upstream's "no decisions yet"), a legitimate non-error state that is
    distinct from a successfully computed WAIT (which stays "ok").
    """
    if isinstance(payload, dict) and payload.get("error"):
        return _error_envelope(
            code=payload.get("code", "INTERNAL_ERROR"),
            message=str(payload["error"]),
            tier=tier,
            retry_after_seconds=payload.get("retry_after_seconds"),
            how_to_fix=payload.get("how_to_fix"),
            payment=payload.get("payment"),
        )
    now = datetime.now(timezone.utc)
    obs = _parse_observation(observation) if observation is not None else _observation_of(payload)
    if unavailable:
        status = "unavailable"
        freshness = _freshness(obs, now)[1] if obs is not None else 0
    else:
        status, freshness = _freshness(obs, now)
    return ResultEnvelope(
        as_of=_iso_of(obs) if obs is not None else _iso_now(),
        freshness_seconds=freshness,
        valid_for_seconds=_VALID_FOR_SECONDS,
        status=status,
        tier=tier,
        data=payload,
        quality=quality,
        request_id=_new_request_id(),
    )


# ═══════════════════════════════════════════════════════════════════
# Tools — canonical 7-tool surface (audit §4.1)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool(structured_output=True, annotations=_READ_ANNOTATIONS, meta=_FREE_TIER_META)
async def brs_market_state() -> ResultEnvelope:
    """Canonical current market posture. Call this FIRST.

    Bundles the three public, keyless reads into one call:
      - regime structure (which game the market is playing)
      - three-eye convergence (how much the sensors agree)
      - system health (whether the instrument is operational)

    Returns market_structure, convergence, and system_health together with
    their as_of timestamps. If any read is stale or a sensor is down, that
    changes what every other answer means — check health before trusting a
    directional read. Free tier, no API key required.
    """
    structure, convergence, health = await asyncio.gather(
        _get("/api/v2/structure"),
        _get("/api/v2/confidence"),
        _get("/api/v1/system/health"),
    )
    for part in (structure, convergence, health):
        if isinstance(part, dict) and part.get("error"):
            return _envelope(part)
    # Bundle freshness: as fresh as its STALEST observed part. Components with
    # no observation instant (e.g. confidence verdicts) simply don't age the
    # bundle; a stalled observed part does.
    now = datetime.now(timezone.utc)
    observations = [_observation_of(p) for p in (structure, convergence, health)]
    oldest = _oldest_observation(observations)
    healthy = sum(
        1 for o in observations
        if o is not None and (now - o).total_seconds() <= _VALID_FOR_SECONDS
    )
    return _envelope(
        {
            "market_structure": structure,
            "convergence": convergence,
            "system_health": health,
        },
        observation=oldest,
        quality=QualityInfo(sources_expected=3, sources_healthy=healthy),
    )


@mcp.tool(structured_output=True, annotations=_READ_ANNOTATIONS, meta=_PRO_TIER_META)
async def brs_decision_context(
    tx_signature: str = "",
    chain: str = "solana",
    ref: str = "",
) -> ResultEnvelope:
    """Directional market context with evidence and caveats (Pro tier).

    Returns the current posture (bullish / bearish / WAIT) with the regime
    and zone it was read in, the reason, confidence, btc_price and timestamp.
    WAIT is the most common answer and means no edge is visible — it is
    context, not an instruction. Confidence is normalised against how much
    evidence was reachable: sent signals typically land 0.30–0.50, so compare
    against that distribution, not 1.0. Suppressed reads are shown
    (suppressed=true), never hidden.

    Payment (BRS-017): this is the metered Pro posture and is payable per-call
    via x402. Call it with no tx_signature first — if the result is
    status='error' with error.code='PAYMENT_REQUIRED', inspect error.payment:
    that carries the exact amount, currency, asset, networks, recipient, expiry
    and request_digest needed to build the settlement. Pay on an advertised
    rail, then re-call with the tx_signature (and matching chain/ref) to get
    the metered result. Retries are idempotent — the same tx_signature is
    never charged twice. A Pro key (BRS_API_KEY or a per-client key) skips
    payment entirely. Spend caps: max 3 re-calls per request; enforce your own
    max-per-call/max-per-day policy against error.payment before paying.

    Args:
        tx_signature: The signed x402 settlement tx from a prior payment. Empty
            on first call (you will receive the challenge instead).
        chain: Rail you paid on — "solana" or "base". Default "solana".
        ref: Optional attribution tag carried through to the payment ledger.
    """
    payload = await _get(_per_call_endpoint(tx_signature, chain, ref))
    # Abstention vs inability (BRS-021d): "no decisions yet" is INSUFFICIENT
    # DATA (status "unavailable"), not a computed WAIT — so an agent can tell
    # "edge not evaluated" apart from "evaluated, no edge".
    unavailable = (
        isinstance(payload, dict)
        and not payload.get("error")
        and payload.get("reason") == "no decisions yet"
    )
    return _envelope(payload, tier="pro", unavailable=unavailable)


@mcp.tool(structured_output=True, annotations=_READ_ANNOTATIONS, meta=_PRO_TIER_META)
async def brs_history(limit: int = Field(default=20, ge=1, le=200)) -> ResultEnvelope:
    """Recent calls and what Bitcoin did next (Pro tier).

    Each record carries timestamp, side, confidence, regime, zone, reason,
    plus resolved outcomes where available (+4h/+24h returns, worst
    drawdown). Outcomes are fixed once written and never re-scored. Use this
    to verify rather than trust.

    Args:
        limit: Number of recent calls to return (1–200, default 20).
    """
    return _envelope(
        await _get(f"/api/v2/bias/history?limit={limit}"),
        tier="pro",
    )


@mcp.tool(structured_output=True, annotations=_READ_ANNOTATIONS, meta=_FREE_TIER_META)
async def brs_audit_track_record(
    limit: int = Field(default=100, ge=1, le=500),
) -> ResultEnvelope:
    """The public proof: every call BRS has made and what Bitcoin did next.

    Returns the keyless track record — each entry carries timestamp, side
    (bullish/bearish), price at call time, confidence, regime, zone, and
    resolved +4h/+24h outcomes where the paper-trading log has them (return
    %, worst drawdown, best upside). Outcomes are fixed once written and
    never re-scored, so this is auditable evidence, not marketing.

    This is the "don't trust us — query us" surface: no API key and no
    payment are required. Use it to verify the system's real silence before
    trusting any signal.

    Args:
        limit: Number of recent calls to return (1–500, default 100).
    """
    data = await _get("/api/v2/signals/track-record")
    if isinstance(data, dict) and data.get("error"):
        return _envelope(data)
    signals = data.get("signals", []) if isinstance(data, dict) else []
    data["signals"] = signals[:limit]
    return _envelope(data)


@mcp.tool(structured_output=True, annotations=_READ_ANNOTATIONS, meta=_FREE_TIER_META)
async def brs_rejection_funnel(
    day: str = "",
    days: int = Field(default=0, ge=0, le=365),
    since: str = "",
) -> ResultEnvelope:
    """Why no signal? The pipeline funnel in one glance (public).

    Every cycle that does not become a signal died at a specific gate. This
    returns the cycle count at each gate in order, so an agent can draw a
    survival funnel and see where reads are rejected — the direct answer to
    "BRS rejects almost everything, prove it."

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
    return _envelope(await _get(f"/api/v2/health/funnel{params}"))


@mcp.tool(structured_output=True, annotations=_READ_ANNOTATIONS, meta=_FREE_TIER_META)
async def brs_system_status() -> ResultEnvelope:
    """Instrument health, SLO standing, and the sample size behind every
    reading (free).

    Bundles two keyless reads plus a measured SLO block:
      - component health: collector/engine status and last-good timestamps
      - system counters: signals sent, data points collected, days collecting.
        "Signals sent" is the authoritative all-time count from
        decoder_decision_records — the same figure the funnel and the landing
        page show, so every surface agrees.
      - slo: status; CONFIGURED (compliance_pct + scope note) vs MEASURED
        (uptime_24h_pct, boot-epoch uptime, latency_ms) kept apart; an
        observation_window discloses the 24h coverage and flags insufficient
        history explicitly. compliance_pct scope is "registry metadata checks"
        only (see compliance_note) — NOT protocol conformance (BRS-021f: this
        server serves 2026-07-28 modern + legacy ≤ 2025-11-25) and NOT
        operational health (the measured fields above)

    Call this when any reading looks stale or absent, and to see exactly how
    small the sample behind a claim is. Small samples cannot prove an edge.
    """
    started = time.monotonic()
    health, counters = await asyncio.gather(
        _get("/api/v1/system/health"),
        _get("/api/v2/system/counters"),
    )
    latency_ms = round((time.monotonic() - started) * 1000.0, 1)
    for part in (health, counters):
        if isinstance(part, dict) and part.get("error"):
            return _envelope(part)

    # Lazy import (BRS-019): mcp_brs/__init__ imports this module, so metadata
    # — pure data with no SDK dependency — is resolved only at call time,
    # mirroring the telemetry lazy-import pattern in _TieredFastMCP.call_tool.
    from mcp_brs import metadata as _metadata

    uptime = (health or {}).get("slo") or {}
    # BRS-021d — separate CONFIGURED targets (promises) from MEASURED results
    # (observations), and disclose the observation window + coverage with an
    # explicit insufficient_history flag. An uptime % is never fabricated: a
    # window the current boot cannot cover reads None + insufficient_history.
    slo = {
        "status": uptime.get("status") or _metadata.REGISTRY_STATUS,
        "status_detail": uptime.get("status_detail"),
        "configured": {
            "compliance_pct": _metadata.COMPLIANCE_PCT,
            "compliance_note": "registry metadata checks (BRS-014): server-card/"
                               "glama.json/mcpb manifest generated from canonical "
                               "metadata, CI drift-check green. NOT protocol "
                               "conformance (serves 2026-07-28 modern + legacy "
                               "<= 2025-11-25 — BRS-021f) and NOT operational "
                               "health (see measured below)",
        },
        "measured": {
            "uptime_24h_pct": uptime.get("uptime_24h_pct"),
            "uptime_note": uptime.get("uptime_note"),
            "uptime_seconds": uptime.get("uptime_seconds"),
            "boot_epoch": uptime.get("boot_epoch"),
            "api_serving": uptime.get("api_serving"),
            "live_loop_ok": uptime.get("live_loop_ok"),
            "signal_loop_age_seconds": uptime.get("signal_loop_age_seconds"),
            "latency_ms": latency_ms,
            "measured_at": _iso_now(),
        },
        "observation_window": {
            "uptime_window_hours": 24,
            "covered": uptime.get("uptime_24h_pct") is not None,
            "insufficient_history": uptime.get("uptime_24h_pct") is None,
        },
    }
    return _envelope({"health": health, "counters": counters, "slo": slo})


@mcp.tool(structured_output=True, annotations=_READ_ANNOTATIONS, meta=_PRO_TIER_META)
async def brs_raw_stream(
    stream: Literal["fees", "funding", "stablecoin", "gamma"] = "fees",
) -> ResultEnvelope:
    """Raw pre-price stream for agents doing explicit decomposition (Pro).

    Selects one raw data stream by name:
      - fees:       mempool fee-curve shape (X-Ray's raw read)
      - funding:    cross-exchange funding spread and squeeze probability
      - stablecoin: whale stablecoin transfers (USDT/USDC)
      - gamma:      dealer gamma exposure and flip level

    These are the ingredients behind the reads, not standalone trade signals.
    Some streams require a Pro API key. Free alternative: brs_market_state.

    Args:
        stream: One of "fees", "funding", "stablecoin", "gamma" (default "fees").
    """
    return _envelope(await _get(f"/api/v2/streams/{stream}"), tier="pro")


# ═══════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════

def _resolve_require_key(require: bool, expected_key: str) -> str:
    """Fail-closed gate (BRS-002): if a key gate is requested but the secret is
    empty, refuse to start. Never silently downgrade auth to keyless.

    Returns the expected key when the gate is armed, "" when keyless.
    Raises SystemExit(1) when armed with no secret.
    """
    if require and not expected_key:
        print("ERROR: --require-key set but BRS_MCP_SERVER_KEY is empty — "
              "refusing to start (fail-closed). Set BRS_MCP_SERVER_KEY to "
              "enforce, or drop --require-key to run keyless.", flush=True)
        raise SystemExit(1)
    return expected_key if require else ""


class _ClientKeyPass(BaseHTTPMiddleware):
    """Q58 Option C — per-client key pass-through (always on).

    Capture the caller's OWN key from the request and stash it in the
    ``_client_key`` context var for the request's duration; ``_headers()``
    then forwards it verbatim upstream. The server holds no key material and
    never logs it. No key on the request => free tier (keyless proxy); a key
    => that caller's own tier, with per-key rate attribution preserved
    upstream.

    Defined at module scope (BRS-021c) so the app the transport test drives is
    the SAME app production serves: ``_build_streamable_http_app()`` adds this
    middleware exactly as ``_run_streamable_http`` always has.
    """

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


class _KeyAuth(BaseHTTPMiddleware):
    """OPT-IN server-key gate for streamable-http (fail-closed, BRS-002).

    When armed (``--require-key``), every request must present the server key
    via ``Authorization: Bearer <key>`` or ``X-API-Key: <key>`` compared in
    constant time. Default OFF so the free-tier UX is unchanged — the operator
    opts in at launch. Applied OUTSIDE ``_ClientKeyPass`` so a rejected request
    never reaches the per-client key capture.
    """

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


def _build_streamable_http_app(
    require_key: bool = False,
    mount_path: str = "/mcp",
    host: str = "127.0.0.1",
):
    """Assemble the streamable-http ASGI app EXACTLY as the entry point does.

    Single construction point (BRS-021c) shared by ``_run_streamable_http``
    (production) and the real-transport tests, so a test drives the identical
    middleware stack — per-client key pass-through always on, optional outer
    server-key gate — and the identical session manager the deployed server
    serves.

    Returns the Starlette app (after middleware is added, which can no longer
    change) so callers may still attach transport-level routes.
    """
    app = mcp.streamable_http_app(
        streamable_http_path=mount_path,
        host=host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=_ALLOWED_HOSTS,
        ),
    )
    app.add_middleware(_ClientKeyPass)
    if require_key:
        expected = _resolve_require_key(
            True, os.environ.get("BRS_MCP_SERVER_KEY", "")
        )
        app.add_middleware(_KeyAuth, expected_key=expected)
    return app


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

    require = bool(args.require_key)
    app = _build_streamable_http_app(
        require_key=require,
        mount_path=args.mount_path,
        host=args.host,
    )

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

    config = uvicorn.Config(app, host=args.host, port=args.port,
                            log_level="info")
    uvicorn.Server(config).run()


def main():
    """Run the MCP server. stdio (default), sse, or streamable-http."""
    import argparse

    parser = argparse.ArgumentParser(
        description="₿RS Signals MCP Server — pre-price, three-eye Bitcoin signals for AI agents",
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
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:  # streamable-http
        _run_streamable_http(args)


if __name__ == "__main__":
    main()
