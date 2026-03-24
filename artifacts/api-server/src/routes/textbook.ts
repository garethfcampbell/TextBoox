import { Router, type IRouter, type Request, type Response } from "express";
import { spawn } from "child_process";
import { randomBytes, timingSafeEqual, createHash } from "crypto";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";
import { db, booksTable } from "@workspace/db";
import { eq } from "drizzle-orm";
import { Resend } from "resend";
import { ideaLimiter, generateLimiter, adminLimiter } from "../lib/limiters";
import { logger } from "../lib/logger";

const router: IRouter = Router();

const resend = new Resend(process.env.RESEND_API_KEY);

const JOB_ID_RE = /^[a-zA-Z0-9_-]+$/;
const SAFE_FILENAME_RE = /^[a-zA-Z0-9_-]+$/;
const SAFE_DOMAIN_RE = /^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

async function sendCompletionEmail(
  email: string,
  title: string,
  jobId: string,
  formats: string[],
): Promise<void> {
  const replitDomain = process.env.REPLIT_DOMAINS?.split(",")[0]?.trim() ?? "";
  const baseUrl =
    replitDomain && SAFE_DOMAIN_RE.test(replitDomain)
      ? `https://${replitDomain}`
      : "https://textboox.org";

  const links = formats
    .map(
      (fmt) =>
        `<a href="${baseUrl}/api/textbook/download/${jobId}/${fmt}" style="display:inline-block;margin:4px 8px 4px 0;padding:8px 20px;background:#1a1a2e;color:#fff;text-decoration:none;border-radius:8px;font-size:14px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em">${fmt}</a>`,
    )
    .join("");

  const fromAddress = process.env.RESEND_FROM_EMAIL ?? "Textboox <notifications@textboox.org>";
  const safeTitle = escapeHtml(title);
  await resend.emails.send({
    from: fromAddress,
    to: email,
    subject: `Your textbook is ready: ${title}`,
    html: `
      <div style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:40px 24px;color:#1a1a1a">
        <h1 style="font-size:28px;font-weight:700;margin-bottom:8px;color:#1a1a2e">${safeTitle}</h1>
        <p style="font-size:16px;color:#555;margin-bottom:32px">Your textbook has been generated and is ready to download.</p>
        <div style="margin-bottom:32px">${links}</div>
        <p style="font-size:13px;color:#999">These links are hosted on Textboox and will remain available for download.</p>
        <hr style="border:none;border-top:1px solid #eee;margin:32px 0"/>
        <p style="font-size:12px;color:#bbb">Textboox.org</p>
      </div>
    `,
  });
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const API_SERVER_ROOT = path.resolve(__dirname, "..");
const WORKSPACE_ROOT = path.resolve(API_SERVER_ROOT, "../..");
const PYTHON_SCRIPT = path.join(API_SERVER_ROOT, "src", "python", "runner.py");
const OUTPUT_DIR = path.join(API_SERVER_ROOT, "output");
const PYTHONLIBS = path.join(WORKSPACE_ROOT, ".pythonlibs", "lib", "python3.11", "site-packages");

function runPython(args: string[]): Promise<string> {
  const existingPythonPath = process.env.PYTHONPATH ?? "";
  const pythonPath = [PYTHONLIBS, existingPythonPath].filter(Boolean).join(":");

  return new Promise((resolve, reject) => {
    const proc = spawn("python3", [PYTHON_SCRIPT, ...args], {
      env: { ...process.env, PYTHONPATH: pythonPath },
      cwd: API_SERVER_ROOT,
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("error", (err) => {
      reject(new Error(`Failed to spawn python3: ${err.message}`));
    });

    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `Process exited with code ${code}`));
      } else {
        resolve(stdout.trim());
      }
    });
  });
}

// Save a completed job's files to the database (runs once per job)
async function saveJobToDb(jobId: string, statusFile: string, jobDir: string): Promise<void> {
  const status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));
  const title = status.title ?? jobId;
  const topic = status.topic ?? "";

  const files = fs.readdirSync(jobDir);
  const findFile = (ext: string) => files.find((f) => f.endsWith(`.${ext}`));

  const htmlFile = findFile("html");
  const pdfFile  = findFile("pdf");
  const epubFile = findFile("epub");

  const MAX_DB_FILE_BYTES = 10 * 1024 * 1024; // 10 MB

  const readIfSmall = (filePath: string): Buffer | null => {
    const stat = fs.statSync(filePath);
    if (stat.size > MAX_DB_FILE_BYTES) {
      logger.error({ filePath, size: stat.size }, "File too large for DB storage; skipping");
      return null;
    }
    return fs.readFileSync(filePath);
  };

  const htmlBuf  = htmlFile  ? readIfSmall(path.join(jobDir, htmlFile))  : null;
  const pdfBuf   = pdfFile   ? readIfSmall(path.join(jobDir, pdfFile))   : null;
  const epubBuf  = epubFile  ? readIfSmall(path.join(jobDir, epubFile))  : null;

  const htmlData  = htmlBuf  ? htmlBuf.toString("utf-8")   : null;
  const pdfData   = pdfBuf   ? pdfBuf.toString("base64")   : null;
  const epubData  = epubBuf  ? epubBuf.toString("base64")  : null;

  const [inserted] = await db
    .insert(booksTable)
    .values({ jobId, title, topic, htmlData, pdfData, epubData })
    .onConflictDoNothing()
    .returning({ id: booksTable.id });

  if (inserted) {
    status.dbId = inserted.id;
    fs.writeFileSync(statusFile, JSON.stringify(status));
  }
}

// Serialization queue: ensures only one finalizeJob runs at a time to prevent
// concurrent large-file reads from spiking memory and killing the process.
let _finalizeQueue: Promise<void> = Promise.resolve();
function queueFinalizeJob(jobId: string, statusFile: string, jobDir: string): void {
  _finalizeQueue = _finalizeQueue.then(() =>
    finalizeJob(jobId, statusFile, jobDir).catch((err) =>
      logger.error({ err, jobId }, "Queued finalize failed"),
    ),
  );
}

// Idempotent: save to DB + send email once per completed job.
// Called from proc.on("close"), status polling endpoint, and startup recovery.
async function finalizeJob(jobId: string, statusFile: string, jobDir: string): Promise<void> {
  let status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));

  // 1. Persist to DB (no-op if already saved)
  if (!status.dbId) {
    await saveJobToDb(jobId, statusFile, jobDir);
    status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));
  }

  // 2. Send completion email (no-op if already sent)
  if (!status.emailSent) {
    const metaFile = path.join(jobDir, "meta.json");
    if (fs.existsSync(metaFile)) {
      try {
        const meta = JSON.parse(fs.readFileSync(metaFile, "utf-8"));
        if (meta.email && status.availableFormats?.length) {
          await sendCompletionEmail(meta.email, status.title ?? jobId, jobId, status.availableFormats);
        }
      } catch (err) {
        logger.error({ err, jobId }, "Failed to send completion email");
      }
    }
    // Mark done whether we sent or not (no meta.json = no email address = nothing to send)
    status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));
    status.emailSent = true;
    fs.writeFileSync(statusFile, JSON.stringify(status));
  }
}

// Shared scan logic used by both recoverJobs (startup) and the periodic watcher.
function scanAndFinalizeJobs(): void {
  try {
    if (!fs.existsSync(OUTPUT_DIR)) return;
    const now = Date.now();
    const STALE_MS = 90 * 60 * 1000; // 90 minutes

    for (const entry of fs.readdirSync(OUTPUT_DIR)) {
      if (!JOB_ID_RE.test(entry)) continue;
      const dir = path.join(OUTPUT_DIR, entry);
      const statusFile = path.join(dir, "status.json");
      if (!fs.existsSync(statusFile)) continue;
      try {
        const status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));
        if (status.status === "completed" && (!status.dbId || !status.emailSent)) {
          logger.info({ jobId: entry }, "Scanner: found completed job needing finalization");
          queueFinalizeJob(entry, statusFile, dir);
        } else if (status.status === "running" || status.status === "pending") {
          // If it's been running longer than 90 min it's almost certainly stale
          const dirStat = fs.statSync(dir);
          if (now - dirStat.mtimeMs > STALE_MS) {
            logger.warn({ jobId: entry }, "Scanner: marking stale job as failed");
            writeStatus(statusFile, {
              ...status,
              status: "failed",
              error: "Generation was interrupted by a server restart. Please try again.",
            });
          }
          // Otherwise leave it — the detached Python process may still be running
        }
      } catch {
        // ignore per-job errors
      }
    }
  } catch {
    // ignore
  }
}

// Runs once at startup to pick up jobs that completed while the server was down.
export function recoverJobs(): void {
  scanAndFinalizeJobs();
}

// Starts a 60-second interval that catches jobs completed by detached Python
// processes whose proc.on("close") was lost (e.g. after a server restart mid-job).
export function startJobWatcher(): void {
  logger.info("Job watcher started (60 s interval)");
  setInterval(scanAndFinalizeJobs, 60_000).unref();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function isSafeJobId(jobId: string): boolean {
  return JOB_ID_RE.test(jobId) && jobId.length <= 64;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email) && email.length <= 254;
}

/** Strip null bytes and ASCII control characters (except tab/newline) from user input. */
function stripControlChars(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
}

function cleanEmail(email: string): string {
  return email.replace(/[\r\n\t]/g, "");
}

function safeContentDispositionName(name: string): string {
  return name.replace(/["\r\n\\]/g, "_").slice(0, 200);
}

const JOB_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function cleanOldJobs(): void {
  try {
    if (!fs.existsSync(OUTPUT_DIR)) return;
    const now = Date.now();
    for (const entry of fs.readdirSync(OUTPUT_DIR)) {
      if (!JOB_ID_RE.test(entry)) continue;
      const dir = path.join(OUTPUT_DIR, entry);
      try {
        const stat = fs.statSync(dir);
        if (stat.isDirectory() && now - stat.mtimeMs > JOB_MAX_AGE_MS) {
          fs.rmSync(dir, { recursive: true, force: true });
        }
      } catch {
        // ignore per-entry errors
      }
    }
  } catch {
    // ignore
  }
}

// ── Debug (development only) ───────────────────────────────────────────────────

router.get("/textbook/debug", requireAdminAuth, async (_req: Request, res: Response) => {
  if (process.env.NODE_ENV === "production") {
    res.status(404).json({ error: "Not found" });
    return;
  }
  const existingPythonPath = process.env.PYTHONPATH ?? "";
  const pythonPath = [PYTHONLIBS, existingPythonPath].filter(Boolean).join(":");

  const checkImports = () =>
    new Promise<string>((resolve, reject) => {
      const proc = spawn(
        "python3",
        ["-c", "import sys, google.genai, ebooklib, xhtml2pdf; print(sys.version)"],
        { env: { ...process.env, PYTHONPATH: pythonPath }, cwd: API_SERVER_ROOT },
      );
      let out = "";
      let err = "";
      proc.stdout.on("data", (d) => (out += d));
      proc.stderr.on("data", (d) => (err += d));
      proc.on("error", (e) => reject(e));
      proc.on("close", (code) =>
        code === 0 ? resolve(out.trim()) : reject(new Error(err.trim())),
      );
    });

  try {
    const pythonVersion = await checkImports();
    res.json({
      pythonVersion,
      pythonScript: PYTHON_SCRIPT,
      pythonScriptExists: fs.existsSync(PYTHON_SCRIPT),
      outputDir: OUTPUT_DIR,
      workspaceRoot: WORKSPACE_ROOT,
      pythonlibs: PYTHONLIBS,
      pythonlibsExists: fs.existsSync(PYTHONLIBS),
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(500).json({
      error: message,
      pythonScript: PYTHON_SCRIPT,
      pythonScriptExists: fs.existsSync(PYTHON_SCRIPT),
      workspaceRoot: WORKSPACE_ROOT,
      pythonlibs: PYTHONLIBS,
      pythonlibsExists: fs.existsSync(PYTHONLIBS),
    });
  }
});

function generateJobId(): string {
  return `job_${Date.now()}_${randomBytes(9).toString("base64url")}`;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Generate idea ─────────────────────────────────────────────────────────────

router.post("/textbook/generate-idea", ideaLimiter, async (req: Request, res: Response) => {
  const { keyword } = req.body;

  if (!keyword || typeof keyword !== "string") {
    res.status(400).json({ error: "keyword is required" });
    return;
  }

  if (keyword.length > 200) {
    res.status(400).json({ error: "keyword must be 200 characters or fewer" });
    return;
  }

  const safeKeyword = stripControlChars(keyword);

  try {
    const output = await runPython(["generate-idea", safeKeyword]);
    const result = JSON.parse(output);

    if (result.error) {
      res.status(500).json({ error: result.error });
      return;
    }

    res.json(result);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    req.log.error({ err }, "Failed to generate idea");
    res.status(500).json({ error: message });
  }
});

// ── Job queue ─────────────────────────────────────────────────────────────────

const MAX_CONCURRENT = 3;
let activeJobs = 0;

interface QueuedJob {
  jobId: string;
  topic: string;
  title: string;
  safeFilename: string;
  jobDir: string;
  statusFile: string;
  logFile: string;
  email: string | null;
}

const jobQueue: QueuedJob[] = [];

function writeStatus(statusFile: string, fields: object): void {
  try {
    fs.writeFileSync(statusFile, JSON.stringify(fields));
  } catch {
    // ignore
  }
}

function spawnBookJob(job: QueuedJob): void {
  const { jobId, topic, title, safeFilename, jobDir, statusFile, logFile, email } = job;

  writeStatus(statusFile, {
    jobId, topic, title,
    status: "pending", progress: "Starting...",
    currentChapter: "", totalChapters: 0, completedChapters: 0,
    availableFormats: [], error: "",
  });

  // Persist the email separately so it survives Python overwriting status.json
  const metaFile = path.join(jobDir, "meta.json");
  fs.writeFileSync(metaFile, JSON.stringify({ email: email || null, title, topic }));

  const existingPythonPath = process.env.PYTHONPATH ?? "";
  const pythonPath = [PYTHONLIBS, existingPythonPath].filter(Boolean).join(":");

  // detached: true puts Python in its own process group so it survives
  // if the Node.js server is restarted (e.g. by a new deployment).
  const proc = spawn(
    "python3",
    [PYTHON_SCRIPT, "generate-book", jobId, topic, title, safeFilename, jobDir],
    {
      env: { ...process.env, PYTHONPATH: pythonPath },
      cwd: API_SERVER_ROOT,
      stdio: ["ignore", "pipe", "pipe"],
      detached: true,
    },
  );

  // Don't keep the Node.js event loop alive just for this child
  proc.unref();

  const logStream = fs.createWriteStream(logFile, { flags: "a" });
  proc.stdout?.pipe(logStream);
  proc.stderr?.pipe(logStream);

  proc.on("error", (err) => {
    writeStatus(statusFile, {
      jobId, topic, title, status: "failed",
      progress: "", currentChapter: "", totalChapters: 0, completedChapters: 0,
      availableFormats: [], error: `Failed to spawn python3: ${err.message}`,
    });
    fs.appendFileSync(logFile, `\nSPAWN ERROR: ${err.message}\n`);
    activeJobs = Math.max(0, activeJobs - 1);
    drainQueue();
  });

  proc.on("close", (code) => {
    logger.info({ jobId, code }, "Python process closed");
    if (code !== 0) {
      try {
        const current = JSON.parse(fs.readFileSync(statusFile, "utf-8"));
        // Even with a non-zero code, if Python already wrote "completed" (e.g.
        // all formats done but exited non-cleanly), still finalize the job.
        if (current.status === "completed") {
          queueFinalizeJob(jobId, statusFile, jobDir);
        } else if (current.status === "running" || current.status === "pending") {
          writeStatus(statusFile, {
            ...current, status: "failed",
            error: `Python exited with code ${code}. Check python.log for details.`,
          });
        }
      } catch {
        // ignore
      }
    } else {
      // Persist to DB and send email (both idempotent, serialized to avoid memory spikes)
      queueFinalizeJob(jobId, statusFile, jobDir);
    }
    activeJobs = Math.max(0, activeJobs - 1);
    drainQueue();
  });
}

function drainQueue(): void {
  while (activeJobs < MAX_CONCURRENT && jobQueue.length > 0) {
    const next = jobQueue.shift()!;
    activeJobs++;
    spawnBookJob(next);
  }
}

// ── Generate book ─────────────────────────────────────────────────────────────

router.post("/textbook/generate-book", generateLimiter, async (req: Request, res: Response) => {
  const { topic, title, filename, email } = req.body;

  if (!topic || !title || !filename) {
    res.status(400).json({ error: "topic, title, and filename are required" });
    return;
  }

  if (typeof topic !== "string" || topic.length > 2000) {
    res.status(400).json({ error: "topic must be a string of 2000 characters or fewer" });
    return;
  }

  if (typeof title !== "string" || title.length > 300) {
    res.status(400).json({ error: "title must be a string of 300 characters or fewer" });
    return;
  }

  if (typeof filename !== "string" || filename.length > 200) {
    res.status(400).json({ error: "filename must be a string of 200 characters or fewer" });
    return;
  }

  if (email !== undefined && email !== null && email !== "") {
    if (typeof email !== "string" || !isValidEmail(email)) {
      res.status(400).json({ error: "Invalid email address" });
      return;
    }
  }

  // Strip control characters and null bytes from user-supplied strings
  const safeTopic = stripControlChars(topic);
  const safeTitle = stripControlChars(title);

  const jobId = generateJobId();
  const jobDir = path.join(OUTPUT_DIR, jobId);
  fs.mkdirSync(jobDir, { recursive: true });

  // Apply allowlist regex to the filename stem (after stripping directory components)
  const baseFilename = path.basename(filename).replace(/\.html$/i, "");
  if (!SAFE_FILENAME_RE.test(baseFilename)) {
    res.status(400).json({ error: "filename must contain only letters, digits, hyphens, and underscores" });
    return;
  }
  const safeFilename = `${baseFilename}.html`;
  const statusFile = path.join(jobDir, "status.json");
  const logFile = path.join(jobDir, "python.log");

  const queuedJob: QueuedJob = {
    jobId, topic: safeTopic, title: safeTitle, safeFilename, jobDir, statusFile, logFile,
    email: email ? cleanEmail(email) : null,
  };

  // Opportunistically clean up jobs older than 7 days
  setImmediate(cleanOldJobs);

  if (activeJobs < MAX_CONCURRENT) {
    activeJobs++;
    spawnBookJob(queuedJob);
    res.json({ jobId, message: "Book generation started" });
  } else {
    jobQueue.push(queuedJob);
    const position = jobQueue.length;
    writeStatus(statusFile, {
      jobId, topic: safeTopic, title: safeTitle, email: email || null,
      status: "queued",
      progress: `Waiting in queue (position ${position} of ${jobQueue.length})...`,
      currentChapter: "", totalChapters: 0, completedChapters: 0,
      availableFormats: [], error: "",
    });
    res.json({ jobId, message: `Job queued (position ${position})` });
  }
});

// ── Job status & log ───────────────────────────────────────────────────────────

router.get("/textbook/job/:jobId/log", requireAdminAuth, async (req: Request, res: Response) => {
  const { jobId } = req.params;
  if (!isSafeJobId(jobId)) {
    res.status(400).json({ error: "Invalid job ID" });
    return;
  }
  const logFile = path.join(OUTPUT_DIR, jobId, "python.log");
  if (!fs.existsSync(logFile)) {
    res.status(404).json({ error: "Log not found" });
    return;
  }
  res.setHeader("Content-Type", "text/plain");
  res.send(fs.readFileSync(logFile, "utf-8"));
});

router.get("/textbook/job/:jobId", async (req: Request, res: Response) => {
  const { jobId } = req.params;
  if (!isSafeJobId(jobId)) {
    res.status(400).json({ error: "Invalid job ID" });
    return;
  }
  const jobDir = path.join(OUTPUT_DIR, jobId);
  const statusFile = path.join(jobDir, "status.json");

  if (!fs.existsSync(statusFile)) {
    res.status(404).json({ error: "Job not found" });
    return;
  }

  try {
    const data = JSON.parse(fs.readFileSync(statusFile, "utf-8"));

    // Finalize (DB save + email) the first time we see a completed job
    if (data.status === "completed" && (!data.dbId || !data.emailSent)) {
      queueFinalizeJob(jobId, statusFile, jobDir);
    }

    res.json(data);
  } catch {
    res.status(500).json({ error: "Failed to read job status" });
  }
});

// ── Download (disk → DB fallback) ─────────────────────────────────────────────

router.get(
  "/textbook/download/:jobId/:format",
  async (req: Request, res: Response) => {
    const { jobId, format } = req.params;

    if (!isSafeJobId(jobId)) {
      res.status(400).json({ error: "Invalid job ID" });
      return;
    }

    if (!["epub", "pdf", "html"].includes(format)) {
      res.status(400).json({ error: "Invalid format" });
      return;
    }

    const contentTypes: Record<string, string> = {
      epub: "application/epub+zip",
      pdf: "application/pdf",
      html: "text/html",
    };

    // ── 1. Try disk first (job still in active output directory) ──────────────
    const jobDir = path.join(OUTPUT_DIR, jobId);
    const statusFile = path.join(jobDir, "status.json");

    if (fs.existsSync(statusFile)) {
      const status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));
      const files = fs.readdirSync(jobDir);
      const matchingFile = files.find((f) => f.endsWith(`.${format}`));

      if (matchingFile) {
        const filePath = path.join(jobDir, matchingFile);
        const rawTitle = status.title ?? path.basename(matchingFile, `.${format}`);
        const safeTitle = safeContentDispositionName(rawTitle);
        res.setHeader("Content-Type", contentTypes[format]);
        res.setHeader("Content-Disposition", `attachment; filename="${safeTitle}.${format}"`);
        if (format === "html") {
          res.setHeader("Content-Security-Policy", "sandbox");
        }
        res.sendFile(filePath);
        return;
      }
    }

    // ── 2. Fall back to database (job cleaned from disk or server restarted) ──
    try {
      const [row] = await db
        .select({
          title: booksTable.title,
          htmlData: booksTable.htmlData,
          pdfData: booksTable.pdfData,
          epubData: booksTable.epubData,
        })
        .from(booksTable)
        .where(eq(booksTable.jobId, jobId))
        .limit(1);

      if (!row) {
        res.status(404).json({ error: "Job not found" });
        return;
      }

      const dataMap: Record<string, string | null | undefined> = {
        html: row.htmlData,
        pdf: row.pdfData,
        epub: row.epubData,
      };

      const data = dataMap[format];
      if (!data) {
        res.status(404).json({ error: `No ${format} file found` });
        return;
      }

      const safeTitle = safeContentDispositionName(row.title);
      res.setHeader("Content-Type", contentTypes[format]);
      res.setHeader("Content-Disposition", `attachment; filename="${safeTitle}.${format}"`);
      if (format === "html") {
        res.setHeader("Content-Security-Policy", "sandbox");
        res.send(data);
      } else {
        // PDF and EPUB are stored as base64 in the DB
        res.send(Buffer.from(data, "base64"));
      }
    } catch (dbErr) {
      logger.error({ err: dbErr, jobId }, "DB lookup failed in download route");
      res.status(500).json({ error: "Failed to retrieve file" });
    }
  },
);

// ── Public library (approved books) ───────────────────────────────────────────

router.get("/textbook/library", async (_req: Request, res: Response) => {
  try {
    const books = await db
      .select({
        id: booksTable.id,
        title: booksTable.title,
        topic: booksTable.topic,
        createdAt: booksTable.createdAt,
      })
      .from(booksTable)
      .where(eq(booksTable.approved, true))
      .orderBy(booksTable.createdAt);

    res.json(books);
  } catch (err) {
    logger.error({ err }, "Failed to fetch library");
    res.status(500).json({ error: "Failed to fetch library" });
  }
});

// Download from DB (library books)
router.get("/textbook/library/:id/download/:format", async (req: Request, res: Response) => {
  const id = parseInt(req.params.id, 10);
  const { format } = req.params;

  if (!["epub", "pdf", "html"].includes(format)) {
    res.status(400).json({ error: "Invalid format" });
    return;
  }

  try {
    const [book] = await db
      .select()
      .from(booksTable)
      .where(eq(booksTable.id, id));

    if (!book || !book.approved) {
      res.status(404).json({ error: "Book not found" });
      return;
    }

    const contentTypes: Record<string, string> = {
      epub: "application/epub+zip",
      pdf: "application/pdf",
      html: "text/html",
    };

    const safeLibTitle = safeContentDispositionName(book.title ?? "textbook");
    res.setHeader("Content-Type", contentTypes[format]);
    res.setHeader("Content-Disposition", `attachment; filename="${safeLibTitle}.${format}"`);

    if (format === "html") {
      res.setHeader("Content-Security-Policy", "sandbox");
      res.send(book.htmlData ?? "");
    } else {
      const field = format === "pdf" ? book.pdfData : book.epubData;
      if (!field) {
        res.status(404).json({ error: `${format} not available` });
        return;
      }
      res.send(Buffer.from(field, "base64"));
    }
  } catch (err) {
    logger.error({ err }, "Failed to serve library file");
    res.status(500).json({ error: "Failed to serve file" });
  }
});

// ── Admin auth middleware ──────────────────────────────────────────────────────
// Design note: admin endpoints use a single shared secret (ADMIN_PASSWORD)
// rather than JWT/OAuth. Mitigations in place:
//   • SHA-256 hash of both sides before timingSafeEqual — no padding side-channel
//   • adminLimiter: 20 requests per 15 minutes per IP — brute-force protection
//   • Fail-closed: 503 if ADMIN_PASSWORD env var is not set
// Upgrade to JWT/OAuth if multi-user admin access is ever needed.

function requireAdminAuth(req: Request, res: Response, next: () => void) {
  const adminPassword = process.env.ADMIN_PASSWORD;
  if (!adminPassword) {
    res.status(503).json({ error: "Admin access is not configured on this server" });
    return;
  }
  const provided = String(req.headers["x-admin-password"] ?? "");
  let authorised = false;
  try {
    // Hash both values with SHA-256 before comparing so lengths are always
    // identical, eliminating the padding timing side-channel.
    const a = createHash("sha256").update(provided).digest();
    const b = createHash("sha256").update(adminPassword).digest();
    authorised = timingSafeEqual(a, b);
  } catch {
    authorised = false;
  }
  if (!authorised) {
    res.status(401).json({ error: "Unauthorized" });
    return;
  }
  next();
}

// ── Admin endpoints ────────────────────────────────────────────────────────────

// List all books (for admin panel)
router.get("/textbook/admin/books", adminLimiter, requireAdminAuth, async (_req: Request, res: Response) => {
  try {
    const books = await db
      .select({
        id: booksTable.id,
        jobId: booksTable.jobId,
        title: booksTable.title,
        topic: booksTable.topic,
        approved: booksTable.approved,
        createdAt: booksTable.createdAt,
      })
      .from(booksTable)
      .orderBy(booksTable.createdAt);

    res.json(books);
  } catch (err) {
    logger.error({ err }, "Failed to fetch admin book list");
    res.status(500).json({ error: "Failed to fetch books" });
  }
});

// Toggle approval for a book
router.patch("/textbook/admin/books/:id/approve", adminLimiter, requireAdminAuth, async (req: Request, res: Response) => {
  const id = parseInt(req.params.id, 10);
  const { approved } = req.body as { approved: boolean };

  if (typeof approved !== "boolean") {
    res.status(400).json({ error: "approved (boolean) is required" });
    return;
  }

  try {
    const [updated] = await db
      .update(booksTable)
      .set({ approved })
      .where(eq(booksTable.id, id))
      .returning({ id: booksTable.id, approved: booksTable.approved });

    if (!updated) {
      res.status(404).json({ error: "Book not found" });
      return;
    }

    res.json(updated);
  } catch (err) {
    logger.error({ err }, "Failed to update book approval");
    res.status(500).json({ error: "Failed to update approval" });
  }
});

// Admin download — bypasses approval check so admins can preview before approving
router.get("/textbook/admin/books/:id/download/:format", adminLimiter, requireAdminAuth, async (req: Request, res: Response) => {
  const id = parseInt(req.params.id, 10);
  const { format } = req.params;

  if (!["epub", "pdf", "html"].includes(format)) {
    res.status(400).json({ error: "Invalid format" });
    return;
  }

  try {
    const [book] = await db
      .select()
      .from(booksTable)
      .where(eq(booksTable.id, id));

    if (!book) {
      res.status(404).json({ error: "Book not found" });
      return;
    }

    const contentTypes: Record<string, string> = {
      epub: "application/epub+zip",
      pdf: "application/pdf",
      html: "text/html",
    };

    const safeLibTitle = safeContentDispositionName(book.title ?? "textbook");
    res.setHeader("Content-Type", contentTypes[format]);
    res.setHeader("Content-Disposition", `attachment; filename="${safeLibTitle}.${format}"`);

    if (format === "html") {
      res.setHeader("Content-Security-Policy", "sandbox");
      res.send(book.htmlData ?? "");
    } else {
      const field = format === "pdf" ? book.pdfData : book.epubData;
      if (!field) {
        res.status(404).json({ error: `${format} not available` });
        return;
      }
      res.send(Buffer.from(field, "base64"));
    }
  } catch (err) {
    logger.error({ err }, "Failed to serve admin download");
    res.status(500).json({ error: "Failed to serve file" });
  }
});

export default router;
