{{- define "slice-r14.name" -}}
{{ .Chart.Name }}-r14
{{- end }}

{{- define "slice-r14.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "slice-r14.name" . }}
{{- end -}}
{{- end }}

{{- define "slice-r18.name" -}}
{{ .Chart.Name }}-r18
{{- end }}

{{- define "slice-r18.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "slice-r18.name" . }}
{{- end -}}
{{- end }}
