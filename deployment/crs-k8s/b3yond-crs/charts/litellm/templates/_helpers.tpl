{{- define "litellm.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "litellm.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "litellm.name" . }}
{{- end -}}
{{- end }}