from flask import Flask, send_from_directory
from flask_cors import CORS
from .config import Config
import os
import logging

def create_app(config_class=Config):
    app = Flask(__name__, static_folder='../frontend/build', static_url_path='')
    app.config.from_object(config_class)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Application starting...")
    logger.info(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    logger.info(f"Static folder path: {app.static_folder}")
    logger.info(f"Absolute static folder path: {os.path.abspath(app.static_folder)}")
    logger.info(f"Index.html exists: {os.path.exists(os.path.join(app.static_folder, 'index.html'))}")

    CORS(app, resources={r"/*": {"origins": "*"}})

    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve(path):
        if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        else:
            return send_from_directory(app.static_folder, 'index.html')

    logger.info("Application created and configured")

    return app