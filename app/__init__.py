import os
import sys
from flask import Flask
from dotenv import load_dotenv

def create_app():
    load_dotenv()
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
        template_folder = os.path.join(base_dir, 'app', 'templates')
        static_folder = os.path.join(base_dir, 'app', 'static')
        app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    else:
        app = Flask(__name__)

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'viral-clipper-secret-key-1billion')

    # Register routes
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    return app
