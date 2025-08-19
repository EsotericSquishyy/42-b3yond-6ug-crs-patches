{{/*
Copyright b3yond.org. All rights reserved.

Most b3yond components should wait for the scheduler to be ready before starting.
*/}}

{{- define "b3yond.initContainers.waitForScheduler" -}}
- name: wait-for-scheduler
  image: curlimages/curl:8.12.1
  command: ["sh", "-c", "until [ \"$(curl -s -o /dev/null -w '%{http_code}' http://{{ .Values.global.serviceName.scheduler }}:8080/health)\" -eq 200 ]; do echo waiting for scheduler; sleep 2; done"]
  resources:
    requests:
      cpu: 500m
{{- end -}}
