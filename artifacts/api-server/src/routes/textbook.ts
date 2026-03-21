import { Router, type IRouter, type Request, type Response } from "express";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const router: IRouter = Router();

// Use import.meta.url so the path works in both dev (src/routes/) and production
// (dist/index.mjs). In production the bundle lives at artifacts/api-server/dist/index.mjs,
// so going up one directory lands at artifacts/api-server/ where src/python/ lives.
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const API_SERVER_ROOT = path.resolve(__dirname, "..");
const PYTHON_SCRIPT = path.join(API_SERVER_ROOT, "src", "python", "runner.py");
const OUTPUT_DIR = path.join(API_SERVER_ROOT, "output");

function runPython(args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const proc = spawn("python3", [PYTHON_SCRIPT, ...args], {
      env: { ...process.env },
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
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

function generateJobId(): string {
  return `job_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

router.post("/textbook/generate-idea", async (req: Request, res: Response) => {
  const { keyword } = req.body;

  if (!keyword) {
    res.status(400).json({ error: "keyword is required" });
    return;
  }

  try {
    const output = await runPython(["generate-idea", keyword]);
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

router.post("/textbook/generate-book", async (req: Request, res: Response) => {
  const { topic, title, filename } = req.body;

  if (!topic || !title || !filename) {
    res.status(400).json({ error: "topic, title, and filename are required" });
    return;
  }

  const jobId = generateJobId();
  const jobDir = path.join(OUTPUT_DIR, jobId);
  fs.mkdirSync(jobDir, { recursive: true });

  const statusFile = path.join(jobDir, "status.json");
  fs.writeFileSync(
    statusFile,
    JSON.stringify({
      jobId,
      status: "pending",
      progress: "Queued...",
      currentChapter: "",
      totalChapters: 0,
      completedChapters: 0,
      availableFormats: [],
      error: "",
    }),
  );

  const safeFilename = filename.endsWith(".html") ? filename : `${filename}.html`;

  runPython(["generate-book", jobId, topic, title, safeFilename]).catch(
    (err) => {
      const errorStatus = {
        jobId,
        status: "failed",
        progress: "",
        currentChapter: "",
        totalChapters: 0,
        completedChapters: 0,
        availableFormats: [],
        error: err.message,
      };
      fs.writeFileSync(statusFile, JSON.stringify(errorStatus));
    },
  );

  res.json({ jobId, message: "Book generation started" });
});

router.get("/textbook/job/:jobId", async (req: Request, res: Response) => {
  const { jobId } = req.params;
  const statusFile = path.join(OUTPUT_DIR, jobId, "status.json");

  if (!fs.existsSync(statusFile)) {
    res.status(404).json({ error: "Job not found" });
    return;
  }

  try {
    const data = JSON.parse(fs.readFileSync(statusFile, "utf-8"));
    res.json(data);
  } catch {
    res.status(500).json({ error: "Failed to read job status" });
  }
});

router.get(
  "/textbook/download/:jobId/:format",
  async (req: Request, res: Response) => {
    const { jobId, format } = req.params;

    if (!["epub", "pdf", "html"].includes(format)) {
      res.status(400).json({ error: "Invalid format" });
      return;
    }

    const jobDir = path.join(OUTPUT_DIR, jobId);
    const statusFile = path.join(jobDir, "status.json");

    if (!fs.existsSync(statusFile)) {
      res.status(404).json({ error: "Job not found" });
      return;
    }

    const status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));

    const files = fs.readdirSync(jobDir);
    const matchingFile = files.find((f) => f.endsWith(`.${format}`));

    if (!matchingFile) {
      res.status(404).json({ error: `No ${format} file found` });
      return;
    }

    const filePath = path.join(jobDir, matchingFile);
    const contentTypes: Record<string, string> = {
      epub: "application/epub+zip",
      pdf: "application/pdf",
      html: "text/html",
    };

    const bookTitle = status.title || matchingFile;
    res.setHeader("Content-Type", contentTypes[format]);
    res.setHeader(
      "Content-Disposition",
      `attachment; filename="${bookTitle}.${format}"`,
    );
    res.sendFile(filePath);
  },
);

export default router;
