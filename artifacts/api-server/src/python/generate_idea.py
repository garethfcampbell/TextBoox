import os
import json

from dotenv import load_dotenv

load_dotenv()


IDEA_PROMPT = """Based on "{keyword}", generate ONE overview of a book.

Create only ONE book, do not create one book per theme.
1. Provide a detailed description of what should be included in the book, with suggestions about areas to examine
2. Suggest ONE compelling book title. The main title should be less than four words, and a subtitle of less than six words, in the format "Title: Subtitle"
3. Suggest an appropriate filename for the book (without spaces, using hyphens)

Format your response as JSON with this structure:
[
  {{
    "topic": "Topic Name",
    "description": "Description of topic",
    "title": "Title: Subtitle",
    "filename": "suggested-filename-1"
  }}
]"""


def call_gemini_api(keyword: str) -> str | None:
    """
    Generate a book idea for the given keyword.
    Returns a JSON string on success, None on failure.
    Uses Gemini with exponential backoff retries and falls back to OpenAI.
    """
    from ai_client import generate_text

    prompt = IDEA_PROMPT.format(keyword=keyword)
    try:
        return generate_text(prompt, json_mode=True, use_thinking=True)
    except Exception as exc:
        print(f"[generate_idea] Failed to generate idea: {exc}")
        return None
