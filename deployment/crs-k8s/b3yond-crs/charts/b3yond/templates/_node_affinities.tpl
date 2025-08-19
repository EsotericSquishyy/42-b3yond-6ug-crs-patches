{{/*
Copyright b3yond.org. All rights reserved.

Define node affinities for pods in b3yond charts.
All b3yond components can only be scheduled on nodes with the label "b3yond.org/role=user".
*/}}

{{/*
Return the nodeAffinity definition.
*/}}
{{- define "b3yond.affinities.nodes" -}}
requiredDuringSchedulingIgnoredDuringExecution:
  nodeSelectorTerms:
  - matchExpressions:
    - key: b3yond.org/role
      operator: In
      values:
      - user
{{- end -}}
