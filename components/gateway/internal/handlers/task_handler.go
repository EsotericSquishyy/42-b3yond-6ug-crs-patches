package handlers

import (
	"crs-gateway/gen/restapi/operations/task"
	"crs-gateway/internal/middle"
	"crs-gateway/internal/services"

	"github.com/go-openapi/runtime/middleware"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

type TaskHandlerParams struct {
	fx.In

	TaskService services.TaskService
	Logger      *zap.Logger
}

type PostV1TskHandler struct {
	taskService services.TaskService
	logger      *zap.Logger
}

func NewPostV1TskHandler(p TaskHandlerParams) task.PostV1TaskHandler {
	return &PostV1TskHandler{
		taskService: p.TaskService,
		logger:      p.Logger,
	}
}

func (h *PostV1TskHandler) Handle(params task.PostV1TaskParams, principal any) middleware.Responder {
	userID := principal.(int)

	logger := h.logger.With(zap.Any("params", params), zap.Int("user_id", userID))
	logger.Info("Creating task")

	messageID := params.HTTPRequest.Context().Value(middle.MessageIdKey{}).(string)
	err := h.taskService.CreateTask(params.Payload, messageID, userID)
	if err != nil {
		logger.Error("Failed to create task", zap.Error(err))
		return RespondError(err)
	}

	logger.Info("Task created successfully")
	return task.NewPostV1TaskAccepted()
}

type DeleteV1TaskHandler struct {
	taskService services.TaskService
	logger      *zap.Logger
}

func NewDeleteV1TaskHandler(p TaskHandlerParams) task.DeleteV1TaskHandler {
	return &DeleteV1TaskHandler{
		taskService: p.TaskService,
		logger:      p.Logger,
	}
}

func (h *DeleteV1TaskHandler) Handle(params task.DeleteV1TaskParams, principal any) middleware.Responder {
	userID := principal.(int)

	logger := h.logger.With(zap.Any("params", params), zap.Int("user_id", userID))
	logger.Info("Cancelling all tasks")
	err := h.taskService.CancelAllTasks()
	if err != nil {
		logger.Error("Failed to cancel all tasks", zap.Error(err))
		return RespondError(err)
	}

	logger.Info("All tasks canceled successfully")
	return task.NewDeleteV1TaskOK()
}

type DeleteV1TaskTaskIDHandler struct {
	taskService services.TaskService
	logger      *zap.Logger
}

func NewDeleteV1TaskTaskIDHandler(p TaskHandlerParams) task.DeleteV1TaskTaskIDHandler {
	return &DeleteV1TaskTaskIDHandler{
		taskService: p.TaskService,
		logger:      p.Logger,
	}
}

func (h *DeleteV1TaskTaskIDHandler) Handle(params task.DeleteV1TaskTaskIDParams, principal any) middleware.Responder {
	userID := principal.(int)

	logger := h.logger.With(zap.Any("params", params), zap.Int("user_id", userID))
	logger.Info("Cancelling task")
	err := h.taskService.CancelTask(params.TaskID.String())
	if err != nil {
		logger.Error("Failed to cancel task", zap.Error(err))
		return RespondError(err)
	}

	logger.Info("Task cancelled successfully")
	return task.NewDeleteV1TaskTaskIDOK()
}
