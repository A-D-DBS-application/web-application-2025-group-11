import os
import time
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from decimal import Decimal
from datetime import datetime, timedelta, date
from werkzeug.utils import secure_filename
from sqlalchemy import text

# Importeer je modellen en database
from .models import Product, Profile, Order, OrderItem, Ingredient, ProductIngredient, db
# Importeer Supabase authenticatie
from . import supabase
# Importeer je AI functie
from .analytics import generate_smart_forecast

# ==============================================================================
#  CONFIGURATIE
# ==============================================================================

main = Blueprint('main', __name__)

ADMIN_EMAILS = [
    "mathisdebaene@gmail.com",
    "emile.debourdeaudhuy@icloud.com", 
    "roel.vanzele@telenet.be",
    "marieberge33@icloud.com",
    "ali.dadachev@hotmail.com"
]

# Pad naar de afbeeldingen map
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'img')

@main.context_processor
def inject_user():
    user_profile = None
    if 'user_id' in session:
        user_profile = Profile.query.get(session['user_id'])
    return dict(current_user=user_profile)


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
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    return render_template('my_orders.html', orders=orders)


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
    
    nu = datetime.now()
    min_datum_obj = date.today() + timedelta(days=1)
    if nu.hour >= 17: 
        min_datum_obj = date.today() + timedelta(days=2)
    
    min_date_str = min_datum_obj.strftime('%Y-%m-%d')
    return render_template('cart.html', cart_items=products_in_cart, total_cart_price=total_cart_price, min_date_str=min_date_str)

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
        
        product_ids = [int(id) for id in cart_dict.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        products_map = {str(p.id): p for p in products} 
        
        # ERP Check (Voorraad)
        ingredients_needed = {}
        for pid, qty in cart_dict.items():
            prod = products_map[pid]
            for rule in prod.ingredients:
                needed = rule.quantity_needed * Decimal(qty)
                if rule.ingredient.id in ingredients_needed:
                    ingredients_needed[rule.ingredient.id]['amount'] += needed
                else:
                    ingredients_needed[rule.ingredient.id] = {'obj': rule.ingredient, 'amount': needed}
        
        for ing_id, data in ingredients_needed.items():
            if data['obj'].stock_quantity < data['amount']:
                flash(f"Te weinig voorraad voor {data['obj'].name}", 'danger')
                return redirect(url_for('main.view_cart'))
        
        # Order maken
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
        
        # Voorraad afboeken
        for ing_id, data in ingredients_needed.items():
            data['obj'].stock_quantity -= data['amount']
            db.session.add(data['obj'])
            
        db.session.commit()
        session.pop('cart', None)
        flash('Bestelling succesvol geplaatst!', 'success')
        return redirect(url_for('main.index'))
        
    except Exception as e:
        db.session.rollback()
        print(e)
        return redirect(url_for('main.view_cart'))


# ==============================================================================
#  4. ADMIN: VOORRAAD & ORDERS
# ==============================================================================

@main.route('/admin/inventory')
@main.route('/admin/voorraad') # Alias voor zekerheid
def admin_inventory():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('admin_inventory.html', ingredients=ingredients)

@main.route('/admin/restock', methods=['POST'])
def restock_ingredient():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        ing = Ingredient.query.get(request.form.get('ingredient_id'))
        ing.stock_quantity += Decimal(request.form.get('amount'))
        db.session.commit()
        flash(f'Voorraad {ing.name} bijgevuld.', 'success')
    except: db.session.rollback()
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin/waste', methods=['POST'])
def waste_ingredient():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        ing = Ingredient.query.get(request.form.get('ingredient_id'))
        ing.stock_quantity -= Decimal(request.form.get('amount'))
        db.session.commit()
        flash(f'Afschrijving {ing.name} verwerkt.', 'warning')
    except: db.session.rollback()
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin/orders')
def admin_orders():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    today = date.today()
    # Vandaag
    orders_today = Order.query.filter(Order.pickup_date == today, Order.status.notin_(['picked_up', 'cancelled'])).all()
    # Historie (Limit 50)
    orders_other = Order.query.filter((Order.pickup_date != today) | (Order.status.in_(['picked_up', 'cancelled']))).order_by(Order.pickup_date.desc()).limit(50).all()
    return render_template('admin_orders.html', orders_today=orders_today, orders_other=orders_other)

@main.route('/admin/order/update/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    order = Order.query.get(order_id)
    order.status = request.form.get('status')
    db.session.commit()
    flash(f'Order #{order.id} gewijzigd.', 'success')
    return redirect(url_for('main.admin_orders'))


# ==============================================================================
#  5. ADMIN: PRODUCTEN & RECEPTEN
# ==============================================================================

@main.route('/admin/products')
def admin_products():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    products = Product.query.order_by(Product.category, Product.name).all()
    return render_template('admin_products.html', products=products)

# Handmatig Toevoegen
@main.route('/admin/product/add', methods=['POST'])
def add_product_manual():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        img_name = 'logo.png'
        file = request.files.get('image_file')
        
        # Eerst object maken
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
        
        # Foto opslaan met ID
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

# Updates (Prijs, Beschrijving, Categorie, Allergenen, Foto)
@main.route('/admin/product/update_price', methods=['POST'])
def update_product_price():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        p.price = Decimal(request.form.get('price'))
        db.session.commit()
        flash('Prijs gewijzigd.', 'success')
    except: pass
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_description', methods=['POST'])
def update_product_description():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        p.description = request.form.get('description')
        db.session.commit()
        flash('Beschrijving gewijzigd.', 'success')
    except: pass
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_category', methods=['POST'])
def update_product_category():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        p.category = request.form.get('category')
        db.session.commit()
        flash('Categorie gewijzigd.', 'success')
    except: pass
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_allergens', methods=['POST'])
def update_product_allergens():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        p = Product.query.get(request.form.get('product_id'))
        p.allergens = request.form.get('allergens')
        db.session.commit()
        flash('Allergenen gewijzigd.', 'success')
    except: pass
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/upload_image', methods=['POST'])
def upload_product_image():
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
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
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
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
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        p = Product.query.get(product_id)
        db.session.delete(p)
        db.session.commit()
        flash('Product verwijderd.', 'success')
    except: flash('Kan niet verwijderen (nog in orders?).', 'danger')
    return redirect(url_for('main.admin_products'))

# Recepten (Ingrediënten koppelen)
@main.route('/admin/product/<int:product_id>/recipe')
def manage_recipe(product_id):
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    product = Product.query.get_or_404(product_id)
    all_ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('admin_recipe.html', product=product, all_ingredients=all_ingredients)

@main.route('/admin/product/<int:product_id>/recipe/add', methods=['POST'])
def add_recipe_rule(product_id):
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    name = request.form.get('ingredient_name')
    try:
        # Zoek of maak ingrediënt
        ing = Ingredient.query.filter(Ingredient.name.ilike(name)).first()
        if not ing:
            ing = Ingredient(name=name, unit=request.form.get('unit'), stock_quantity=0)
            db.session.add(ing)
            db.session.flush()
        
        # Maak koppeling
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
    if session.get('user_email') not in ADMIN_EMAILS: return redirect(url_for('main.index'))
    try:
        rule = ProductIngredient.query.get(rule_id)
        pid = rule.product_id
        db.session.delete(rule)
        db.session.commit()
        return redirect(url_for('main.manage_recipe', product_id=pid))
    except: return redirect(url_for('main.admin_products'))


# ==============================================================================
#  6. AI FORECAST
# ==============================================================================

@main.route('/admin/forecast/refresh', methods=['POST'])
def refresh_forecast():
    if 'user_id' not in session or session.get('user_email') not in ADMIN_EMAILS:
        return redirect(url_for('main.index'))
    
    try:
        # Hier roepen we hem aan met force_refresh=True!
        generate_smart_forecast(force_refresh=True)
        flash('De voorspelling is opnieuw berekend.', 'success')
    except Exception as e:
        flash(f'Fout bij verversen: {e}', 'danger')
        
    return redirect(url_for('main.admin_forecast'))

@main.route('/admin/forecast')
def admin_forecast():
    if 'user_id' not in session or session.get('user_email') not in ADMIN_EMAILS:
        return redirect(url_for('main.index'))
    
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