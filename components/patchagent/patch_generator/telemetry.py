import logging
from logging import Logger
from typing import Any, Dict, List, Optional

import openlit
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.status import Status, StatusCode

from aixcc.db import PatchDebug, Task, make_session
from patch_generator.env import OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS


class TelemetryContext:
    CURRENT_TASK_ID: Optional[str] = None
    METADATA_CACHE: Dict[str, Dict[str, Any]] = {}

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    def __enter__(self) -> None:
        assert TelemetryContext.CURRENT_TASK_ID is None
        TelemetryContext.CURRENT_TASK_ID = self.task_id

    def __exit__(self, exc_type: str, exc_value: Exception, traceback: Any) -> None:
        assert TelemetryContext.CURRENT_TASK_ID == self.task_id
        TelemetryContext.CURRENT_TASK_ID = None

    @staticmethod
    def current_metadata() -> Dict[str, Any]:
        if TelemetryContext.CURRENT_TASK_ID is None:
            return {}

        task_id = TelemetryContext.CURRENT_TASK_ID
        if task_id not in TelemetryContext.METADATA_CACHE:
            with make_session() as session:
                metadata = session.query(Task).filter(Task.id == task_id).one().metadata_ or {}
                TelemetryContext.METADATA_CACHE[task_id] = metadata

        return TelemetryContext.METADATA_CACHE[task_id]


def patchagent_hook(logger: Logger) -> None:
    class PatchAgentErrorRecorder(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno == logging.ERROR:
                description = record.getMessage()
                if TelemetryContext.CURRENT_TASK_ID is not None:
                    description = f"Task ID: {TelemetryContext.CURRENT_TASK_ID} - {description}"

                with make_session() as session:
                    session.add(PatchDebug(event="fixme", description=description))
                    session.commit()

    patchagent_error_recorder = PatchAgentErrorRecorder()
    patchagent_error_recorder.setLevel(logging.ERROR)
    logger.addHandler(patchagent_error_recorder)


def telemetry_hook(loggers: List[Logger]) -> None:
    service_name = "patchagent"
    resource = Resource(attributes={"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT, headers=OTEL_EXPORTER_OTLP_HEADERS)
    span_processor = BatchSpanProcessor(otlp_exporter)
    tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(tracer_provider)

    tracer = trace.get_tracer(__name__)
    openlit.init(tracer=tracer, disable_metrics=True)

    class TelemetryLogHandler(logging.Handler):
        def __init__(self) -> None:
            super().__init__()

        def emit(self, record: logging.LogRecord) -> None:
            task_metadata = TelemetryContext.current_metadata()

            if record.levelname == "DEBUG":
                crs_action_category = "patch_generation"
                crs_action_name = "debug"
            else:
                crs_action_category = "execution"
                crs_action_name = "log"

            with tracer.start_as_current_span(crs_action_category) as span:
                span.set_attribute("crs.action.category", crs_action_category)
                span.set_attribute("crs.action.name", crs_action_name)

                for key, value in task_metadata.items():
                    span.set_attribute(key, value)

                span.set_attribute("info", record.getMessage())
                span.set_attribute("level", record.levelname)
                span.set_status(Status(StatusCode.OK))

    telemetry_handler = TelemetryLogHandler()
    for logger in loggers:
        logger.addHandler(telemetry_handler)
