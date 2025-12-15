import os
from dotenv import load_dotenv

# Laad de variabelen uit het .env bestand
load_dotenv()

class Config:
    # Haal de secret key op, of gebruik een fallback voor lokaal testen als hij mist
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-voor-lokaal'
    
    # Database connectie (Supabase Pooler)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- FIX VOOR SUPABASE ERROR ---
    # Dit blok voorkomt de "DuplicatePreparedStatement" error
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {
            "prepare_threshold": None
        }
    }
    # -------------------------------

    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
    API_KEY = os.environ.get('API_KEY')

    # Debug check (optioneel, handig om te zien of het werkt bij opstarten)
    if not SQLALCHEMY_DATABASE_URI:
        print("⚠️ WAARSCHUWING: Geen DATABASE_URL gevonden in .env bestand!")