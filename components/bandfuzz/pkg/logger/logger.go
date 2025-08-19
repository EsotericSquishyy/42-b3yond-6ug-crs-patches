package logger

import (
	"b3fuzz/config"
	"b3fuzz/pkg/telemetry"
	"context"
	"fmt"
	"strings"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/log"
	"go.uber.org/fx"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

type LoggerParams struct {
	fx.In
	Lc        fx.Lifecycle
	AppConfig *config.AppConfig
	Telemetry telemetry.Telemetry `optional:"true"`
}

func NewLogger(p LoggerParams) *zap.Logger {
	loggerCtx, cancel := context.WithCancel(context.Background())
	p.Lc.Append(fx.Hook{
		OnStop: func(ctx context.Context) error {
			cancel()
			return nil
		},
	})

	level := zapcore.InfoLevel
	switch strings.ToLower(p.AppConfig.LogLevel) {
	case "debug":
		level = zapcore.DebugLevel
	case "warn", "warning":
		level = zapcore.WarnLevel
	case "error":
		level = zapcore.ErrorLevel
	}

	var cfg zap.Config
	if level > zapcore.InfoLevel {
		cfg = zap.NewProductionConfig()
	} else {
		cfg = zap.NewDevelopmentConfig()
	}
	cfg.Level = zap.NewAtomicLevelAt(level)

	if p.Telemetry == nil {
		lg, err := cfg.Build()
		if err != nil {
			// log failed to build, return a default one
			return zap.NewExample()
		}
		return lg
	}

	lg, err := cfg.Build(
		zap.WrapCore(func(core zapcore.Core) zapcore.Core {
			return &telemetryCore{
				Core:  core,
				telem: p.Telemetry,
				ctx:   loggerCtx,
				attrsBase: []attribute.KeyValue{
					attribute.String("crs.action.name", "fuzzing_log"),
				},
			}
		}),
		zap.AddCaller(),
	)
	if err != nil {
		lg, err := cfg.Build()
		if err != nil {
			// log failed to build, return a default one
			return zap.NewExample()
		}
		return lg
	}
	lg.Info("Logger with telemetry and fields enabled")
	return lg
}

// telemetryCore decorates a zapcore.Core to emit both through the original core
// and into OpenTelemetry, converting each zap.Field into an attribute.
type telemetryCore struct {
	zapcore.Core
	telem     telemetry.Telemetry
	ctx       context.Context
	attrsBase []attribute.KeyValue
}

// 1) With makes sure child cores (e.g. when you do logger.With(...)) keep the wrapper.
func (t *telemetryCore) With(fields []zapcore.Field) zapcore.Core {
	return &telemetryCore{
		Core:      t.Core.With(fields),
		telem:     t.telem,
		ctx:       t.ctx,
		attrsBase: t.attrsBase,
	}
}

// 2) Check tells Zap to add _this_ core (not the inner one) to the CheckedEntry.
func (t *telemetryCore) Check(ent zapcore.Entry, checked *zapcore.CheckedEntry) *zapcore.CheckedEntry {
	if t.Enabled(ent.Level) {
		return checked.AddCore(ent, t)
	}
	return checked
}

func (t *telemetryCore) Write(ent zapcore.Entry, fields []zapcore.Field) error {
	if err := t.Core.Write(ent, fields); err != nil {
		return err
	}

	rec := log.Record{}
	rec.SetTimestamp(ent.Time)
	rec.SetBody(log.StringValue(ent.Message))
	rec.SetSeverityText(ent.Level.String())

	attrs := make([]attribute.KeyValue, 0, len(fields)+len(t.attrsBase))
	attrs = append(attrs, t.attrsBase...)
	for _, f := range fields {
		switch f.Type {
		case zapcore.BoolType:
			attrs = append(attrs, attribute.Bool(f.Key, f.Integer != 0))
		case zapcore.Float64Type:
			if v, ok := f.Interface.(float64); ok {
				attrs = append(attrs, attribute.Float64(f.Key, v))
			}
		case zapcore.Float32Type:
			if v, ok := f.Interface.(float32); ok {
				attrs = append(attrs, attribute.Float64(f.Key, float64(v)))
			}
		case zapcore.Int64Type:
			attrs = append(attrs, attribute.Int64(f.Key, f.Integer))
		case zapcore.Int32Type:
			attrs = append(attrs, attribute.Int64(f.Key, int64(int32(f.Integer))))
		case zapcore.Int16Type:
			attrs = append(attrs, attribute.Int64(f.Key, int64(int16(f.Integer))))
		case zapcore.Int8Type:
			attrs = append(attrs, attribute.Int64(f.Key, int64(int8(f.Integer))))
		case zapcore.Uint64Type:
			attrs = append(attrs, attribute.Int64(f.Key, int64(uint64(f.Integer))))
		case zapcore.Uint32Type:
			attrs = append(attrs, attribute.Int64(f.Key, int64(uint32(f.Integer))))
		case zapcore.Uint16Type:
			attrs = append(attrs, attribute.Int64(f.Key, int64(uint16(f.Integer))))
		case zapcore.Uint8Type:
			attrs = append(attrs, attribute.Int64(f.Key, int64(uint8(f.Integer))))
		case zapcore.StringType:
			attrs = append(attrs, attribute.String(f.Key, f.String))
		case zapcore.ErrorType:
			if errVal, ok := f.Interface.(error); ok {
				attrs = append(attrs, attribute.String(f.Key, errVal.Error()))
			}
		default:
			attrs = append(attrs, attribute.String(f.Key, fmt.Sprint(f.Interface)))
		}
	}

	for _, attr := range attrs {
		rec.AddAttributes(log.KeyValueFromAttribute(attr))
	}

	t.telem.GetLogger().Emit(t.ctx, rec)
	return nil
}
