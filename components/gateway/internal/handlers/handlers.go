package handlers

import (
	"go.uber.org/fx"
)

// Module provides all handlers
var Module = fx.Module("handlers",
	fx.Provide(
		// api /status
		NewGetStatusHandler,
		NewDeleteStatusHandler,
		// api /task
		NewPostV1TskHandler,
		NewDeleteV1TaskHandler,
		NewDeleteV1TaskTaskIDHandler,
		// api /sarif
		NewPostV1SarifHandler,
	),
)
