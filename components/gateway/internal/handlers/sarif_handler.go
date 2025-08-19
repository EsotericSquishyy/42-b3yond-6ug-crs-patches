package handlers

import (
	"crs-gateway/gen/restapi/operations/sarif"
	"crs-gateway/internal/middle"
	"crs-gateway/internal/services"

	"github.com/go-openapi/runtime/middleware"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

type SarifHandlerParams struct {
	fx.In

	SarifService services.SarifService
	Logger       *zap.Logger
}

type PostV1SarifHandler struct {
	sarifService services.SarifService
	logger       *zap.Logger
}

func NewPostV1SarifHandler(p SarifHandlerParams) *PostV1SarifHandler {
	return &PostV1SarifHandler{
		sarifService: p.SarifService,
		logger:       p.Logger,
	}
}

func (h *PostV1SarifHandler) Handle(params sarif.PostV1SarifParams, principal any) middleware.Responder {
	userID := principal.(int)

	logger := h.logger.With(zap.Any("params", params), zap.Int("user_id", userID))
	logger.Info("Processing SARIF file")

	messageID := params.HTTPRequest.Context().Value(middle.MessageIdKey{}).(string)
	if err := h.sarifService.CreateSarif(params.Payload, messageID); err != nil {
		logger.Error("Failed to create SARIF", zap.Error(err))
		return RespondError(err)
	}

	return sarif.NewPostV1SarifOK()
}
