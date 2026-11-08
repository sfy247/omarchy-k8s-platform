{{- define "web-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "web-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "web-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "web-service.labels" -}}
{{ include "web-service.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/* The app's Postgres role and database: <namespace>_<name>, Postgres-safe */}}
{{- define "web-service.dbRole" -}}
{{- printf "%s_%s" .Release.Namespace (include "web-service.name" .) | replace "-" "_" | lower | trunc 63 -}}
{{- end }}
