class Config:
    SECRET_KEY = 'cuvwiN-zosmob-8wonzu'
    # Database connectie (Supabase Pooler)
    SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg://postgres.pavocfhmigmdzrzxoiio:cuvwiN-zosmob-8wonzu@aws-1-eu-west-1.pooler.supabase.com:6543/postgres'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Dit blok voorkomt de "DuplicatePreparedStatement" error
    SQLALCHEMY_ENGINE_OPTIONS = {
    "connect_args": {
"prepare_threshold": None
}
    }

    SUPABASE_URL = "https://pavocfhmigmdzrzxoiio.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBhdm9jZmhtaWdtZHpyenhvaWlvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEyMjYzMTcsImV4cCI6MjA3NjgwMjMxN30.TV3nd9t8OoHMf98BhSrUwMYsg878gkxBuzVitfLru8I"
    API_KEY = "SaHo5ACiML8AdIW4"


# Dit is een voorbeeldconfiguratie die gebruik maakt van omgevingsvariabelen. Je kunt dit gebruiken door de commentaartekens te verwijderen en een .env bestand aan te maken met de juiste variabelen. Dit zorgt ervoor dat gevoelige informatie niet hardcoded in je code staat.

#import os
#from dotenv import load_dotenv

# Laad de variabelen uit het .env bestand
#load_dotenv()

#class Config:
    # Haal de secret key op, of gebruik een fallback voor lokaal testen als hij mist
#    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-voor-lokaal'
    
    # Database connectie (Supabase Pooler)
#    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
#    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- FIX VOOR SUPABASE ERROR ---
    # Dit blok voorkomt de "DuplicatePreparedStatement" error
#    SQLALCHEMY_ENGINE_OPTIONS = {
#        "connect_args": {
#            "prepare_threshold": None
#        }
#    }
    # -------------------------------

#    SUPABASE_URL = os.environ.get('SUPABASE_URL')
#    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
#    API_KEY = os.environ.get('API_KEY')

    # Debug check (optioneel, handig om te zien of het werkt bij opstarten)
#   if not SQLALCHEMY_DATABASE_URI:
#        print("⚠️ WAARSCHUWING: Geen DATABASE_URL gevonden in .env bestand!")

# Inhoud .env bestand voorbeeld:
#SECRET_KEY=cuvwiN-zosmob-8wonzu
#DATABASE_URL=postgresql+psycopg://postgres.pavocfhmigmdzrzxoiio:cuvwiN-zosmob-8wonzu@aws-1-eu-west-1.pooler.supabase.com:6543/postgres
#SUPABASE_URL=https://pavocfhmigmdzrzxoiio.supabase.co
#SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBhdm9jZmhtaWdtZHpyenhvaWlvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEyMjYzMTcsImV4cCI6MjA3NjgwMjMxN30.TV3nd9t8OoHMf98BhSrUwMYsg878gkxBuzVitfLru8I
#API_KEY=SaHo5ACiML8AdIW4