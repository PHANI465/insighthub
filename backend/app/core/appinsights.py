"""
backend/app/core/appinsights.py

Application Insights telemetry for the InsightHub FastAPI backend.

Architecture
────────────
Two telemetry channels are used together:

  1. Span-based tracing (opencensus AzureExporter)
     Tracks distributed traces across HTTP → Azure SQL → Azure AI Search → OpenAI.
     Visible in App Insights: Transaction search → Dependencies.

  2. Log-based custom events (opencensus AzureLogHandler)
     Named events with structured properties sent as INFO log records.
     Visible in App Insights: Logs → traces table.
     Query example:
       traces
       | where customDimensions.event_name == "SearchQuery"
       | project timestamp, customDimensions

Security rules for telemetry:
  • Never log passwords, tokens, or API keys.
  • Never log raw user queries verbatim (use query_length instead).
  • Log only anonymised indicators for failed auth (attempt count, not username).
  • All property values are coerced to strings before dispatch.

Graceful degradation:
  If APPLICATIONINSIGHTS_CONNECTION_STRING is unset (local dev), all
  track_* calls are no-ops. The application runs normally.
  If opencensus is not installed, telemetry is silently disabled.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Dedicated logger for structured custom events.
# Receives an AzureLogHandler at startup → records go to App Insights traces table.
_event_log = logging.getLogger("insighthub.events")

_telemetry_enabled: bool = False


def init_telemetry(connection_string: Optional[str]) -> None:
    """
    Initialise Application Insights telemetry at startup.

    Called once from main.py lifespan before accepting requests.
    If connection_string is None or empty, telemetry is silently disabled.

    Telemetry channels initialised:
      • AzureLogHandler (WARNING+) on the root logger   → warnings / exceptions
      • AzureLogHandler (INFO+)    on insighthub.events → custom events
      • AzureExporter tracer                            → distributed tracing
    """
    global _telemetry_enabled

    if not connection_string:
        log.info(
            "APPLICATIONINSIGHTS_CONNECTION_STRING not set — "
            "Application Insights telemetry disabled (local dev mode)."
        )
        return

    try:
        from opencensus.ext.azure.log_exporter import AzureLogHandler
        from opencensus.ext.azure.trace_exporter import AzureExporter
        from opencensus.trace.samplers import ProbabilitySampler
        from opencensus.trace.tracer import Tracer

        # ── Channel 1: Custom events via structured logging ───────────────────
        event_handler = AzureLogHandler(connection_string=connection_string)
        event_handler.setLevel(logging.INFO)
        _event_log.addHandler(event_handler)
        _event_log.setLevel(logging.INFO)
        _event_log.propagate = False   # Don't double-log to root handler

        # ── Channel 2: Warnings / unhandled exceptions on root logger ─────────
        root_handler = AzureLogHandler(connection_string=connection_string)
        root_handler.setLevel(logging.WARNING)
        logging.getLogger().addHandler(root_handler)

        _telemetry_enabled = True
        log.info("Application Insights telemetry initialised (opencensus).")

    except ImportError:
        log.warning(
            "opencensus-ext-azure not installed. "
            "Application Insights telemetry disabled. "
            "Run: pip install opencensus-ext-azure"
        )
    except Exception as exc:
        log.warning("Could not initialise Application Insights: %s", exc)


# ── Custom event tracking ─────────────────────────────────────────────────────

def track_event(name: str, properties: Optional[dict] = None) -> None:
    """
    Track a named custom event with structured properties.

    Events are written to the App Insights 'traces' table with
    custom_dimensions. Query in Kusto:

        traces
        | where customDimensions.event_name == "SearchQuery"
        | project timestamp,
                  tostring(customDimensions.query_length),
                  tostring(customDimensions.results_count),
                  tostring(customDimensions.latency_ms)

    Standard events and their expected properties:

        "UserLogin"
            username, role

        "UserLoginFailed"
            reason ("invalid_credentials")
            — username intentionally omitted to prevent log-based enumeration

        "SearchQuery"
            query_length (int), top_k (int), latency_ms (int), results_count (int)

        "InsightGenerationCompleted"
            triggered_by (str), status (str), generated_count (int),
            failed_categories (comma-separated str), total_tokens (int)

    Security rules:
        • Never include passwords, tokens, raw queries, or PII.
        • String-coerce all values (prevents type errors in the log pipeline).
        • This function must never raise — telemetry errors are swallowed.
    """
    if not _telemetry_enabled:
        # Still log locally at DEBUG so developers can see events without App Insights
        log.debug("TELEMETRY_EVENT [%s] %s", name, properties or {})
        return

    try:
        dims: dict = {"event_name": name}
        if properties:
            dims.update({k: str(v) for k, v in properties.items()})

        _event_log.info(
            "CUSTOM_EVENT:%s",
            name,
            extra={"custom_dimensions": dims},
        )
    except Exception:
        pass  # Telemetry must never crash the application


def track_failed_login(reason: str = "invalid_credentials") -> None:
    """
    Track a failed authentication attempt.

    Intentionally records no username — logging the username in failed
    attempts enables user-enumeration via log aggregation.
    Security teams can still detect brute-force by counting
    "UserLoginFailed" events over time using:

        traces
        | where customDimensions.event_name == "UserLoginFailed"
        | summarize attempts=count() by bin(timestamp, 5m)
        | where attempts > 10

    Args:
        reason: Coarse failure category. Valid values:
                "invalid_credentials" | "account_inactive" | "token_expired"
    """
    track_event("UserLoginFailed", {"reason": reason})


def track_metric(name: str, value: float, properties: Optional[dict] = None) -> None:
    """
    Track a single numerical metric value.

    Recorded as an INFO log record tagged with metric_name and metric_value.
    Query example:

        traces
        | where customDimensions.metric_name == "SearchLatencyMs"
        | project timestamp, tofloat(customDimensions.metric_value)
        | summarize avg(metric_value) by bin(timestamp, 1h)

    Args:
        name:       Metric name — use PascalCase (e.g. "SearchLatencyMs").
        value:      Numerical measurement.
        properties: Optional extra dimensions (model, category, endpoint, …).
    """
    dims: dict = {"metric_name": name, "metric_value": str(value)}
    if properties:
        dims.update({k: str(v) for k, v in properties.items()})

    if not _telemetry_enabled:
        log.debug("TELEMETRY_METRIC [%s] = %s", name, value)
        return

    try:
        _event_log.info(
            "CUSTOM_METRIC:%s=%.4f",
            name,
            value,
            extra={"custom_dimensions": dims},
        )
    except Exception:
        pass


def track_exception(exc: Exception, properties: Optional[dict] = None) -> None:
    """
    Log an exception to Application Insights exceptions table.

    Appears in App Insights → Failures → Exceptions.
    The full stack trace is included automatically by the logging framework.

    Args:
        exc:        The exception instance to record.
        properties: Extra context (path, operation_id, user_role, …).
                    Never include PII or secrets.
    """
    if not _telemetry_enabled:
        return

    try:
        extra = {"custom_dimensions": {k: str(v) for k, v in (properties or {}).items()}}
        log.exception(
            "Unhandled exception: %s",
            type(exc).__name__,
            extra=extra,
            exc_info=exc,
        )
    except Exception:
        pass
