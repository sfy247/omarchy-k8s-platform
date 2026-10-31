#!/usr/bin/env python3
"""Generate the lab's Grafana dashboards as JSON (dashboards as code).

Run from this folder:  python3 generate.py
Writes ../dashboards/<Folder>/<uid>.json; the chart turns each file into a
ConfigMap and Grafana's sidecar files it into <Folder>.

"All" in a variable means ".+" (any non-empty value): Loki rejects stream
selectors that could match an empty label, such as cluster=~".*".

Label conventions every dashboard relies on:
  metrics  cluster, namespace, pod, container, app (apps), route/status/method (HTTP)
  logs     cluster, namespace, app, pod, container, level, service_name, job
  events   job="integrations/kubernetes/eventhandler", JSON lines with reason/name
"""
import json
import pathlib

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
OUT = pathlib.Path(__file__).resolve().parent.parent / "dashboards"
EVENTS = 'job="integrations/kubernetes/eventhandler"'


# ---------------------------------------------------------------- building blocks
class Layout:
    """Places panels left-to-right on Grafana's 24-column grid."""

    def __init__(self):
        self.panels, self.x, self.y, self.row_h, self.next_id = [], 0, 0, 0, 1

    def add(self, panel, w, h):
        if self.x + w > 24:
            self.x, self.y, self.row_h = 0, self.y + self.row_h, 0
        panel["id"] = self.next_id
        panel["gridPos"] = {"x": self.x, "y": self.y, "w": w, "h": h}
        self.next_id += 1
        self.x += w
        self.row_h = max(self.row_h, h)
        self.panels.append(panel)

    def row(self, title):
        self.x, self.y, self.row_h = 0, self.y + self.row_h, 0
        self.add({"type": "row", "title": title, "collapsed": False, "panels": []}, 24, 1)
        self.x, self.y, self.row_h = 0, self.y + 1, 0


def prom(expr, legend="", instant=False):
    t = {"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": "A"}
    if instant:
        t.update(instant=True, range=False)
    return t


def loki(expr, legend=""):
    return {"datasource": LOKI, "expr": expr, "legendFormat": legend, "refId": "A", "queryType": "range"}


def stat(title, expr, unit="short", thresholds=None, desc="", links=None):
    steps = [{"color": "green", "value": None}] + [
        {"color": c, "value": v} for v, c in (thresholds or [])]
    p = {"type": "stat", "title": title, "description": desc, "datasource": PROM,
         "targets": [prom(expr, instant=True)],
         "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps},
                                      "color": {"mode": "thresholds"}, "noValue": "0"}, "overrides": []},
         "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                     "graphMode": "none", "textMode": "value"}}
    if links:
        p["fieldConfig"]["defaults"]["links"] = links
    return p


def ts(title, targets, unit="short", desc="", stack=False, links=None, ds=PROM, bars=False):
    custom = {"lineWidth": 1, "fillOpacity": 20 if stack or bars else 8, "showPoints": "never",
              "stacking": {"mode": "normal" if stack else "none"},
              "drawStyle": "bars" if bars else "line"}
    p = {"type": "timeseries", "title": title, "description": desc, "datasource": ds,
         "targets": [dict(t, refId=chr(65 + i)) for i, t in enumerate(targets)],
         "fieldConfig": {"defaults": {"unit": unit, "custom": custom}, "overrides": []},
         "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull", "max"]},
                     "tooltip": {"mode": "multi", "sort": "desc"}}}
    if links:
        p["fieldConfig"]["defaults"]["links"] = links
    return p


def logs(title, expr, desc=""):
    return {"type": "logs", "title": title, "description": desc, "datasource": LOKI,
            "targets": [{"datasource": LOKI, "expr": expr, "refId": "A", "queryType": "range"}],
            "options": {"showTime": True, "wrapLogMessage": True, "prettifyLogMessage": False,
                        "enableLogDetails": True, "sortOrder": "Descending", "dedupStrategy": "none"}}


def table(title, expr, desc="", links=None, ds=PROM):
    p = {"type": "table", "title": title, "description": desc, "datasource": ds,
         "targets": [dict(prom(expr, instant=True), format="table") if ds is PROM else loki(expr)],
         "fieldConfig": {"defaults": {}, "overrides": []},
         "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True}}}],
         "options": {"showHeader": True, "footer": {"show": False}}}
    if links:
        p["fieldConfig"]["defaults"]["links"] = links
    return p


def text(content):
    return {"type": "text", "title": "", "options": {"mode": "markdown", "content": content}}


def prom_var(name, query, label=None, multi=True, include_all=True):
    return {"name": name, "label": label or name.capitalize(), "type": "query", "datasource": PROM,
            "query": {"query": query, "refId": "PromVar"}, "refresh": 2, "sort": 1,
            "multi": multi, "includeAll": include_all, "allValue": ".+" if include_all else None,
            "current": {"selected": True, "text": "All", "value": "$__all"} if include_all else {}}


def loki_var(name, label, stream, title=None):
    return {"name": name, "label": title or name.capitalize(), "type": "query", "datasource": LOKI,
            "query": {"label": label, "stream": stream, "type": 1, "refId": "LokiVar"},
            "refresh": 2, "sort": 1, "multi": True, "includeAll": True, "allValue": ".+",
            "current": {"selected": True, "text": "All", "value": "$__all"}}


def custom_var(name, values, label=None):
    opts = [{"text": v, "value": v, "selected": False} for v in values]
    return {"name": name, "label": label or name.capitalize(), "type": "custom", "query": ",".join(values),
            "multi": True, "includeAll": True, "allValue": ".+", "options": opts,
            "current": {"selected": True, "text": "All", "value": "$__all"}}


def textbox(name, label):
    return {"name": name, "label": label, "type": "textbox", "query": "", "current": {"text": "", "value": ""}}


def link(title, uid, params=""):
    """Data link to another dashboard, keeping time range (and given variables)."""
    return {"title": title, "url": f"/d/{uid}?${{__url_time_range}}{params}"}


def dashboard(uid, title, layout, variables, tags, links=(), desc=""):
    return {
        "uid": uid, "title": title, "description": desc, "tags": ["lab"] + tags,
        "schemaVersion": 41, "version": 1, "editable": False, "graphTooltip": 1,
        "time": {"from": "now-1h", "to": "now"}, "refresh": "30s", "timezone": "browser",
        "templating": {"list": variables},
        "links": [{"type": "dashboards", "tags": ["lab"], "title": "Lab dashboards", "asDropdown": True,
                   "includeVars": True, "keepTime": True}] + list(links),
        "panels": layout.panels,
    }


CLUSTER = prom_var("cluster", "label_values(up, cluster)")
CL = 'cluster=~"$cluster"'


# ---------------------------------------------------------------- Platform overview
def platform_overview():
    l = Layout()
    l.add(text("**Start here.** Red means look closer: each panel links to the dashboard that "
               "explains it. Flow: *Platform Overview → Service Health → Pod Troubleshooting / Logs Explorer*."), 24, 2)
    l.row("Is anything wrong?")
    l.add(stat("Firing alerts", f'count(ALERTS{{alertstate="firing", severity!="none", {CL}}}) or vector(0)',
               thresholds=[(1, "red")], desc="Alerts currently firing (Alertmanager has the details)."), 4, 4)
    l.add(stat("Pods not ready", f'sum(kube_pod_status_ready{{condition="false", {CL}}}) or vector(0)',
               thresholds=[(1, "orange")]), 4, 4)
    l.add(stat("Containers waiting", f'sum(kube_pod_container_status_waiting{{{CL}}}) or vector(0)',
               thresholds=[(1, "orange")], desc="CrashLoopBackOff, ImagePullBackOff, ... see the table below."), 4, 4)
    l.add(stat("Restarts (1h)", f'sum(increase(kube_pod_container_status_restarts_total{{{CL}}}[1h])) or vector(0)',
               thresholds=[(1, "orange"), (5, "red")]), 4, 4)
    l.add(stat("Error logs (15m)", f'sum(count_over_time({{{CL}, level=~"error|fatal"}}[15m])) or vector(0)',
               thresholds=[(1, "orange"), (50, "red")]), 4, 4)
    l.panels[-1]["datasource"] = LOKI
    l.panels[-1]["targets"] = [{"datasource": LOKI, "expr": f'sum(count_over_time({{{CL}, level=~"error|fatal"}}[15m]))',
                               "refId": "A", "queryType": "instant"}]
    l.add(stat("Clusters reporting", f'count(count by (cluster) (up{{job="integrations/alloy", {CL}}}))',
               desc="Clusters whose agents pushed metrics in the last scrape."), 4, 4)
    l.add(table("Problem pods",
                f'sum by (cluster, namespace, pod, container, reason) (kube_pod_container_status_waiting_reason{{{CL}}}) > 0',
                desc="Containers stuck waiting, with the reason. Click a row for the pod's troubleshooting view.",
                links=[link("Troubleshoot this pod", "pod-troubleshooting",
                            "&var-cluster=${__data.fields.cluster}&var-namespace=${__data.fields.namespace}"
                            "&var-pod=${__data.fields.pod}")]), 12, 8)
    l.add(table("Recently terminated containers (OOMKilled, Error, ...)",
                f'sum by (cluster, namespace, pod, container, reason) '
                f'(kube_pod_container_status_last_terminated_reason{{{CL}}}) > 0',
                links=[link("Troubleshoot this pod", "pod-troubleshooting",
                            "&var-cluster=${__data.fields.cluster}&var-namespace=${__data.fields.namespace}"
                            "&var-pod=${__data.fields.pod}")]), 12, 8)
    l.row("Capacity")
    l.add(ts("CPU used (cores)", [prom(f'sum by (cluster) (rate(container_cpu_usage_seconds_total{{container!="", {CL}}}[$__rate_interval]))', "{{cluster}}")]), 8, 8)
    l.add(ts("Memory working set", [prom(f'sum by (cluster) (container_memory_working_set_bytes{{container!="", {CL}}})', "{{cluster}}")], unit="bytes"), 8, 8)
    l.add(ts("Pods by phase", [prom(f'sum by (phase) (kube_pod_status_phase{{{CL}}})', "{{phase}}")], stack=True), 8, 8)
    l.row("Applications")
    l.add(ts("Request rate by app", [prom(f'sum by (cluster, app) (rate(http_requests_total{{{CL}}}[$__rate_interval]))', "{{cluster}} {{app}}")],
             unit="reqps", links=[link("Service health", "service-health", "&var-cluster=${__field.labels.cluster}&var-app=${__field.labels.app}")]), 12, 8)
    l.add(ts("5xx ratio by app", [prom(
        f'sum by (cluster, app) (rate(http_requests_total{{status=~"5..", {CL}}}[$__rate_interval])) / '
        f'sum by (cluster, app) (rate(http_requests_total{{{CL}}}[$__rate_interval]))', "{{cluster}} {{app}}")],
        unit="percentunit", links=[link("Service health", "service-health", "&var-cluster=${__field.labels.cluster}&var-app=${__field.labels.app}")]), 12, 8)
    l.row("Logs and telemetry pipeline")
    l.add(ts("Log lines by level", [loki(f'sum by (level) (count_over_time({{{CL}}} [$__auto]))', "{{level}}")],
             ds=LOKI, bars=True, stack=True, links=[link("Logs explorer", "logs-explorer", "&var-cluster=${cluster}&var-level=${__field.labels.level}")]), 12, 8)
    l.add(ts("Telemetry pipeline (per cluster)", [
        prom(f'sum by (cluster) (rate(prometheus_remote_storage_samples_total{{job="integrations/alloy", {CL}}}[$__rate_interval]))', "{{cluster}} samples/s sent"),
        prom(f'sum by (cluster) (rate(prometheus_remote_storage_samples_failed_total{{job="integrations/alloy", {CL}}}[$__rate_interval]))', "{{cluster}} samples/s failed"),
    ], desc="Metrics each cluster's Alloy pushes to the hub. Failures here mean data is missing everywhere else."), 12, 8)
    return dashboard("platform-overview", "Platform Overview", l, [CLUSTER], ["platform"],
                     desc="Health of every cluster and app, with links to drill down")


# ---------------------------------------------------------------- Service health (RED)
def service_health():
    sel = 'cluster=~"$cluster", namespace=~"$namespace", app=~"$app"'
    l = Layout()
    l.row("Golden signals")
    l.add(stat("Requests/s", f'sum(rate(http_requests_total{{{sel}}}[5m]))', unit="reqps"), 5, 4)
    l.add(stat("Error ratio (5xx)", f'(sum(rate(http_requests_total{{status=~"5..", {sel}}}[5m])) / '
               f'sum(rate(http_requests_total{{{sel}}}[5m]))) or vector(0)',
               unit="percentunit", thresholds=[(0.01, "orange"), (0.05, "red")]), 5, 4)
    l.add(stat("p95 latency", f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[5m])))',
               unit="s", thresholds=[(0.5, "orange"), (1, "red")]), 5, 4)
    l.add(stat("Ready pods", f'sum(kube_pod_status_ready{{condition="true", cluster=~"$cluster", namespace=~"$namespace", pod=~"$app-.*"}})'), 4, 4)
    l.add(stat("Restarts (1h)", f'sum(increase(kube_pod_container_status_restarts_total{{cluster=~"$cluster", namespace=~"$namespace", pod=~"$app-.*"}}[1h])) or vector(0)',
               thresholds=[(1, "orange"), (5, "red")]), 5, 4)
    l.add(ts("Requests by route", [prom(f'sum by (route) (rate(http_requests_total{{{sel}}}[$__rate_interval]))', "{{route}}")], unit="reqps"), 8, 8)
    l.add(ts("Responses by status", [prom(f'sum by (status) (rate(http_requests_total{{{sel}}}[$__rate_interval]))', "{{status}}")], unit="reqps", stack=True), 8, 8)
    l.add(ts("Latency", [
        prom(f'histogram_quantile(0.50, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[$__rate_interval])))', "p50"),
        prom(f'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[$__rate_interval])))', "p95"),
        prom(f'histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{{{sel}}}[$__rate_interval])))', "p99"),
    ], unit="s"), 8, 8)
    l.row("Why? Errors, events and resources")
    l.add(logs("Error and warning logs",
               f'{{cluster=~"$cluster", namespace=~"$namespace", app=~"$app", level=~"error|warn|fatal"}}',
               desc="What the app said when things went wrong."), 12, 10)
    l.add(logs("Kubernetes events",
               f'{{{EVENTS}, cluster=~"$cluster", namespace=~"$namespace"}} |~ "$app"',
               desc="Scheduling, restarts, OOM kills, image pulls, probe failures."), 12, 10)
    l.add(ts("CPU by pod (cores)", [prom(f'sum by (pod) (rate(container_cpu_usage_seconds_total{{container!="", cluster=~"$cluster", namespace=~"$namespace", pod=~"$app-.*"}}[$__rate_interval]))', "{{pod}}")],
             links=[link("Troubleshoot pod", "pod-troubleshooting", "&var-cluster=${cluster}&var-namespace=${namespace}&var-pod=${__field.labels.pod}")]), 12, 8)
    l.add(ts("Memory by pod vs limit", [
        prom(f'sum by (pod) (container_memory_working_set_bytes{{container!="", cluster=~"$cluster", namespace=~"$namespace", pod=~"$app-.*"}})', "{{pod}}"),
        prom(f'max(kube_pod_container_resource_limits{{resource="memory", cluster=~"$cluster", namespace=~"$namespace", pod=~"$app-.*"}})', "limit"),
    ], unit="bytes", links=[link("Troubleshoot pod", "pod-troubleshooting", "&var-cluster=${cluster}&var-namespace=${namespace}&var-pod=${__field.labels.pod}")]), 12, 8)
    variables = [CLUSTER,
                 prom_var("namespace", 'label_values(http_requests_total{cluster=~"$cluster"}, namespace)'),
                 prom_var("app", 'label_values(http_requests_total{cluster=~"$cluster", namespace=~"$namespace"}, app)', multi=False, include_all=False)]
    return dashboard("service-health", "Service Health", l, variables, ["applications"],
                     links=[{"type": "link", "title": "Logs for this app", "url": "/d/logs-explorer?${__url_time_range}&${cluster:queryparam}&${namespace:queryparam}&${app:queryparam}",
                             "icon": "doc"}],
                     desc="RED metrics, logs and events for one service")


# ---------------------------------------------------------------- Logs explorer
def logs_explorer():
    stream = 'cluster=~"$cluster", namespace=~"$namespace", app=~"$app", level=~"$level"'
    query = f'{{{stream}}} |~ "(?i)$search"'
    l = Layout()
    l.add(ts("Log volume by level", [loki(f'sum by (level) (count_over_time({query} [$__auto]))', "{{level}}")],
             ds=LOKI, bars=True, stack=True), 16, 7)
    l.add(table("Noisiest apps (errors, current range)",
                f'topk(10, sum by (namespace, app) (count_over_time({{cluster=~"$cluster", level=~"error|fatal"}} [$__range])))',
                ds=LOKI), 8, 7)
    l.panels[-1]["targets"][0]["queryType"] = "instant"
    l.add(logs("Logs", query, desc="Click a line to see every field (method, path, status, duration_ms, ...)."), 24, 18)
    variables = [CLUSTER,
                 loki_var("namespace", "namespace", '{cluster=~"$cluster"}'),
                 loki_var("app", "app", '{cluster=~"$cluster", namespace=~"$namespace"}'),
                 custom_var("level", ["error", "warn", "info", "debug", "fatal"]),
                 textbox("search", "Search text (regex)")]
    return dashboard("logs-explorer", "Logs Explorer", l, variables, ["logs"],
                     desc="Structured logs from every cluster, by app and level")


# ---------------------------------------------------------------- Pod troubleshooting
def pod_troubleshooting():
    sel = 'cluster=~"$cluster", namespace=~"$namespace", pod=~"$pod"'
    l = Layout()
    l.row("Status")
    l.add(stat("Phase", f'max by (phase) (kube_pod_status_phase{{{sel}}}) == 1', desc="Running, Pending, Failed, ..."), 6, 4)
    l.panels[-1]["options"]["textMode"] = "name"
    l.panels[-1]["targets"][0]["legendFormat"] = "{{phase}}"
    l.add(stat("Ready", f'sum(kube_pod_status_ready{{condition="true", {sel}}})', thresholds=None), 4, 4)
    l.add(stat("Restarts (total)", f'sum(kube_pod_container_status_restarts_total{{{sel}}})',
               thresholds=[(1, "orange"), (5, "red")]), 4, 4)
    l.add(table("Last termination reason", f'sum by (container, reason) (kube_pod_container_status_last_terminated_reason{{{sel}}}) > 0',
                desc="OOMKilled = memory limit too low or a leak; Error = the process exited non-zero (see logs)."), 10, 4)
    l.add(table("Waiting containers", f'sum by (container, reason) (kube_pod_container_status_waiting_reason{{{sel}}}) > 0',
                desc="CrashLoopBackOff, ImagePullBackOff, CreateContainerConfigError (missing Secret/ConfigMap), ..."), 24, 4)
    l.row("Resources")
    l.add(ts("CPU vs request and limit", [
        prom(f'sum by (container) (rate(container_cpu_usage_seconds_total{{container!="", {sel}}}[$__rate_interval]))', "{{container}} used"),
        prom(f'sum by (container) (kube_pod_container_resource_requests{{resource="cpu", {sel}}})', "{{container}} request"),
        prom(f'sum by (container) (kube_pod_container_resource_limits{{resource="cpu", {sel}}})', "{{container}} limit"),
    ]), 8, 8)
    l.add(ts("Memory vs limit", [
        prom(f'sum by (container) (container_memory_working_set_bytes{{container!="", {sel}}})', "{{container}} working set"),
        prom(f'sum by (container) (kube_pod_container_resource_limits{{resource="memory", {sel}}})', "{{container}} limit"),
    ], unit="bytes", desc="Working set reaching the limit ends in OOMKilled."), 8, 8)
    l.add(ts("CPU throttling", [prom(
        f'sum by (container) (rate(container_cpu_cfs_throttled_periods_total{{{sel}}}[$__rate_interval])) / '
        f'sum by (container) (rate(container_cpu_cfs_periods_total{{{sel}}}[$__rate_interval]))', "{{container}}")],
        unit="percentunit", desc="High throttling = CPU limit too low; shows up as latency."), 8, 8)
    l.row("Logs and events")
    l.add(logs("Pod logs", f'{{{sel}}}'), 14, 12)
    l.add(logs("Events for this pod", f'{{{EVENTS}, cluster=~"$cluster", namespace=~"$namespace"}} |= "$pod"'), 10, 12)
    variables = [CLUSTER,
                 prom_var("namespace", 'label_values(kube_pod_info{cluster=~"$cluster"}, namespace)', multi=False, include_all=False),
                 prom_var("pod", 'label_values(kube_pod_info{cluster=~"$cluster", namespace=~"$namespace"}, pod)', multi=False, include_all=False)]
    return dashboard("pod-troubleshooting", "Pod Troubleshooting", l, variables, ["troubleshooting"],
                     desc="Why one pod is unhealthy: status, restarts, resources, logs and events")


if __name__ == "__main__":
    for folder, dash in [("Platform", platform_overview()), ("Applications", service_health()),
                         ("Logs", logs_explorer()), ("Troubleshooting", pod_troubleshooting())]:
        path = OUT / folder / f"{dash['uid']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dash, indent=2) + "\n")
        print(f"wrote {path.relative_to(OUT.parent)} ({len(dash['panels'])} panels)")
