package server

import (
	"crs-gateway/gen/restapi"
	"crs-gateway/gen/restapi/operations"
	"crs-gateway/gen/restapi/operations/status"
	"crs-gateway/gen/restapi/operations/task"
	"crs-gateway/internal/handlers"
	"crs-gateway/internal/middle"

	"github.com/go-openapi/loads"
	"go.uber.org/fx"
	"go.uber.org/zap"
)

// ServerParams holds the dependencies needed for the API server
type ServerParams struct {
	fx.In

	Logger *zap.Logger
	Port   int `name:"port"`

	GetStatusHandler          status.GetStatusHandler
	DeleteStatusHandler       status.DeleteStatusHandler
	PostV1TskHandler          task.PostV1TaskHandler
	DeleteV1TaskHandler       task.DeleteV1TaskHandler
	DeleteV1TaskTaskIDHandler task.DeleteV1TaskTaskIDHandler
	PostV1SarifHandler        *handlers.PostV1SarifHandler

	DBLogMiddleware *middle.DBLogMiddleware

	Authenticator *Authenticator
}

// ServerResult holds the API server components
type ServerResult struct {
	fx.Out

	API    *operations.CrsGatewayAPI
	Server *restapi.Server
}

// NewServer provides the API and Server instances
func NewServer(p ServerParams) (ServerResult, error) {
	swaggerSpec, err := loads.Analyzed(restapi.SwaggerJSON, "")
	if err != nil {
		return ServerResult{}, err
	}

	api := operations.NewCrsGatewayAPI(swaggerSpec)
	api.Logger = p.Logger.Sugar().Infof

	// setup handlers
	setupHandlers(api, p)

	// setup authenticator
	api.BasicAuthAuth = p.Authenticator.BasicAuth

	server := restapi.NewServer(api)
	server.ConfigureFlags()
	server.ConfigureAPI()
	server.SetHandler(p.DBLogMiddleware.Middleware(server.GetHandler()))

	server.Port = p.Port
	server.Host = "0.0.0.0"

	p.Logger.Info("Starting server", zap.Int("port", p.Port), zap.String("host", "0.0.0.0"))

	return ServerResult{
		API:    api,
		Server: server,
	}, nil
}

func setupHandlers(api *operations.CrsGatewayAPI, p ServerParams) {
	// api /status
	api.StatusGetStatusHandler = p.GetStatusHandler
	api.StatusDeleteStatusHandler = p.DeleteStatusHandler

	// api /task
	api.TaskPostV1TaskHandler = p.PostV1TskHandler
	api.TaskDeleteV1TaskHandler = p.DeleteV1TaskHandler
	api.TaskDeleteV1TaskTaskIDHandler = p.DeleteV1TaskTaskIDHandler

	// api /sarif
	api.SarifPostV1SarifHandler = p.PostV1SarifHandler
}
