{{/*
Copyright b3yond.org. All rights reserved.

Most b3yond components should scaled by the unacked messages number in the RabbitMQ.
*/}}

{{/* Default scale config merged with user-defined overrides */}}
{{- define "b3yond.scale.mq" -}}
scaleTargetRef:
  name: {{ include "b3yond.names.fullname" . }}
{{ include "b3yond.scale.mq.setups" . }}
{{- end -}}

{{- define "b3yond.scale.mq.setups" -}}
pollingInterval: 60 # seconds
cooldownPeriod:  {{ .Values.scale.cooldownPeriod  }}
minReplicaCount: {{ .Values.scale.minReplicaCount }}
maxReplicaCount: {{ .Values.scale.maxReplicaCount }}
triggers:
- type: metrics-api
  metadata:
    targetValue: "{{ .Values.scale.targetValue }}"
    url: "http://{{ .Values.global.serviceName.scheduler }}.{{ .Release.Namespace }}.svc.cluster.local:8080/queue?queue={{ .Values.scale.queue }}"
    valueLocation: 'length'
{{- end -}}
