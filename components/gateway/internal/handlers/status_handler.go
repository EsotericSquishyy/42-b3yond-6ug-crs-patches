package handlers

import (
	"crs-gateway/gen/models"
	"crs-gateway/gen/restapi/operations/status"
	"crs-gateway/internal/db"
	"crs-gateway/internal/services"

	"github.com/go-openapi/runtime/middleware"
	"github.com/go-openapi/swag"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

type GetStatusHandler struct {
	statusService services.StatusService
	logger        *zap.Logger
	version       string
}

type StatusHandlerParams struct {
	fx.In

	StatusService services.StatusService
	Logger        *zap.Logger
	Version       string `name:"version"`
}

func NewGetStatusHandler(p StatusHandlerParams) status.GetStatusHandler {
	return &GetStatusHandler{
		statusService: p.StatusService,
		logger:        p.Logger,
		version:       p.Version,
	}
}

func (h *GetStatusHandler) Handle(params status.GetStatusParams, principal any) middleware.Responder {
	userID := principal.(int)
	logger := h.logger.With(zap.Any("params", params), zap.Int("user_id", userID))
	logger.Info("Getting status")

	statusCount, err := h.statusService.GetTaskStatus()
	if err != nil {
		// this is an undefined behavior
		logger.Error("failed to get task status", zap.Error(err))
		return RespondError(err)
	}

	// waiting count is the sum of all the tasks, except for succeeded, failed, and canceled
	waitingCnt := int64(0)
	for status, cnt := range statusCount {
		if status != db.TaskStatusSucceeded && status != db.TaskStatusFailed && status != db.TaskStatusCanceled {
			waitingCnt += int64(cnt)
		}
	}

	// transform statusCount to status.TypesStatus
	typeStatus := &models.TypesStatus{
		Ready: swag.Bool(true),
		Since: swag.Int64(h.statusService.GetLastClearTime().Unix()),
		State: struct{ models.TypesStatusState }{
			models.TypesStatusState{
				Tasks: &models.TypesStatusTasksState{
					Canceled:   swag.Int64(statusCount[db.TaskStatusCanceled]),
					Errored:    swag.Int64(statusCount[db.TaskStatusErrored]),
					Failed:     swag.Int64(statusCount[db.TaskStatusFailed]),
					Pending:    swag.Int64(statusCount[db.TaskStatusPending]),
					Processing: swag.Int64(statusCount[db.TaskStatusProcessing]),
					Succeeded:  swag.Int64(statusCount[db.TaskStatusSucceeded]),
					Waiting:    swag.Int64(waitingCnt),
				},
			},
		},
		Version: swag.String(h.version),
	}

	return status.NewGetStatusOK().WithPayload(typeStatus)
}

type DeleteStatusHandler struct {
	statusService services.StatusService
	logger        *zap.Logger
}

func NewDeleteStatusHandler(p StatusHandlerParams) status.DeleteStatusHandler {
	return &DeleteStatusHandler{
		statusService: p.StatusService,
		logger:        p.Logger,
	}
}

func (h *DeleteStatusHandler) Handle(params status.DeleteStatusParams, principal any) middleware.Responder {
	err := h.statusService.ClearStatus()
	if err != nil {
		h.logger.Error("failed to clear status", zap.Error(err))
		return RespondError(err)
	}

	return status.NewDeleteStatusOK()
}
