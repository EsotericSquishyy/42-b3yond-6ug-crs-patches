{{- define "patch-submitter.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "patch-submitter.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "patch-submitter.name" . }}
{{- end -}}
{{- end }}