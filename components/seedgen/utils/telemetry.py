import logging
import json
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.status import Status, StatusCode
import openlit

from utils.redis import get_redis_client


def init_opentelemetry(otel_endpoint: str, otel_headers: str, otel_protocol: str, service_name: str):
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)

    resource = Resource(attributes={"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)

    if otel_protocol == "grpc":
        otlp_exporter = OTLPSpanExporter(
            endpoint=otel_endpoint, headers=otel_headers)
    elif otel_protocol == "http/protobuf":
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHTTPSpanExporter
            otlp_exporter = OTLPHTTPSpanExporter(
                endpoint=otel_endpoint, headers=otel_headers)
        except ImportError:
            logging.error(
                "OTLP HTTP exporter is not installed; falling back to gRPC exporter.")
            otlp_exporter = OTLPSpanExporter(
                endpoint=otel_endpoint, headers=otel_headers)
    else:
        logging.warning(
            "Unsupported OTLP protocol '%s' provided, using gRPC exporter instead.", otel_protocol)
        otlp_exporter = OTLPSpanExporter(
            endpoint=otel_endpoint, headers=otel_headers)

    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)

    openlit.init(tracer=trace.get_tracer(__name__), disable_metrics=True)


def get_task_metadata(task_id: str):
    redis_client = get_redis_client()
    if redis_client:
        task_metadata = redis_client.get(f"global:task_metadata:{task_id}")
        if task_metadata:
            return json.loads(task_metadata)

    return {
        "round.id": "test-round",
        "task.id": task_id,
        "team.id": "test-team",
    }


def get_task_span(task_id: str):
    redis_client = get_redis_client()
    if redis_client:
        task_span = redis_client.get(f"global:trace_context:{task_id}")
        if task_span:
            return task_span

    return None


def propagate_crs_attributes_to_child(child_span, parent_span):
    """
    Propagate all attributes with the 'crs.' prefix from parent_span to child_span,
    unless the child_span already has that attribute set.
    """
    if not parent_span or not child_span:
        return

    # Get all parent attributes with 'crs.' prefix
    parent_attrs = getattr(parent_span, "attributes", None)
    if parent_attrs is None:
        # For some SDKs, use parent_span._attributes (private, but common in Python SDK)
        parent_attrs = getattr(parent_span, "_attributes", {})

    crs_attrs = {k: v for k, v in parent_attrs.items() if k.startswith("crs.")}

    # Set them on the child span if not already set
    for k, v in crs_attrs.items():
        if k not in child_span.attributes:
            child_span.set_attribute(k, v)


@contextmanager
def start_span_with_crs_inheritance(name, **kwargs):
    tracer = trace.get_tracer(__name__)
    parent_span = trace.get_current_span()
    with tracer.start_as_current_span(name, **kwargs) as child_span:
        propagate_crs_attributes_to_child(child_span, parent_span)
        yield child_span