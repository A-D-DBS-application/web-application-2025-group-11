from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from decimal import Decimal
from datetime import datetime, timedelta, date
from .models import Product, Profile, Order, OrderItem, Ingredient, db
from . import supabase

# ==============================================================================
#  CONFIGURATIE & BLUEPRINT
# ==============================================================================

main = Blueprint('main', __name__)

ADMIN_EMAILS = [
    "mathisdebaene@gmail.com",
    "emile.debourdeaudhuy@icloud.com", 
    "roel.vanzele@telenet.be",
    "marieberge33@icloud.com",
    "ali.dadachev@hotmail.com"
]

# Deze functie zorgt ervoor dat 'current_user' op elke pagina beschikbaar is
@main.context_processor
def inject_user():
    user_profile = None
    if 'user_id' in session:
        user_profile = Profile.query.get(session['user_id'])
    return dict(current_user=user_profile)


# ==============================================================================
#  1. ALGEMENE PAGINA'S (Home, Contact, Profiel)
# ==============================================================================

@main.route('/')
def index():
    """De homepage met producten en filter."""
    category_filter = request.args.get('category')

    if category_filter and category_filter != 'alles':
        # Filter op specifieke categorie uit de database
        products = Product.query.filter_by(is_available=True, category=category_filter).all()
    else:
        # Toon alles
        products = Product.query.filter_by(is_available=True).all()
    
    return render_template('index.html', products=products, current_category=category_filter)

@main.route('/contact')
def contact():
    return render_template('contact.html')

@main.route('/mijn-bestellingen')
def my_orders():
    """Overzicht van bestellingen voor de ingelogde gebruiker."""
    if 'user_id' not in session:
        flash('Je moet ingelogd zijn om je bestellingen te zien.', 'warning')
        return redirect(url_for('main.login'))
    
    user_id = session['user_id']
    # Sorteer op nieuwste eerst
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    
    return render_template('my_orders.html', orders=orders)


# ==============================================================================
#  2. AUTHENTICATIE (Login, Register, Logout)
# ==============================================================================

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            # Inloggen via Supabase
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            # Sessie opslaan
            session['user_id'] = response.user.id
            session['access_token'] = response.session.access_token
            session['user_email'] = response.user.email
            return redirect(url_for('main.index'))

        except Exception as e:
            return render_template('login.html', error="E-mailadres of wachtwoord is onjuist.")

    return render_template('login.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            # 1. Account maken in Supabase Auth
            auth_response = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {"data": {"full_name": full_name}}
            })

            # 2. Profiel opslaan in lokale database
            if auth_response.user and auth_response.user.id:
                user_id = auth_response.user.id
                new_profile = Profile(id=user_id, full_name=full_name)
                db.session.add(new_profile)
                db.session.commit()
                return redirect(url_for('main.index'))

        except Exception as e:
            db.session.rollback()
            return render_template('register.html', error=str(e))

    return render_template('register.html')

@main.route('/logout')
def logout():
    supabase.auth.sign_out()
    session.clear()
    return redirect(url_for('main.index'))


# ==============================================================================
#  3. WINKELWAGEN LOGICA
# ==============================================================================

@main.route('/cart')
def view_cart():
    """Toont de winkelwagen en berekent de eerstvolgende ophaaldatum."""
    cart_dict = session.get('cart', {})
    products_in_cart = []
    total_cart_price = 0

    if cart_dict:
        # Haal alle producten in één keer op uit de DB
        product_ids = [int(id) for id in cart_dict.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        
        for product in products:
            quantity = cart_dict[str(product.id)]
            total_for_product = product.price * quantity
            total_cart_price += total_for_product
            
            products_in_cart.append({
                'product': product,
                'quantity': quantity,
                'total_price': total_for_product
            })

    # --- 17:00 REGEL LOGICA ---
    nu = datetime.now()
    min_datum_obj = date.today() + timedelta(days=1) # Standaard: morgen
    
    if nu.hour >= 17:
        min_datum_obj = date.today() + timedelta(days=2) # Na 17u: overmorgen
    
    min_date_str = min_datum_obj.strftime('%Y-%m-%d')

    return render_template('cart.html', 
                           cart_items=products_in_cart, 
                           total_cart_price=total_cart_price,
                           min_date_str=min_date_str)

@main.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    try:
        quantity = int(request.form.get('quantity', '1'))
        if quantity < 1: quantity = 1
    except (ValueError, TypeError):
        quantity = 1
    
    cart = session.get('cart', {})
    current_quantity = cart.get(str(product_id), 0)
    cart[str(product_id)] = current_quantity + quantity
    
    session['cart'] = cart
    session.modified = True 

    product = Product.query.get_or_404(product_id) 
    flash(f'{quantity}x {product.name} toegevoegd aan je mandje!', 'success')
    return redirect(url_for('main.index'))

@main.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        session['cart'] = cart
        session.modified = True
        flash(f'Product verwijderd.', 'success')
    return redirect(url_for('main.view_cart'))


# ==============================================================================
#  4. CHECKOUT & ERP SYSTEEM (De complexe logica)
# ==============================================================================

@main.route('/checkout', methods=['POST'])
def checkout():
    # --- STAP 1: Basis Validatie ---
    if 'user_id' not in session:
        flash('Je moet ingelogd zijn om af te rekenen.', 'danger')
        return redirect(url_for('main.login'))

    cart_dict = session.get('cart', {})
    if not cart_dict:
        flash('Je mandje is leeg.', 'warning')
        return redirect(url_for('main.view_cart'))
    
    pickup_date_str = request.form.get('pickup_date')
    remarks = request.form.get('remarks')

    try:
        if pickup_date_str:
            pickup_date_obj = datetime.strptime(pickup_date_str, '%Y-%m-%d').date()
        else:
            flash('Geen ophaaldatum geselecteerd.', 'danger')
            return redirect(url_for('main.view_cart'))

        # Haal producten op voor berekeningen
        product_ids = [int(id) for id in cart_dict.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        products_map = {str(p.id): p for p in products} 

        # --- STAP 2: ERP CHECK (Voorraad berekenen) ---
        # We tellen alle ingrediënten van alle producten in het mandje op
        ingredients_needed = {}
        
        for product_id, quantity in cart_dict.items():
            product = products_map[str(product_id)]
            for recept_regel in product.ingredients:
                ingredient = recept_regel.ingredient
                nodig_voor_dit_product = recept_regel.quantity_needed * Decimal(quantity)

                if ingredient.id in ingredients_needed:
                    ingredients_needed[ingredient.id]['amount'] += nodig_voor_dit_product
                else:
                    ingredients_needed[ingredient.id] = {
                        'object': ingredient,
                        'amount': nodig_voor_dit_product
                    }

        # Check of er genoeg is van elk ingrediënt
        for ing_id, data in ingredients_needed.items():
            ingredient = data['object']
            if ingredient.stock_quantity < data['amount']:
                flash(f"Helaas, we hebben niet genoeg {ingredient.name} voor deze bestelling.", 'danger')
                return redirect(url_for('main.view_cart'))
        
        # --- STAP 3: Order Aanmaken ---
        total_price = Decimal(0.0) 
        for product_id, quantity in cart_dict.items():
            total_price += (products_map[product_id].price * Decimal(quantity))

        new_order = Order(
            user_id=session['user_id'],
            total_price=total_price,
            status='pending',
            pickup_date=pickup_date_obj,
            remarks=remarks
        )
        db.session.add(new_order)
        db.session.flush() # Zorgt dat new_order.id beschikbaar komt

        # Orderregels toevoegen
        for product_id, quantity in cart_dict.items():
            product = products_map[product_id]
            order_item = OrderItem(
                order_id=new_order.id,      
                product_id=product.id,
                quantity=quantity,
                unit_price_at_order=product.price 
            )
            db.session.add(order_item)

        # --- STAP 4: Voorraad Afboeken (ERP Update) ---
        for ing_id, data in ingredients_needed.items():
            ingredient = data['object']
            ingredient.stock_quantity -= data['amount']
            db.session.add(ingredient)
        
        # Alles opslaan
        db.session.commit()
        
        # Mandje legen
        session.pop('cart', None)
        session.modified = True

        flash('Bestelling succesvol geplaatst!', 'success')
        return redirect(url_for('main.index'))

    except Exception as e:
        db.session.rollback()
        print(f"FOUT bij checkout: {e}")
        flash('Er ging iets mis bij het plaatsen van je bestelling.', 'danger')
        return redirect(url_for('main.view_cart'))


# ==============================================================================
#  5. ADMIN PAGINA'S
# ==============================================================================

@main.route('/admin/voorraad')
def admin_inventory():
    if 'user_id' not in session:
        flash('Je moet ingelogd zijn.', 'warning')
        return redirect(url_for('main.login'))

    if session.get('user_email') not in ADMIN_EMAILS:
        flash('Geen toegang! Alleen de beheerder mag hier komen.', 'danger')
        return redirect(url_for('main.index'))

    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('admin_inventory.html', ingredients=ingredients)

@main.route('/admin/restock', methods=['POST'])
def restock_ingredient():
    if 'user_id' not in session or session.get('user_email') not in ADMIN_EMAILS:
        return redirect(url_for('main.index'))

    ingredient_id = request.form.get('ingredient_id')
    amount = request.form.get('amount')

    try:
        ingredient = Ingredient.query.get(ingredient_id)
        if ingredient and amount:
            ingredient.stock_quantity += Decimal(amount)
            db.session.commit()
            flash(f'Voorraad van {ingredient.name} bijgewerkt!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Fout bij bijwerken.', 'danger')
        print(f"FOUT: {e}")

    return redirect(url_for('main.admin_inventory'))