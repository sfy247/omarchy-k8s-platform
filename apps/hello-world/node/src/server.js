const http = require("node:http");

const port = Number(process.env.PORT || 8080);

const server = http.createServer((req, res) => {
  let status = 200;
  let body;
  if (req.url === "/healthz") body = { status: "ok" };
  else if (req.url === "/") body = { message: "Hello, World!", language: "node" };
  else { status = 404; body = { error: "not found" }; }
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
});

server.listen(port, () => console.log(`node hello listening on :${port}`));
process.on("SIGTERM", () => server.close(() => process.exit(0)));
