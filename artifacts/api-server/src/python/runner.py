"""
Wrapper script called by the Express API server to run book generation.
Usage:
  python runner.py generate-idea <keyword>
  python runner.py generate-book <job_id> <topic> <title> <filename> <absolute_output_dir>
"""

import sys
import os
import json
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_generate_idea(keyword: str):
    import contextlib
    import io as _io

    # Suppress all print/stderr output from the underlying library calls
    with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(_io.StringIO()):
        from generate_idea import call_gemini_api
        response = call_gemini_api(keyword)

    if not response:
        sys.stdout.write(json.dumps({"error": "Failed to generate idea"}) + "\n")
        sys.exit(1)

    clean = response.strip()
    if clean.startswith("```json"):
        clean = clean[7:].strip()
    if clean.endswith("```"):
        clean = clean[:-3].strip()

    data = json.loads(clean)
    if not isinstance(data, list):
        data = [data]

    topic = data[0]
    result = {
        "topic": topic.get("topic", keyword),
        "description": topic.get("description", ""),
        "title": topic.get("title", keyword),
        "filename": topic.get("filename", keyword.lower().replace(" ", "-"))
    }
    sys.stdout.write(json.dumps(result) + "\n")


def run_generate_book(job_id: str, topic: str, title: str, filename: str, output_dir: str):
    # ── PHASE 1: chapter structure only (book_creation.py fully commented out) ──
    # Once this works in production we will add chapter content, EPUB, PDF back.

    os.makedirs(output_dir, exist_ok=True)
    status_file = os.path.join(output_dir, "status.json")

    def update_status(status: str, progress: str = "", current_chapter: str = "",
                      total_chapters: int = 0, completed_chapters: int = 0,
                      available_formats=None, error: str = ""):
        data = {
            "jobId": job_id,
            "status": status,
            "progress": progress,
            "currentChapter": current_chapter,
            "totalChapters": total_chapters,
            "completedChapters": completed_chapters,
            "availableFormats": available_formats or [],
            "error": error
        }
        with open(status_file, 'w') as f:
            json.dump(data, f)

    update_status("running", "Step 1: importing google.genai...")

    try:
        from google import genai
        update_status("running", "Step 2: importing genai types...")
        from google.genai import types as genai_types

        update_status("running", "Step 3: reading API key...")
        api_key = os.environ.get("GOOGLE_API_KEY", "")

        update_status("running", "Step 4: creating AI client...")
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

        # ── Phase 1: generate chapter structure ──────────────────────────────────
        update_status("running", "Generating chapter structure...", total_chapters=10)

        structure_prompt = (
            f"Create a table of contents for an academic textbook titled '{title}' on the topic: {topic}.\n"
            "Return ONLY a JSON object where each key is a chapter title (exactly 10 chapters) "
            "and each value is a list of 3-5 section titles for that chapter.\n"
            "Example format: {\"Chapter 1: Introduction\": [\"Section 1.1\", \"Section 1.2\"], ...}\n"
            "Return only valid JSON, no markdown fences."
        )

        resp = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=structure_prompt,
            config=genai_types.GenerateContentConfig(temperature=0.7)
        )

        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        structure = json.loads(raw)
        total = len(structure)

        # ── Phase 2: generate full content for each chapter ───────────────────
        chapter_contents: dict = {}
        previous_summaries: list = []

        for i, (chapter_title, sections) in enumerate(structure.items(), 1):
            update_status(
                "running",
                f"Writing chapter {i} of {total}...",
                current_chapter=chapter_title,
                total_chapters=total,
                completed_chapters=i - 1,
            )

            context = ""
            if previous_summaries:
                context = "Previously covered:\n" + "\n".join(previous_summaries[-3:]) + "\n\n"

            section_list = "\n".join(f"  - {s}" for s in sections)
            chapter_prompt = (
                f"{context}"
                f"Write a detailed academic textbook chapter for the book '{title}' (topic: {topic}).\n\n"
                f"Chapter title: {chapter_title}\n"
                f"Sections to cover:\n{section_list}\n\n"
                "Write thorough, graduate-level prose for each section. "
                "Use clear headings for each section. "
                "Each section should be at least 4-6 substantial paragraphs. "
                "Do not use markdown fences. Use plain text with section headings on their own lines."
            )

            ch_resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=chapter_prompt,
                config=genai_types.GenerateContentConfig(temperature=0.8)
            )

            content = ch_resp.text.strip()
            chapter_contents[chapter_title] = content
            previous_summaries.append(f"Chapter {i}: {chapter_title}")

        # ── Assemble HTML ─────────────────────────────────────────────────────
        update_status("running", "Assembling HTML book...",
                      total_chapters=total, completed_chapters=total)

        base_name = os.path.splitext(filename)[0] if "." in filename else filename
        html_path = os.path.join(output_dir, f"{base_name}.html")

        toc_items = ""
        for i, ch in enumerate(structure.keys(), 1):
            anchor = f"chapter-{i}"
            toc_items += f'<li><a href="#{anchor}">{ch}</a></li>\n'

        chapter_html = ""
        for i, (ch, content) in enumerate(chapter_contents.items(), 1):
            anchor = f"chapter-{i}"
            # Convert plain-text section headings to <h3>
            lines = content.split("\n")
            formatted = []
            for line in lines:
                stripped = line.strip()
                if stripped and len(stripped) < 100 and not stripped.endswith(".") and stripped == stripped.strip():
                    # Heuristic: short lines without ending punctuation are likely headings
                    formatted.append(f"<h3>{stripped}</h3>")
                elif stripped:
                    formatted.append(f"<p>{stripped}</p>")
                else:
                    formatted.append("<br>")
            chapter_html += (
                f'<section id="{anchor}">\n'
                f"<h2>Chapter {i}: {ch}</h2>\n"
                + "\n".join(formatted)
                + "\n</section>\n<hr>\n"
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 860px; margin: 40px auto; padding: 0 24px; line-height: 1.7; color: #222; }}
  h1 {{ font-size: 2rem; border-bottom: 3px solid #333; padding-bottom: 12px; }}
  h2 {{ font-size: 1.5rem; margin-top: 48px; color: #1a1a2e; border-left: 4px solid #4a90d9; padding-left: 12px; }}
  h3 {{ font-size: 1.15rem; margin-top: 28px; color: #333; }}
  p {{ margin: 0.8em 0; text-align: justify; }}
  nav {{ background: #f5f5f5; border: 1px solid #ddd; padding: 16px 24px; margin: 24px 0; border-radius: 6px; }}
  nav h2 {{ font-size: 1.1rem; margin: 0 0 8px 0; border: none; padding: 0; }}
  nav ol {{ margin: 0; padding-left: 20px; }}
  nav li {{ margin: 4px 0; }}
  nav a {{ color: #4a90d9; text-decoration: none; }}
  nav a:hover {{ text-decoration: underline; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 40px 0; }}
  section {{ margin-bottom: 48px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p><em>{topic}</em></p>
<nav>
  <h2>Table of Contents</h2>
  <ol>{toc_items}</ol>
</nav>
{chapter_html}
</body>
</html>"""

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # ── Phase 3: EPUB export ──────────────────────────────────────────────
        update_status("running", "Building EPUB...",
                      total_chapters=total, completed_chapters=total)

        epub_path = os.path.join(output_dir, f"{base_name}.epub")
        try:
            from ebooklib import epub

            book = epub.EpubBook()
            book.set_identifier(job_id)
            book.set_title(title)
            book.set_language("en")

            css = epub.EpubItem(
                uid="style",
                file_name="style/main.css",
                media_type="text/css",
                content=b"""
body { font-family: Georgia, serif; line-height: 1.7; margin: 20px; }
h1 { font-size: 1.8em; border-bottom: 2px solid #333; padding-bottom: 8px; }
h2 { font-size: 1.4em; margin-top: 2em; color: #1a1a2e; }
h3 { font-size: 1.1em; margin-top: 1.4em; }
p  { margin: 0.7em 0; text-align: justify; }
""",
            )
            book.add_item(css)

            spine = ["nav"]
            toc_entries = []

            for i, (ch, content) in enumerate(chapter_contents.items(), 1):
                lines = content.split("\n")
                body_parts = []
                for line in lines:
                    s = line.strip()
                    if s and len(s) < 100 and not s.endswith("."):
                        body_parts.append(f"<h3>{s}</h3>")
                    elif s:
                        body_parts.append(f"<p>{s}</p>")

                ch_html = (
                    f'<?xml version="1.0" encoding="utf-8"?>'
                    f'<!DOCTYPE html>'
                    f'<html xmlns="http://www.w3.org/1999/xhtml">'
                    f'<head><title>{ch}</title>'
                    f'<link rel="stylesheet" type="text/css" href="../style/main.css"/>'
                    f'</head><body>'
                    f'<h2>Chapter {i}: {ch}</h2>'
                    + "".join(body_parts)
                    + "</body></html>"
                )

                item = epub.EpubHtml(
                    title=f"Chapter {i}: {ch}",
                    file_name=f"chapter_{i:02d}.xhtml",
                    lang="en",
                )
                item.content = ch_html.encode("utf-8")
                item.add_item(css)
                book.add_item(item)
                spine.append(item)
                toc_entries.append(epub.Link(f"chapter_{i:02d}.xhtml", f"Chapter {i}: {ch}", f"ch{i}"))

            book.toc = toc_entries
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = spine

            epub.write_epub(epub_path, book)
        except Exception as epub_err:
            print(f"EPUB generation failed (non-fatal): {epub_err}")
            epub_path = None

        # ── Phase 4: PDF export ───────────────────────────────────────────────
        update_status("running", "Building PDF...",
                      total_chapters=total, completed_chapters=total)

        pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
        try:
            from xhtml2pdf import pisa

            # xhtml2pdf works best with simpler CSS — strip unsupported properties
            pdf_html = html.replace("text-align: justify;", "")

            with open(pdf_path, "wb") as pdf_file:
                result = pisa.CreatePDF(pdf_html, dest=pdf_file)

            if result.err:
                print(f"PDF conversion errors: {result.err}")
                pdf_path = None
        except Exception as pdf_err:
            print(f"PDF generation failed (non-fatal): {pdf_err}")
            pdf_path = None

        available = ["html"]
        if epub_path and os.path.exists(epub_path):
            available.append("epub")
        if pdf_path and os.path.exists(pdf_path):
            available.append("pdf")

        update_status("completed", "Book generation complete!",
                      total_chapters=total, completed_chapters=total,
                      available_formats=available)

    except Exception as e:
        tb = traceback.format_exc()
        update_status("failed", error=f"{str(e)}\n\n{tb}")
        sys.exit(1)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""

    if command == "generate-idea":
        keyword = sys.argv[2] if len(sys.argv) > 2 else ""
        run_generate_idea(keyword)
    elif command == "generate-book":
        if len(sys.argv) < 7:
            print(json.dumps({"error": "generate-book requires: job_id topic title filename output_dir"}))
            sys.exit(1)
        job_id = sys.argv[2]
        topic = sys.argv[3]
        title = sys.argv[4]
        filename = sys.argv[5]
        output_dir = sys.argv[6]
        run_generate_book(job_id, topic, title, filename, output_dir)
    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))
        sys.exit(1)
