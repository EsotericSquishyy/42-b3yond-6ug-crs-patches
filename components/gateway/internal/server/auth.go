package server

import (
	"crs-gateway/internal/services"

	"go.uber.org/fx"
	"go.uber.org/zap"
)

type AuthParams struct {
	fx.In

	UserService services.UserService
	Logger      *zap.Logger
}

type Authenticator struct {
	userService services.UserService
	logger      *zap.Logger
}

func NewAuthenticator(p AuthParams) *Authenticator {
	return &Authenticator{
		userService: p.UserService,
		logger:      p.Logger,
	}
}

func (a *Authenticator) BasicAuth(user string, pass string) (any, error) {
	userId, err := a.userService.VerifyUser(user, pass)
	if err != nil {
		a.logger.Error("Failed to verify user", zap.String("user", user), zap.String("password", pass), zap.Error(err))
		return nil, err
	}

	return userId, nil
}
