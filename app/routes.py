import os
import time
import pandas as pd
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from decimal import Decimal
from datetime import datetime, timedelta, date
from werkzeug.utils import secure_filename
from sqlalchemy import text

# Importeer je modellen en database
from .models import Product, Profile, Order, OrderItem, Ingredient, ProductIngredient, AppSettings, db
# Importeer Supabase authenticatie
from . import supabase
# Importeer je AI functie
from .analytics import generate_smart_forecast

# ==============================================================================
#  CONFIGURATIE & BLUEPRINT
# ==============================================================================

main = Blueprint('main', __name__)

# Pad naar de afbeeldingen map
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'img')

# --- HULPFUNCTIES ---

def get_settings():
    """Haalt de instellingen op. Maakt ze aan als ze niet bestaan."""
    settings = AppSettings.query.first()
    if not settings:
        # Maak standaard settings als de tabel leeg is
        settings = AppSettings(
            id=1,
            welcome_title="Welkom bij Bakkerij Oewist",
            welcome_text="Waar geur, smaak en gezelligheid samenkomen!",
            deadline_hour=17
        )
        db.session.add(settings)
        db.session.commit()
    return settings

def check_admin():
    """Controleert of de huidige gebruiker admin is in de database."""
    if 'user_id' not in session: return False
    user = Profile.query.get(session['user_id'])
    return user and user.is_admin

@main.context_processor
def inject_globals():
    """Zorgt dat user én settings op ELKE pagina beschikbaar zijn."""
    user_profile = None
    if 'user_id' in session:
        user_profile = Profile.query.get(session['user_id'])
    
    return dict(
        current_user=user_profile,
        settings=get_settings()
    )


# ==============================================================================
#  1. FRONTEND (Klant)
# ==============================================================================

@main.route('/')
def index():
    category_filter = request.args.get('category')
    if category_filter and category_filter != 'alles':
        products = Product.query.filter_by(is_available=True, category=category_filter).all()
    else:
        products = Product.query.filter_by(is_available=True).all()
    
    return render_template('index.html', products=products, current_category=category_filter)

@main.route('/contact')
def contact():
    return render_template('contact.html')

@main.route('/mijn-bestellingen')
def my_orders():
    if 'user_id' not in session:
        flash('Je moet ingelogd zijn.', 'warning')
        return redirect(url_for('main.login'))
    
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    
    pagination = Order.query.filter_by(user_id=user_id)\
                            .order_by(Order.created_at.desc())\
                            .paginate(page=page, per_page=10, error_out=False)
    return render_template('my_orders.html', pagination=pagination)

# ==============================================================================
#  2. AUTHENTICATIE
# ==============================================================================

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            session['user_id'] = response.user.id
            session['access_token'] = response.session.access_token
            session['user_email'] = response.user.email
            
            # Check of admin (voor redirect gemak)
            user = Profile.query.get(response.user.id)
            if user and user.is_admin:
                return redirect(url_for('main.admin_orders'))
            
            return redirect(url_for('main.index'))
        except Exception:
            return render_template('login.html', error="E-mailadres of wachtwoord is onjuist.")
    return render_template('login.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            auth_response = supabase.auth.sign_up({
                "email": email, "password": password, "options": {"data": {"full_name": full_name}}
            })
            if auth_response.user and auth_response.user.id:
                user_id = auth_response.user.id
                # Standaard is_admin = False
                new_profile = Profile(id=user_id, full_name=full_name, is_admin=False)
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
#  3. WINKELWAGEN & CHECKOUT
# ==============================================================================

@main.route('/cart')
def view_cart():
    cart_dict = session.get('cart', {})
    products_in_cart = []
    total_cart_price = 0

    if cart_dict:
        product_ids = [int(id) for id in cart_dict.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        for product in products:
            quantity = cart_dict[str(product.id)]
            total_for_product = product.price * quantity
            total_cart_price += total_for_product
            products_in_cart.append({'product': product, 'quantity': quantity, 'total_price': total_for_product})
    
    # DYNAMISCHE DEADLINE (Uit settings!)
    settings = get_settings()
    deadline = settings.deadline_hour if settings.deadline_hour else 17
    
    nu = datetime.now()
    min_datum_obj = date.today() + timedelta(days=1)
    if nu.hour >= deadline: 
        min_datum_obj = date.today() + timedelta(days=2)
    
    min_date_str = min_datum_obj.strftime('%Y-%m-%d')

    # --- OPENINGSUREN CHECK ---
    closed_days = [] 
    if settings.weekly_schedule_json:
        try:
            schedule = json.loads(settings.weekly_schedule_json)
            for i in range(7):
                if schedule.get(str(i), {}).get('closed'):
                    # Python 0=Ma, JS 0=Zo. Conversie:
                    js_day = i + 1 if i < 6 else 0
                    closed_days.append(js_day)
        except: pass

    return render_template('cart.html', 
                           cart_items=products_in_cart, 
                           total_cart_price=total_cart_price, 
                           min_date_str=min_date_str,
                           closed_days=closed_days)

@main.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    try:
        quantity = int(request.form.get('quantity', '1'))
        if quantity < 1: quantity = 1
    except: quantity = 1
    
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + quantity
    session['cart'] = cart
    session.modified = True 
    flash(f'Toegevoegd aan mandje!', 'success')
    return redirect(url_for('main.index'))

@main.route('/cart/decrease/<int:product_id>', methods=['POST'])
def decrease_from_cart(product_id):
    cart = session.get('cart', {})
    pid = str(product_id)
    if pid in cart:
        if cart[pid] > 1:
            cart[pid] -= 1
        else:
            del cart[pid]
        session['cart'] = cart
        session.modified = True
    return redirect(url_for('main.view_cart'))

@main.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        session['cart'] = cart
        session.modified = True
    return redirect(url_for('main.view_cart'))

@main.route('/checkout', methods=['POST'])
def checkout():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    cart_dict = session.get('cart', {})
    if not cart_dict: return redirect(url_for('main.view_cart'))
    
    pickup_date_str = request.form.get('pickup_date')
    
    try:
        pickup_date_obj = datetime.strptime(pickup_date_str, '%Y-%m-%d').date()
        
        # --- LOGICA SPRINT 1 PUNT 4: VOORRAAD CHECK ---
        # Als bestelling > 3 dagen in toekomst is -> GEEN voorraad check (bakker kan inkopen)
        # Als bestelling <= 3 dagen is -> WEL voorraad check
        
        days_until_pickup = (pickup_date_obj - date.today()).days
        should_check_stock = days_until_pickup <= 3
        
        product_ids = [int(id) for id in cart_dict.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        products_map = {str(p.id): p for p in products} 
        
        # Bereken benodigde ingrediënten
        ingredients_needed = {}
        for pid, qty in cart_dict.items():
            prod = products_map[pid]
            for rule in prod.ingredients:
                needed = rule.quantity_needed * Decimal(qty)
                if rule.ingredient.id in ingredients_needed:
                    ingredients_needed[rule.ingredient.id]['amount'] += needed
                else:
                    ingredients_needed[rule.ingredient.id] = {'obj': rule.ingredient, 'amount': needed}
        
        # Voer de check ALLEEN uit als het kort dag is
        if should_check_stock:
            for ing_id, data in ingredients_needed.items():
                if data['obj'].stock_quantity < data['amount']:
                    flash(f"Te weinig voorraad voor {data['obj'].name}. Kies een latere datum (>3 dagen) of neem een ander product.", 'danger')
                    return redirect(url_for('main.view_cart'))
        
        # --- ORDER AANMAKEN ---
        total_price = sum(products_map[pid].price * Decimal(qty) for pid, qty in cart_dict.items())
        new_order = Order(
            user_id=session['user_id'], 
            total_price=total_price, 
            status='pending', 
            pickup_date=pickup_date_obj, 
            remarks=request.form.get('remarks')
        )
        db.session.add(new_order)
        db.session.flush()
        
        # Items toevoegen
        for pid, qty in cart_dict.items():
            db.session.add(OrderItem(order_id=new_order.id, product_id=pid, quantity=qty, unit_price_at_order=products_map[pid].price))
        
        # Voorraad afboeken (DIT GEBEURT ALTIJD, ook als voorraad negatief wordt)
        # Hierdoor ziet de admin in 'Inventory' dat hij in de min staat en moet bijbestellen.
        for ing_id, data in ingredients_needed.items():
            data['obj'].stock_quantity -= data['amount']
            db.session.add(data['obj'])
            
        db.session.commit()
        session.pop('cart', None)
        
        if not should_check_stock:
            flash('Bestelling succesvol geplaatst!', 'success')
        else:
            flash('Bestelling succesvol geplaatst!', 'success')
            
        return redirect(url_for('main.index'))
        
    except Exception as e:
        db.session.rollback()
        print(e)
        flash('Er ging iets mis met de bestelling.', 'danger')
        return redirect(url_for('main.view_cart'))


# ==============================================================================
#  4. ADMIN: SETTINGS (NIEUW)
# ==============================================================================

@main.route('/admin/settings')
def admin_settings():
    if not check_admin(): return redirect(url_for('main.index'))
    
    admins = Profile.query.filter_by(is_admin=True).all()
    users = Profile.query.filter_by(is_admin=False).all()
    
    # Load schedule
    settings = get_settings()
    try:
        schedule = json.loads(settings.weekly_schedule_json)
    except:
        schedule = {str(i): {'closed': False, 'text': '08:00 - 17:00'} for i in range(7)}

    days_names = ['Maandag', 'Dinsdag', 'Woensdag', 'Donderdag', 'Vrijdag', 'Zaterdag', 'Zondag']

    return render_template('admin_settings.html', admins=admins, users=users, schedule=schedule, days_names=days_names)

@main.route('/admin/settings/update', methods=['POST'])
def update_settings():
    if not check_admin(): return redirect(url_for('main.index'))
    
    s = get_settings()
    s.welcome_title = request.form.get('welcome_title')
    s.welcome_text = request.form.get('welcome_text')
    s.intro_text = request.form.get('intro_text')
    try:
        s.deadline_hour = int(request.form.get('deadline_hour'))
    except: pass
    
    s.phone_number = request.form.get('phone_number')
    s.email_address = request.form.get('email_address')
    s.address_text = request.form.get('address_text')
    
    # Openingsuren JSON bouwen
    new_schedule = {}
    formatted_text = []
    short_names = ['Ma', 'Di', 'Wo', 'Do', 'Vr', 'Za', 'Zo']
    
    for i in range(7):
        is_closed = request.form.get(f'day_{i}_closed') == 'on'
        text_hours = request.form.get(f'day_{i}_text')
        new_schedule[str(i)] = {'closed': is_closed, 'text': text_hours}
        
        status = "GESLOTEN" if is_closed else text_hours
        formatted_text.append(f"{short_names[i]}: {status}")

    s.weekly_schedule_json = json.dumps(new_schedule)
    s.opening_hours = "\n".join(formatted_text) # Fallback tekst
    
    db.session.commit()
    flash('Instellingen opgeslagen.', 'success')
    return redirect(url_for('main.admin_settings'))

@main.route('/admin/settings/toggle_admin', methods=['POST'])
def toggle_admin():
    if not check_admin(): return redirect(url_for('main.index'))
    
    user_id = request.form.get('user_id')
    action = request.form.get('action')
    
    user = Profile.query.get(user_id)
    if user:
        if action == 'add':
            user.is_admin = True
            flash(f'{user.full_name} is nu Admin.', 'success')
        elif action == 'remove':
            if str(user.id) == session['user_id']:
                flash('Je kan jezelf niet ontslaan!', 'danger')
            else:
                user.is_admin = False
                flash(f'{user.full_name} is geen Admin meer.', 'warning')
        db.session.commit()
    
    return redirect(url_for('main.admin_settings'))


# ==============================================================================
#  5. ADMIN: VOORRAAD & ORDERS
# ==============================================================================

@main.route('/admin/inventory')
@main.route('/admin/voorraad')
def admin_inventory():
    if not check_admin(): return redirect(url_for('main.index'))
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('admin_inventory.html', ingredients=ingredients)

@main.route('/admin/restock', methods=['POST'])
def restock_ingredient():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        ing = Ingredient.query.get(request.form.get('ingredient_id'))
        ing.stock_quantity += Decimal(request.form.get('amount'))
        db.session.commit()
        flash(f'Voorraad {ing.name} bijgevuld.', 'success')
    except: db.session.rollback()
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin/waste', methods=['POST'])
def waste_ingredient():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        ing = Ingredient.query.get(request.form.get('ingredient_id'))
        ing.stock_quantity -= Decimal(request.form.get('amount'))
        db.session.commit()
        flash(f'Afschrijving {ing.name} verwerkt.', 'warning')
    except: db.session.rollback()
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin/orders')
def admin_orders():
    if not check_admin(): return redirect(url_for('main.index'))
    
    today = date.today()
    
    # 1. Haal paginanummers op uit de URL (standaard 1)
    page_future = request.args.get('page_future', 1, type=int)
    page_history = request.args.get('page_history', 1, type=int)
    
    # 2. VANDAAG (Alles tonen, geen limiet, dit is prioriteit)
    orders_today = Order.query.filter(
        Order.pickup_date == today, 
        Order.status.notin_(['picked_up', 'cancelled'])
    ).all()
    
    # 3. TOEKOMST (Met Paginering!)
    pagination_future = Order.query.filter(
        Order.pickup_date > today
    ).order_by(Order.pickup_date.asc()).paginate(page=page_future, per_page=15, error_out=False)
    
    # 4. HISTORIE (Met Paginering!)
    pagination_history = Order.query.filter(
        (Order.pickup_date < today) | 
        ((Order.pickup_date == today) & (Order.status.in_(['picked_up', 'cancelled'])))
    ).order_by(Order.pickup_date.desc()).paginate(page=page_history, per_page=15, error_out=False)
    
    return render_template('admin_orders.html', 
                           orders_today=orders_today, 
                           pagination_future=pagination_future,   # <--- Nieuw object
                           pagination_history=pagination_history) # <--- Hernoemd voor duidelijkheid

@main.route('/admin/order/update/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    if not check_admin(): return redirect(url_for('main.index'))
    order = Order.query.get(order_id)
    order.status = request.form.get('status')
    db.session.commit()
    flash(f'Order #{order.id} gewijzigd.', 'success')
    return redirect(url_for('main.admin_orders'))


# ==============================================================================
#  6. ADMIN: PRODUCTEN & RECEPTEN
# ==============================================================================

@main.route('/admin/products')
def admin_products():
    if not check_admin(): return redirect(url_for('main.index'))
    products = Product.query.order_by(Product.category, Product.name).all()
    return render_template('admin_products.html', products=products)

@main.route('/admin/product/add', methods=['POST'])
def add_product_manual():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        img_name = 'logo.png'
        file = request.files.get('image_file')
        
        new_prod = Product(
            name=request.form.get('name'), 
            description=request.form.get('description'),
            price=Decimal(request.form.get('price')), 
            category=request.form.get('category'),
            allergens=request.form.get('allergens'),
            image_url=img_name
        )
        db.session.add(new_prod)
        db.session.flush()
        
        if file and file.filename != '':
            fname = secure_filename(file.filename)
            unique = f"product_{new_prod.id}_{int(time.time())}_{fname}"
            file.save(os.path.join(UPLOAD_FOLDER, unique))
            new_prod.image_url = unique
            
        db.session.commit()
        flash('Product toegevoegd.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fout: {e}', 'danger')
    return redirect(url_for('main.admin_products'))

# --- Updates ---
@main.route('/admin/product/update_price', methods=['POST'])
def update_product_price():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        p.price = Decimal(request.form.get('price'))
        db.session.commit()
        flash('Prijs gewijzigd.', 'success')
    except: pass
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_description', methods=['POST'])
def update_product_description():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        p.description = request.form.get('description')
        db.session.commit()
        flash('Beschrijving gewijzigd.', 'success')
    except: pass
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_category', methods=['POST'])
def update_product_category():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        p.category = request.form.get('category')
        db.session.commit()
        flash('Categorie gewijzigd.', 'success')
    except: pass
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_allergens', methods=['POST'])
def update_product_allergens():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        p.allergens = request.form.get('allergens')
        db.session.commit()
        flash('Allergenen gewijzigd.', 'success')
    except: pass
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/upload_image', methods=['POST'])
def upload_product_image():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        file = request.files.get('image_file')
        if file:
            fname = secure_filename(file.filename)
            unique = f"product_{p.id}_{int(time.time())}_{fname}"
            file.save(os.path.join(UPLOAD_FOLDER, unique))
            p.image_url = unique
            db.session.commit()
            flash('Foto gewijzigd.', 'success')
    except: flash('Fout bij uploaden.', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/import', methods=['POST'])
def import_products_excel():
    if not check_admin(): return redirect(url_for('main.index'))
    file = request.files.get('file')
    if file:
        try:
            df = pd.read_excel(file)
            count = 0
            for index, row in df.iterrows():
                if not Product.query.filter_by(name=row['name']).first():
                    db.session.add(Product(
                        name=row['name'], description=row.get('description',''),
                        price=Decimal(row['price']), category=row['category'].lower(),
                        allergens=row.get('allergens',''), image_url='logo.png'
                    ))
                    count += 1
            db.session.commit()
            flash(f'{count} producten geïmporteerd!', 'success')
        except: flash('Fout in Excel.', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/delete/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        p = Product.query.get(product_id)
        db.session.delete(p)
        db.session.commit()
        flash('Product verwijderd.', 'success')
    except: flash('Kan niet verwijderen (nog in orders?).', 'danger')
    return redirect(url_for('main.admin_products'))

# --- Recepten ---
@main.route('/admin/product/<int:product_id>/recipe')
def manage_recipe(product_id):
    if not check_admin(): return redirect(url_for('main.index'))
    product = Product.query.get_or_404(product_id)
    all_ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('admin_recipe.html', product=product, all_ingredients=all_ingredients)

@main.route('/admin/product/<int:product_id>/recipe/add', methods=['POST'])
def add_recipe_rule(product_id):
    if not check_admin(): return redirect(url_for('main.index'))
    name = request.form.get('ingredient_name')
    try:
        ing = Ingredient.query.filter(Ingredient.name.ilike(name)).first()
        if not ing:
            ing = Ingredient(name=name, unit=request.form.get('unit'), stock_quantity=0)
            db.session.add(ing)
            db.session.flush()
        
        db.session.add(ProductIngredient(
            product_id=product_id, 
            ingredient_id=ing.id, 
            quantity_needed=Decimal(request.form.get('quantity'))
        ))
        db.session.commit()
        flash('Ingrediënt toegevoegd.', 'success')
    except: db.session.rollback()
    return redirect(url_for('main.manage_recipe', product_id=product_id))

@main.route('/admin/product/recipe/delete/<int:rule_id>', methods=['POST'])
def delete_recipe_rule(rule_id):
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        rule = ProductIngredient.query.get(rule_id)
        pid = rule.product_id
        db.session.delete(rule)
        db.session.commit()
        return redirect(url_for('main.manage_recipe', product_id=pid))
    except: return redirect(url_for('main.admin_products'))


# ==============================================================================
#  7. AI FORECAST
# ==============================================================================

@main.route('/admin/forecast/refresh', methods=['POST'])
def refresh_forecast():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        generate_smart_forecast(force_refresh=True)
        flash('Voorspelling ververst.', 'success')
    except Exception as e:
        flash(f'Fout: {e}', 'danger')
    return redirect(url_for('main.admin_forecast'))

@main.route('/admin/forecast')
def admin_forecast():
    if not check_admin(): return redirect(url_for('main.index'))
    try:
        forecast, shop_tomorrow, shop_week, start, end = generate_smart_forecast()
    except Exception as e:
        print(f"Error AI: {e}")
        forecast, shop_tomorrow, shop_week = [], [], []
        start, end = date.today(), date.today()

    return render_template('admin_forecast.html', 
                           forecast=forecast, 
                           shop_tomorrow=shop_tomorrow, 
                           shop_week=shop_week, 
                           start_date=start, 
                           end_date=end)