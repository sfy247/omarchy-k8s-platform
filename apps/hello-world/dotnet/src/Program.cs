var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/", () => Results.Json(new { message = "Hello, World!", language = "csharp" }));
app.MapGet("/healthz", () => Results.Json(new { status = "ok" }));

app.Run();
