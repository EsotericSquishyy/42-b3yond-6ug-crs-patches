{{- define "mock.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "mock.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "mock.name" . }}
{{- end -}}
{{- end }}