{{/*
Copyright b3yond.org. All rights reserved.

Define tolerations for pods in b3yond charts.
All b3yond components must tolerate the "user" taint.
*/}}

{{/*
Return the tolerations for nodes in b3yond charts.
*/}}
{{- define "b3yond.tolerations" -}}
- key: "b3yond.org/role"
  operator: "Equal"
  value: "user"
  effect: "NoSchedule"
{{- end -}}
