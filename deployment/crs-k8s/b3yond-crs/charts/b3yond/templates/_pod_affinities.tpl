{{/*
Copyright b3yond.org. All rights reserved.

There are two types of affinities in b3yond charts: "utilities" and "isolated".
Utilities are used for general-purpose workloads that can share resources,
while isolated are used for workloads that require dedicated resources.
*/}}

{{/*
Return a "isolated" podAntiAffinity definition.
*/}}
{{- define "b3yond.affinities.pods.isolated" -}}
requiredDuringSchedulingIgnoredDuringExecution:
  - labelSelector:
      matchExpressions:
        - key: b3yond.org/anti-affinity-group
          operator: In
          values:
            - isolated
            - utilities
    topologyKey: kubernetes.io/hostname
{{- end -}}



{{/*
Return a "utilities" podAntiAffinity definition.
*/}}
{{- define "b3yond.affinities.pods.utilities" -}}
requiredDuringSchedulingIgnoredDuringExecution:
  - labelSelector:
      matchExpressions:
        - key: b3yond.org/anti-affinity-group
          operator: In
          values:
            - isolated
    topologyKey: kubernetes.io/hostname
preferredDuringSchedulingIgnoredDuringExecution:
  - weight: 100
    podAffinityTerm:
      labelSelector:
        matchExpressions:
          - key: b3yond.org/anti-affinity-group
            operator: In
            values:
              - utilities
      topologyKey: kubernetes.io/hostname
{{- end -}}
