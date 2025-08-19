import time
import logging
import os
import json
from typing import Optional, Dict, Any, Union
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
import openlit
import functools

def span_decorator(name):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            current_span = self.current_span
            with create_span(name, parent_span=current_span) as span:
                try:
                    self.current_span = span
                    result = func(self, *args, **kwargs)
                    self.current_span = current_span
                    if result or result is None:
                        set_span_status(span, "OK")
                    else:
                        set_span_status(span, "ERROR")
                    return result
                except Exception as e:
                    set_span_status(span, "ERROR", description=str(e))
                    raise
        return wrapper
    return decorator



resource = Resource(attributes={"service.name": "sarif", "service.version": 1})

# Get the tracer after openlit has been initialized
tracer = trace.get_tracer(__name__)
trace.set_tracer_provider(TracerProvider(resource=resource))
openlit.init(tracer=tracer)

# Add our exporter to the existing provider (if possible)
try:
    otel_exporter_otlp_headers = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS")
    otel_exporter_otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    otlp_exporter = OTLPSpanExporter(
        endpoint=otel_exporter_otlp_endpoint, headers=otel_exporter_otlp_headers
    )
    span_processor = BatchSpanProcessor(otlp_exporter)
    # Try to add our span processor to the existing provider
    provider = trace.get_tracer_provider()
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(span_processor)
    else:
        logging.warning(
            "Unable to add span processor to the current TracerProvider. Telemetry may be limited."
        )
except Exception as e:
    logging.warning(f"Failed to configure additional telemetry: {str(e)}")

def create_span(
    name: str,
    parent_span: Optional[trace.Span] = None,
    attributes: Optional[Dict[str, Any]] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL
) -> trace.Span:
    """
    Create a new span with optional parent span and attributes.
    
    Args:
        name: Name of the span
        parent_span: Optional parent span to create parent-child relationship
        attributes: Optional dictionary of attributes to set on the span
        kind: Span kind (INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER)
        
    Returns:
        The created span
    """
    if parent_span:
        context = trace.set_span_in_context(parent_span)
        span = tracer.start_span(name, context=context, kind=kind)
    else:
        span = tracer.start_span(name, kind=kind)
        
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
            
    return span

def inject_span_context(carrier: Dict[str, str], current_span: Optional[trace.Span] = None) -> Dict[str, str]:
    """
    Inject span context into a carrier dictionary.
    
    Args:
        carrier: Dictionary to inject context into
        current_span: Optional span to use for context injection. If None, will try to get current span.
        
    Returns:
        Updated carrier with injected context
    """
    propagator = TraceContextTextMapPropagator()
    
    if current_span is None:
        current_span = trace.get_current_span()
    
    if not current_span or not current_span.get_span_context().is_valid:
        logging.warning("No active span or invalid span context")
        return carrier
    
    context = trace.set_span_in_context(current_span)
    
    propagator.inject(carrier, context=context)
    
    logging.debug(f"Injected span context: {carrier}")
    return carrier

def extract_span_context(carrier: Dict[str, str]) -> trace.SpanContext:
    """
    Extract span context from a carrier dictionary.
    
    Args:
        carrier: Dictionary containing span context
        
    Returns:
        Extracted span context
    """
    propagator = TraceContextTextMapPropagator()
    return propagator.extract(carrier)

def log_event(
    span: trace.Span,
    name: str,
    attributes: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log an event on a span.
    
    Args:
        span: Span to add event to
        name: Name of the event
        attributes: Optional attributes for the event
    """
    print(f"log_event: {span}")
    span.add_event(name, attributes=attributes or {})

def set_span_status(
    span: trace.Span,
    status: str,
    description: Optional[str] = None
) -> None:
    """
    Set the status of a span.
    
    Args:
        span: Span to set status on
        status: Status code (OK or ERROR)
        description: Optional description of the status
    """
    status_code = StatusCode.OK if status == "OK" else StatusCode.ERROR
    print(f"set_span_status: {span}")
    span.set_status(Status(status_code, description))

def get_current_span(ctx: trace.SpanContext=None) -> trace.Span:
    """
    Get the current active span.
    
    Returns:
        Current span
    """
    return trace.get_current_span(ctx)

def get_telemetry_metric_mock() -> dict:

    return {
        "crs.action.category": "directed",
        "crs.action.name": "test_action",
        "directed.corpus.update.method": "periodic",
        "title": [],
        "msg": [],
        "log.level": "verbose",
    }


def log_action(
    directed_title: str,
    directed_msg: list,
    crs_action_category: str,
    crs_action_name: str,
    status: str = StatusCode.OK,
    log_level: str = "verbose"
):
    try:
        with tracer.start_as_current_span(crs_action_category) as span:
            span.set_attribute("crs.action.category", crs_action_category)
            span.set_attribute("crs.action.name", crs_action_name)
            span.set_attribute("title", directed_title)
            directed_msg_str = [str(msg) for msg in directed_msg]
            span.set_attribute("msg","\n".join(directed_msg_str))
            span.set_attribute("log.level", log_level)
            span.set_status(Status(status))
            # span.set_status(Status(StatusCode.ERROR))

        logging.debug(f"Logged crs action: {crs_action_name}")
    except Exception as e:
        logging.warning(f"Failed to log telemetry action: {str(e)}")
        logging.debug(
            f"Action details: category={crs_action_category}, name={crs_action_name}",
            exc_info=True,
        )
        print(f"Failed to log telemetry action: {str(e)}")
    # print("Logged telemetry action")


def log_action_from_metrics(
    metrics: dict,
    crs_action_name: str = "action",
    status_str: str = "OK"
):
    # alternatively, we can use another environment variable
    collector_endpoint = os.getenv("OTEL_COLLECTOR_ENDPOINT")
    if collector_endpoint:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = collector_endpoint

    # endpoint_env = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    endpoint_env = "https://otel.virtual-echo.aixcc.tech"

    if not endpoint_env:
        print("OTEL_EXPORTER_OTLP_ENDPOINT is not set. Skipping telemetry logging.")
        return

    crs_action_category = metrics.get("crs.action.category", "directed")
    directed_title = metrics.get("title", [])
    directed_msg = metrics.get("msg", [])
    log_level = metrics.get("log.level", "verbose")

    status = StatusCode.OK if status_str == "OK" else StatusCode.ERROR

    log_action(directed_title, directed_msg, crs_action_category, crs_action_name, status, log_level)

def log_telemetry_action(title: str, msg_list: list, action_name: str, status: str, level: str = "verbose"):
    return True
    try:
        telemetry_metric = get_telemetry_metric_mock()
        telemetry_metric["title"].append(title)
        telemetry_metric["msg"].extend(msg_list)
        telemetry_metric["log.level"] = level
        log_action_from_metrics(metrics=telemetry_metric, crs_action_name=action_name, status_str=status)
    except Exception as e:
        logging.error("Error logging action: %s", e)
        return False
    return True