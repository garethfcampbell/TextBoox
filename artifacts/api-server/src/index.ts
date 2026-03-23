import app from "./app";
import { logger } from "./lib/logger";
import { recoverJobs, startJobWatcher } from "./routes/textbook";

const rawPort = process.env["PORT"];

if (!rawPort) {
  throw new Error(
    "PORT environment variable is required but was not provided.",
  );
}

const port = Number(rawPort);

if (Number.isNaN(port) || port <= 0) {
  throw new Error(`Invalid PORT value: "${rawPort}"`);
}

if (!process.env["OPENAI_API_KEY"]) {
  logger.warn(
    "OPENAI_API_KEY is not set — OpenAI gpt-4.1-nano fallback will be unavailable. " +
    "Add this secret so book generation can fall back when Gemini is rate-limited.",
  );
}

if (!process.env["RESEND_API_KEY"]) {
  logger.warn(
    "RESEND_API_KEY is not set — completion email notifications will not be sent. " +
    "Add this secret to enable email delivery.",
  );
}

if (!process.env["RESEND_FROM_EMAIL"]) {
  logger.warn(
    "RESEND_FROM_EMAIL is not set — using default 'Textboox <notifications@textboox.org>'. " +
    "This requires the textboox.org domain to be verified in your Resend account. " +
    "Set RESEND_FROM_EMAIL to a verified sender address to enable email delivery.",
  );
}

app.listen(port, (err) => {
  if (err) {
    logger.error({ err }, "Error listening on port");
    process.exit(1);
  }

  logger.info({ port }, "Server listening");

  // Finalize any jobs that completed while the server was down
  setImmediate(recoverJobs);
  // Watch for jobs completed by detached Python processes (every 60 s)
  startJobWatcher();
});
