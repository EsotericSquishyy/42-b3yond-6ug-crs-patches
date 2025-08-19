{{- define "otel-backend.name" -}}
otel-backend
{{- end -}}

{{- define "otel-backend.fullname" -}}
{{ include "otel-backend.name" . }}
{{- end -}}