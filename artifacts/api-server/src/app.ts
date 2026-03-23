import express, { type Express } from "express";
import cors from "cors";
import helmet from "helmet";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";

const app: Express = express();

// Trust exactly one hop of proxy headers (Replit's single reverse proxy layer)
// so IP-based rate limiting reads the real client IP from X-Forwarded-For
// rather than the proxy's IP. Adjust if your deployment topology adds more
// proxy layers between the internet and this process.
app.set("trust proxy", 1);

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);

const allowedOrigins = [
  "https://textboox.org",
  "https://www.textboox.org",
];

// Always include all Replit-assigned domains (covers both dev preview and production deployment)
const replitDomains = process.env.REPLIT_DOMAINS?.split(",") ?? [];
for (const d of replitDomains) {
  if (d) allowedOrigins.push(`https://${d.trim()}`);
}

if (process.env.NODE_ENV !== "production") {
  allowedOrigins.push("http://localhost:3000", "http://localhost:5173");
}

app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin || allowedOrigins.includes(origin)) {
        callback(null, true);
      } else {
        callback(new Error(`CORS: origin not allowed — ${origin}`));
      }
    },
    credentials: true,
  }),
);

app.use(helmet());
app.use(express.json({ limit: "100kb" }));
app.use(express.urlencoded({ extended: true, limit: "100kb" }));

app.use("/api", router);

export default app;
