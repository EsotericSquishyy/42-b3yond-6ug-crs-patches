{{- define "libcmin-controller.name" -}}
{{ .Chart.Name }}-controller
{{- end }}

{{- define "libcmin-controller.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "libcmin-controller.name" . }}
{{- end -}}
{{- end }}

{{- define "libcmin-calculator.name" -}}
{{ .Chart.Name }}-calculator
{{- end }}

{{- define "libcmin-calculator.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "libcmin-calculator.name" . }}
{{- end -}}
{{- end }}
