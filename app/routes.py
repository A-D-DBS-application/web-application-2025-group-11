from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from .models import Product, Profile, Order, OrderItem, db
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

@main.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    # 1. Haal het mandje op uit de sessie, of maak een leeg mandje (dict)
    #    Formaat: { 'product_id': quantity, 'product_id_2': quantity }
    cart = session.get('cart', {})

    # 2. Haal de huidige hoeveelheid op (of 0) en tel er 1 bij op
    current_quantity = cart.get(str(product_id), 0)
    cart[str(product_id)] = current_quantity + 1

    # 3. Sla het bijgewerkte mandje terug op in de sessie
    session['cart'] = cart
    # BELANGRIJK: Zeg Flask dat de sessie is gewijzigd (omdat we een dict *in* de sessie hebben aangepast)
    session.modified = True 

    print(f"DEBUG: Mandje bijgewerkt: {session['cart']}")
    flash(f'Product toegevoegd aan je mandje!', 'success')
    return redirect(url_for('main.index'))

@main.route('/cart')
def view_cart():
    # 1. Haal het mandje op uit de sessie
    cart_dict = session.get('cart', {})
    
    products_in_cart = []
    total_cart_price = 0

    if cart_dict:
        # 2. Haal de product-ID's uit het mandje
        product_ids = [int(id) for id in cart_dict.keys()]
        
        # 3. Haal de bijbehorende product-objecten uit de database
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        
        # 4. Bereken de totaalprijs en maak een mooie lijst
        for product in products:
            quantity = cart_dict[str(product.id)]
            total_for_product = product.price * quantity
            total_cart_price += total_for_product
            
            products_in_cart.append({
                'product': product,
                'quantity': quantity,
                'total_price': total_for_product
            })

    return render_template('cart.html', 
                           cart_items=products_in_cart, 
                           total_cart_price=total_cart_price)

@main.route('/checkout', methods=['POST'])
def checkout():
    # 1. Is de gebruiker ingelogd?
    if 'user_id' not in session:
        flash('Je moet ingelogd zijn om af te rekenen.', 'danger')
        return redirect(url_for('main.login'))

    # 2. Is het mandje leeg?
    cart_dict = session.get('cart', {})
    if not cart_dict:
        flash('Je mandje is leeg.', 'warning')
        return redirect(url_for('main.view_cart'))

    try:
        # --- We gaan de database in schrijven ---
        
        # 3. Haal alle product-objecten op
        product_ids = [int(id) for id in cart_dict.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        
        # 4. Bereken de ECHTE totaalprijs (vertrouw de sessie niet voor prijzen)
        total_price = 0
        products_map = {str(p.id): p for p in products} # Makkelijk opzoeken
        
        for product_id, quantity in cart_dict.items():
            product_price = products_map[product_id].price
            total_price += (product_price * quantity)

        # 5. Maak de 'Order' (de "bon") aan
        new_order = Order(
            user_id=session['user_id'],
            total_price=total_price,
            status='pending' # We beginnen altijd als 'pending'
        )
        db.session.add(new_order)
        # BELANGRIJK: 'flush' om de new_order.id te krijgen van de database
        # We 'committen' nog niet, voor het geval er iets misgaat
        db.session.flush() 

        # 6. Maak de 'OrderItems' (de "regels op de bon") aan
        for product_id, quantity in cart_dict.items():
            product = products_map[product_id]
            
            order_item = OrderItem(
                order_id=new_order.id,      # De ID van de bon die we net maakten
                product_id=product.id,
                quantity=quantity,
                unit_price_at_order=product.price # Sla de prijs van DIT MOMENT op
            )
            db.session.add(order_item)

        # 7. Alles is gelukt! Maak het permanent.
        db.session.commit()

        # 8. Maak het mandje leeg
        session.pop('cart', None)
        session.modified = True

        flash('Bestelling succesvol geplaatst!', 'success')
        return redirect(url_for('main.index')) # Stuur naar bv. "mijn bestellingen"

    except Exception as e:
        # 7b. Er ging iets mis. Draai ALLES terug.
        db.session.rollback()
        print(f"FOUT bij checkout: {e}")
        flash('Er ging iets mis bij het plaatsen van je bestelling.', 'danger')
        return redirect(url_for('main.view_cart'))