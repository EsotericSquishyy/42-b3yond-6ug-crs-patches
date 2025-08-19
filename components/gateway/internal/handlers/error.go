package handlers

import (
	"encoding/json"
	"net/http"

	"github.com/go-openapi/runtime"
	"github.com/go-openapi/runtime/middleware"
)

func RespondError(err error) middleware.ResponderFunc {
	return middleware.ResponderFunc(func(w http.ResponseWriter, p runtime.Producer) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
	})
}
