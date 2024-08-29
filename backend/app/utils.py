import re
import docx
import openpyxl
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import openai
import logging
import json
from typing import List, Dict, Optional
import PyPDF2
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import datetime
import zipfile
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)

openai.api_key = os.getenv("OPENAI_API_KEY")

def read_file_content(file_path: str) -> Optional[str]:
    file_extension = os.path.splitext(file_path)[1].lower()

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return None

    try:
        if file_extension == '.txt':
            logger.info(f"Reading .txt file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()

        elif file_extension == '.docx':
            logger.info(f"Reading .docx file: {file_path}")
            doc = docx.Document(file_path)
            return ' '.join([para.text for para in doc.paragraphs])

        elif file_extension == '.xlsx':
            logger.info(f"Reading .xlsx file: {file_path}")
            workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            sheet = workbook.active
            return '\n'.join([' '.join([str(cell.value) if cell.value is not None else '' for cell in row]) for row in sheet.iter_rows()])

        elif file_extension == '.pdf':
            logger.info(f"Reading .pdf file: {file_path}")
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                return ' '.join([page.extract_text() for page in reader.pages])

        else:
            logger.warning(f"Unsupported file type: {file_extension}")
            return None

    except PermissionError:
        logger.error(f"Permission denied when trying to read file: {file_path}")
    except docx.opc.exceptions.PackageNotFoundError:
        logger.error(f"Invalid or corrupted .docx file: {file_path}")
    except openpyxl.utils.exceptions.InvalidFileException:
        logger.error(f"Invalid or corrupted .xlsx file: {file_path}")
    except PyPDF2.errors.PdfReadError:
        logger.error(f"Invalid or corrupted .pdf file: {file_path}")
    except UnicodeDecodeError:
        logger.error(f"Unable to decode file (possibly not in UTF-8 encoding): {file_path}")
    except Exception as e:
        logger.error(f"Unexpected error reading file {file_path}: {str(e)}", exc_info=True)

    return None

def parse_content(content):
    try:
        sections = re.split(r'\n(?=#{1,3}\s)', content)  # Split on headings
        if len(sections) <= 1:
            # If no headings found, split by word count
            words = content.split()
            sections = [' '.join(words[i:i + 500]) for i in range(0, len(words), 500)]
        return sections
    except Exception as e:
        logger.error(f"Error parsing content: {str(e)}")
        raise

def extract_keywords(text):
    try:
        stop_words = set(stopwords.words('norwegian'))
        words = word_tokenize(text.lower())
        filtered_words = [word for word in words if word.isalnum() and word not in stop_words]
        word_freq = nltk.FreqDist(filtered_words)
        return [word for word, _ in word_freq.most_common(6)]
    except Exception as e:
        logger.error(f"Error extracting keywords: {str(e)}")
        raise
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10),
       retry=retry_if_exception_type(openai.error.OpenAIError))
def call_openai_api(system_instruction: Dict, user_prompt: str) -> str:
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                system_instruction,
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=4096,
            timeout=60  # Increase timeout to 60 seconds
        )

        if not response.choices or not response.choices[0].message['content'].strip():
            raise ValueError("OpenAI API returned an empty response")

        return response.choices[0].message['content'].strip()

    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in OpenAI API call: {str(e)}")
        raise

def extract_and_structure_data(content: str, keywords: List[str]) -> Dict:
    logger.debug(f"Content type: {type(content)}")
    logger.debug(f"Keywords type: {type(keywords)}")
    logger.debug(f"Keywords: {keywords}")

    system_instruction = {
        "role": "system",
        "content": """Du er en hjelpsom assistent som ekstraherer, strukturerer og organiserer informasjon fra tekst. Din oppgave er å:
        1. Identifisere og kategorisere nøkkelbegreper, enheter (f.eks. navn, datoer, steder) og relasjoner innen teksten.
        2. Strukturere informasjonen i et klart og logisk format, for eksempel JSON, med riktige etiketter og hierarki.
        3. Sørge for at resultatet er både lesbart for mennesker og optimalisert for søkbarhet av en LLM, inkludert indekserte nøkkelord og metadata-tagging.
        4. Tilpasse ekstraheringen basert på konteksten.
        5. Prioritere klarhet, konsistens og fullstendighet i strukturen.
        6. ALLTID returnere resultatet som et JSON-objekt med feltene 'title', 'body', og 'tags'."""
    }

    user_prompt = f"""Analyser følgende innhold og nøkkelord, og ekstraher og strukturer hovedpunktene:

    Innhold: {content}

    Nøkkelord: {', '.join(keywords)}

    Vennligst gi et strukturert resultat i JSON-format med følgende felter:
    - title: Tittel på seksjonen (hvis ingen tydelig tittel, bruk 'Untitled Section')
    - body: Hovedinnholdet i seksjonen
    - tags: Liste over relevante nøkkelord fra innholdet"""

    try:
        logger.info(f"Sending prompt to OpenAI. Content length: {len(content)}")
        result = call_openai_api(system_instruction, user_prompt)
        logger.info(f"Received response from OpenAI. Response length: {len(result)}")

        # Check if the response starts with ```json and ends with ```
        if result.startswith("```json") and result.endswith("```"):
            # Remove the ```json and ``` markers
            result = result[7:-3].strip()

        # Parse the JSON result
        try:
            parsed_result = json.loads(result)

            # Ensure the parsed result has the required fields
            if not all(key in parsed_result for key in ['title', 'body', 'tags']):
                logger.warning("Parsed result is missing required fields. Adding default values.")
                parsed_result = {
                    "title": parsed_result.get('title', 'Untitled Section'),
                    "body": parsed_result.get('body', 'No content available.'),
                    "tags": parsed_result.get('tags', [])
                }

            return parsed_result

        except json.JSONDecodeError as json_error:
            logger.error(f"Failed to parse JSON from OpenAI response. Response content: {result}")
            logger.error(f"JSON parsing error: {str(json_error)}")
            return {
                "title": "Error: Invalid JSON",
                "body": f"Failed to parse JSON from OpenAI response: {result}",
                "tags": []
            }

    except ValueError as ve:
        logger.error(f"ValueError in OpenAI API call: {str(ve)}")
        return {
            "title": "Error: Empty Response",
            "body": "The AI model returned an empty response for this section.",
            "tags": []
        }
    except Exception as e:
        logger.error(f"Unexpected error in extract_and_structure_data: {str(e)}", exc_info=True)
        return {
            "title": "Error: Unexpected",
            "body": f"Unexpected error in OpenAI API call: {str(e)}",
            "tags": []
        }

def process_file(file_path: str) -> str:
    content = read_file_content(file_path)
    if content is None:
        logger.error(f"Unable to read file content: {file_path}")
        return "Error: Unable to read file content"

    keywords = extract_keywords(content)
    sections = parse_content(content)

    output_dir = "processed_files"
    os.makedirs(output_dir, exist_ok=True)

    json_files = []
    for i, section in enumerate(sections):
        structured_data = extract_and_structure_data(section, keywords)
        file_name = f"section_{i+1}.json"
        file_path = os.path.join(output_dir, file_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)
        json_files.append(file_path)

    # Create a zip file
    zip_file_name = f"processed_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(zip_file_name, 'w') as zipf:
        for file in json_files:
            zipf.write(file, arcname=os.path.basename(file))

    return zip_file_name

# Usage
if __name__ == "__main__":
    file_path = "path_to_your_file.txt"  # Replace with the actual file path
    zip_file = process_file(file_path)
    print(f"Processing complete. Output saved in {zip_file}")
