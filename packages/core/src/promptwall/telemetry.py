"""OpenTelemetry tracing + structlog setup.

Call :func:`configure` exactly once at startup (the proxy does this from its
FastAPI lifespan). The OTLP exporter ships spans non-blockingly via a batch
processor; tracing failures never break the request path.
"""

import logging

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from promptwall.settings import Settings


def configure(settings: Settings) -> None:
    """Wire up structlog (JSON to stdout) and OTel tracing (OTLP gRPC)."""
    _configure_logging(settings)
    _configure_tracing(settings)


def _configure_logging(settings: Settings) -> None:
    level = logging.getLevelNamesMapping().get(
        settings.log_level.upper(),
        logging.INFO,
    )
    logging.basicConfig(level=level, format="%(message)s")

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.log_renderer == "console":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _configure_tracing(settings: Settings) -> None:
    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
