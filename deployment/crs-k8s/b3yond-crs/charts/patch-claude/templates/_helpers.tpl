{{- define "patch-claude.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "patch-claude.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "patch-claude.name" . }}
{{- end -}}
{{- end }}