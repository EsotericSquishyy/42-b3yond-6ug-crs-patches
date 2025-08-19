import logging
import json
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.status import Status, StatusCode
# If you’re using the v2 instrumentor:
# from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
# from opentelemetry.instrumentation.openai import OpenAIInstrumentor

# This flag suppresses *all* input‐content attributes (including stop_sequences)

import openlit

import openlit.instrumentation.anthropic.utils as _uanthro


tracer = None


def init_opentelemetry(otel_endpoint: str, otel_headers: str, otel_protocol: str, service_name: str):
    
    _orig_common_chat_logic = _uanthro.common_chat_logic

    def _safe_common_chat_logic(scope, pricing_info, environment, application_name, metrics,
                        event_provider, capture_message_content, disable_metrics, version, is_stream):
        # if someone set scope._tool_calls to a dict, turn it into a list of its values
        if hasattr(scope, '_tool_calls') and scope._tool_calls == []:
            scope._tool_calls = None
        if hasattr(scope, '_tool_calls') and isinstance(scope._tool_calls, dict):
            current_tool_calls = scope._tool_calls
            scope._tool_calls[0] = current_tool_calls
        return _orig_common_chat_logic(scope, pricing_info, environment, application_name, metrics,
                        event_provider, capture_message_content, disable_metrics, version, is_stream)

    # overwrite the buggy function
    _uanthro.common_chat_logic = _safe_common_chat_logic
    
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    
    # OpenAIInstrumentor().instrument(suppress_input_content=True)
    
    resource = Resource(attributes={"service.name": service_name})
    
    tracer_provider = TracerProvider(resource=resource)

    if otel_protocol == "grpc":
        otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, headers=otel_headers)
    elif otel_protocol == "http/protobuf":
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHTTPSpanExporter
            otlp_exporter = OTLPHTTPSpanExporter(endpoint=otel_endpoint, headers=otel_headers)
        except ImportError:
            logging.error("OTLP HTTP exporter is not installed; falling back to gRPC exporter.")
            otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, headers=otel_headers)
    else:
        logging.warning("Unsupported OTLP protocol '%s' provided, using gRPC exporter instead.", otel_protocol)
        otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, headers=otel_headers)
    
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)
    
    global tracer
    tracer = trace.get_tracer(__name__)
    
    openlit.init(tracer=tracer, disable_metrics=True, capture_message_content=False)

