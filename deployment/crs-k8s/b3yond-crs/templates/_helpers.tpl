{{/*
Expand the name of the chart.
*/}}
{{- define "b3yond-crs.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "b3yond-crs.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "b3yond-crs.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "b3yond-crs.labels" -}}
helm.sh/chart: {{ include "b3yond-crs.chart" . }}
{{ include "b3yond-crs.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "b3yond-crs.selectorLabels" -}}
app.kubernetes.io/name: {{ include "b3yond-crs.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "b3yond-crs.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "b3yond-crs.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "crs.rabbitmq.fullname" -}}
{{ printf "%s-rabbitmq" .Release.Name }}
{{- end }}

{{- define "crs.redis-master.fullname" -}}
{{ printf "%s-redis-master" .Release.Name }}
{{- end }}

{{- define "crs.redis-headless.fullname" -}}
{{ printf "%s-redis-headless" .Release.Name }}
{{- end }}

{{- define "crs.otel-collector.endpoint.http" -}}
{{ printf "http://otel-backend:4317" }}
{{- end }}

{{- define "crs.litellm.fullname" -}}
{{ printf "%s-litellm" .Release.Name }}
{{- end }}

{{- define "crs.litellm.masterkey" -}}
{{ printf "sk-42-b3yond-6ug-win" }}
{{- end }}
