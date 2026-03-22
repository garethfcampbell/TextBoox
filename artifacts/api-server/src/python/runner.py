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
                      available_formats=None, error: str = "", progress_percent: int = 0):
        data = {
            "jobId": job_id,
            "title": title,
            "status": status,
            "progress": progress,
            "currentChapter": current_chapter,
            "totalChapters": total_chapters,
            "completedChapters": completed_chapters,
            "progressPercent": progress_percent,
            "availableFormats": available_formats or [],
            "error": error
        }
        with open(status_file, 'w') as f:
            json.dump(data, f)

    update_status("running", "Textbook Creation in Progress (will take a few minutes)", progress_percent=5)

    try:
        from google import genai
        from google.genai import types as genai_types

        api_key = os.environ.get("GOOGLE_API_KEY", "")
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

        # ── Phase 1: generate chapter structure ──────────────────────────────────
        # Matches book_creation.py format: nested dict {chapter: {section: desc}}
        update_status("running", "Generating chapter structure...", total_chapters=10, progress_percent=10)

        resp = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=f"""
TASK
You are structuring an academic textbook.

OUTPUT FORMAT
Output ONLY valid JSON with no additional text. Do NOT begin with ```json or close with ```.

{{
    "Title of Chapter 1": {{
        "Title of Section 1": "Description of what to include",
        "Title of Section 2": "Description of what to include",
        "Title of Section 3": "Description of what to include",
        "Title of Section 4": "Description of what to include"
    }},
    "Title of Chapter 2": {{
        "Title of Section 1": "Description of what to include",
        "Title of Section 2": "Description of what to include",
        "Title of Section 3": "Description of what to include",
        "Title of Section 4": "Description of what to include"
    }}
}}

PROMPT
Write a comprehensive structure in JSON format for a book titled "{title}" about:

{topic}

Include 10 chapters, each with 5 sections. Chapter titles must be descriptive and thematic — do NOT use "Chapter 1", "Chapter 2" etc. The final chapter should be a concluding discussion about the key aspects covered in the book.
""",
            config=genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(thinking_level="high"),
                response_mime_type="application/json"
            )
        )

        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        structure = json.loads(raw)
        total = len(structure)

        # Build full book structure string for context (matches book_creation.py)
        def format_structure(struct):
            out = ""
            for ch_title, sections in struct.items():
                out += f"  Chapter: {ch_title}\n"
                if isinstance(sections, dict):
                    for sec_title, sec_desc in sections.items():
                        out += f"    Section: {sec_title}: {sec_desc}\n"
            return out

        book_structure_text = format_structure(structure)

        # ── Phase 2: generate full content for each chapter ───────────────────
        # Asks AI for raw HTML output with summary boxes — matches book_creation.py
        chapter_contents: dict = {}
        previous_chapters: list = []

        for i, (chapter_title, sections) in enumerate(structure.items(), 1):
            ch_pct = int(15 + (i - 1) / max(1, total) * 75)
            update_status(
                "running",
                f"Writing chapter {i} of {total}...",
                current_chapter=chapter_title,
                total_chapters=total,
                completed_chapters=i - 1,
                progress_percent=ch_pct,
            )

            prev_context = ""
            if previous_chapters:
                prev_context = "CONTENT OF ALL PREVIOUS CHAPTERS:\n"
                for j, prev in enumerate(previous_chapters, 1):
                    prev_context += f"\n=== CHAPTER {j} ===\n{prev[:800]}...\n"

            section_lines = ""
            if isinstance(sections, dict):
                for sec_title, sec_desc in sections.items():
                    section_lines += f"- {sec_title}: {sec_desc}\n"
            else:
                for sec in sections:
                    section_lines += f"- {sec}\n"

            chapter_prompt = f"""
CONTEXT
You are writing an academic textbook.
Book title: {title}
Overall topic: {topic}

{prev_context}

COMPLETE BOOK STRUCTURE:
{book_structure_text}

TO BE COMPLETED NOW:
Chapter: {chapter_title}
Sections to include:
{section_lines}

TASK
Write a detailed, engaging, and comprehensive essay explanation suitable for an academic textbook for the current chapter. Maintain academic rigor while keeping the content accessible and engaging.

WRITING STYLE
The text MUST have a medium difficulty Flesch readability score.
1. Use clear, straightforward vocabulary accessible to a general audience.
2. Maintain a professional and informative tone while avoiding unnecessarily complex terminology.
3. Break down complex concepts into understandable components with concrete examples.
4. Write about 7-10 paragraphs for each section. Use moderately-sized paragraphs (4-6 sentences) that each develop a single main idea.
5. Include practical applications and real-world examples but do NOT mention specific people or companies.
6. Structure information logically, building from foundational concepts to more advanced applications.
7. Maintain formal sentence structure but prefer active voice. Do NOT use contractions.
8. When introducing specialized terms, immediately provide clear definitions.
9. Use comparison and contrast to highlight key differences between related concepts.

FORMATTING — output raw HTML only, no markdown:
- Do NOT use <h1> (it will be added manually)
- <h2> for each section title within the chapter
- <h3> for the Summary subheading inside each summary box
- <p> for paragraphs; <p class="first"> for the first paragraph of each section
- <ul> and <li> for bullet lists
- <div class="box"> for the summary box at the end of each section
- No bare text outside of tags. No markdown. No code fences.
- Do NOT quote specific statistics or percentages.
- Do NOT use hyperbole on the first line (fascinating, crucial, transform, revolutionize).

Each section must end with a summary box:
<div class="box">
    <h3>Summary</h3>
    <ul>
        <li>Concise bullet point of 8-12 words.</li>
        <li>Concise bullet point of 8-12 words.</li>
        <li>Concise bullet point of 8-12 words.</li>
        <li>Concise bullet point of 8-12 words.</li>
    </ul>
</div>
"""

            ch_resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=chapter_prompt,
                config=genai_types.GenerateContentConfig(temperature=0.8)
            )

            content = ch_resp.text.strip()
            # Strip any accidental markdown fences
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            chapter_contents[chapter_title] = content
            previous_chapters.append(content)

        # ── Assemble HTML ─────────────────────────────────────────────────────
        update_status("running", "Assembling HTML book...",
                      total_chapters=total, completed_chapters=total, progress_percent=92)

        base_name = os.path.splitext(filename)[0] if "." in filename else filename
        html_path = os.path.join(output_dir, f"{base_name}.html")

        toc_items = ""
        for i, ch in enumerate(structure.keys(), 1):
            toc_items += f'<li><a href="#chapter-{i}">{ch}</a></li>\n'

        chapter_html = ""
        for i, (ch, content) in enumerate(chapter_contents.items(), 1):
            chapter_html += (
                f'<section id="chapter-{i}" class="chapter">\n'
                f'<h2 class="chapter-title">{ch}</h2>\n'
                f'<div class="book">{content}</div>\n'
                f'</section>\n<hr>\n'
            )

        html = f"""<!DOCTYPE html>
<html class="book-mode" lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: "Liberation Serif", Georgia, "Times New Roman", serif; font-size: 11.5pt; line-height: 1.6; text-align: justify; max-width: 860px; margin: 40px auto; padding: 0 24px; color: #1a1a1a; letter-spacing: 0.01em; hyphens: auto; }}
  h1.book-title {{ font-size: 2.2rem; font-weight: 300; text-align: center; border-bottom: 1pt solid #1a1a1a; padding-bottom: 0.5em; margin-bottom: 0.3em; letter-spacing: 0.05em; text-transform: uppercase; color: #1a1a1a; }}
  p.subtitle {{ font-size: 1.1rem; text-align: center; color: #555; font-style: italic; margin-top: 0.3em; }}
  h2.chapter-title {{ font-size: 1.7rem; font-weight: 500; margin-top: 60px; margin-bottom: 4px; color: #1a1a2e; border-left: 5px solid #2c3e50; padding-left: 14px; letter-spacing: 0.03em; }}
  .book h2 {{ font-size: 1.3rem; font-weight: 500; margin-top: 40px; color: #2c3e50; border-bottom: 1px solid #e0e0e0; padding-bottom: 4px; letter-spacing: 0.02em; }}
  .book h3 {{ font-size: 1.05rem; font-weight: 500; margin-top: 20px; color: #34495e; }}
  p {{ margin: 0.5em 0; text-indent: 1.5em; hyphens: auto; }}
  h1 + p, h2 + p, h3 + p, p.first {{ text-indent: 0; }}
  nav {{ background: #f5f5f5; border: 1px solid #ddd; padding: 16px 24px; margin: 24px 0; border-radius: 6px; }}
  nav h2 {{ font-size: 1.05rem; margin: 0 0 10px 0; border: none; padding: 0; color: #333; }}
  nav ol {{ margin: 0; padding-left: 20px; }}
  nav li {{ margin: 5px 0; }}
  nav a {{ color: #2c3e50; text-decoration: none; }}
  nav a:hover {{ text-decoration: underline; }}
  .box {{ background-color: #f8f9fa; padding: 1.2rem; margin: 1rem 0; border: 1px solid #e5e5e5; border-left: 3px solid #2c3e50; }}
  .box h3 {{ margin-top: 0; margin-bottom: 0.8rem; font-size: 1rem; color: #2c3e50; }}
  .box > *:last-child {{ margin-bottom: 0; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 48px 0; }}
  ul, ol {{ margin: 0.8rem 0; padding-left: 1.5rem; }}
  li {{ margin-bottom: 0.4rem; text-align: justify; line-height: 1.4; }}
  blockquote {{ margin: 2em 3em; padding-left: 1em; border-left: 3pt solid #2c3e50; font-style: italic; color: #34495e; line-height: 1.6; }}
  table {{ width: 100%; margin: 1.5em 0; border-collapse: collapse; }}
  th {{ background-color: #f8f9fa; border-bottom: 2pt solid #2c3e50; padding: 0.8em; font-weight: 600; color: #2c3e50; }}
  td {{ padding: 0.8em; border: 1pt solid #e5e5e5; vertical-align: top; }}
</style>
</head>
<body>
<h1 class="book-title">{title}</h1>
<p class="subtitle">{topic}</p>
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
                      total_chapters=total, completed_chapters=total, progress_percent=95)

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
body { font-family: Georgia, serif; line-height: 1.7; margin: 5%; }
h1 { font-size: 1.6em; border-bottom: 2px solid #333; padding-bottom: 8px; }
h2 { font-size: 1.3em; margin-top: 1.8em; color: #34495e; border-bottom: 1px solid #ddd; padding-bottom: 3px; }
h3 { font-size: 1.05em; margin-top: 1.2em; color: #333; }
p  { margin: 0.7em 0; text-align: justify; }
p.first { margin-top: 0; }
.box { background: #f8f9fa; border-left: 3px solid #4a90d9; padding: 10px 14px; margin: 14px 0; }
.box h3 { margin: 0 0 6px 0; font-size: 1em; color: #2c3e50; }
.box ul { margin: 0; padding-left: 16px; }
.box li { margin: 3px 0; }
ul, ol { padding-left: 20px; }
li { margin: 3px 0; }
""",
            )
            book.add_item(css)

            spine = ["nav"]
            toc_entries = []

            for i, (ch, content) in enumerate(chapter_contents.items(), 1):
                ch_html = (
                    '<?xml version="1.0" encoding="utf-8"?>'
                    '<!DOCTYPE html>'
                    '<html xmlns="http://www.w3.org/1999/xhtml">'
                    f'<head><title>{ch}</title>'
                    '<link rel="stylesheet" type="text/css" href="../style/main.css"/>'
                    '</head><body>'
                    f'<h1>{ch}</h1>'
                    f'<div class="book">{content}</div>'
                    '</body></html>'
                )

                item = epub.EpubHtml(
                    title=ch,
                    file_name=f"chapter_{i:02d}.xhtml",
                    lang="en",
                )
                item.content = ch_html.encode("utf-8")
                item.add_item(css)
                book.add_item(item)
                spine.append(item)
                toc_entries.append(epub.Link(f"chapter_{i:02d}.xhtml", ch, f"ch{i}"))

            book.toc = toc_entries
            book.add_item(epub.EpubNcx())
            nav = epub.EpubNav()
            nav.add_item(css)
            book.add_item(nav)
            book.spine = spine

            epub.write_epub(epub_path, book)
        except Exception as epub_err:
            print(f"EPUB generation failed (non-fatal): {epub_err}")
            epub_path = None

        # ── Phase 4: PDF export ───────────────────────────────────────────────
        update_status("running", "Building PDF...",
                      total_chapters=total, completed_chapters=total, progress_percent=97)

        pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
        try:
            from weasyprint import HTML as WeasyHTML, CSS

            pdf_chapter_html = ""
            for i, (ch, content) in enumerate(chapter_contents.items(), 1):
                pdf_chapter_html += f"<h1>{ch}</h1>\n<div class=\"book\">{content}</div>\n"

            pdf_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body {{
  font-family: "Liberation Serif", Georgia, "Times New Roman", serif;
  font-size: 11.5pt;
  line-height: 1.4;
  text-align: justify;
  color: #1a1a1a;
  letter-spacing: 0.01em;
}}
h1 {{
  string-set: chapter-title content();
  font-family: "Liberation Serif", Georgia, serif;
  font-size: 24pt;
  font-weight: 300;
  text-align: center;
  margin-top: 2in;
  margin-bottom: 2em;
  page-break-before: always;
  page-break-after: avoid;
  color: #1a1a1a;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  border-bottom: 1pt solid #1a1a1a;
  padding-bottom: 0.5em;
}}
.title-page h1 {{
  font-size: 36pt;
  font-weight: bold;
  page-break-before: avoid;
  margin-top: 0;
  border: none;
  text-transform: none;
}}
h2 {{
  font-family: "Liberation Serif", Georgia, serif;
  font-size: 16pt;
  font-weight: 500;
  text-align: left;
  margin: 1.5rem 0 1rem;
  page-break-after: avoid;
  color: #2c3e50;
  letter-spacing: 0.03em;
}}
h3 {{
  font-family: "Liberation Serif", Georgia, serif;
  font-size: 14pt;
  font-weight: 500;
  text-align: left;
  margin: 1.2rem 0 0.8rem;
  page-break-after: avoid;
  color: #34495e;
  letter-spacing: 0.02em;
}}
p {{
  text-align: justify;
  text-indent: 1.5em;
  margin: 0.5rem 0;
}}
h1 + p, h2 + p, h3 + p, p.first {{
  text-indent: 0;
}}
ul {{
  margin: 0.8rem 0;
  padding-left: 1.5rem;
}}
li {{
  margin-bottom: 0.4rem;
  text-align: justify;
  line-height: 1.4;
}}
.box {{
  background-color: #f8f9fa;
  padding: 1.2rem;
  margin: 1rem 0;
  border: 1pt solid #e5e5e5;
  border-left: 3pt solid #2c3e50;
  break-inside: avoid;
}}
.box h3 {{
  margin-top: 0;
  margin-bottom: 0.8rem;
  font-size: 12pt;
  color: #2c3e50;
}}
blockquote {{
  margin: 2em 3em;
  padding-left: 1em;
  border-left: 3pt solid #2c3e50;
  font-style: italic;
  color: #34495e;
  line-height: 1.6;
}}
table {{
  width: 100%;
  margin: 1.5em 0;
  border-collapse: collapse;
  break-inside: avoid;
}}
th {{
  background-color: #f8f9fa;
  border-bottom: 2pt solid #2c3e50;
  padding: 0.8em;
  font-weight: 600;
  color: #2c3e50;
}}
td {{
  padding: 0.8em;
  border: 1pt solid #e5e5e5;
  vertical-align: top;
}}
.title-page {{
  text-align: center;
  padding-top: 80mm;
}}
.subtitle {{
  font-size: 16pt;
  text-align: center;
  color: #555;
  margin-top: 4mm;
  font-style: italic;
}}
</style>
</head>
<body>
<div class="title-page">
  <h1>{title}</h1>
  <p class="subtitle">{topic}</p>
</div>
{pdf_chapter_html}
</body>
</html>"""

            page_css = CSS(string="""
@page {
  size: 210mm 297mm;
  margin: 38mm 32mm;
}
@page:not(:first) {
  @top-center {
    content: string(chapter-title, first);
    font-family: "Liberation Serif", Georgia, serif;
    font-size: 9pt;
    font-style: italic;
    color: #333333;
    padding-bottom: 0.3em;
  }
  @bottom-center {
    content: counter(page);
    font-family: "Liberation Serif", Georgia, serif;
    font-size: 9pt;
    color: #666666;
    margin-top: 0.3em;
    border-top: 0.5pt solid #cccccc;
    padding-top: 0.3em;
  }
}
""")

            WeasyHTML(string=pdf_html).write_pdf(pdf_path, stylesheets=[page_css])
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
                      available_formats=available, progress_percent=100)

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
