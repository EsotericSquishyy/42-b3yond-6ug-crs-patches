{{- define "patch-reproducer.name" -}}
{{ .Chart.Name }}
{{- end }}

{{- define "patch-reproducer.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride }}
{{- else -}}
{{ .Release.Name }}-{{ include "patch-reproducer.name" . }}
{{- end -}}
{{- end }}