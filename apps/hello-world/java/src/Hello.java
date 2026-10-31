// Hello World service with RED metrics, JSON logs and failure modes.
// Endpoints: /  /healthz  /metrics  /fail (500)  /slow?ms=N (adds latency)
// JDK only.
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.Executors;

public class Hello {
    static final String SERVICE = System.getenv().getOrDefault("SERVICE_NAME", "java");
    static final Set<String> ROUTES = Set.of("/", "/healthz", "/fail", "/slow");
    static final double[] BUCKETS = {0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10};
    static final Map<String, Long> REQUESTS = new TreeMap<>();      // method|route|status
    static final Map<String, double[]> DURATIONS = new TreeMap<>(); // method|route -> buckets..., sum, count

    static String esc(String s) { return s.replace("\\", "\\\\").replace("\"", "\\\""); }

    static void log(String level, String msg, String extraJson) {
        System.out.println("{\"ts\":\"" + Instant.now() + "\",\"level\":\"" + level + "\",\"msg\":\"" + esc(msg)
            + "\",\"service\":\"" + SERVICE + "\"" + (extraJson.isEmpty() ? "" : "," + extraJson) + "}");
    }

    static synchronized void observe(String method, String route, int status, double seconds) {
        REQUESTS.merge(method + "|" + route + "|" + status, 1L, Long::sum);
        double[] h = DURATIONS.computeIfAbsent(method + "|" + route, k -> new double[BUCKETS.length + 2]);
        for (int i = 0; i < BUCKETS.length; i++) if (seconds <= BUCKETS[i]) h[i] += 1;
        h[BUCKETS.length] += seconds;
        h[BUCKETS.length + 1] += 1;
    }

    static synchronized String exposition() {
        StringBuilder sb = new StringBuilder();
        sb.append("# HELP http_requests_total Requests handled, by route and status.\n");
        sb.append("# TYPE http_requests_total counter\n");
        REQUESTS.forEach((k, v) -> {
            String[] p = k.split("\\|");
            sb.append("http_requests_total{method=\"").append(p[0]).append("\",route=\"").append(p[1])
              .append("\",status=\"").append(p[2]).append("\"} ").append(v).append('\n');
        });
        sb.append("# HELP http_request_duration_seconds Request latency.\n");
        sb.append("# TYPE http_request_duration_seconds histogram\n");
        DURATIONS.forEach((k, h) -> {
            String[] p = k.split("\\|");
            String l = "method=\"" + p[0] + "\",route=\"" + p[1] + "\"";
            for (int i = 0; i < BUCKETS.length; i++)
                sb.append("http_request_duration_seconds_bucket{").append(l).append(",le=\"").append(BUCKETS[i])
                  .append("\"} ").append((long) h[i]).append('\n');
            long count = (long) h[BUCKETS.length + 1];
            sb.append("http_request_duration_seconds_bucket{").append(l).append(",le=\"+Inf\"} ").append(count).append('\n');
            sb.append("http_request_duration_seconds_sum{").append(l).append("} ").append(h[BUCKETS.length]).append('\n');
            sb.append("http_request_duration_seconds_count{").append(l).append("} ").append(count).append('\n');
        });
        return sb.toString();
    }

    static void send(HttpExchange ex, int status, String body, String type) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = ex.getResponseBody()) { os.write(bytes); }
    }

    static int param(String query, String name, int fallback) {
        if (query == null) return fallback;
        for (String kv : query.split("&")) {
            String[] p = kv.split("=", 2);
            if (p.length == 2 && p[0].equals(name)) {
                try { return Integer.parseInt(p[1]); } catch (NumberFormatException e) { return fallback; }
            }
        }
        return fallback;
    }

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);

        server.createContext("/", ex -> {
            String path = ex.getRequestURI().getPath();
            if (path.equals("/metrics")) { send(ex, 200, exposition(), "text/plain; version=0.0.4"); return; }

            long start = System.nanoTime();
            String route = ROUTES.contains(path) ? path : "other";
            int status = 200;
            String body;
            switch (path) {
                case "/" -> body = "{\"message\":\"Hello, World!\",\"language\":\"java\"}";
                case "/healthz" -> body = "{\"status\":\"ok\"}";
                case "/fail" -> {
                    status = 500;
                    body = "{\"error\":\"simulated failure\"}";
                    log("error", "simulated failure", "\"path\":\"/fail\",\"reason\":\"requested via /fail\"");
                }
                case "/slow" -> {
                    int ms = Math.min(param(ex.getRequestURI().getQuery(), "ms", 1500), 10000);
                    try { Thread.sleep(ms); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                    body = "{\"message\":\"slow response\",\"delay_ms\":" + ms + "}";
                }
                default -> { status = 404; body = "{\"error\":\"not found\"}"; }
            }

            send(ex, status, body, "application/json");
            double seconds = (System.nanoTime() - start) / 1e9;
            observe(ex.getRequestMethod(), route, status, seconds);
            if (!route.equals("/healthz")) {
                String level = status >= 500 ? "error" : seconds > 1 ? "warn" : "info";
                log(level, "request", "\"method\":\"" + ex.getRequestMethod() + "\",\"path\":\"" + esc(path)
                    + "\",\"route\":\"" + route + "\",\"status\":" + status
                    + ",\"duration_ms\":" + Math.round(seconds * 10000) / 10.0);
            }
        });

        server.setExecutor(Executors.newVirtualThreadPerTaskExecutor());
        server.start();
        log("info", "starting", "\"port\":" + port);
    }
}
