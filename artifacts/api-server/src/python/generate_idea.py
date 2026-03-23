import os
import json

from dotenv import load_dotenv

load_dotenv()


_IDEA_PROMPT_TEMPLATE = (
    'Based on "{keyword}", generate ONE overview of a book.\n\n'
    "Create only ONE book, do not create one book per theme.\n"
    "1. Provide a detailed description of what should be included in the book, with suggestions about areas to examine\n"
    "2. Suggest ONE compelling book title. The main title should be less than four words, and a subtitle of less than six words, in the format \"Title: Subtitle\"\n"
    "3. Suggest an appropriate filename for the book (without spaces, using hyphens)\n\n"
    "Format your response as JSON with this structure:\n"
    "[\n"
    "  {{\n"
    '    "topic": "Topic Name",\n'
    '    "description": "Description of topic",\n'
    '    "title": "Title: Subtitle",\n'
    '    "filename": "suggested-filename-1"\n'
    "  }}\n"
    "]"
)


def call_gemini_api(keyword: str) -> str | None:
    """
    Generate a book idea for the given keyword.
    Returns a JSON string on success, None on failure.
    Uses Gemini with exponential backoff retries and falls back to OpenAI.
    """
    from ai_client import generate_text

    # Use str.replace instead of .format() so curly braces in the keyword
    # cannot accidentally be interpreted as format specifiers.
    prompt = _IDEA_PROMPT_TEMPLATE.replace("{keyword}", keyword)
    try:
        return generate_text(prompt, json_mode=True, use_thinking=True)
    except Exception as exc:
        print(f"[generate_idea] Failed to generate idea: {exc}")
        return None
