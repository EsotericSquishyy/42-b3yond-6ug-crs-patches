import time
import logging
import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.status import Status, StatusCode
import openlit
import json
import asyncio

from contextvars import ContextVar

telemetry_spans = ContextVar("telemetry_spans", default={})

resource = Resource(
    attributes={"service.name": "submitter", "service.version": 1})

# Get the tracer after openlit has been initialized
tracer = trace.get_tracer(__name__)
trace.set_tracer_provider(TracerProvider(resource=resource))
openlit.init(tracer=tracer)

# Add our exporter to the existing provider (if possible)
try:
    otel_exporter_otlp_headers = os.environ.get('OTEL_EXPORTER_OTLP_HEADERS')
    otel_exporter_otlp_endpoint = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT')
    otlp_exporter = OTLPSpanExporter(
        endpoint=otel_exporter_otlp_endpoint, headers=otel_exporter_otlp_headers)
    # otlp_exporter = OTLPSpanExporter()
    span_processor = BatchSpanProcessor(otlp_exporter)
    # Try to add our span processor to the existing provider
    provider = trace.get_tracer_provider()
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(span_processor)
    else:
        logging.warning(
            "Unable to add span processor to the current TracerProvider. Telemetry may be limited.")
except Exception as e:
    logging.warning(f"Failed to configure additional telemetry: {str(e)}")



def log_action(crs_action_category: str, crs_action_name: str, task_metadata: dict, extra_attributes: dict | None = None):
    extra_attributes = extra_attributes or {}
    with tracer.start_as_current_span(crs_action_category) as span:
        span.set_attribute("crs.action.category", crs_action_category)
        span.set_attribute("crs.action.name", crs_action_name)

        for key, value in task_metadata.items():
            span.set_attribute(key, value)

        for key, value in extra_attributes.items():
            span.set_attribute(key, value)

        span.set_status(Status(StatusCode.OK))

    # print(f"Logged crs action: {crs_action_category} - {crs_action_name}")
    
async def get_task_metadata(redisstore, task_id: str):
    redis_client = redisstore
    if redis_client:
        task_metadata = await redis_client.get(f"global:task_metadata:{task_id}")
        if task_metadata:
            return json.loads(task_metadata)
    
    return {
        "round.id": "test-round",
        "task.id": task_id,
        "team.id": "test-team",
    }

def create_span(name: str, attributes: dict | None = None, parent_span=None) -> trace.Span:
    """Create a new span with the given name and attributes.
    
    Args:
        name: Name of the span
        attributes: Optional dictionary of attributes to add to the span
        parent_span: Optional parent span to create this span under
    
    Returns:
        The created span
    """
    context = trace.set_span_in_context(parent_span) if parent_span else None
    span = tracer.start_span(name, context=context)
    
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
            
    return span

def mark_span_failed(span: trace.Span, error: Exception):
    """Mark a span as failed with the given error.
    
    Args:
        span: The span to mark as failed
        error: The exception that caused the failure
    """
    span.set_status(Status(StatusCode.ERROR))
    span.record_exception(error)
    
def end_span(span: trace.Span, status: StatusCode = StatusCode.OK):
    """End the given span with the specified status.
    
    Args:
        span: The span to end
        status: Optional status code (defaults to OK)
    """
    span.set_status(Status(status))
    span.end()
    
def end_span_with_failure(span: trace.Span, error: Exception):
    mark_span_failed(span, error)
    end_span(span)

class SpanContextManager:
    """Context manager for automatically managing span lifecycle."""
    
    def __init__(self, name: str, attributes: dict | None = None, parent_span: trace.Span | None = None):
        self.name = name
        self.attributes = attributes or {}
        self.parent_span = parent_span
        self.span = None
        
    def __enter__(self):
        self.span = create_span(self.name, self.attributes, self.parent_span)
        return self.span
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            mark_span_failed(self.span, exc_val)
        end_span(self.span)
        return False  # Don't suppress exceptions

def with_span(name: str, attributes: dict | None = None, parent_span: trace.Span | None = None):
    """Decorator to automatically create and manage a span around a function.
    
    Args:
        name: Name of the span
        attributes: Optional dictionary of attributes to add to the span
        parent_span: Optional parent span to create this span under
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with SpanContextManager(name, attributes, parent_span) as span:
                return func(*args, **kwargs)
        return wrapper
    return decorator

# Example usage:
"""
# Using the context manager:
with SpanContextManager("operation_name", {"attribute": "value"}, parent_span=some_span) as span:
    # Do work here
    pass

# Using the decorator:
@with_span("operation_name", {"attribute": "value"}, parent_span=some_span)
def my_function():
    # Do work here
    pass

# Using the functions directly:
span = create_span("operation_name", {"attribute": "value"}, parent_span=some_span)
try:
    # Do work here
    end_span(span)
except Exception as e:
    mark_span_failed(span, e)
    raise
"""

