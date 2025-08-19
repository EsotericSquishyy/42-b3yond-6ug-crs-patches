package middle

import (
	"bytes"
	"context"
	"crs-gateway/internal/db"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.uber.org/fx"
	"go.uber.org/zap"
	"gorm.io/gorm"
)

type DBLogMiddlewareParams struct {
	fx.In

	DB     *gorm.DB
	Logger *zap.Logger
}

type DBLogMiddleware struct {
	db     *gorm.DB
	logger *zap.Logger
}

type MessageIdKey struct{}

func NewDBLogMiddleware(p DBLogMiddlewareParams) *DBLogMiddleware {
	return &DBLogMiddleware{
		db:     p.DB,
		logger: p.Logger,
	}
}

func (m *DBLogMiddleware) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Skip logging for status endpoint
		if strings.Contains(r.URL.Path, "status") {
			next.ServeHTTP(w, r)
			return
		}

		var bodyBytes []byte
		if r.Body != nil {
			data, err := io.ReadAll(r.Body)
			if err != nil {
				m.logger.Error("failed to read request body", zap.Error(err))
			} else {
				bodyBytes = data
			}
			r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
		}

		messageId := uuid.New().String()
		msg := &db.Message{
			ID:          messageId,
			MessageTime: time.Now().UnixNano(),
			HTTPMethod:  r.Method,
			RawEndpoint: r.URL.Path,
			HTTPBody:    string(bodyBytes),
		}
		if err := m.db.Create(msg).Error; err != nil {
			m.logger.Error("failed to log API call", zap.Error(err))
		}
		ctx := r.Context()
		ctx = context.WithValue(ctx, MessageIdKey{}, messageId)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}
