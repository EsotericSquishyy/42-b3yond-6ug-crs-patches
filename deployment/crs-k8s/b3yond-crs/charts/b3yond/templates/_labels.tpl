{{/*
Copyright b3yond.org. All rights reserved.
Define common labels for b3yond components.
*/}}

{{/*
Standard labels for Kubernetes resources.
*/}}
{{- define "b3yond.labels.standard" -}}
app.kubernetes.io/name: {{ include "b3yond.names.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.Version }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{ include "b3yond.labels.antiAffinityGroup" . }}
{{- end -}}

{{/*
Return the anti-affinity label for b3yond components.
If the antiAffinityGroup value is not set, it defaults to "isolated".
*/}}
{{- define "b3yond.labels.antiAffinityGroup" -}}
b3yond.org/anti-affinity-group: {{ .Values.antiAffinityGroup | default "isolated" }}
{{- end -}}


{{/*
Standard match labels for Kubernetes resources.
*/}}
{{- define "b3yond.labels.matchLabels" -}}
app.kubernetes.io/name: {{ include "b3yond.names.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Standard metadata block for Kubernetes resources.
*/}}
{{- define "b3yond.metadata" -}}
name: {{ include "b3yond.names.fullname" . }}
labels:
  app.kubernetes.io/name: {{ include "b3yond.names.name" . }}
  app.kubernetes.io/instance: {{ .Release.Name }}
  app.kubernetes.io/version: {{ .Chart.Version }}
  helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
  app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Standard metadata block for depolyment templates.
*/}}
{{- define "b3yond.template.metadata" -}}
labels:
  app.kubernetes.io/name: {{ include "b3yond.names.name" . }}
  app.kubernetes.io/instance: {{ .Release.Name }}
  app.kubernetes.io/version: {{ .Chart.Version }}
  helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
  app.kubernetes.io/managed-by: {{ .Release.Service }}
  {{- include "b3yond.labels.antiAffinityGroup" . | nindent 2 }}
{{- end -}}

{{/*
Standard metadata block for scaled_objects templates.
*/}}
{{- define "b3yond.scale.metadata" -}}
name: {{ include "b3yond.names.fullname" . }}-scaled-object
labels:
  app.kubernetes.io/name: {{ include "b3yond.names.name" . }}-scaled-object
  app.kubernetes.io/instance: {{ .Release.Name }}
  app.kubernetes.io/version: {{ .Chart.Version }}
  helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
  app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Standard metadata block for pdb templates.
*/}}
{{- define "b3yond.pdb.metadata" -}}
name: {{ include "b3yond.names.fullname" . }}-pdb
labels:
  app.kubernetes.io/name: {{ include "b3yond.names.name" . }}-pdb
  app.kubernetes.io/instance: {{ .Release.Name }}
  app.kubernetes.io/version: {{ .Chart.Version }}
  helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
  app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Standard metadata block for service templates.
*/}}
{{- define "b3yond.service.metadata" -}}
name: {{ include "b3yond.names.fullname" . }}-service
labels:
  app.kubernetes.io/name: {{ include "b3yond.names.name" . }}-service
  app.kubernetes.io/instance: {{ .Release.Name }}
  app.kubernetes.io/version: {{ .Chart.Version }}
  helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
  app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

