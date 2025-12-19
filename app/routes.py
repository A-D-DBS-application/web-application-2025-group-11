import os
import time
import pandas as pd
import json
from functools import wraps 
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, date
from werkzeug.utils import secure_filename
from sqlalchemy import func, text
from sqlalchemy import or_
from icalendar import Calendar, Event

# Importeer je modellen en database
from .models import Product, Profile, Order, OrderItem, Ingredient, ProductIngredient, AppSettings, db
# Importeer Supabase authenticatie
from . import supabase
# Importeer Algoritmen
from .analytics import generate_smart_forecast
from .analytics import get_cart_recommendations

# ==============================================================================
#  CONFIGURATIE & BLUEPRINT
# ==============================================================================

main = Blueprint('main', __name__)

# --- HULPFUNCTIES & DECORATORS ---

def get_settings():
    """Haalt de instellingen op. Maakt ze aan als ze niet bestaan."""
    settings = AppSettings.query.first()
    if not settings:
        settings = AppSettings(
            id=1,
            welcome_title="Welkom bij Bakkerij Oewist",
            welcome_text="Waar geur, smaak en gezelligheid samenkomen!",
            deadline_hour=17
        )
        db.session.add(settings)
        db.session.commit()
    return settings

def get_categories():
    """Haalt categorieën uit DB of geeft defaults terug."""
    settings = get_settings()
    defaults = ["brood", "pistolets", "koffiekoeken"]
    
    if settings.product_categories_json:
        try:
            return json.loads(settings.product_categories_json)
        except Exception as e:
            print(f"⚠️ Error parsing categories JSON: {e}")
            return defaults
    return defaults

def upload_image_to_supabase(file):
    """Upload afbeelding naar Supabase Storage Bucket."""
    if not file: return None
    try:
        filename = secure_filename(file.filename)
        file_path = f"{int(time.time())}_{filename}"
        file_content = file.read()
        
        bucket_name = "product-images"
        res = supabase.storage.from_(bucket_name).upload(
            path=file_path, 
            file=file_content, 
            file_options={"content-type": file.mimetype}
        )
        return supabase.storage.from_(bucket_name).get_public_url(file_path)
    except Exception as e:
        print(f"❌ Upload Error: {e}")
        return None

# --- ADMIN DECORATOR ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Je moet inloggen om deze pagina te bekijken.', 'warning')
            return redirect(url_for('main.login'))
        
        user = Profile.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Geen toegang: Alleen voor beheerders.', 'danger')
            return redirect(url_for('main.index'))
           
        return f(*args, **kwargs)
    return decorated_function

# --- TEMPLATE FILTERS ---
@main.app_template_filter('product_img')
def product_img_filter(image_url):
    if not image_url: 
        return url_for('static', filename='img/logo.png')
    if image_url.startswith('http'):
        return image_url
    return url_for('static', filename='img/' + image_url)


# --- CONTEXT PROCESSOR (Globale Variabelen) ---
@main.context_processor
def inject_global_vars():
    cart_count = 0
    if 'cart' in session:
        cart_count = sum(session['cart'].values())
    
    user_profile = None
    if 'user_id' in session:
        user_profile = Profile.query.get(session['user_id'])

    settings = get_settings()
    current_year = datetime.now().year
    today_date = date.today()
    
    categories = get_categories()

    return dict(
        cart_item_count=cart_count,
        current_user=user_profile,
        settings=settings,
        current_year=current_year,
        today=today_date,
        categories=categories
    )

@main.app_errorhandler(404)
def page_not_found(e):
    settings = get_settings()
    return render_template('404.html', settings=settings), 404

@main.app_errorhandler(500)
def internal_server_error(e):
    settings = get_settings()
    print(f"🔥 500 ERROR: {e}")
    db.session.rollback()
    return render_template('500.html', settings=settings), 500


# ==============================================================================
#  1. FRONTEND (Klant)
# ==============================================================================

@main.route('/')
def index():
    categories_list = get_categories()
    
    category_filter = request.args.get('category')
    query = Product.query.filter_by(is_available=True)
    
    if category_filter and category_filter != 'alles':
        query = query.filter_by(category=category_filter)
    
    all_products = query.order_by(Product.name).all()
    
    visible_products = []
    today_str = date.today().strftime('%m-%d')
    
    for p in all_products:
        if not p.season_start or not p.season_end:
            visible_products.append(p)
        else:
            start = p.season_start
            end = p.season_end
            if start <= end:
                if start <= today_str <= end: visible_products.append(p)
            else:
                if today_str >= start or today_str <= end: visible_products.append(p)
    
    return render_template('index.html', 
                           products=visible_products, 
                           current_category=category_filter,
                           categories=categories_list)

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
    
    f_date = request.args.get('filter_date')
    f_product = request.args.get('filter_product')
    f_price = request.args.get('filter_price')
    
    query = Order.query.filter_by(user_id=user_id)
    
    if f_date:
        try:
            date_obj = datetime.strptime(f_date, '%Y-%m-%d').date()
            query = query.filter(Order.pickup_date == date_obj)
        except ValueError: 
            pass 

    if f_product:
        query = query.join(OrderItem).join(Product).filter(Product.name.ilike(f"%{f_product}%")).distinct()

    if f_price:
        try:
            query = query.filter(Order.total_price >= Decimal(f_price))
        except (ValueError, InvalidOperation): 
            pass

    pagination = query.order_by(Order.pickup_date.desc()).paginate(page=page, per_page=5, error_out=False)
    
    current_filters = {
        'date': f_date or '',
        'product': f_product or '',
        'price': f_price or ''
    }
    
    return render_template('my_orders.html', pagination=pagination, filters=current_filters)

@main.route('/order/cancel/<int:order_id>', methods=['POST'])
def cancel_my_order(order_id):
    if 'user_id' not in session: return redirect(url_for('main.login'))
    
    try:
        order = Order.query.get_or_404(order_id)
        
        if str(order.user_id) != session['user_id']:
            flash("Je kunt alleen je eigen bestellingen annuleren.", "danger")
            return redirect(url_for('main.my_orders'))
        
        if order.status != 'pending':
            flash("Deze bestelling kan niet meer geannuleerd worden.", "warning")
            return redirect(url_for('main.my_orders'))

        settings = get_settings()
        limit_days = settings.cancellation_days if settings.cancellation_days is not None else 2
        
        days_difference = (order.pickup_date - date.today()).days
        
        if days_difference >= limit_days:
            order.status = 'cancelled'
            db.session.commit()
            flash(f'Bestelling #{order.id} is succesvol geannuleerd.', 'success')
        else:
            flash(f'Annuleren kan tot {limit_days} dagen voor ophaaldatum. Neem telefonisch contact op.', 'warning')
            
    except Exception as e:
        db.session.rollback()
        print(f"❌ Cancel error: {e}")
        flash("Er ging iets mis bij het annuleren.", "danger")
        
    return redirect(url_for('main.my_orders'))

@main.route('/order/<int:order_id>/ical')
def download_ical(order_id):
    order = Order.query.get_or_404(order_id)
    
    cal = Calendar()
    cal.add('prodid', '-//Bakkerij Oewist//mxm.dk//')
    cal.add('version', '2.0')

    event = Event()
    event.add('summary', f'Ophalen bestelling #{order.id} - Bakkerij Oewist')
    
    if order.pickup_date:
        start_time = datetime.combine(order.pickup_date, datetime.min.time()) + timedelta(hours=10)
    else:
        start_time = datetime.now() + timedelta(days=1)

    end_time = start_time + timedelta(minutes=30)
    
    event.add('dtstart', start_time)
    event.add('dtend', end_time)
    event.add('description', 'Je verse broodjes staan klaar! Vergeet ze niet op te halen.')
    event.add('location', 'Bakkerij Oewist')

    cal.add_component(event)

    response = make_response(cal.to_ical())
    response.headers["Content-Disposition"] = f"attachment; filename=order_{order_id}.ics"
    response.headers["Content-Type"] = "text/calendar"
    
    return response


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
            
            user = Profile.query.get(response.user.id)
            if user and user.is_admin:
                return redirect(url_for('main.admin_dashboard'))
            
            return redirect(url_for('main.index'))
        except Exception as e:
            err_msg = str(e)
            print(f"Login error: {err_msg}")
            
            if "Email not confirmed" in err_msg:
                error = "Bevestig eerst je e-mailadres via de link die je hebt ontvangen."
            elif "Invalid login credentials" in err_msg:
                error = "E-mailadres of wachtwoord is onjuist."
            else:
                error = "Inloggen mislukt. Probeer het later opnieuw."
                
            return render_template('login.html', error=error)
    return render_template('login.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            # 1. Gebruiker aanmaken in Supabase Auth
            auth_response = supabase.auth.sign_up({
                "email": email, 
                "password": password, 
                "options": {"data": {"full_name": full_name}}
            })
            
            # 2. Gebruiker OOK opslaan in eigen 'profiles' tabel
            if auth_response.user and auth_response.user.id:
                user_id = auth_response.user.id
                
                new_profile = Profile(
                    id=user_id, 
                    full_name=full_name, 
                    email=email,
                    is_admin=False
                )
                
                db.session.add(new_profile)
                db.session.commit()
                
                return redirect(url_for('main.index'))
                
        except Exception as e:
            db.session.rollback()
            err_msg = str(e)
            print(f"Registratie fout: {err_msg}")
            
            if "User already registered" in err_msg or "already exists" in err_msg:
                dutch_error = "Er bestaat al een account met dit e-mailadres."
            elif "Password should be at least" in err_msg:
                dutch_error = "Het wachtwoord moet minimaal 6 tekens lang zijn."
            else:
                dutch_error = "Er is iets misgegaan. Controleer je gegevens."
                
            return render_template('register.html', error=dutch_error)
            
    return render_template('register.html')

@main.route('/logout')
def logout():
    supabase.auth.sign_out()
    session.clear()
    return redirect(url_for('main.index'))

@main.route('/profiel', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session: return redirect(url_for('main.login'))
    
    user = Profile.query.get(session['user_id'])
    
    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name')
            phone = request.form.get('phone_number')
            
            if full_name: user.full_name = full_name
            if phone: user.phone_number = phone
            
            new_password = request.form.get('new_password')
            if new_password and len(new_password) > 0:
                if len(new_password) < 6:
                    flash('Nieuw wachtwoord moet minstens 6 tekens zijn.', 'danger')
                else:
                    supabase.auth.update_user({"password": new_password})
                    flash('Profiel én wachtwoord gewijzigd!', 'success')
            else:
                flash('Profielgegevens opgeslagen.', 'success')
                
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Profiel update fout: {e}")
            flash('Kon profiel niet opslaan.', 'danger')
            
        return redirect(url_for('main.profile'))

    return render_template('profile.html', user=user)


# ==============================================================================
#  3. WINKELWAGEN & CHECKOUT
# ==============================================================================

@main.route('/cart')
def view_cart():
    cart_dict = session.get('cart', {})
    products_in_cart = []
    total_cart_price = 0
    
    current_ids = []
    shortage_ingredients = [] 

    if cart_dict:
        product_ids = [int(id) for id in cart_dict.keys()]
        current_ids = product_ids 
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        
        ingredients_needed = {}

        for product in products:
            quantity = cart_dict[str(product.id)]
            total_for_product = product.price * quantity
            total_cart_price += total_for_product
            products_in_cart.append({'product': product, 'quantity': quantity, 'total_price': total_for_product})
            
            for rule in product.ingredients:
                needed = rule.quantity_needed * Decimal(quantity)
                if rule.ingredient.id in ingredients_needed:
                    ingredients_needed[rule.ingredient.id]['amount'] += needed
                else:
                    ingredients_needed[rule.ingredient.id] = {'obj': rule.ingredient, 'amount': needed}
        
        for ing_id, data in ingredients_needed.items():
            if data['obj'].stock_quantity < data['amount']:
                shortage_ingredients.append(data['obj'].name)

    # --- Suggesties Ophalen ---
    recommendations = []
    if current_ids:
        try:
            suggested_ids = get_cart_recommendations(current_ids)
            if suggested_ids:
                recommendations = Product.query.filter(Product.id.in_(suggested_ids)).all()
        except Exception as e:
            print(f"Recommendation Error: {e}")

    # --- Settings ---
    settings = get_settings()
    deadline = settings.deadline_hour if settings.deadline_hour else 17
    
    nu = datetime.now()
    # Minimaal 1 dag in de toekomst (of 2 na deadline)
    min_datum_obj = date.today() + timedelta(days=1)
    if nu.hour >= deadline: 
        min_datum_obj = date.today() + timedelta(days=2)
    
    min_date_str = min_datum_obj.strftime('%Y-%m-%d')

    closed_days = [] 
    if settings.weekly_schedule_json:
        try:
            schedule = json.loads(settings.weekly_schedule_json)
            for i in range(7):
                if schedule.get(str(i), {}).get('closed'):
                    js_day = i + 1 if i < 6 else 0
                    closed_days.append(js_day)
        except Exception as e: 
            print(f"Error parsing weekly schedule: {e}")
    
    specific_closed_dates = []
    if settings.closed_dates_json:
        try:
            specific_closed_dates = json.loads(settings.closed_dates_json)
        except Exception as e: 
            print(f"Error parsing closed dates: {e}")

    return render_template('cart.html', 
                           cart_items=products_in_cart, 
                           total_cart_price=total_cart_price, 
                           recommendations=recommendations,
                           min_date_str=min_date_str,
                           closed_days=closed_days,
                           specific_closed_dates=specific_closed_dates,
                           shortage_ingredients=shortage_ingredients)

@main.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    try:
        quantity = int(request.form.get('quantity', '1'))
        if quantity < 1: quantity = 1
    except ValueError: 
        quantity = 1
    
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
        days_until_pickup = (pickup_date_obj - date.today()).days
        should_check_stock = days_until_pickup <= 2
        
        product_ids = [int(id) for id in cart_dict.keys()]
        products = Product.query.filter(Product.id.in_(product_ids)).all()
        products_map = {str(p.id): p for p in products} 
        
        ingredients_needed = {}
        for pid, qty in cart_dict.items():
            prod = products_map[pid]
            for rule in prod.ingredients:
                needed = rule.quantity_needed * Decimal(qty)
                if rule.ingredient.id in ingredients_needed:
                    ingredients_needed[rule.ingredient.id]['amount'] += needed
                else:
                    ingredients_needed[rule.ingredient.id] = {'obj': rule.ingredient, 'amount': needed}
        
        if should_check_stock:
            for ing_id, data in ingredients_needed.items():
                if data['obj'].stock_quantity < data['amount']:
                    flash(f"Te weinig voorraad voor {data['obj'].name}. Kies een latere datum (>2 dagen) of neem een ander product.", 'danger')
                    return redirect(url_for('main.view_cart'))
        
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
        print(f"Checkout Error: {e}")
        flash('Er ging iets mis met de bestelling. Probeer opnieuw.', 'danger')
        return redirect(url_for('main.view_cart'))


# ==============================================================================
#  4. ADMIN: SETTINGS
# ==============================================================================

@main.route('/admin/settings')
@admin_required
def admin_settings():
    admins = Profile.query.filter_by(is_admin=True).all()
    users = Profile.query.filter_by(is_admin=False).all()
    
    settings = get_settings()
    
    # Auto-Cleanup: Verwijder oude gesloten dagen
    if settings.closed_dates_json:
        try:
            dates_list = json.loads(settings.closed_dates_json)
            today_str = date.today().strftime('%Y-%m-%d')
            clean_dates = [d for d in dates_list if d >= today_str]
            
            if len(dates_list) != len(clean_dates):
                settings.closed_dates_json = json.dumps(clean_dates)
                db.session.commit()
        except Exception as e:
            print(f"Fout bij opschonen datums: {e}")
    
    try:
        schedule = json.loads(settings.weekly_schedule_json)
    except:
        schedule = {str(i): {'closed': False, 'text': '08:00 - 17:00'} for i in range(7)}

    days_names = ['Maandag', 'Dinsdag', 'Woensdag', 'Donderdag', 'Vrijdag', 'Zaterdag', 'Zondag']
    
    categories = get_categories()

    return render_template('admin_settings.html', 
                           admins=admins, 
                           users=users, 
                           schedule=schedule, 
                           days_names=days_names,
                           categories=categories)

@main.route('/admin/settings/update', methods=['POST'])
@admin_required
def update_settings():
    try:
        s = get_settings()
        s.welcome_title = request.form.get('welcome_title')
        s.welcome_text = request.form.get('welcome_text')
        s.intro_text = request.form.get('intro_text')
        
        try:
            s.deadline_hour = int(request.form.get('deadline_hour'))
        except ValueError: pass

        try:
            c_days = request.form.get('cancellation_days')
            if c_days:
                val = int(c_days)
                s.cancellation_days = val if val >= 0 else 0
        except ValueError: pass
        
        s.phone_number = request.form.get('phone_number')
        s.email_address = request.form.get('email_address')
        s.address_text = request.form.get('address_text')
        
        hero_file = request.files.get('hero_image_file')
        if hero_file and hero_file.filename != '':
            url = upload_image_to_supabase(hero_file)
            if url:
                s.hero_image_url = url

        raw_dates = request.form.get('closed_dates_input')
        date_list = []
        if raw_dates:
            date_list = [d.strip() for d in raw_dates.split(',') if d.strip()]
            s.closed_dates_json = json.dumps(date_list)
        else:
            s.closed_dates_json = json.dumps([])

        # Conflict Check
        total_conflicts = 0
        conflict_msg = []

        if date_list:
            try:
                date_objs = [datetime.strptime(d, '%Y-%m-%d').date() for d in date_list]
                specific_conflicts = Order.query.filter(
                    Order.pickup_date.in_(date_objs),
                    Order.status.notin_(['picked_up', 'cancelled'])
                ).count()
                
                if specific_conflicts > 0:
                    total_conflicts += specific_conflicts
                    conflict_msg.append(f"{specific_conflicts} op vakantiedagen")
            except Exception as e:
                print(f"Specific conflict check error: {e}")

        new_schedule = {}
        formatted_text = []
        short_names = ['Ma', 'Di', 'Wo', 'Do', 'Vr', 'Za', 'Zo']
        closed_weekdays = [] 

        for i in range(7):
            is_closed = request.form.get(f'day_{i}_closed') == 'on'
            text_hours = request.form.get(f'day_{i}_text')
            new_schedule[str(i)] = {'closed': is_closed, 'text': text_hours}
            
            status = "GESLOTEN" if is_closed else text_hours
            formatted_text.append(f"{short_names[i]}: {status}")
            
            if is_closed:
                closed_weekdays.append(i)

        if closed_weekdays:
            try:
                future_orders = Order.query.filter(
                    Order.pickup_date >= date.today(),
                    Order.status.notin_(['picked_up', 'cancelled'])
                ).all()
                
                weekly_conflicts = 0
                for order in future_orders:
                    if order.pickup_date.weekday() in closed_weekdays:
                        weekly_conflicts += 1
                
                if weekly_conflicts > 0:
                    total_conflicts += weekly_conflicts
                    conflict_msg.append(f"{weekly_conflicts} op vaste sluitingsdagen")

            except Exception as e:
                print(f"Weekly conflict check error: {e}")

        s.weekly_schedule_json = json.dumps(new_schedule)
        s.opening_hours = "\n".join(formatted_text)
        
        db.session.commit()
        
        if total_conflicts > 0:
            details = " & ".join(conflict_msg)
            flash(f'⚠️ LET OP: Je rooster botst met bestaande bestellingen! ({details}). Contacteer deze klanten.', 'warning')
        else:
            flash('Instellingen opgeslagen.', 'success')
            
    except Exception as e:
        db.session.rollback()
        print(f"Settings update error: {e}")
        flash("Kon instellingen niet opslaan.", "danger")
        
    return redirect(url_for('main.admin_settings'))

@main.route('/admin/settings/toggle_admin', methods=['POST'])
@admin_required
def toggle_admin():
    try:
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
    except Exception as e:
        db.session.rollback()
        print(f"Admin toggle error: {e}")
        flash("Actie mislukt.", "danger")
    
    return redirect(url_for('main.admin_settings'))

@main.route('/admin/settings/category/add', methods=['POST'])
@admin_required
def add_category():
    try:
        new_cat = request.form.get('new_category').strip().lower()
        if new_cat:
            s = get_settings()
            current_cats = get_categories()
            
            if new_cat not in current_cats:
                current_cats.append(new_cat)
                s.product_categories_json = json.dumps(current_cats)
                db.session.commit()
                flash(f'Categorie "{new_cat}" toegevoegd.', 'success')
            else:
                flash('Deze categorie bestaat al.', 'warning')
    except Exception as e:
        db.session.rollback()
        print(f"Category add error: {e}")
        flash("Kon categorie niet toevoegen.", "danger")
            
    return redirect(url_for('main.admin_settings'))

@main.route('/admin/settings/category/delete', methods=['POST'])
@admin_required
def delete_category():
    try:
        cat_to_remove = request.form.get('category_name')
        s = get_settings()
        current_cats = get_categories()
        
        if cat_to_remove in current_cats:
            current_cats.remove(cat_to_remove)
            s.product_categories_json = json.dumps(current_cats)
            db.session.commit()
            flash(f'Categorie "{cat_to_remove}" verwijderd.', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Category delete error: {e}")
        flash("Kon categorie niet verwijderen.", "danger")
        
    return redirect(url_for('main.admin_settings'))


# ==============================================================================
#  5. ADMIN: VOORRAAD & ORDERS
# ==============================================================================

@main.route('/admin/inventory')
@main.route('/admin/voorraad')
@admin_required
def admin_inventory():
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    products = Product.query.order_by(Product.name).all()
    
    try:
        res = generate_smart_forecast()
        shop_week = res[2]
        if shop_week:
            needs_map = {item['name']: item['amount'] for item in shop_week}
        else:
            needs_map = {}
    except Exception as e:
        print(f"Forecast error in inventory: {e}")
        needs_map = {}

    return render_template('admin_inventory.html', 
                           ingredients=ingredients, 
                           needs_map=needs_map, 
                           products=products)

@main.route('/admin/restock', methods=['POST'])
@admin_required
def restock_ingredient():
    try:
        ing = Ingredient.query.get(request.form.get('ingredient_id'))
        if ing:
            ing.stock_quantity += Decimal(request.form.get('amount'))
            db.session.commit()
            flash(f'Voorraad {ing.name} bijgevuld.', 'success')
    except Exception as e: 
        db.session.rollback()
        print(f"Restock error: {e}")
        flash('Fout bij bijvullen.', 'danger')
        
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin/inventory/refresh', methods=['POST'])
@admin_required
def refresh_inventory_forecast():
    try:
        generate_smart_forecast(force_refresh=True)
        flash("Prognose ververst. De kolom 'Nodig' is weer up-to-date.", 'success')
    except Exception as e:
        flash(f"Fout bij verversen: {e}", 'danger')
    
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin/waste', methods=['POST'])
@admin_required
def waste_ingredient():
    try:
        ing = Ingredient.query.get(request.form.get('ingredient_id'))
        if ing:
            ing.stock_quantity -= Decimal(request.form.get('amount'))
            db.session.commit()
            flash(f'Afschrijving {ing.name} verwerkt.', 'warning')
    except Exception as e: 
        db.session.rollback()
        print(f"Waste error: {e}")
        flash('Fout bij afschrijven.', 'danger')
        
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin/inventory/product_waste', methods=['POST'])
@admin_required
def process_product_waste():
    try:
        product_id = request.form.get('product_id')
        quantity = int(request.form.get('quantity'))
        
        product = Product.query.get(product_id)
        
        if product and quantity > 0:
            for rule in product.ingredients:
                total_loss = rule.quantity_needed * Decimal(quantity)
                rule.ingredient.stock_quantity -= total_loss
            
            db.session.commit()
            flash(f'{quantity}x {product.name} verwerkt als derving. Voorraad is bijgewerkt.', 'warning')
        else:
            flash('Ongeldige invoer.', 'danger')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Fout bij verwerken: {e}', 'danger')
        
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin/inventory/missed_sale', methods=['POST'])
@admin_required
def register_missed_sale():
    try:
        product_id = request.form.get('product_id')
        quantity = int(request.form.get('quantity'))
        shop_profile = Profile.query.filter(Profile.full_name.ilike("%Winkel%")).first()
        
        if not shop_profile:
             flash("Profiel 'Winkelverkoop' niet gevonden.", "danger")
             return redirect(url_for('main.admin_inventory'))

        if product_id and quantity > 0:
            order = Order(
                user_id=shop_profile.id,
                status='cancelled', 
                pickup_date=date.today(),
                total_price=0,
                remarks="Gemiste Verkoop (Uitverkocht)"
            )
            db.session.add(order)
            db.session.flush()
            
            product = Product.query.get(product_id)
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                unit_price_at_order=product.price
            ))
            
            db.session.commit()
            flash(f'Geregistreerd: {quantity}x {product.name} als gemiste verkoop. De AI neemt dit mee!', 'info')
        else:
            flash('Ongeldige invoer.', 'danger')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Fout: {e}', 'danger')
        
    return redirect(url_for('main.admin_inventory'))

@main.route('/admin')
@main.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    today = date.today()
    revenue_today = db.session.query(func.sum(Order.total_price))\
        .filter(Order.pickup_date == today, Order.status != 'cancelled').scalar() or 0
    
    open_orders = Order.query.filter(Order.status.in_(['pending', 'ready'])).count()
    
    low_stock_count = 0
    try:
        ai_result = generate_smart_forecast()
        shop_week_list = ai_result[2] 
        
        for item in shop_week_list:
            if 'Tekort' in item.get('status', ''):
                low_stock_count += 1
                
    except Exception as e:
        print(f"⚠️ Dashboard AI Error: {e}")
        low_stock_count = Ingredient.query.filter(Ingredient.stock_quantity < Ingredient.threshold).count()
    
    last_7_days = []
    revenues = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        rev = db.session.query(func.sum(Order.total_price))\
            .filter(Order.pickup_date == d, Order.status != 'cancelled').scalar() or 0
        last_7_days.append(d.strftime('%d-%m'))
        revenues.append(float(rev))

    return render_template('admin_dashboard.html', 
                           revenue_today=revenue_today,
                           open_orders=open_orders,
                           low_stock_count=low_stock_count,
                           chart_labels=last_7_days,
                           chart_data=revenues)

@main.route('/admin/orders')
@admin_required
def admin_orders():
    today = date.today()
    
    page_future = request.args.get('page_future', 1, type=int)
    page_history = request.args.get('page_history', 1, type=int)
    
    f_date = request.args.get('filter_date')
    f_client = request.args.get('filter_client')
    f_product = request.args.get('filter_product')
    f_status = request.args.get('filter_status')
    f_price_min = request.args.get('filter_price_min')
    
    orders_today = Order.query.filter(
        Order.pickup_date == today
    ).all()
    
    q_future = Order.query.filter(Order.pickup_date > today)
    
    q_history = Order.query.filter(
        (Order.pickup_date < today) | 
        ((Order.pickup_date == today) & (Order.status.in_(['picked_up', 'cancelled'])))
    )

    def apply_filters(query):
        if f_date:
            try:
                date_obj = datetime.strptime(f_date, '%Y-%m-%d').date()
                query = query.filter(Order.pickup_date == date_obj)
            except ValueError: pass
        
        if f_client:
            query = query.join(Profile).filter(Profile.full_name.ilike(f"%{f_client}%"))
            
        if f_product:
            query = query.join(OrderItem).join(Product).filter(Product.name.ilike(f"%{f_product}%"))
            
        if f_status and f_status != 'all':
            query = query.filter(Order.status == f_status)
            
        if f_price_min:
            try:
                query = query.filter(Order.total_price >= Decimal(f_price_min))
            except: pass
            
        return query

    q_future = apply_filters(q_future)
    q_history = apply_filters(q_history)

    if f_product:
        q_future = q_future.distinct()
        q_history = q_history.distinct()

    pagination_future = q_future.order_by(Order.pickup_date.asc()).paginate(page=page_future, per_page=10, error_out=False)
    pagination_history = q_history.order_by(Order.pickup_date.desc()).paginate(page=page_history, per_page=10, error_out=False)
    
    current_filters = {
        'date': f_date or '', 'client': f_client or '', 'product': f_product or '',
        'status': f_status or 'all', 'price_min': f_price_min or ''
    }

    return render_template('admin_orders.html', 
                           orders_today=orders_today, 
                           pagination_future=pagination_future,
                           pagination_history=pagination_history,
                           filters=current_filters)

@main.route('/admin/order/update/<int:order_id>', methods=['POST'])
@admin_required
def update_order_status(order_id):
    try:
        order = Order.query.get(order_id)
        if order:
            order.status = request.form.get('status')
            db.session.commit()
            flash(f'Order #{order.id} gewijzigd.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fout bij wijzigen status.', 'danger')
        
    return redirect(url_for('main.admin_orders'))


# ==============================================================================
#  6. ADMIN: PRODUCTEN & RECEPTEN
# ==============================================================================

@main.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.name).all()
    categories_list = get_categories()
    return render_template('admin_products.html', products=products, categories=categories_list)

@main.route('/admin/product/add', methods=['POST'])
@admin_required
def add_product_manual():
    try:
        file = request.files.get('image_file')
        image_url = 'logo.png'
        if file and file.filename != '':
            url = upload_image_to_supabase(file)
            if url: image_url = url
        
        s_start = request.form.get('season_start')
        s_end = request.form.get('season_end')
        
        if not s_start or not s_end:
            s_start = None
            s_end = None

        new_prod = Product(
            name=request.form.get('name'), 
            description=request.form.get('description'),
            price=Decimal(request.form.get('price')), 
            category=request.form.get('category'),
            allergens=request.form.get('allergens'),
            image_url=image_url,
            season_start=s_start,
            season_end=s_end
        )
        db.session.add(new_prod)
        db.session.commit()
        flash('Product toegevoegd.', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Product add error: {e}")
        flash(f'Fout bij toevoegen: {e}', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_price', methods=['POST'])
@admin_required
def update_product_price():
    try:
        p = Product.query.get(request.form.get('product_id'))
        if p:
            p.price = Decimal(request.form.get('price'))
            db.session.commit()
            flash('Prijs gewijzigd.', 'success')
    except Exception as e: 
        db.session.rollback()
        print(f"Price update error: {e}")
        flash('Kon prijs niet wijzigen.', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_season', methods=['POST'])
@admin_required
def update_product_season():
    try:
        p = Product.query.get(request.form.get('product_id'))
        if p:
            s_start = request.form.get('season_start')
            s_end = request.form.get('season_end')
            
            if s_start and s_end:
                p.season_start = s_start
                p.season_end = s_end
            else:
                p.season_start = None
                p.season_end = None
                
            db.session.commit()
            flash('Seizoen aangepast.', 'success')
    except Exception as e: 
        db.session.rollback()
        print(f"Season update error: {e}")
        flash('Kon seizoen niet wijzigen.', 'danger')
        
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_description', methods=['POST'])
@admin_required
def update_product_description():
    try:
        p = Product.query.get(request.form.get('product_id'))
        if p:
            p.description = request.form.get('description')
            db.session.commit()
            flash('Beschrijving gewijzigd.', 'success')
    except Exception as e: 
        db.session.rollback()
        print(f"Description update error: {e}")
        flash('Kon beschrijving niet wijzigen.', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_category', methods=['POST'])
@admin_required
def update_product_category():
    try:
        p = Product.query.get(request.form.get('product_id'))
        if p:
            p.category = request.form.get('category')
            db.session.commit()
            flash('Categorie gewijzigd.', 'success')
    except Exception as e: 
        db.session.rollback()
        print(f"Category update error: {e}")
        flash('Kon categorie niet wijzigen.', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/update_allergens', methods=['POST'])
@admin_required
def update_product_allergens():
    try:
        p = Product.query.get(request.form.get('product_id'))
        if p:
            p.allergens = request.form.get('allergens')
            db.session.commit()
            flash('Allergenen gewijzigd.', 'success')
    except Exception as e: 
        db.session.rollback()
        print(f"Allergen update error: {e}")
        flash('Kon allergenen niet wijzigen.', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/upload_image', methods=['POST'])
@admin_required
def upload_product_image():
    try:
        p = Product.query.get(request.form.get('product_id'))
        file = request.files.get('image_file')
        if file and file.filename != '' and p:
            url = upload_image_to_supabase(file)
            if url:
                p.image_url = url
                db.session.commit()
                flash('Foto gewijzigd (Supabase).', 'success')
            else:
                flash('Fout bij uploaden naar Supabase.', 'danger')
    except Exception as e: 
        db.session.rollback()
        print(f"Image upload error: {e}")
        flash('Fout bij uploaden.', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/import', methods=['POST'])
@admin_required
def import_products_excel():
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
        except Exception as e: 
            db.session.rollback()
            print(f"Excel import error: {e}")
            flash('Fout in Excel bestand.', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/delete/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    try:
        p = Product.query.get(product_id)
        if p:
            db.session.delete(p)
            db.session.commit()
            flash('Product verwijderd.', 'success')
    except Exception as e: 
        db.session.rollback()
        print(f"Delete product error: {e}")
        flash('Kan niet verwijderen (mogelijk nog in orders?).', 'danger')
    return redirect(url_for('main.admin_products'))

@main.route('/admin/product/<int:product_id>/recipe')
@admin_required
def manage_recipe(product_id):
    product = Product.query.get_or_404(product_id)
    all_ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template('admin_recipe.html', product=product, all_ingredients=all_ingredients)

@main.route('/admin/product/<int:product_id>/recipe/add', methods=['POST'])
@admin_required
def add_recipe_rule(product_id):
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
    except Exception as e: 
        db.session.rollback()
        print(f"Recipe add error: {e}")
        flash('Fout bij toevoegen ingrediënt.', 'danger')
    return redirect(url_for('main.manage_recipe', product_id=product_id))

@main.route('/admin/product/recipe/delete/<int:rule_id>', methods=['POST'])
@admin_required
def delete_recipe_rule(rule_id):
    try:
        rule = ProductIngredient.query.get(rule_id)
        pid = rule.product_id
        db.session.delete(rule)
        db.session.commit()
        return redirect(url_for('main.manage_recipe', product_id=pid))
    except Exception as e: 
        db.session.rollback()
        print(f"Recipe delete error: {e}")
        flash('Kon ingrediënt niet verwijderen.', 'danger')
        return redirect(url_for('main.admin_products'))


# ==============================================================================
#  7. AI FORECAST
# ==============================================================================

@main.route('/admin/forecast/refresh', methods=['POST'])
@admin_required
def refresh_forecast():
    try:
        generate_smart_forecast(force_refresh=True)
        flash('Voorspelling ververst.', 'success')
    except Exception as e:
        print(f"AI refresh error: {e}")
        flash(f'Fout bij verversen: {e}', 'danger')
    return redirect(url_for('main.admin_forecast'))

@main.route('/admin/forecast')
@admin_required
def admin_forecast():
    try:
        forecast, shop_tomorrow, shop_week, start, end = generate_smart_forecast()
    except Exception as e:
        print(f"Error AI forecast view: {e}")
        flash('Kon voorspelling niet laden.', 'danger')
        forecast, shop_tomorrow, shop_week = [], [], []
        start, end = date.today(), date.today()

    return render_template('admin_forecast.html', 
                           forecast=forecast, 
                           shop_tomorrow=shop_tomorrow, 
                           shop_week=shop_week, 
                           start_date=start, 
                           end_date=end)