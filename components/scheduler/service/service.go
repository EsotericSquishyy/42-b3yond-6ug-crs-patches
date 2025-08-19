package service

import (
	"go.uber.org/fx"
)

var Module = fx.Options(
	fx.Provide(NewTaskService),
	fx.Provide(fx.Annotated{
		Group:  "routines",
		Target: NewTaskRoutine,
	}),
	fx.Provide(fx.Annotated{
		Group:  "routines",
		Target: NewSarifRoutine,
	}),
	fx.Provide(fx.Annotated{
		Group:  "routines",
		Target: NewBugRoutine,
	}),
	fx.Provide(fx.Annotated{
		Group:  "routines",
		Target: NewCancelRoutine,
	}),
)
