package telemetry

import (
	"context"
	"encoding/json"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

type TelemetryTracer struct {
	tracer     trace.Tracer
	span       trace.Span
	tracerCtx  context.Context // use spanCtx to create child spans
	link       []trace.Link
	spanName   string
	attributes *SpanAttributes

	started bool // to track if the span has been started
}

func NewTelemetryTracer(ctx context.Context, tracer trace.Tracer, spanName string) *TelemetryTracer {
	return &TelemetryTracer{
		tracer:     tracer,
		tracerCtx:  ctx,
		spanName:   spanName,
		attributes: EmptySpanAttributes(),
	}
}

func NewTelemetryTracerFrom(ctx context.Context, tracer trace.Tracer, exported string) (*TelemetryTracer, error) {
	carrier := make(map[string]string)
	if err := json.Unmarshal([]byte(exported), &carrier); err != nil {
		return nil, err
	}

	extractedCtx := otel.GetTextMapPropagator().Extract(ctx, propagation.MapCarrier(carrier))

	origin := &TelemetryTracer{
		tracer:     tracer,
		tracerCtx:  extractedCtx,
		attributes: EmptySpanAttributes(),
		started:    true, // mark as started since we are importing an existing span
	}

	return origin, nil
}

func (t *TelemetryTracer) Start() {
	attributes := t.attributes.Attributes()
	attributes = append(attributes, attribute.String("crs.action.name", t.spanName))
	t.tracerCtx, t.span = t.tracer.Start(t.tracerCtx,
		t.spanName,
		trace.WithAttributes(attributes...),
		trace.WithLinks(t.link...))
	t.started = true // mark as started
}

func (t *TelemetryTracer) SetStatus(code codes.Code, message string) {
	t.span.SetStatus(code, message)
}

func (t *TelemetryTracer) WithAttributes(attributes *SpanAttributes) Tracer {
	t.attributes.Merge(attributes)
	if t.started {
		t.span.SetAttributes(t.attributes.Attributes()...)
	}
	return t
}

func (t *TelemetryTracer) AddEvent(name string, e EventAttributes) {
	t.span.AddEvent(name, trace.WithAttributes(e...))
}

func (t *TelemetryTracer) Spawn(spanName string) Tracer {
	newTracer := NewTelemetryTracer(t.tracerCtx, t.tracer, spanName)
	return newTracer.WithAttributes(t.attributes)
}

func (t *TelemetryTracer) AddLink(spanContext trace.SpanContext) {
	link := trace.Link{SpanContext: spanContext}
	t.link = append(t.link, link)
	if t.started {
		t.span.AddLink(link)
	}
}

// export the tracing context to a JSON string
func (t *TelemetryTracer) Export() string {
	carrier := make(map[string]string)
	otel.GetTextMapPropagator().Inject(t.tracerCtx, propagation.MapCarrier(carrier))
	payload, _ := json.Marshal(carrier)
	return string(payload)
}

func (t *TelemetryTracer) End() {
	if !t.started {
		return // do not end if the span was never started
	}
	t.span.End()
}

func spanContextFromRaw(raw string) (trace.SpanContext, error) {
	carrier := make(map[string]string)
	if err := json.Unmarshal([]byte(raw), &carrier); err != nil {
		return trace.SpanContext{}, err
	}
	extractedCtx := otel.GetTextMapPropagator().Extract(context.Background(), propagation.MapCarrier(carrier))
	return trace.SpanContextFromContext(extractedCtx), nil
}
