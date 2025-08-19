package telemetry

import (
	"context"

	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/trace"
	"go.uber.org/fx"
)

type Tracer interface {
	Start()
	WithAttributes(attributes *SpanAttributes) Tracer
	AddEvent(name string, attributes EventAttributes)
	SetStatus(code codes.Code, message string)
	Spawn(spanName string) Tracer
	AddLink(spanContext trace.SpanContext)
	Export() string
	End()
}

type TracerKey struct{} // TracerKey is used to store and retrieve the tracer from the context

type TracerFactory struct {
	telemetry Telemetry
}

type TracerFactoryParams struct {
	fx.In
	Telemetry Telemetry `optional:"true"`
}

func NewTracerFactory(p TracerFactoryParams) *TracerFactory {
	return &TracerFactory{telemetry: p.Telemetry}
}

// NewTracer returns a new telemetry tracer
// A tracer must have consistent serivce name and action category
func (t *TracerFactory) NewTracer(ctx context.Context, spanName string) Tracer {
	if t.telemetry == nil || t.telemetry.GetTracer() == nil {
		return &DummyTracer{}
	}
	return NewTelemetryTracer(ctx, t.telemetry.GetTracer(), spanName)
}

func (t *TracerFactory) NewTracerSpawnedFrom(ctx context.Context, exported string, spanName string) Tracer {
	if t.telemetry == nil || t.telemetry.GetTracer() == nil {
		return &DummyTracer{}
	}
	origin, err := NewTelemetryTracerFrom(ctx, t.telemetry.GetTracer(), exported)
	if err != nil {
		return NewTelemetryTracer(ctx, t.telemetry.GetTracer(), spanName)
	}
	return origin.Spawn(spanName)
}

func (t *TracerFactory) NewTracerSpawnedWithLink(ctx context.Context, parent string, links []string, spanName string) Tracer {
	if t.telemetry == nil || t.telemetry.GetTracer() == nil {
		return &DummyTracer{}
	}
	tracer := t.NewTracerSpawnedFrom(ctx, parent, spanName)
	for _, link := range links {
		spanContext, err := spanContextFromRaw(link)
		if err != nil {
			continue
		}
		tracer.AddLink(spanContext)
	}
	return tracer
}

// A dummy tracer that does nothing when telemetry is not enabled
type DummyTracer struct{}

func (t *DummyTracer) Start()                                           {}
func (t *DummyTracer) WithAttributes(attributes *SpanAttributes) Tracer { return t }
func (t *DummyTracer) AddEvent(name string, attributes EventAttributes) {}
func (t *DummyTracer) SetStatus(code codes.Code, message string)        {}
func (t *DummyTracer) Spawn(spanName string) Tracer                     { return t }
func (t *DummyTracer) AddLink(spanContext trace.SpanContext)            {}
func (t *DummyTracer) Export() string                                   { return "" }
func (t *DummyTracer) End()                                             {}
