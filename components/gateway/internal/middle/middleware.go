package middle

import "go.uber.org/fx"

// Module provides all handlers
var Module = fx.Module("handlers",
	fx.Provide(
		NewDBLogMiddleware,
	),
)
