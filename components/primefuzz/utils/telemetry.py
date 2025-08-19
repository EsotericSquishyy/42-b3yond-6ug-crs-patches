import time
import logging
import os
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.status import Status, StatusCode
# from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
import openlit

resource = Resource(
    attributes={"service.name": "primefuzz", "service.version": 1})

# Get the tracer after openlit has been initialized
tracer = trace.get_tracer(__name__)
# propagator = TraceContextTextMapPropagator()
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


def get_current_task_mock() -> dict:
    # Context for the task
    return {
        "metadata": {
            "round.id": "final",
            "task.id": "task-1",
            "team.id": "team-1",
        }
    }


def get_telemetry_metric_mock() -> dict:

    return {
        "crs.action.category": "fuzzing",
        "crs.action.name": "fuzz_test_network_inputs",
        "crs.action.target.harness": "network_harness",
        "fuzz.corpus.update.method": "periodic",
        "fuzz.corpus.size": 1500,
        "fuzz.corpus.additions": ["inputA", "inputB"],
    }


def log_action(
    crs_action_category: str,
    crs_action_name: str,
    task_metadata: dict,
    extra_attributes: dict | None = None,
    status=None
):
    try:
        extra_attributes = extra_attributes or {}
        with tracer.start_as_current_span(crs_action_category) as span:
            span.set_attribute("crs.action.category", crs_action_category)
            span.set_attribute("crs.action.name", crs_action_name)
            instance_id = os.getenv("INSTANCE_ID", "primefuzz-NA")

            span.set_attribute("fuzz.instance.id", instance_id)

            for key, value in task_metadata.items():
                span.set_attribute(key, value)

            for key, value in extra_attributes.items():
                span.set_attribute(key, value)

            if status:
                span.set_status(Status(StatusCode.ERROR, str(status)))
            else:
                span.set_status(Status(StatusCode.OK))

        print(
            f"[TELEMETRY] Logged crs action: {crs_action_category} - {crs_action_name}")
    except Exception as e:
        logging.warning(f"Failed to log telemetry action: {str(e)}")
        logging.debug(
            f"Action details: category={crs_action_category}, name={crs_action_name}",
            exc_info=True,
        )


def log_action_from_metrics(
    metrics: dict,
    round_id: str,
    task_id: str,
    harness_name: str,
    extra_info: str,
    team_id: str = "b3yond",
):
    # alternatively, we can use another environment variable
    collector_endpoint = os.getenv("OTEL_COLLECTOR_ENDPOINT")
    if collector_endpoint:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = collector_endpoint

    endpoint_env = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint_env:
        print("OTEL_EXPORTER_OTLP_ENDPOINT is not set. Skipping telemetry logging.")
        return

    task_metadata = {
        # always 1 for the first round
        "round.id": "final",
        "task.id": task_id,
        "team.id": team_id,
    }
    metadata_middleware = metrics.get("metadata", {})
    task_metadata.update(metadata_middleware)
    crs_action_category = metrics.get("crs.action.category", "fuzzing")
    crs_action_name = (
        "primejavadirected"
        if os.getenv("DIRECTED_MODE")
        else metrics.get("crs.action.name", "primefuzz")
    )
    extra_attributes = {"fuzz.corpus.update.method": "periodic"}
    # set required attributes
    additions = metrics.get("additions", [])
    additions.append(metrics.get("coverage", 0))
    additions.append(metrics.get("features", 0))
    additions.append(metrics.get("execs_per_sec", 0))
    extra_attributes["crs.action.target.harness"] = harness_name
    extra_attributes["fuzz.corpus.size"] = metrics.get("corpus_count", 0)
    extra_attributes["fuzz.corpus.update.time"] = time.time()
    extra_attributes["fuzz.corpus.additions"] = additions
    extra_attributes["fuzz.findings.memo"] = extra_info
    extra_attributes["fuzz.corpus.full_snapshot"] = True

    log_action(crs_action_category, crs_action_name,
               task_metadata, extra_attributes)


def local_test_with_mock():
    task_metadata = get_current_task_mock()
    telemetry_metric = get_telemetry_metric_mock()

    log_action(
        crs_action_category=telemetry_metric["crs.action.category"],
        crs_action_name=telemetry_metric["crs.action.name"],
        task_metadata=task_metadata,
        extra_attributes=telemetry_metric,
    )


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
