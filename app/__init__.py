from flask import Flask
from config import Config
from .models import db
from supabase import create_client

def create_app(config_class=Config):
    app = Flask(__name__)
    
    app.config.from_object(config_class)

    db.init_app(app)

    global supabase
    supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])

    from .routes import main
    app.register_blueprint(main)

    return app