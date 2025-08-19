// This file is safe to edit. Once it exists it will not be overwritten

package restapi

import (
	"crs-gateway/gen/restapi/operations"
	"crs-gateway/gen/restapi/operations/sarif"
	"crs-gateway/gen/restapi/operations/status"
	"crs-gateway/gen/restapi/operations/task"
	"crypto/tls"
	"net/http"

	"github.com/go-openapi/errors"
	"github.com/go-openapi/runtime"
	"github.com/go-openapi/runtime/middleware"
)

//go:generate swagger generate server --target ../../gen --name CrsGateway --spec ../../swagger/crs-swagger-v1.3.0.yaml --principal interface{} --exclude-main

func configureFlags(api *operations.CrsGatewayAPI) {
	// api.CommandLineOptionsGroups = []swag.CommandLineOptionsGroup{ ... }
}

func configureAPI(api *operations.CrsGatewayAPI) http.Handler {
	// configure the api here
	api.ServeError = errors.ServeError

	// Set your custom logger if needed. Default one is log.Printf
	// Expected interface func(string, ...interface{})
	//
	// Example:
	// api.Logger = log.Printf

	api.UseSwaggerUI()
	// To continue using redoc as your UI, uncomment the following line
	// api.UseRedoc()

	api.JSONConsumer = runtime.JSONConsumer()

	api.JSONProducer = runtime.JSONProducer()

	// Applies when the Authorization header is set with the Basic scheme
	if api.BasicAuthAuth == nil {
		api.BasicAuthAuth = func(user string, pass string) (any, error) {
			return nil, errors.NotImplemented("basic auth  (BasicAuth) has not yet been implemented")
		}
	}

	// Set your custom authorizer if needed. Default one is security.Authorized()
	// Expected interface runtime.Authorizer
	//
	// Example:
	// api.APIAuthorizer = security.Authorized()

	if api.StatusDeleteStatusHandler == nil {
		api.StatusDeleteStatusHandler = status.DeleteStatusHandlerFunc(func(params status.DeleteStatusParams, principal any) middleware.Responder {
			return middleware.NotImplemented("operation status.DeleteStatus has not yet been implemented")
		})
	}
	if api.TaskDeleteV1TaskHandler == nil {
		api.TaskDeleteV1TaskHandler = task.DeleteV1TaskHandlerFunc(func(params task.DeleteV1TaskParams, principal any) middleware.Responder {
			return middleware.NotImplemented("operation task.DeleteV1Task has not yet been implemented")
		})
	}
	if api.TaskDeleteV1TaskTaskIDHandler == nil {
		api.TaskDeleteV1TaskTaskIDHandler = task.DeleteV1TaskTaskIDHandlerFunc(func(params task.DeleteV1TaskTaskIDParams, principal any) middleware.Responder {
			return middleware.NotImplemented("operation task.DeleteV1TaskTaskID has not yet been implemented")
		})
	}
	if api.StatusGetStatusHandler == nil {
		api.StatusGetStatusHandler = status.GetStatusHandlerFunc(func(params status.GetStatusParams, principal any) middleware.Responder {
			return middleware.NotImplemented("operation status.GetStatus has not yet been implemented")
		})
	}
	if api.SarifPostV1SarifHandler == nil {
		api.SarifPostV1SarifHandler = sarif.PostV1SarifHandlerFunc(func(params sarif.PostV1SarifParams, principal any) middleware.Responder {
			return middleware.NotImplemented("operation sarif.PostV1Sarif has not yet been implemented")
		})
	}
	if api.TaskPostV1TaskHandler == nil {
		api.TaskPostV1TaskHandler = task.PostV1TaskHandlerFunc(func(params task.PostV1TaskParams, principal any) middleware.Responder {
			return middleware.NotImplemented("operation task.PostV1Task has not yet been implemented")
		})
	}

	api.PreServerShutdown = func() {}

	api.ServerShutdown = func() {}

	return setupGlobalMiddleware(api.Serve(setupMiddlewares))
}

// The TLS configuration before HTTPS server starts.
func configureTLS(tlsConfig *tls.Config) {
	// Make all necessary changes to the TLS configuration here.
}

// As soon as server is initialized but not run yet, this function will be called.
// If you need to modify a config, store server instance to stop it individually later, this is the place.
// This function can be called multiple times, depending on the number of serving schemes.
// scheme value will be set accordingly: "http", "https" or "unix".
func configureServer(s *http.Server, scheme, addr string) {
}

// The middleware configuration is for the handler executors. These do not apply to the swagger.json document.
// The middleware executes after routing but before authentication, binding and validation.
func setupMiddlewares(handler http.Handler) http.Handler {
	return handler
}

// The middleware configuration happens before anything, this middleware also applies to serving the swagger.json document.
// So this is a good place to plug in a panic handling middleware, logging and metrics.
func setupGlobalMiddleware(handler http.Handler) http.Handler {
	return handler
}
