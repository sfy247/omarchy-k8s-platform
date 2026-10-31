{{- define "gateway.hostnames" -}}
{{- $h := required "hostnames is required (set from the cluster's lab/gateway-hostnames annotation)" .Values.hostnames -}}
{{- toJson (splitList " " (trim $h)) -}}
{{- end -}}

{{/* Listener hostname line, only when the gateway serves exactly one name */}}
{{- define "gateway.listenerHostname" -}}
{{- $hosts := include "gateway.hostnames" . | fromJsonArray -}}
{{- if eq (len $hosts) 1 }}
      hostname: {{ first $hosts | quote }}
{{- end -}}
{{- end -}}
