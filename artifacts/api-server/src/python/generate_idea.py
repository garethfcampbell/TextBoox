import os
import csv
import json

from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Function to call Gemini API with thinking enabled
def call_gemini_api(keyword):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("⚠️ API key not found! Please set your GOOGLE_API_KEY in .env file.")
        return None
        
    # Initialize the Gemini client
    client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})

    # Prepare the prompt - modified to request ONE topic
    prompt = f"""
    Based on "{keyword}", generate ONE overview of a book.

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
      }},
    ]
    """

    try:
        # Call Gemini 3 Flash with thinking enabled
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="high"),
                response_mime_type="application/json"
            )
        )

        # Process the response
        print("Generating topic...")
        # Gemini 3 Flash response is already complete (non-streaming in this simple case, or we can stream)
        # For simplicity, we'll use non-streaming here as the output is short JSON.
        
        response_content = response.text
        print("\nGeneration completed.")
        
        return response_content

    except Exception as e:
        print(f"\nError: {str(e)}")
        return None

# Function to parse JSON response and save to CSV
def parse_and_save_response(response_text, keyword):
    try:
        # Clean the response text to remove Markdown code fences
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:].strip() # Remove the ```json and any whitespace
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3].strip() # Remove the trailing ``` and any whitespace

        # Parse the CLEANED JSON response
        data = json.loads(clean_text) # Use the cleaned text here

        # Convert single topic to a list with one item for consistent processing
        if not isinstance(data, list):
            data = [data]

        # Prepare data for CSV
        csv_data = []
        for topic in data:
            row = {
                "Background": keyword,
                "TopicName": topic["topic"],
                "Description": topic["description"],
                "Topic": f"<Background>{keyword}</Background><Task>{topic['description']}</Task>",
                "Title": topic.get("title", ""),
                "OutputFilename": topic["filename"]
            }
            csv_data.append(row)

        # Create a CSV file
        filename = "book_topics.csv"
        with open(filename, 'w', newline='', encoding='cp1252') as csvfile:
            fieldnames = ['Background', 'TopicName', 'Description', 'Topic', 'Title', 'OutputFilename']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for row in csv_data:
                writer.writerow(row)

        print(f"CSV file saved as {filename}")

        # Display the results
        print(f"Generated topic for {keyword}")

        return filename

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {str(e)}")
        # Print the cleaned text for better debugging
        print("Cleaned text that failed parsing:", clean_text)
        return None
    except Exception as e:
        print(f"Error processing response: {str(e)}")
        return None

def main():
    # Get keyword from user
    # keyword = input("Enter a keyword:")
    keyword = "Asset Pricing Factors"


    print(f"Generating topic for '{keyword}'...")
    response = call_gemini_api(keyword)

    if response:
        parse_and_save_response(response, keyword)
    else:
        print("Failed to generate topic. Please check your API key and try again.")

if __name__ == "__main__":
    main()
