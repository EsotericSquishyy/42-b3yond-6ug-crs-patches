{{- define "patch-gpt.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "patch-gpt.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "patch-gpt.name" . }}
{{- end -}}
{{- end }}