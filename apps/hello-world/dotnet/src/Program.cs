// Hello World service with RED metrics, JSON logs and failure modes.
// Endpoints: /  /healthz  /metrics  /fail (500)  /slow?ms=N (adds latency)
// No packages beyond ASP.NET Core.
using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;

var service = Environment.GetEnvironmentVariable("SERVICE_NAME") ?? "dotnet";
string[] routes = ["/", "/healthz", "/fail", "/slow"];
double[] buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10];
var gate = new object();
var requests = new SortedDictionary<string, long>(StringComparer.Ordinal);
var durations = new SortedDictionary<string, double[]>(StringComparer.Ordinal);

void Log(string level, string msg, Dictionary<string, object?>? fields = null)
{
    var record = new Dictionary<string, object?>
    {
        ["ts"] = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss.fff'Z'", CultureInfo.InvariantCulture), ["level"] = level, ["msg"] = msg, ["service"] = service,
    };
    if (fields is not null) foreach (var (k, v) in fields) record[k] = v;
    Console.Out.WriteLine(JsonSerializer.Serialize(record));
}

var builder = WebApplication.CreateBuilder(args);
// Framework logs as JSON too, so every line from this container is parseable
builder.Logging.ClearProviders();
builder.Logging.AddJsonConsole();
builder.Logging.SetMinimumLevel(LogLevel.Warning);
var app = builder.Build();

app.Use(async (ctx, next) =>
{
    var path = ctx.Request.Path.Value ?? "/";
    if (path == "/metrics") { await next(); return; }
    var sw = Stopwatch.StartNew();
    await next();
    var seconds = sw.Elapsed.TotalSeconds;
    var route = routes.Contains(path) ? path : "other";
    var status = ctx.Response.StatusCode;
    lock (gate)
    {
        var key = $"{ctx.Request.Method}|{route}|{status}";
        requests[key] = requests.GetValueOrDefault(key) + 1;
        if (!durations.TryGetValue($"{ctx.Request.Method}|{route}", out var h))
            durations[$"{ctx.Request.Method}|{route}"] = h = new double[buckets.Length + 2];
        for (var i = 0; i < buckets.Length; i++) if (seconds <= buckets[i]) h[i]++;
        h[buckets.Length] += seconds;
        h[buckets.Length + 1]++;
    }
    if (route != "/healthz")
    {
        var level = status >= 500 ? "error" : seconds > 1 ? "warn" : "info";
        Log(level, "request", new()
        {
            ["method"] = ctx.Request.Method, ["path"] = path, ["route"] = route,
            ["status"] = status, ["duration_ms"] = Math.Round(seconds * 1000, 1),
        });
    }
});

app.MapGet("/", () => Results.Json(new { message = "Hello, World!", language = "csharp" }));
app.MapGet("/healthz", () => Results.Json(new { status = "ok" }));
app.MapGet("/fail", () =>
{
    Log("error", "simulated failure", new() { ["path"] = "/fail", ["reason"] = "requested via /fail" });
    return Results.Json(new { error = "simulated failure" }, statusCode: 500);
});
app.MapGet("/slow", async (int? ms) =>
{
    var delay = Math.Min(ms ?? 1500, 10000);
    await Task.Delay(delay);
    return Results.Json(new { message = "slow response", delay_ms = delay });
});
app.MapGet("/metrics", () =>
{
    var sb = new StringBuilder();
    var inv = CultureInfo.InvariantCulture;
    lock (gate)
    {
        sb.Append("# HELP http_requests_total Requests handled, by route and status.\n# TYPE http_requests_total counter\n");
        foreach (var (k, v) in requests)
        {
            var p = k.Split('|');
            sb.Append(inv, $"http_requests_total{{method=\"{p[0]}\",route=\"{p[1]}\",status=\"{p[2]}\"}} {v}\n");
        }
        sb.Append("# HELP http_request_duration_seconds Request latency.\n# TYPE http_request_duration_seconds histogram\n");
        foreach (var (k, h) in durations)
        {
            var p = k.Split('|');
            var l = $"method=\"{p[0]}\",route=\"{p[1]}\"";
            for (var i = 0; i < buckets.Length; i++)
                sb.Append(inv, $"http_request_duration_seconds_bucket{{{l},le=\"{buckets[i]}\"}} {h[i]}\n");
            sb.Append(inv, $"http_request_duration_seconds_bucket{{{l},le=\"+Inf\"}} {h[buckets.Length + 1]}\n");
            sb.Append(inv, $"http_request_duration_seconds_sum{{{l}}} {h[buckets.Length]}\n");
            sb.Append(inv, $"http_request_duration_seconds_count{{{l}}} {h[buckets.Length + 1]}\n");
        }
    }
    return Results.Text(sb.ToString(), "text/plain; version=0.0.4");
});

Log("info", "starting", new() { ["port"] = Environment.GetEnvironmentVariable("ASPNETCORE_HTTP_PORTS") });
app.Run();
