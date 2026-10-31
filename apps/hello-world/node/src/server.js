// Hello World service with RED metrics, JSON logs and failure modes.
// Endpoints: /  /healthz  /metrics  /fail (500)  /slow?ms=N (adds latency)
// Node standard library only.
const http = require("node:http");

const port = Number(process.env.PORT || 8080);
const service = process.env.SERVICE_NAME || "node";
const routes = new Set(["/", "/healthz", "/fail", "/slow"]);
const buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10];

const requests = new Map();  // "method|route|status" -> count
const durations = new Map(); // "method|route" -> { b: [...], sum, count }

const log = (level, msg, fields = {}) =>
  console.log(JSON.stringify({ ts: new Date().toISOString(), level, msg, service, ...fields }));

function observe(method, route, status, seconds) {
  const key = `${method}|${route}|${status}`;
  requests.set(key, (requests.get(key) || 0) + 1);
  const hk = `${method}|${route}`;
  const h = durations.get(hk) || { b: buckets.map(() => 0), sum: 0, count: 0 };
  buckets.forEach((bound, i) => { if (seconds <= bound) h.b[i] += 1; });
  h.sum += seconds;
  h.count += 1;
  durations.set(hk, h);
}

function exposition() {
  const out = [
    "# HELP http_requests_total Requests handled, by route and status.",
    "# TYPE http_requests_total counter",
  ];
  for (const [key, v] of [...requests].sort()) {
    const [m, r, s] = key.split("|");
    out.push(`http_requests_total{method="${m}",route="${r}",status="${s}"} ${v}`);
  }
  out.push("# HELP http_request_duration_seconds Request latency.",
           "# TYPE http_request_duration_seconds histogram");
  for (const [key, h] of [...durations].sort()) {
    const [m, r] = key.split("|");
    buckets.forEach((bound, i) =>
      out.push(`http_request_duration_seconds_bucket{method="${m}",route="${r}",le="${bound}"} ${h.b[i]}`));
    out.push(`http_request_duration_seconds_bucket{method="${m}",route="${r}",le="+Inf"} ${h.count}`);
    out.push(`http_request_duration_seconds_sum{method="${m}",route="${r}"} ${h.sum}`);
    out.push(`http_request_duration_seconds_count{method="${m}",route="${r}"} ${h.count}`);
  }
  return out.join("\n") + "\n";
}

const send = (res, status, body, type = "application/json") => {
  res.writeHead(status, { "Content-Type": type });
  res.end(typeof body === "string" ? body : JSON.stringify(body));
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/metrics") return send(res, 200, exposition(), "text/plain; version=0.0.4");

  const start = process.hrtime.bigint();
  const route = routes.has(url.pathname) ? url.pathname : "other";
  let status = 200;
  let body;
  if (url.pathname === "/") body = { message: "Hello, World!", language: "node" };
  else if (url.pathname === "/healthz") body = { status: "ok" };
  else if (url.pathname === "/fail") {
    status = 500;
    body = { error: "simulated failure" };
    log("error", "simulated failure", { path: url.pathname, reason: "requested via /fail" });
  } else if (url.pathname === "/slow") {
    const ms = Math.min(Number(url.searchParams.get("ms")) || 1500, 10000);
    await new Promise(r => setTimeout(r, ms));
    body = { message: "slow response", delay_ms: ms };
  } else {
    status = 404;
    body = { error: "not found" };
  }

  send(res, status, body);
  const seconds = Number(process.hrtime.bigint() - start) / 1e9;
  observe(req.method, route, status, seconds);
  if (route !== "/healthz") {
    const level = status >= 500 ? "error" : seconds > 1 ? "warn" : "info";
    log(level, "request", { method: req.method, path: url.pathname, route, status,
                            duration_ms: Math.round(seconds * 10000) / 10 });
  }
});

server.listen(port, () => log("info", "starting", { port }));
process.on("SIGTERM", () => server.close(() => process.exit(0)));
