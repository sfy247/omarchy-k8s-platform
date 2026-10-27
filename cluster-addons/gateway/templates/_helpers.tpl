{{- define "gateway.hostname" -}}
{{- required "hostname is required (set from the cluster's lab/gateway-hostname annotation)" .Values.hostname -}}
{{- end -}}
