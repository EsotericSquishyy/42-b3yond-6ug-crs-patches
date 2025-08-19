{{/*
Copyright b3yond.org. All rights reserved.

Most b3yond components should scaled by the unacked messages number in the RabbitMQ.
*/}}

{{/* Default PDB config for pods to make sure at least one pod available */}}
{{- define "b3yond.pdb.pod" -}}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: {{- include "b3yond.pdb.metadata" . | nindent 2}}
spec:
  minAvailable: 1
  selector:
    matchLabels: {{- include "b3yond.labels.matchLabels" . | nindent 6 }}
{{- end -}}
