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
    import io

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

    # Write initial running status immediately — before any imports that might be slow
    update_status("running", "Loading generation engine...")

    try:
        import contextlib as _ctx
        import io as _io

        # Suppress all verbose print/logging output from book_creation
        # (it prints entire chapter content to stdout which is piped to log file anyway)
        with _ctx.redirect_stdout(_io.StringIO()), _ctx.redirect_stderr(_io.StringIO()):
            from book_creation import BookGenerator, EPUBConverter

        update_status("running", "Generating book structure...", total_chapters=10)

        generator = BookGenerator(topic=topic, output_filename=filename)
        generator.book_title = title
        generator.save_dir = output_dir
        generator.base_save_dir = output_dir

        structure_json = generator.retry_with_backoff(
            generator.generate_book_structure,
            generator.client,
            topic
        )
        generator.book_structure = json.loads(structure_json)
        total = len(generator.book_structure)

        update_status("running", "Generating chapters...", total_chapters=total, completed_chapters=0)

        for i, (chapter_title, sections) in enumerate(generator.book_structure.items()):
            update_status("running", f"Writing chapter {i+1} of {total}...",
                          current_chapter=chapter_title, total_chapters=total, completed_chapters=i)
            try:
                chapter_content = generator.retry_with_backoff(
                    generator.generate_chapter,
                    generator.client,
                    chapter_title,
                    sections
                )
                generator.book_content[chapter_title] = chapter_content
                generator.all_previous_sections.append(chapter_content)
            except Exception as e:
                generator.failed_sections[chapter_title] = str(e)

        update_status("running", "Assembling book files...", total_chapters=total, completed_chapters=total)

        html_content = generator.generate_html()
        generator.generate_pdf(html_content)

        available = []
        base_name = os.path.splitext(filename)[0] if '.' in filename else filename

        for ext in ['html', 'pdf', 'epub']:
            file_path = os.path.join(output_dir, f"{base_name}.{ext}")
            if os.path.exists(file_path):
                available.append(ext)

        update_status("completed", "Book generation complete!", total_chapters=total,
                      completed_chapters=total, available_formats=available)

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
