{{- define "submitter.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "submitter.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "submitter.name" . }}
{{- end -}}
{{- end }}