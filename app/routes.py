from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from .models import Product, Profile, Order, OrderItem, db
from . import supabase
from decimal import Decimal
from datetime import datetime

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
    
    # 1. Haal de hoeveelheid op (gecorrigeerde, veiligere versie)
    try:
        # Haal de string op, met '1' als standaard
        quantity_str = request.form.get('quantity', '1') 
        # Probeer er een getal van te maken
        quantity_to_add = int(quantity_str)
        
        # Zorg dat het minimaal 1 is
        if quantity_to_add < 1:
            quantity_to_add = 1
    except (ValueError, TypeError):
        # Vangt fouten op als iemand "abc" invult
        quantity_to_add = 1
    
    # 2. Haal het mandje op uit de sessie
    cart = session.get('cart', {})

    # 3. Tel de NIEUWE hoeveelheid op bij wat er al in zit
    current_quantity = cart.get(str(product_id), 0)
    cart[str(product_id)] = current_quantity + quantity_to_add

    # 4. Sla het bijgewerkte mandje terug op in de sessie
    session['cart'] = cart
    session.modified = True 

    # 5. Flash een duidelijker bericht
    product = Product.query.get_or_404(product_id) 
    flash(f'{quantity_to_add}x {product.name} toegevoegd aan je mandje!', 'success')
    
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

# In app/routes.py

@main.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    # Haal het mandje op
    cart = session.get('cart', {})
    product_id_str = str(product_id) # IDs in de sessie zijn strings

    # Als het product in het mandje zit, verwijder het
    if product_id_str in cart:
        del cart[product_id_str]
        session['cart'] = cart
        session.modified = True
        flash(f'Product uit je winkelwagen verwijderd.', 'success')
    
    # Stuur de gebruiker terug naar de winkelwagen
    return redirect(url_for('main.view_cart'))

# In app/routes.py

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
    
    # 3. NIEUW: Lees de extra formulier-data uit
    pickup_date_str = request.form.get('pickup_date')
    remarks = request.form.get('remarks')

    try:
        # 4. NIEUW: Converteer de datum-string naar een Python datum-object
        pickup_date_obj = None
        if pickup_date_str:
            pickup_date_obj = datetime.strptime(pickup_date_str, '%Y-%m-%d').date()
        else:
            # Als de 'required' in HTML faalt, vangen we het hier op
            flash('Geen ophaaldatum geselecteerd.', 'danger')
            return redirect(url_for('main.view_cart'))

        # --- We gaan de database in schrijven ---
        
        # 5. Haal alle product-objecten op
        product_ids = [int(id) for id in cart_dict.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        
        # 6. Bereken de ECHTE totaalprijs
        total_price = Decimal(0.0) # Gebruik Decimal
        products_map = {str(p.id): p for p in products} 
        
        for product_id, quantity in cart_dict.items():
            product_price = products_map[product_id].price
            total_price += (product_price * quantity)

        # 7. AANGEPAST: Maak de 'Order' aan MET de nieuwe velden
        new_order = Order(
            user_id=session['user_id'],
            total_price=total_price,
            status='pending',
            pickup_date=pickup_date_obj,  # <-- HIER TOEGEVOEGD
            remarks=remarks               # <-- HIER TOEGEVOEGD
        )
        db.session.add(new_order)
        db.session.flush() # Vraag de ID op

        # 8. Maak de 'OrderItems' aan
        for product_id, quantity in cart_dict.items():
            product = products_map[product_id]
            
            order_item = OrderItem(
                order_id=new_order.id,      
                product_id=product.id,
                quantity=quantity,
                unit_price_at_order=product.price 
            )
            db.session.add(order_item)

        # 9. Alles is gelukt! Maak het permanent.
        db.session.commit()

        # 10. Maak het mandje leeg
        session.pop('cart', None)
        session.modified = True

        flash('Bestelling succesvol geplaatst! Je kan ze ophalen op de gekozen datum.', 'success')
        return redirect(url_for('main.index')) # Stuur naar de homepagina

    except Exception as e:
        db.session.rollback()
        print(f"FOUT bij checkout: {e}")
        flash('Er ging iets mis bij het plaatsen van je bestelling.', 'danger')
        return redirect(url_for('main.view_cart'))