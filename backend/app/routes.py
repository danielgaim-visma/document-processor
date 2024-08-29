from flask import Blueprint, request, jsonify, current_app, send_file, Response, stream_with_context
from werkzeug.utils import secure_filename
from .utils import read_file_content, parse_content, extract_keywords, extract_and_structure_data
import os
import logging
import json
from datetime import datetime
import zipfile
import shutil
import tempfile
from flask_cors import cross_origin

main = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

@main.route('/api/upload-and-parse', methods=['POST'])
@cross_origin()
def upload_and_parse():
    logger.debug("Received request to /api/upload-and-parse")

    if 'file' not in request.files:
        logger.error("No file part in the request")
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']

    if file.filename == '':
        logger.error("No selected file")
        return jsonify({'error': 'No selected file'}), 400

    if file:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                filename = secure_filename(file.filename)
                file_path = os.path.join(temp_dir, filename)
                logger.debug(f"Attempting to save file to: {file_path}")
                file.save(file_path)
                logger.info(f"File saved: {file_path}")

                logger.debug("Reading file content")
                content = read_file_content(file_path)

                if content is None:
                    logger.error(f"Unable to read file content: {file_path}")
                    return jsonify({'error': 'Unable to read file content'}), 400

                logger.debug("Parsing content")
                parsed_sections = parse_content(content)
                logger.debug(f"Number of parsed sections: {len(parsed_sections)}")

                logger.debug("Extracting keywords")
                keywords = extract_keywords(content)
                logger.debug(f"Extracted keywords: {keywords}")

                logger.debug("Preparing response")
                return jsonify({
                    'parsed_sections': parsed_sections,
                    'keywords': keywords,
                    'original_filename': filename
                }), 200
        except Exception as e:
            logger.error(f"Error in upload_and_parse: {str(e)}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    logger.error("File upload failed")
    return jsonify({'error': 'File upload failed'}), 400

@main.route('/api/process-sections', methods=['POST'])
@cross_origin()
def process_sections():
    data = request.json
    if not data or 'parsed_sections' not in data or 'keywords' not in data or 'original_filename' not in data:
        logger.error("Insufficient data provided")
        return jsonify({'error': 'Insufficient data provided'}), 400

    def generate():
        temp_dir = tempfile.mkdtemp()
        try:
            parsed_sections = data['parsed_sections']
            keywords = data['keywords']
            original_filename = data['original_filename']

            logger.debug(f"Number of sections to process: {len(parsed_sections)}")
            logger.debug(f"Keywords: {keywords}")
            logger.debug(f"Original filename: {original_filename}")

            output_dir = os.path.join(temp_dir, 'processed_files')
            os.makedirs(output_dir, exist_ok=True)

            json_files = []
            errors = []
            total_sections = len(parsed_sections)

            for i, section in enumerate(parsed_sections, 1):
                try:
                    logger.info(f"Processing section {i} of {total_sections}")
                    structured_data = extract_and_structure_data(section, keywords)

                    if isinstance(structured_data, list):
                        structured_data = {
                            'content': structured_data,
                            'section_number': i
                        }
                    elif isinstance(structured_data, dict):
                        structured_data['section_number'] = i
                    else:
                        logger.error(f"Unexpected type for structured_data in section {i}: {type(structured_data)}")
                        raise TypeError(f"Unexpected type for structured_data: {type(structured_data)}")

                    file_name = f"section_{i:03d}.json"
                    file_path = os.path.join(output_dir, file_name)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(structured_data, f, ensure_ascii=False, indent=2)
                    json_files.append(file_path)

                    yield json.dumps({'progress': i, 'total': total_sections}) + '\n'

                except Exception as section_error:
                    error_message = f"Error processing section {i}: {str(section_error)}"
                    logger.error(error_message, exc_info=True)
                    errors.append(error_message)
                    yield json.dumps({'error': error_message}) + '\n'

            if not json_files:
                logger.error("No sections were successfully processed")
                yield json.dumps({'error': 'No sections were successfully processed', 'details': errors}) + '\n'
                return

            metadata = {
                "original_file": original_filename,
                "total_sections": total_sections,
                "processed_sections": len(json_files),
                "global_keywords": keywords,
                "processed_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "errors": errors
            }
            metadata_file = os.path.join(output_dir, "metadata.json")
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            json_files.append(metadata_file)

            zip_file_name = f"processed_files_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            zip_file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], zip_file_name)
            with zipfile.ZipFile(zip_file_path, 'w') as zipf:
                for file in json_files:
                    zipf.write(file, arcname=os.path.basename(file))

            yield json.dumps({'zip_file': zip_file_name, 'errors': errors}) + '\n'

        except Exception as e:
            logger.error(f"Error in process_sections: {str(e)}", exc_info=True)
            yield json.dumps({'error': str(e)}) + '\n'
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    return Response(stream_with_context(generate()), mimetype='application/json')

@main.route('/api/download/<filename>', methods=['GET'])
@cross_origin()
def download_file(filename):
    try:
        return send_file(os.path.join(current_app.config['UPLOAD_FOLDER'], filename), as_attachment=True)
    except Exception as e:
        logger.error(f"Error in download_file: {str(e)}")
        return jsonify({'error': str(e)}), 500