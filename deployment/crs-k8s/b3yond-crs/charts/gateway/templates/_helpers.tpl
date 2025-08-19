{{- define "gateway.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "gateway.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "gateway.name" . }}
{{- end -}}
{{- end }}