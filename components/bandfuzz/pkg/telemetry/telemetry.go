package telemetry

import (
	"b3fuzz/config"
	"context"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/log"
	"go.opentelemetry.io/otel/propagation"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.4.0"
	"go.opentelemetry.io/otel/trace"
	"go.uber.org/fx"
)

type Telemetry interface {
	GetTracer() trace.Tracer
	GetLogger() log.Logger
}

type TelemetryImpl struct {
	tracer trace.Tracer
	logger log.Logger
}

type TelemetryParams struct {
	fx.In
	Lifecyle fx.Lifecycle
	Config   *config.AppConfig
}

func NewTelemetry(p TelemetryParams) (Telemetry, error) {
	telemetryCtx, cancel := context.WithCancel(context.Background())

	// --- Tracing Setup ---
	tracerExp, err := otlptracegrpc.New(telemetryCtx)
	if err != nil {
		cancel()
		return nil, err
	}

	traceProvider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(tracerExp),
		sdktrace.WithResource(resource.NewWithAttributes(
			semconv.SchemaURL,
			attribute.String("service.name", p.Config.ServiceName),
		)),
	)
	otel.SetTracerProvider(traceProvider)
	tracer := traceProvider.Tracer(p.Config.ServiceName)

	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	// --- Logging Setup ---
	// Log exporter may fail (because SDK is still beta), so we won't require it.
	logExp, err := otlploggrpc.New(telemetryCtx)
	var logProvider *sdklog.LoggerProvider = nil
	var logger log.Logger = nil
	if err == nil {
		processor := sdklog.NewBatchProcessor(logExp)
		logProvider = sdklog.NewLoggerProvider(sdklog.WithProcessor(processor))
		logger = logProvider.Logger(p.Config.ServiceName)
	}

	// when the app shuts down, stop the providers
	p.Lifecyle.Append(fx.Hook{
		OnStop: func(ctx context.Context) error {
			cancel()
			traceProvider.Shutdown(ctx)
			if logProvider != nil {
				logProvider.Shutdown(ctx)
			}
			return nil
		},
	})

	return &TelemetryImpl{tracer, logger}, nil
}

func (t *TelemetryImpl) GetTracer() trace.Tracer {
	return t.tracer
}

func (t *TelemetryImpl) GetLogger() log.Logger {
	return t.logger
}
