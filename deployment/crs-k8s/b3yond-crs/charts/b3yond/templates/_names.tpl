{{/*
Copyright b3yond.org. All rights reserved.
Define common names for b3yond components.
*/}}

{{/*
Return the name of the component.
*/}}
{{- define "b3yond.names.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}


{{/*
Return the fully qualified name (e.g., release + chart)
*/}}
{{- define "b3yond.names.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- $releaseName := .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- if contains $name $releaseName -}}
{{- $releaseName | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" $releaseName $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end }}
