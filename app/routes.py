from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from .models import Product, Profile, db
from . import supabase

main = Blueprint('main', __name__)

@main.context_processor
def inject_user():
    user_profile = None
    # Check of er een user_id in de sessie zit (dus: is iemand ingelogd?)
    if 'user_id' in session:
        # Haal het profiel op uit de lokale database
        user_profile = Profile.query.get(session['user_id'])
    
    # Maak de variabele 'current_user' beschikbaar in alle HTML-bestanden
    return dict(current_user=user_profile)

# AANGEPAST: De index route haalt nu data op
@main.route('/')
def index():
    # 1. Vraag aan de database: "Geef mij alle producten waar is_available True is"
    products = Product.query.filter_by(is_available=True).all()
    
    # 2. Geef de lijst met producten door aan de index.html template
    return render_template('index.html', products=products)


@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # 1. Haal data op
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')

        # DEBUG: Print de waarde naar je terminal om te checken
        print(f"DEBUG: Ontvangen naam uit formulier: '{full_name}'")

        try:
            # 2. Registreer bij Supabase Auth (met metadata!)
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {"data": {"full_name": full_name}}
            })

            if auth_response.user and auth_response.user.id:
                user_id = auth_response.user.id
                
                # 3. Maak profiel aan in jouw database
                new_profile = Profile(
                    id=user_id,
                    full_name=full_name  # Zorg dat deze variabele hier wordt gebruikt!
                )
                db.session.add(new_profile)
                db.session.commit()
                
                print("DEBUG: Profiel succesvol opgeslagen in database.")
                return redirect(url_for('main.index'))

        except Exception as e:
            print(f"FOUT: {e}")
            db.session.rollback() # Belangrijk: draai transactie terug bij fout
            return render_template('register.html', error=str(e))

    return render_template('register.html')

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            # 1. Vraag Supabase om in te loggen
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            # 2. Als het lukt, sla de gebruikers-ID en access token op in de sessie
            # Dit is het 'toegangsbewijs' dat Flask onthoudt zolang je browser open is.
            session['user_id'] = response.user.id
            session['access_token'] = response.session.access_token

            print(f"DEBUG: Ingelogd als {email} met ID {response.user.id}")
            return redirect(url_for('main.index'))

        except Exception as e:
            # Als inloggen mislukt (bijv. verkeerd wachtwoord), toon de fout op de pagina
            print(f"FOUT bij inloggen: {e}")
            # We vertalen de Engelse Supabase foutmelding naar iets vriendelijkers (optioneel)
            error_message = "E-mailadres of wachtwoord is onjuist."
            return render_template('login.html', error=error_message)

    return render_template('login.html')

@main.route('/logout')
def logout():
    # 1. Vertel Supabase dat we uitloggen
    supabase.auth.sign_out()
    # 2. Gooi het 'toegangsbewijs' weg uit Flask's geheugen
    session.clear()
    print("DEBUG: Uitgelogd")
    return redirect(url_for('main.index'))