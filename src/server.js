import { createApp } from "./app.js";
const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || "127.0.0.1";
const server = createApp().listen(port, host, () =>
  console.log(`Plum is ready at http://${host}:${port}`),
);
server.on("error", (error) => {
  console.error(
    error.code === "EADDRINUSE"
      ? `Port ${port} is already in use. Stop the other server or set PORT.`
      : "Server could not start.",
  );
  process.exitCode = 1;
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.once(signal, () => {
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(1), 10000).unref();
  });
