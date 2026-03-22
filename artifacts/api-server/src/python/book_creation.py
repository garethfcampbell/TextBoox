import os
import csv
import json
import time
import logging
import argparse
import re
import io
from typing import Optional, List, Dict
from dataclasses import dataclass
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from ebooklib import epub
from google import genai
from google.genai import types



# Configure logging
logging.basicConfig(level=logging.DEBUG)



# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Apply nest_asyncio






# ==================================================================================
# TASK 1 - TEXTBOOK
# ==================================================================================


@dataclass
class Chapter:
    """Represents a chapter in the EPUB book."""
    title: str
    content: str
    file_name: str
    subheadings: List[Dict[str, str]]
    has_hidden_h2: bool = False



class EPUBConverter:
    """Handles conversion of HTML files to EPUB format with proper TOC support."""

    def __init__(self, html_content: str, output_filename: str = "output.epub", title: str = None):
        self.html_content = html_content
        self.output_filename = output_filename
        self.title = title
        self.book = epub.EpubBook()
        self.chapters: List[Chapter] = []
        self.soup: Optional[BeautifulSoup] = None

    def parse_html(self) -> bool:
        try:
            self.soup = BeautifulSoup(self.html_content, 'html.parser')
            return True
        except Exception as e:
            logger.error(f"Error parsing HTML: {str(e)}")
            return False

    def process_chapters(self) -> None:
        if not self.soup:
            return

        body = self.soup.body if self.soup.body else self.soup

        # Find all chapter divs
        chapter_divs = body.find_all('div', class_='chapter')

        if chapter_divs:
            # Process each chapter div as a separate chapter
            for chapter_div in chapter_divs:
                h1 = chapter_div.find('h1')
                if not h1:
                    continue  # Skip if no h1 found

                chapter_title = h1.get_text(strip=True)
                subheadings = []
                has_hidden_h2 = False

                # Find the chapter-content div within this chapter div
                chapter_content_div = chapter_div.find('div', class_='chapter-content')
                if not chapter_content_div:
                    # If no chapter-content div, use the chapter div itself (excluding h1)
                    chapter_content_div = chapter_div

                # Create a new soup for this chapter's content only
                chapter_content_html = str(chapter_content_div)
                chapter_soup = BeautifulSoup(chapter_content_html, 'html.parser')

                # Process h2 elements for TOC
                h2_elements = chapter_soup.find_all('h2')
                for i, h2 in enumerate(h2_elements):
                    heading_id = f'section_{i}'
                    h2['id'] = heading_id

                    # Add all h2 elements to subheadings for TOC
                    subheadings.append({
                        'title': h2.get_text(strip=True),
                        'id': heading_id
                    })

                # Add the h1 back to the beginning of the content
                h1_tag = f"<h1>{chapter_title}</h1>"
                content = h1_tag + str(chapter_soup)

                # Use the chapter div content
                file_name = f'text/chapter_{chapter_title.lower().replace(" ", "_").replace(":", "-")}.xhtml'

                self.chapters.append(Chapter(
                    title=chapter_title,
                    content=content,
                    file_name=file_name,
                    subheadings=subheadings,
                    has_hidden_h2=has_hidden_h2
                ))
        else:
            # Fallback to h1 elements if no chapter divs found
            h1_elements = body.find_all('h1')

            # Create a mapping of h1 elements to their positions
            h1_positions = {h1: i for i, h1 in enumerate(h1_elements)}

            for i, h1 in enumerate(h1_elements):
                chapter_title = h1.get_text(strip=True)
                subheadings = []
                has_hidden_h2 = False

                # Create a new soup for this chapter's content
                chapter_soup = BeautifulSoup("<div></div>", 'html.parser')
                chapter_div = chapter_soup.div

                # Add the h1 itself to the chapter content
                new_h1 = chapter_soup.new_tag('h1')
                new_h1.string = chapter_title
                chapter_div.append(new_h1)

                # Get all content until the next h1
                current = h1.next_sibling

                # Track h2 elements for TOC
                h2_counter = 0

                # Continue until we reach the next h1 or run out of siblings
                while current:
                    # If we hit the next chapter heading, stop
                    if current.name == 'h1' and current in h1_positions:
                        break

                    # Clone the current node to avoid modifying the original
                    if hasattr(current, 'name') and current.name:
                        # For element nodes, create a copy
                        new_node = chapter_soup.new_tag(current.name)

                        # Copy attributes
                        for attr, value in current.attrs.items():
                            new_node[attr] = value

                        # Handle h2 elements specially for TOC
                        if current.name == 'h2':
                            heading_id = f'section_{h2_counter}'
                            new_node['id'] = heading_id

                            # Add all h2 elements to subheadings for TOC
                            subheadings.append({
                                'title': current.get_text(strip=True),
                                'id': heading_id
                            })
                            h2_counter += 1

                        # Copy content
                        for child in current.contents:
                            if hasattr(child, 'name'):
                                # Recursively clone element nodes
                                child_copy = chapter_soup.new_tag(child.name)
                                for attr, value in child.attrs.items():
                                    child_copy[attr] = value
                                child_copy.string = child.string
                                new_node.append(child_copy)
                            else:
                                # Text nodes
                                new_node.append(chapter_soup.new_string(str(child)))

                        chapter_div.append(new_node)
                    elif current.string and current.string.strip():
                        # For text nodes with content
                        chapter_div.append(chapter_soup.new_string(str(current)))

                    # Move to next sibling
                    current = current.next_sibling

                file_name = f'text/chapter_{chapter_title.lower().replace(" ", "_").replace(":", "-")}.xhtml'

                self.chapters.append(Chapter(
                    title=chapter_title,
                    content=str(chapter_div),
                    file_name=file_name,
                    subheadings=subheadings,
                    has_hidden_h2=has_hidden_h2
                ))

    def create_epub(self) -> Optional[bytes]:
        try:
            self.book.set_identifier(f'id_{os.path.basename(self.output_filename)}')
            self.book.set_title(self.title)
            self.book.set_language('en')

            epub_chapters = []
            toc_entries = []

            # Create and add CSS
            style = epub.EpubItem(
                uid="style_default",
                file_name="style/default.css",
                media_type="text/css",
                content="""
                    .hidden {
                        display: none;
                    }
                    body {
                        font-family: serif;
                        margin: 5%;
                        text-align: justify;
                    }
                    h1 {
                        text-align: center;
                        font-size: 1.5em;
                        margin: 1em 0;
                    }
                    h2 {
                        font-size: 1.2em;
                        margin: 0.8em 0;
                    }
                    h3 {
                        font-size: 1.1em;
                        margin: 0.6em 0;
                    }
                    .box {
                        background-color: #f8f9fa;
                        padding: 1em;
                        margin: 1em 0;
                        border: 1px solid #e5e5e5;
                        border-left: 3px solid #2c3e50;
                    }
                """
            )
            self.book.add_item(style)

            for idx, chapter in enumerate(self.chapters):
                chapter_id = f'chapter_{idx}'
                epub_chapter = epub.EpubHtml(
                    uid=chapter_id,
                    title=chapter.title,
                    file_name=chapter.file_name
                )
                epub_chapter.content = f"""
                    <html>
                    <head>
                        <title>{chapter.title}</title>
                        <link rel="stylesheet" href="style/default.css" type="text/css" />
                    </head>
                    <body>
                        {chapter.content}
                    </body>
                    </html>
                """
                self.book.add_item(epub_chapter)
                epub_chapters.append(epub_chapter)

                # Add chapter to TOC
                chapter_toc = epub.Link(
                    chapter.file_name,
                    chapter.title,
                    chapter_id
                )

                # Process subheadings
                if chapter.subheadings:
                    subheadings_list = []
                    for subheading in chapter.subheadings:
                        # Create link for subheading
                        sub_link = epub.Link(
                            f"{chapter.file_name}#{subheading['id']}",
                            subheading['title'],
                            f"{chapter_id}_{subheading['id']}"
                        )
                        subheadings_list.append(sub_link)

                    # Add chapter with nested subheadings to TOC
                    toc_entries.append((chapter_toc, subheadings_list))
                else:
                    # Add just the chapter to TOC (no nested items)
                    toc_entries.append(chapter_toc)

            # Create navigation files
            nav = epub.EpubNav()
            nav.add_item(style)  # Apply the same style to nav

            ncx = epub.EpubNcx()

            self.book.add_item(nav)
            self.book.add_item(ncx)

            # Set TOC and spine
            self.book.toc = toc_entries
            self.book.spine = ['nav'] + epub_chapters

            # Add a default cover page
            if self.title:
                cover = epub.EpubHtml(
                    uid='cover',
                    file_name='cover.xhtml',
                    title='Cover'
                )
                cover.content = f'''
                <html>
                <head>
                    <title>Cover</title>
                    <link rel="stylesheet" href="style/default.css" type="text/css" />
                    <style>
                        body {{ text-align: center; padding-top: 20%; }}
                        h1 {{ font-size: 2em; }}
                    </style>
                </head>
                <body>
                    <h1>{self.title}</h1>
                </body>
                </html>
                '''
                self.book.add_item(cover)
                self.book.spine.insert(0, cover)  # Add cover as first item in spine

            # Write to BytesIO object
            epub_buffer = io.BytesIO()
            epub.write_epub(epub_buffer, self.book)
            return epub_buffer.getvalue()

        except Exception as e:
            logger.error(f"Error creating EPUB: {str(e)}")
            return None

    def convert(self) -> Optional[bytes]:
        if not self.parse_html():
            return None

        self.process_chapters()
        return self.create_epub()







class BookGenerator:
    def __init__(self, topic, output_filename):
        self.previous_section_content = None
        
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            # Fallback for development/testing if not explicitly set, though genai.Client checks env too
            print("⚠️ GOOGLE_API_KEY not found in environment variables. Please ensure it is set.")
            
        self.client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
        
        # Get Ideogram API key from environment
        self.ideogram_api_key = os.environ.get("IDEOGRAM_API_KEY")
        self.reset(topic, output_filename)

    def reset(self, topic, output_filename):
        """Reset all instance variables to their initial state"""
        self.topic = topic

        # Set base save directory to the specified path
        self.base_save_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(self.base_save_dir, exist_ok=True)
        self.save_dir = self.base_save_dir
        print(f"Files will be saved to: {self.save_dir}")


        # Ensure output_filename is just the base name, will be joined with save_dir later
        self.output_filename = os.path.basename(output_filename)
        self.book_content = {}
        self.book_title = ""
        self.book_structure = {}
        self._generated_sections = {}  # Track which sections have been generated with chapter context
        self.all_previous_sections = []  # NEW: Track all previous sections
        self.failed_sections = {}  # NEW: Track sections that failed to generate
        self.cover_files = []  # NEW: Track generated cover files


    def generate_book_structure(self, client, prompt: str):
        """Generate book structure using Gemini 3 Flash."""
        # Initialize content buffer
        structure_content = ""

        try:
            # Gemini 3 Flash call
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=f"""
                TASK
                You are structuring an academic textbook.

                OUTPUT FORMAT
                You are a JSON generator. Output ONLY valid JSON, with no additional text, comments, or explanations. You MUST write only in JSON format following this structure, but with the requested number of chapters and scenes. Do NOT begin with ```json, or close with ```.

                {{
                    "Title of Chapter 1": {{
                        "Title of Section 1": "Description of what to include in Chapter 1 Section 1",
                        "Title of Section 2": "Description of what to include in Chapter 1 Section 2",
                        "Title of Section 3": "Description of what to include in Chapter 1 Section 3",
                        "Title of Section 4": "Description of what to include in Chapter 1 Section 4",
                        "Title of Section 5": "Description of what to include in Chapter 1 Section 5"
                    }},
                    "Title of Chapter 2": {{
                        "Title of Section 1": "Description of what to include in Chapter 2 Section 1",
                        "Title of Section 2": "Description of what to include in Chapter 2 Section 2",
                        "Title of Section 3": "Description of what to include in Chapter 2 Section 3",
                        "Title of Section 4": "Description of what to include in Chapter 2 Section 4",
                        "Title of Section 5": "Description of what to include in Chapter 2 Section 5"
                    }}
                }}

                PROMPT
                Write a comprehensive structure in JSON format for a book with the title: "{self.book_title}" about: 

                {self.topic}

                Include 10 chapters, each with 5 sections. The final chapter should be a concluding discussion about the key aspects covered in the book.
                """,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="high"),
                    response_mime_type="application/json" 
                )
            )

            structure_content = response.text
            print(f"Structure generated. Length: {len(structure_content)}")

            if not structure_content:
                raise ValueError("Empty response received from Gemini")

            # Try to parse the JSON to validate it
            try:
                # Gemini with response_mime_type="application/json" usually returns clean JSON, 
                # but sometimes it might wrap it or add text if thinking is involved (though thinking is separate in API usually).
                # The response.text should be the model output.
                json.loads(structure_content)
            except json.JSONDecodeError as e:
                print(f"\nInvalid JSON received: {structure_content}")
                # Try to clean it just in case
                json_match = re.search(r'\{.*\}', structure_content, re.DOTALL)
                if json_match:
                    structure_content = json_match.group(0)
                    json.loads(structure_content) # Verify again
                else:
                    raise ValueError(f"Invalid JSON structure: {str(e)}")

            return structure_content

        except Exception as e:
            print(f"\n❌ Error during structure generation: {str(e)}")
            raise

    def retry_with_backoff(self, func, *args, max_retries=12, initial_delay=10, **kwargs):
        """Retry a function with exponential backoff."""
        delay = initial_delay
        last_exception = None

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                last_exception = e
                time.sleep(delay)
                delay *= 2  # Exponential backoff

        raise last_exception

    def generate_chapter(self, client, chapter_title: str, sections: dict, parent_sections=None):
        """Generate an entire chapter's content using Gemini 3 Flash with all sections as subheadings."""

        # Create context similar to generate_section but for entire chapter
        print(f"\n🔍 Building Context Information for Chapter: {chapter_title}...")

        context = f"""
Book Information:
- TITLE: {self.book_title}
- OVERALL TOPIC: {self.topic}

CONTENT OF ALL PREVIOUS CHAPTERS:
"""

        # Add all accumulated sections
        for i, section in enumerate(self.all_previous_sections, 1):
            context += f"\n=== CHAPTER {i} ===\n{section}\n"

        context += "\n"

        # Add Complete Book Structure
        context += "\nCOMPLETE BOOK STRUCTURE:\n"
        context += self.add_structure(self.book_structure)

        # Add Current Chapter Information and Parent Context
        context += f"\nTO BE COMPLETED NOW:\nChapter: {chapter_title}\n"
        if parent_sections:
            context += f"Parent Sections: {' > '.join(parent_sections)}\n"
        context += "Sections to include:\n"
        for section_title, section_desc in sections.items():
            context += f"- {section_title}: {section_desc}\n"

        print("Context prepared. Generating content with Gemini 3 Flash...")

        prompt = f"""
    CONTEXT
    You are writing an academic textbook: {context}

    TASK
    Write a detailed, engaging, and comprehensive essay explanation suitable for an academic textbook for the current chapter. Remember to maintain academic rigor while keeping the content accessible and engaging.

    WRITING STYLE
    The text MUST have a medium difficulty Flesch readability score.

    Use the following writing style guidelines:
    1. Use clear, straightforward vocabulary accessible to a general audience.
    2. Maintain a professional and informative tone while avoiding unnecessarily complex terminology.
    3. Break down complex concepts into understandable components with concrete examples.
    4. Write about 7-10 paragraphs for each section. Use moderately-sized paragraphs (4-6 sentences) that each develop a single main idea. Do NOT use dense paragraphs with multiple complex ideas presented simultaneously. Do NOT use complex sentence structures that require careful parsing
    5. Include practical applications and real-world examples to illustrate abstract concepts, but do NOT mention any specific people or companies. Do NOT state that academic studies support or oppose anything.
    6. Structure information logically, building from foundational concepts to more advanced applications.
    7. Maintain formal sentence structure but prefer active voice and direct explanations. Do NOT use contractions such as isn't or you've.
    8. When introducing specialized terms, immediately provide clear definitions or explanations.
    9. Use comparison and contrast to highlight key differences between related concepts.
    10. End with a concise summary of the main points in a bulleted list format.

    The article should be educational but accessible, avoiding academic jargon while still conveying substantive information that would be valuable to someone wanting to understand and apply the concepts in their own life or work.

    CONTEXTUAL FLOW
    This chapter should take into consideration the overall structure of the book. Avoid unnecessary repetition within the chapter, and between chapters.


    FORMATTING FOR DIV CLASS="BOOK"
    Within the chapter there should be multiple sections. For each section, write about 6-8 paragraphs, which give full and extensive essay explanations of the topic, suitable for an academic textbook.  Generally, use medium length sentences and ensure that the text is reader-friendly. Include a summary box with 4-5 concise bullet points which are about 8-12 words in length each.

    Your output must use the following HTML tags appropriately:
    - do not use <h1> as it will be added manually
    - <h2> must be added for each section title within the chapter
    - <h3> for the Summary subheadings
    - <p> for paragraphs (each paragraph must be wrapped in <p> tags)
    - <p class="first"> for the first paragraph of each section
    - <ul> and <li> for unordered lists
    - <div class="box"> should be used for summary boxes

    Format your content following these rules:
    1. Every piece of text must be inside appropriate HTML tags
    2. Main content must be in <p> tags
    3. Use appropriate heading levels for hierarchy
    4. Lists must be properly nested inside <ul> or <ol> tags
    5. No bare text outside of tags
    6. No markdown formatting
    7. Do NOT quote specific statistics or percentages
    8. Do NOT use hyperbole on the first line, such as fascinating, crucial, transform, revolutionize, or most interesting.

    EXAMPLE INPUT
    Write a section about Pre-IPO Readiness and Corporate Governance.

    EXAMPLE OUPUT

<div class="book">

    <h2>Pre-IPO Readiness and Corporate Governance</h2>

    <p class="first">Preparing for an initial public offering requires a fundamental shift in how a business operates internally. This transition begins with a comprehensive readiness assessment to identify gaps in the current organizational structure. Management must evaluate whether the existing accounting systems and internal controls can handle the rigorous demands of public reporting. Often, this involves hiring additional staff with specific expertise in financial reporting and compliance. Addressing these gaps early ensures that the company can meet strict deadlines once the formal process begins.</p>

    <p>A central component of this preparation is the establishment of a formal board of directors. Private companies often operate with small boards comprised primarily of founders and major investors. Transitioning to a public model requires the inclusion of independent directors who have no material relationship with the firm. These individuals provide objective oversight and help build trust with future shareholders. Public markets generally require a majority of the board to be independent to ensure that the interests of all investors are protected.</p>

    <p>The board must also organize into specialized committees to manage specific areas of governance. An audit committee is essential for overseeing financial reporting and the relationship with external auditors. A compensation committee ensures that executive pay is aligned with long-term shareholder value and market standards. Finally, a nominating and corporate governance committee manages the selection of new board members and establishes ethical guidelines. These structures create a system of checks and balances that is vital for maintaining public confidence.</p>

    <p>Beyond the board structure, comprehensive legal due diligence is a prerequisite that runs parallel to financial preparation. Legal teams and external counsel must scrutinize the company’s corporate records, material contracts, and intellectual property portfolios to ensure there are no outstanding liabilities that could derail the offering. This process involves cleaning up historical capitalization tables and ensuring that all past stock issuances complied with relevant securities laws. Furthermore, the company must begin drafting the prospectus, specifically the "Risk Factors" section, which requires a candid and exhaustive disclosure of potential threats to the business model.</p>

    <p>Financial statement preparation remains a critical pillar of pre-IPO readiness. Companies must produce several years of audited financial statements that comply with established accounting standards. This process often involves restating past financial results to ensure they meet the level of detail required by regulators. External auditors will conduct a thorough review of these documents to verify their accuracy and completeness. Clear and transparent financial history allows potential investors to assess the health and growth prospects of the business accurately.</p>

    <p>Internal controls over financial reporting must be robust and well-documented. Management is responsible for establishing a framework that prevents errors and fraudulent activities within the organization. This includes formalizing processes for revenue recognition, expense approvals, and data security. During the preparation phase, companies often perform internal audits to test these controls and fix any weaknesses. Strong internal systems reduce the risk of future financial restatements and regulatory penalties after the company is public.</p>

    <p>To support these controls, upgrading technology infrastructure is often necessary to handle the accelerated reporting timelines of a public entity. Many private companies rely on legacy systems or disjointed software that cannot produce data with the speed and accuracy required by the SEC. Implementing a robust Enterprise Resource Planning (ERP) system allows for the automation of data collection and ensures consistency across departments. Additionally, cybersecurity protocols must be strengthened, as public companies are prime targets for attacks; demonstrating resilience in this area is now a critical expectation of both regulators and institutional investors.</p>

    <p>Finally, the company must develop a public company mindset across its leadership team. This involves shifting from a focus on long-term vision alone to a disciplined cycle of quarterly reporting and guidance. Executives must become comfortable with the level of transparency required by public markets, where successes and failures are scrutinized by the public. Training for management on disclosure rules and communication strategies is a common part of this transformation. Establishing these professional habits before the listing date helps the organization navigate the pressure of life in the public eye.</p>
    
    <div class="box">
        <h3>Summary</h3>
        <ul>
            <li>Internal readiness assessments identify gaps in infrastructure and financial controls.</li>
            <li>Independent boards of directors provide objective oversight for public investors.</li>
            <li>Specialized committees manage audits, compensation, and corporate governance practices.</li>
            <li>Audited financial statements must comply with rigorous regulatory accounting standards.</li>
        </ul>
    </div>
</div>



"""

        # Initialize content buffer
        chapter_content = ""

        # Process the streaming response
        try:
            response = client.models.generate_content_stream(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_level="high")
                )
            )

            print("Generating chapter content...", flush=True)
            for chunk in response:
                if chunk.text:
                    print(chunk.text, end="", flush=True)
                    chapter_content += chunk.text
            
            print("\n\nChapter generation completed.")

            # Ensure the content starts with <div class="chapter-content"> and ends with </div>
            if not chapter_content.strip().startswith('<div class="chapter-content">'):
                chapter_content = f'<div class="chapter-content">\n{chapter_content}'
            if not chapter_content.strip().endswith('</div>'):
                chapter_content = f'{chapter_content}\n</div>'

            return chapter_content
        except Exception as e:
            print(f"\n❌ Error during chapter generation: {str(e)}")
            raise

    def add_structure(self, structure):
        """Enhanced structure formatter that includes section descriptions"""
        structure_text = ""
        for title, section in structure.items():
            prefix = ""
            structure_text += f"{prefix}Chapter: {title}\n"

            if isinstance(section, dict):
                # This is a chapter with sections
                for subsection_title, subsection_content in section.items():
                    subprefix = "  "
                    structure_text += f"{subprefix}Section: {subsection_title}\n"
                    if isinstance(subsection_content, str):
                        desc_prefix = "  "
                        structure_text += f"{desc_prefix}Description: {subsection_content}\n"
                    else:
                        # Handle deeper nesting if needed
                        structure_text += self.add_structure(subsection_content)
            else:
                # This shouldn't happen with our current structure
                structure_text += f'<p>{section}</p>\n'

        return structure_text

    def generate_book(self):
        """Generate the entire book."""
        try:
            # Check if book title is set
            if not self.book_title:
                # Default to topic if no title is provided
                self.book_title = self.topic
                print(f"\n📖 No title provided, using topic as title: {self.book_title}")
            else:
                print(f"\n📖 Using Book Title: {self.book_title}")

            # Generate book structure
            print("\n🏗️ Generating book structure...")
            structure_json = self.retry_with_backoff(
                self.generate_book_structure,
                self.client,
                self.topic
            )
            self.book_structure = json.loads(structure_json)

            # Generate chapters
            print("\n📝 Generating chapters...")
            for chapter_title, sections in self.book_structure.items():
                print(f"\n📄 Generating chapter: {chapter_title}")
                try:
                    chapter_content = self.retry_with_backoff(
                        self.generate_chapter,
                        self.client,
                        chapter_title,
                        sections
                    )
                    self.book_content[chapter_title] = chapter_content
                    self.all_previous_sections.append(chapter_content)
                except Exception as e:
                    print(f"\n❌ Failed to generate chapter {chapter_title}: {str(e)}")
                    self.failed_sections[chapter_title] = str(e)

            # Generate HTML
            print("\n🌐 Generating HTML...")
            html_content = self.generate_html()

            # Convert to PDF and EPUB
            print("\n📄 Converting to PDF and EPUB...")
            self.generate_pdf(html_content)

            print(f"\n✅ Book generation completed! Output saved to: {self.output_filename}")

            if self.failed_sections:
                print("\n⚠️ Some sections failed to generate:")
                for section, error in self.failed_sections.items():
                    print(f"- {section}: {error}")

        except Exception as e:
            print(f"\n❌ Error generating book: {str(e)}")
            raise

    def generate_html(self):
        """Generate complete HTML content."""
        html_content = ""

        html_content += self.add_section_content(self.book_structure)
        return html_content

    def add_section_content(self, structure):
        """Add section content recursively."""
        content = ""
        for title, section in structure.items():
            if isinstance(section, dict):
                # For chapters, add a chapter div and title
                content += f'<div class="chapter">\n'
                content += f'<h1>{title}</h1>\n'

                # Get the chapter content from book_content if it exists
                if title in self.book_content:
                    content += self.book_content[title]
                else:
                    content += f'<p>Content not generated for chapter: {title}</p>\n'

                content += "</div>\n\n"
            else:
                # This shouldn't happen with our current structure
                content += f'<p>{section}</p>\n'

        return content

    def generate_pdf(self, html_content):
      """Save the book as HTML, PDF, and EPUB files with enhanced styling."""
      try:
        print("\n💾 Saving HTML, PDF, and EPUB versions...")

        # Ensure filename has .html extension
        if not self.output_filename.lower().endswith('.html'):
          self.output_filename = f"{self.output_filename}.html"

        # Create full path using Google Drive directory
        full_path = os.path.join(self.save_dir, self.output_filename)
        print(f"Full output path: {full_path}")

        # Create directory if it doesn't exist
        try:
          os.makedirs(self.save_dir, exist_ok=True)
          print(f"Directory created/verified: {self.save_dir}")
        except Exception as dir_error:
          print(f"Error creating directory: {str(dir_error)}")
          raise

        # HTML template with CSS styling - simplified for debugging
        html_template = '''

    <html>
            <head>
              <meta charset="UTF-8">


              <style>

/* Base styles */
    @page {{
      size: a4 portrait;
      margin: 25mm;
    }}

    body {{
      font-family: "Times-Roman", serif;
      font-size: 11.5pt;
      line-height: 1.4;
      text-align: justify;
      color: #1a1a1a;
    }}

    h1 {{
      font-family: "Times-Roman";
      font-size: 24pt;
      font-weight: 300;
      text-align: center;
      margin-top: 50mm;
      margin-bottom: 10mm;
      page-break-before: always;
      page-break-after: avoid;
      color: #34495e;
      text-transform: uppercase;
      border-bottom: 1pt solid #1a1a1a;
      padding-bottom: 5mm;
    }}

    /* Specific fix for Title Page H1 */
    .title-page h1 {{
        font-size: 36pt;
        font-weight: bold;
        margin-bottom: 10mm;
        border: none;
        text-transform: none;
        page-break-before: avoid; 
        margin-top: 0;  
        color: #34495e;         
    }}

    h2 {{
      font-family: "Times-Roman";
      font-size: 16pt;
      font-weight: 500;
      text-align: left;
      margin: 10mm 0 0;
      padding-bottom: 0;
      page-break-after: avoid;
      color: #34495e;
    }}

    h3 {{
      font-family: "Times-Roman";
      font-size: 14pt;
      font-weight: 500;
      text-align: left;
      margin: 8mm 0 4mm;
      page-break-after: avoid;
      color: #34495e;
    }}

    p {{
      text-align: justify;
      text-indent: 0;
      margin: 2mm 0;
    }}

    p.first {{
      page-break-before: avoid;
      text-indent: 0;
    }}

    ul {{
      padding-left: 0;
      list-style-position: inside;
    }}

    li {{
      text-align: justify;
    }}

    li p {{
      margin-top: 0;
      margin-bottom: 0;
      text-indent: 0;
    }}

    table {{
      width: 100%;
      margin: 5mm 0;
      border-collapse: collapse;
      border: 1pt solid #e5e5e5;
    }}

    th {{
      background-color: #f8f9fa;
      border-bottom: 2pt solid #2c3e50;
      padding: 3mm;
      font-weight: 600;
      color: #2c3e50;
    }}

    td {{
      padding: 3mm;
      border: 1pt solid #e5e5e5;
      vertical-align: top;
    }}

    blockquote {{
      margin: 5mm 10mm;
      padding-left: 5mm;
      border-left: 3pt solid #2c3e50;
      font-style: italic;
      color: #34495e;
      line-height: 1.6;
    }}

    .definition {{
      background-color: #f8f9fa;
      padding: 5mm;
      margin: 5mm 0;
      border-radius: 2pt;
      border: 1pt solid #e5e5e5;
    }}

    .box {{
      background-color: #f4f6f9;
      padding: 4mm 6mm;
      margin: 6mm 0;
      border-left: 3pt solid #34495e;
      break-inside: avoid;
    }}

    .box h3 {{
      margin-top: 0;
      margin-bottom: 2mm;
      color: #34495e;
    }}

    .box li {{
      font-style: italic;
    }}

    .title-page {{
        text-align: center;
        padding-top: 80mm;
    }}




              </style>


    <script>

    </script>


            </head>
            <body>
              <div class="pdf-container">
                <div class="title-page">
                    <h1>{title}</h1>
                </div>
              {content}
              </div>
            </body>
          </html>

    '''

        # Format the HTML template with content
        styled_html = html_template.format(content=html_content, title=self.book_title)

        # Save HTML file
        try:
          print(f"Attempting to save HTML to: {full_path}")
          with open(full_path, 'w', encoding='utf-8') as f:
            f.write(styled_html)
          print(f"✅ HTML file saved successfully to: {full_path}")
        except Exception as html_error:
          print(f"❌ Error saving HTML file: {str(html_error)}")
          print(f"Attempted to save to: {full_path}")
          raise



        # Generate PDF filename
        pdf_filepath = full_path.replace('.html', '.pdf')
        print(f"\n📄 Converting to PDF with WeasyPrint... Output path: {pdf_filepath}")

        try:
            from weasyprint import HTML
            HTML(string=styled_html).write_pdf(pdf_filepath)
            print(f"✅ PDF file saved successfully to: {pdf_filepath}")

        except Exception as pdf_error:
            print(f"❌ Error generating PDF: {str(pdf_error)}")

        # Generate EPUB version using the book_mode_html instead of the full HTML
        epub_filepath = full_path.replace('.html', '.epub')
        print(f"\n📚 Converting to EPUB... Output path: {epub_filepath}")

        try:
          converter = EPUBConverter(
            html_content=styled_html,
            output_filename=epub_filepath,
            title=self.book_title
          )
          epub_content = converter.convert()

          if epub_content:
            with open(epub_filepath, 'wb') as f:
              f.write(epub_content)
            print(f"✅ EPUB file saved successfully to: {epub_filepath}")
          else:
            print("❌ Failed to create EPUB version")
        except Exception as epub_error:
          print(f"❌ Error generating EPUB: {str(epub_error)}")
          raise

      except Exception as e:
        print(f"\n❌ Error saving files: {str(e)}")
        raise



















# Main execution
def main():
    parser = argparse.ArgumentParser(description="Book Creation Tool")
    parser.add_argument("--csv", default="book_topics.csv", help="Path to the CSV file containing topics")
    args = parser.parse_args()

    # Default mode is generate-book
    csv_file_path = args.csv
    
    if not os.path.exists(csv_file_path):
        print(f"CSV file '{csv_file_path}' not found. Creating a sample file...")
        with open(csv_file_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Topic', 'OutputFilename', 'Title'])
            writer.writerow(['The Evolution of iPhone', 'iphone_history', 'The Revolutionary Journey of iPhone: From Concept to Cultural Icon'])
            writer.writerow(['Artificial Intelligence in Healthcare', 'ai_healthcare', 'Healing with Algorithms: AI Transforming Modern Medicine'])
            writer.writerow(['Climate Change Solutions', 'climate_solutions', 'Earth\'s Renewal: Innovative Approaches to Climate Change'])
        print(f"Sample CSV file created at '{csv_file_path}'. Edit this file to add your own topics and filenames.")
        print("Format: Topic,OutputFilename,Title (one per line)")
        return

    # Read the topics, filenames, and titles from the CSV file
    book_data = []
    with open(csv_file_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            topic = row.get('Topic', '').strip()
            output_filename = row.get('OutputFilename', '').strip()
            title = row.get('Title', '').strip()

            if topic and output_filename:
                if title:
                    book_data.append((topic, output_filename, title))
                else:
                    # If title is missing, use the topic as the title
                    book_data.append((topic, output_filename, topic))

    if not book_data:
        print(f"No valid book data found in '{csv_file_path}'. Please add topics, filenames, and titles to the CSV file.")
        return



    # Process each book
    for topic, output_filename, title in book_data:
        print(f"\n{'=' * 80}")
        print(f"Processing: {topic} -> {output_filename}")
        print(f"Title: {title}")
        print(f"{'=' * 80}\n")

        try:
            # Create the book generator
            generator = BookGenerator(topic, output_filename)
            print(f"Files will be saved to: {generator.save_dir}")

            # Set the book title from CSV
            generator.book_title = title
            print(f"Using book title: {generator.book_title}")

            # Generate the book content
            print("Generating book content...")
            generator.generate_book()



            print(f"\nCompleted: {topic} -> {output_filename}")
            print(f"Files generated: {output_filename}.html, {output_filename}.pdf, {output_filename}.epub")

        except Exception as e:
            print(f"Error processing '{topic}': {str(e)}")
            print("Continuing with next topic...")
            import traceback
            traceback.print_exc()

    print("\nAll books have been processed!")

if __name__ == "__main__":
    main()





