package org.b3yond.utils;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import io.opentelemetry.exporter.otlp.trace.OtlpGrpcSpanExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import io.opentelemetry.semconv.ServiceAttributes;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Utility class for OpenTelemetry integration to handle tracing in the
 * application.
 */
public class OpenTelemetryUtil {
    private static final String SERVICE_NAME = "java-slicer";
    private static Tracer tracer;
    private static OpenTelemetry openTelemetry;

    static {
        initializeOpenTelemetry();
    }

    /**
     * Initializes the OpenTelemetry SDK using environment variables.
     */
    private static void initializeOpenTelemetry() {
        String endpoint = System.getenv("OTEL_EXPORTER_OTLP_ENDPOINT");
        if (endpoint == null || endpoint.isEmpty()) {
            System.err
                    .println("OTEL_EXPORTER_OTLP_ENDPOINT environment variable is not set. Tracing will be disabled.");
            return;
        }

        String headers = System.getenv("OTEL_EXPORTER_OTLP_HEADERS");

        try {
            Resource resource = Resource.getDefault()
                    .merge(Resource.create(Attributes.of(
                            ServiceAttributes.SERVICE_NAME, SERVICE_NAME)));

            OtlpGrpcSpanExporter exporter = OtlpGrpcSpanExporter.builder()
                    .setEndpoint(endpoint)
                    .addHeader("Authorization", extractAuthHeader(headers))
                    .setTimeout(30, TimeUnit.SECONDS)
                    .build();

            SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
                    .addSpanProcessor(BatchSpanProcessor.builder(exporter).build())
                    .setResource(resource)
                    .build();

            openTelemetry = OpenTelemetrySdk.builder()
                    .setTracerProvider(tracerProvider)
                    .buildAndRegisterGlobal();

            tracer = openTelemetry.getTracer(SERVICE_NAME);

            System.out.println("OpenTelemetry initialized successfully with endpoint: " + endpoint);
        } catch (Exception e) {
            System.err.println("Failed to initialize OpenTelemetry: " + e.getMessage());
            e.printStackTrace();
        }
    }

    /**
     * Extract authorization header value from the OTEL_EXPORTER_OTLP_HEADERS
     * environment variable
     */
    private static String extractAuthHeader(String headers) {
        if (headers == null || headers.isEmpty()) {
            return "";
        }

        // Parse header string like "Authorization=Basic dXNlcm5hbWU6cGFzc3dvcmQ="
        String[] parts = headers.split("=", 2);
        return parts.length > 1 ? parts[1].replace("\"", "") : "";
    }

    /**
     * Logs an action with the specified category, name, and attributes.
     * 
     * @param actionCategory  The category of the action (e.g., "task_processing")
     * @param actionName      The specific action name (e.g., "save_result")
     * @param taskMetadata    Map of task-related attributes
     * @param extraAttributes Additional attributes to include
     */
    public static void logAction(String actionCategory, String actionName,
            Map<String, String> taskMetadata,
            Map<String, String> extraAttributes) {
        if (tracer == null) {
            System.err.println("OpenTelemetry tracer not initialized. Skipping trace.");
            return;
        }

        Span span = tracer.spanBuilder(actionCategory)
                .setSpanKind(SpanKind.INTERNAL)
                .startSpan();

        try (Scope scope = span.makeCurrent()) {
            // Set standard attributes
            span.setAttribute("crs.action.category", actionCategory);
            span.setAttribute("crs.action.name", actionName);
            span.setAttribute("crs.action.code.file", "not_available.java");

            // Set task metadata attributes
            if (taskMetadata != null) {
                for (Map.Entry<String, String> entry : taskMetadata.entrySet()) {
                    span.setAttribute(entry.getKey(), entry.getValue());
                }
            }

            // Set extra attributes
            if (extraAttributes != null) {
                for (Map.Entry<String, String> entry : extraAttributes.entrySet()) {
                    span.setAttribute(entry.getKey(), entry.getValue());
                }
            }

            span.setStatus(StatusCode.OK);
        } finally {
            span.end();
        }

        System.out.println("Logged crs action: " + actionCategory + " - " + actionName);
    }

    /**
     * Simplified version to log task-related actions
     */
    public static void logTaskAction(String actionName, String taskId, String resultPath) {
        Map<String, String> taskMetadata = Map.of(
                "task.id", taskId,
                "round.id", "final",
                "team.id", "b3yond",
                "crs.action.result.path", resultPath != null ? resultPath : "null");

        logAction("java_static_analysis", actionName, taskMetadata, null);
    }
}
