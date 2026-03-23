# TextBoox

An AI-powered textbook generator. Enter any Finance topic and TextBoox will write a full, professionally structured textbook and export it as HTML, PDF, and EPUB.

Live at [textboox.org](https://textboox.org)

---

## How it works

1. Enter a Finance topic (e.g. "Corporate Finance", "Behavioural Finance")
2. The AI generates a concept — title, description, and chapter outline
3. Review the concept and optionally enter your email address
4. TextBoox writes each chapter using Google Gemini and assembles the book
5. Download as **HTML**, **PDF**, or **EPUB** — or receive a download link by email when it's done

Generation runs as a background job, so you can close the tab and come back (or get emailed) when it's ready. A job queue limits concurrent generations to 3 at a time.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite + Tailwind CSS |
| Backend | Node.js + Express 5 |
| AI | Google Gemini (`gemini-3-flash-preview`) via `google-genai` |
| PDF export | WeasyPrint (Python) |
| EPUB export | ebooklib (Python) |
| Email notifications | Resend |
| Database | PostgreSQL + Drizzle ORM |
| Monorepo | pnpm workspaces |
| API codegen | Orval (OpenAPI → React Query hooks + Zod schemas) |

---

## Project structure

```
textboox/
├── artifacts/
│   ├── api-server/          # Express API + Python generation scripts
│   │   ├── src/routes/      # API routes (textbook, admin, health)
│   │   ├── src/python/      # Book generation, EPUB/PDF export
│   │   └── output/          # Generated job files (gitignored)
│   └── textbook-generator/  # React frontend
│       ├── src/pages/       # Home, Admin
│       └── src/components/  # BookCover, GenerationProgress, BookLibrary, etc.
├── lib/
│   ├── api-spec/            # openapi.yaml + Orval config
│   ├── api-client-react/    # Generated React Query hooks
│   ├── api-zod/             # Generated Zod schemas
│   └── db/                  # Drizzle ORM schema + DB client
└── requirements.txt         # Python dependencies
```

---

## Running locally

### Prerequisites

- Node.js 20+
- pnpm (`npm install -g pnpm`)
- Python 3.11+
- PostgreSQL database

### 1. Clone and install

```bash
git clone https://github.com/garethfcampbell/textboox.git
cd textboox
pnpm install
pip install -r requirements.txt
```

### 2. Set environment variables

Create a `.env` file in `artifacts/api-server/` (or export these in your shell):

```env
DATABASE_URL=postgresql://user:password@localhost:5432/textboox
GEMINI_API_KEY=your_google_gemini_api_key
RESEND_API_KEY=your_resend_api_key        # optional — only needed for email notifications
```

**Getting API keys:**
- **Gemini** — [Google AI Studio](https://aistudio.google.com/app/apikey) (free tier available)
- **Resend** — [resend.com](https://resend.com) (free tier: 3,000 emails/month)

### 3. Set up the database

```bash
pnpm --filter @workspace/db run push
```

### 4. Start the servers

In two separate terminals:

```bash
# API server
pnpm --filter @workspace/api-server run dev

# Frontend
pnpm --filter @workspace/textbook-generator run dev
```

The frontend will be available at `http://localhost:5173` and the API at `http://localhost:8080`.

---

## Regenerating API types

If you modify `lib/api-spec/openapi.yaml`, regenerate the React Query hooks and Zod schemas:

```bash
cd lib/api-spec && npx orval
```

---

## Email notifications

When a user provides their email before starting generation, Resend sends them a link to download all formats (HTML, PDF, EPUB) once the job completes. Emails are sent from `notifications@textboox.org` — update the `from` address in `artifacts/api-server/src/routes/textbook.ts` to match your verified Resend domain.

---

## Inspired by

[Infinite Bookshelf](https://github.com/Bklieger/infinite-bookshelf) by Benjamin Klieger
