package telemetry

import (
	"fmt"
	"maps"
	"time"

	"go.opentelemetry.io/otel/attribute"
)

type SpanAttributes struct {
	ActionCategory string

	CodeFile           optional[string]    // crs.code.file
	CodeLines          optional[string]    // crs.code.lines
	TargetHarness      optional[string]    // crs.target.harness
	EffortWeight       optional[string]    // crs.effort.weight
	corpusUpdateMethod optional[string]    // fuzz.corpus.update.method
	corpusUpdateTime   optional[time.Time] // fuzz.corpus.update.time
	corpusSize         optional[int]       // fuzz.corpus.size
	corpusAdditions    optional[[]string]  // fuzz.corpus.additions
	corpusFullSnapShot optional[bool]      // fuzz.corpus.full_snapshot

	extraAttributes map[string]any
}

func NewSpanAttributes(actionCategory ActionCategory) *SpanAttributes {
	return &SpanAttributes{
		ActionCategory:  actionCategory.String(),
		extraAttributes: make(map[string]any),
	}
}

// returns an empty SpanAttributes instance with no service name or action category.
// this is useful for creating a SpanAttributes instance that can be populated later.
func EmptySpanAttributes() *SpanAttributes {
	return &SpanAttributes{
		extraAttributes: make(map[string]any),
	}
}

// Merge updates the current SpanAttributes with values from another SpanAttributes.
// Values are only updated if they are set in the other SpanAttributes and not set in the current one.
// The ServiceName and ActionCategory are always updated regardless of their state.
func (o *SpanAttributes) Merge(other *SpanAttributes) {
	if other == nil {
		return
	}

	if other.ActionCategory != "" {
		o.ActionCategory = other.ActionCategory
	}

	// Merge optional fields - only update if not already set
	mergeOptional(&o.CodeFile, &other.CodeFile)
	mergeOptional(&o.CodeLines, &other.CodeLines)
	mergeOptional(&o.TargetHarness, &other.TargetHarness)
	mergeOptional(&o.EffortWeight, &other.EffortWeight)
	mergeOptional(&o.corpusUpdateMethod, &other.corpusUpdateMethod)
	mergeOptional(&o.corpusUpdateTime, &other.corpusUpdateTime)
	mergeOptional(&o.corpusSize, &other.corpusSize)
	mergeOptional(&o.corpusAdditions, &other.corpusAdditions)
	mergeOptional(&o.corpusFullSnapShot, &other.corpusFullSnapShot)

	// Merge extra attributes
	if o.extraAttributes == nil {
		o.extraAttributes = make(map[string]any)
	}
	for k, v := range other.extraAttributes {
		if _, exists := o.extraAttributes[k]; !exists {
			o.extraAttributes[k] = v
		}
	}
}

func (o *SpanAttributes) WithCodeFile(val string) *SpanAttributes {
	o.CodeFile.Set(val)
	return o
}

func (o *SpanAttributes) WithCodeLines(val string) *SpanAttributes {
	o.CodeLines.Set(val)
	return o
}

func (o *SpanAttributes) WithTargetHarness(val string) *SpanAttributes {
	o.TargetHarness.Set(val)
	return o
}

func (o *SpanAttributes) WithEffortWeight(val string) *SpanAttributes {
	o.EffortWeight.Set(val)
	return o
}

func (o *SpanAttributes) WithCorpusUpdateMethod(val string) *SpanAttributes {
	o.corpusUpdateMethod.Set(val)
	return o
}

func (o *SpanAttributes) WithCorpusUpdateTime(val time.Time) *SpanAttributes {
	o.corpusUpdateTime.Set(val)
	return o
}

func (o *SpanAttributes) WithCorpusSize(val int) *SpanAttributes {
	o.corpusSize.Set(val)
	return o
}

func (o *SpanAttributes) WithCorpusAdditions(val []string) *SpanAttributes {
	o.corpusAdditions.Set(val)
	return o
}

func (o *SpanAttributes) WithCorpusFullSnapShot(val bool) *SpanAttributes {
	o.corpusFullSnapShot.Set(val)
	return o
}

func (o *SpanAttributes) WithExtraAttribute(key string, val any) *SpanAttributes {
	if o.extraAttributes == nil {
		o.extraAttributes = make(map[string]any)
	}
	o.extraAttributes[key] = val
	return o
}

func (o *SpanAttributes) WithExtraAttributes(attrs map[string]any) *SpanAttributes {
	if o.extraAttributes == nil {
		o.extraAttributes = make(map[string]any)
	}
	maps.Copy(o.extraAttributes, attrs)
	return o
}

func (o SpanAttributes) Attributes() []attribute.KeyValue {
	var attrs []attribute.KeyValue
	attrs = append(attrs, attribute.String("crs.action.category", o.ActionCategory))
	if o.CodeFile.set {
		attrs = append(attrs, attribute.String("crs.code.file", o.CodeFile.val))
	}
	if o.CodeLines.set {
		attrs = append(attrs, attribute.String("crs.code.lines", o.CodeLines.val))
	}
	if o.TargetHarness.set {
		attrs = append(attrs, attribute.String("crs.target.harness", o.TargetHarness.val))
	}
	if o.EffortWeight.set {
		attrs = append(attrs, attribute.String("crs.effort.weight", o.EffortWeight.val))
	}
	if o.corpusUpdateMethod.set {
		attrs = append(attrs, attribute.String("fuzz.corpus.update.method", o.corpusUpdateMethod.val))
	}
	if o.corpusUpdateTime.set {
		attrs = append(attrs, attribute.String("fuzz.corpus.update.time", o.corpusUpdateTime.val.Format(time.RFC3339Nano)))
	}
	if o.corpusSize.set {
		attrs = append(attrs, attribute.Int("fuzz.corpus.size", o.corpusSize.val))
	}
	if o.corpusAdditions.set {
		attrs = append(attrs, attribute.StringSlice("fuzz.corpus.additions", o.corpusAdditions.val))
	}

	for k, v := range o.extraAttributes {
		switch val := v.(type) {
		case string:
			attrs = append(attrs, attribute.String(k, val))
		case int:
			attrs = append(attrs, attribute.Int(k, val))
		case int64:
			attrs = append(attrs, attribute.Int64(k, val))
		case float64:
			attrs = append(attrs, attribute.Float64(k, val))
		case bool:
			attrs = append(attrs, attribute.Bool(k, val))
		default:
			attrs = append(attrs, attribute.String(k, fmt.Sprintf("%v", val)))
		}
	}

	return attrs
}

type EventAttributes []attribute.KeyValue

func NewEventAttributes(attributes map[string]string) EventAttributes {
	attrs := make(EventAttributes, 0, len(attributes))
	for k, v := range attributes {
		attrs = append(attrs, attribute.String(k, v))
	}
	return attrs
}

type optional[T any] struct {
	val T
	set bool
}

func (o *optional[T]) Set(val T) { o.val = val; o.set = true }

func mergeOptional[T any](target, source *optional[T]) {
	if !target.set && source.set {
		target.val = source.val
		target.set = true
	}
}
