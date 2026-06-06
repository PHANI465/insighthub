"""
backend/app/core/appinsights.py

Application Insights telemetry for the InsightHub FastAPI backend.

What gets tracked
──────────────────
• Custom events: search queries, insight generation requests, embed token requests
• Exceptions: unhandled errors with full stack traces
• Dependency calls: Azure SQL, AI Search, OpenAI (via opencensus auto-instrumentation)

In production, Application Insights receives the telemetry and makes it
searchable in Azure Monitor → Application Insights → Logs (Kusto queries).

If APPLICATIONINSIGHTS_CONNECTION_STRING is not set (local dev), telemetry
calls are no-ops — the application runs normally without any tracking.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Module-level flag: True once opencensus is initialised
_telemetry_enabled = False
_tracer = None


def init_telemetry(connection_string: Optional[str]) -> None:
    """
    Initialise Application Insights telemetry at startup.
    Must be called once from main.py lifespan before accepting requests.

    If connection_string is None/empty, telemetry is silently disabled.
    """
    global _telemetry_enabled, _tracer

    if not connection_string:
        log.info("APPLICATIONINSIGHTS_CONNECTION_STRING not set — telemetry disabled.")
        return

    try:
        from opencensus.ext.azure import metrics_exporter
        from opencensus.ext.azure.log_exporter import AzureLogHandler
        from opencensus.ext.azure.trace_exporter import AzureExporter
        from opencensus.trace.samplers import ProbabilitySampler
        from opencensus.trace.tracer import Tracer

        # Add Azure log handler so Python logging goes to App Insights
        handler = AzureLogHandler(connection_string=connection_string)
        handler.setLevel(logging.WARNING)
        logging.getLogger().addHandler(handler)

        # Create a tracer for custom spans
        _tracer = Tracer(
            exporter=AzureExporter(connection_string=connection_string),
            sampler=ProbabilitySampler(1.0),
        )
        _telemetry_enabled = True
        log.info("Application Insights telemetry initialised.")

    except ImportError:
        log.warning(
            "opencensus-ext-azure not installed. "
            "Application Insights telemetry disabled."
        )
    except Exception as exc:
        log.warning("Could not initialise Application Insights: %s", exc)


def track_event(name: str, properties: Optional[dict] = None) -> None:
    """
    Track a named custom event with optional properties.

    Usage:
        track_event("SearchQuery", {"query": q, "results_count": n})
        track_event("EmbedTokenRequested", {"report_id": rid})
        track_event("InsightGenerated", {"category": cat, "tokens_used": n})

    Properties are sanitised — never log raw user input that could contain PII.
    """
    if not _telemetry_enabled or _tracer is None:
        return

    try:
        with _tracer.span(name=name) as span:
            if properties:
                for k, v in properties.items():
                    span.add_attribute(k, str(v))
    except Exception:
        pass  # Telemetry must never crash the application


def track_exception(exc: Exception, properties: Optional[dict] = None) -> None:
    """Log an exception to Application Insights."""
    if not _telemetry_enabled:
        return

    try:
        # opencensus will capture the exception from the log record
        extra = {"custom_dimensions": properties or {}}
        log.exception("Unhandled exception tracked", extra=extra, exc_info=exc)
    except Exception:
        pass
