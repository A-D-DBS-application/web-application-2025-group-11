import pandas as pd
import numpy as np
import holidays
import json
import traceback
import math
from datetime import datetime, date, timedelta
from decimal import Decimal
from sklearn.ensemble import RandomForestRegressor
from .models import db, Product, AppSettings
from sqlalchemy import text

# ==============================================================================
#  GLOBAL CACHE (PERFORMANCE OPTIMIZATION)
# ==============================================================================
# We cachen het resultaat om te voorkomen dat de database en CPU
# bij elke pageload belast worden. De forecast verandert immers niet elke minuut.
_cached_forecast = None
_last_calculation_time = None

# ==============================================================================
#  HELPER: FEATURE ENGINEERING
# ==============================================================================
def is_special_day(d):
    """
    Kent gewichten toe aan dagen.
    Hierdoor leert de AI dat feestdagen = meer omzet.
    """
    # 1. Officiële Belgische feestdagen
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return 1.8
    
    # 2. Decembermaand (Sinterklaas & Kerst)
    if d.month == 12:
        if d.day <= 6: return 1.5  # Sinterklaas piek
        if d.day >= 20: return 1.6 # Kerst piek
        return 1.2 
        
    # 3. Commerciële hoogdagen
    if d.month == 2 and d.day == 14: return 1.3  # Valentijn
    if d.month == 1 and d.day == 6: return 1.4   # Driekoningen
    
    # 4. Variabele zondagen (Moederdag/Vaderdag gokje voor demo)
    if d.weekday() == 6 and d.month in [5, 6] and 8 <= d.day <= 14: return 1.5 
    
    # 5. Verloren Maandag (Worstenbroden!)
    if d.month == 1 and d.weekday() == 0 and 7 <= d.day <= 13: return 1.6
    
    return 0

def get_season_status(product, d):
    """
    Hard-filtert producten die niet beschikbaar zijn.
    Voorkomt dat de AI 'Speculaas' voorspelt in juli, zelfs als het patroon dat zou denken.
    """
    if not product.season_start or not product.season_end: return True
    curr_md = d.strftime('%m-%d')
    if product.season_start <= product.season_end:
        return product.season_start <= curr_md <= product.season_end
    else:
        # Over de jaarwisseling heen (bv. Dec tot Jan)
        return curr_md >= product.season_start or curr_md <= product.season_end

# ==============================================================================
#  CORE ALGORITHM: TWIN-ENGINE FORECAST
# ==============================================================================
def generate_smart_forecast(force_refresh=False):
    global _cached_forecast, _last_calculation_time
    
    # 1. Cache Check
    if not force_refresh and _cached_forecast and _last_calculation_time:
        if datetime.now() - _last_calculation_time < timedelta(minutes=60):
            return _cached_forecast

    print("--- 🧠 AI TWIN-ENGINE: START BEREKENING ---")

    try:
        # ---------------------------------------------------------
        # STAP A: Settings & Sluitingsdagen ophalen
        # ---------------------------------------------------------
        settings = AppSettings.query.first()
        closed_dates_list = []
        closed_weekdays = [] 
        if settings:
            if settings.closed_dates_json:
                try: closed_dates_list = json.loads(settings.closed_dates_json)
                except: pass
            if settings.weekly_schedule_json:
                try:
                    sch = json.loads(settings.weekly_schedule_json)
                    for day_idx, data in sch.items():
                        if data.get('closed'): closed_weekdays.append(int(day_idx))
                except: pass

        # ---------------------------------------------------------
        # STAP B: Historische Data (Training Set)
        # ---------------------------------------------------------
        start_date_db = date.today() - timedelta(days=370)
        
        # We halen ALLE items op, ook cancelled (want dat is gemiste vraag!)
        sql = text("""
            SELECT orders.pickup_date, orders.remarks, products.name, products.category, order_items.quantity
            FROM order_items
            JOIN orders ON order_items.order_id = orders.id
            JOIN products ON order_items.product_id = products.id
            WHERE orders.pickup_date >= :start_date
            AND orders.pickup_date < :today
        """)
        
        with db.engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={'start_date': start_date_db, 'today': date.today()})

        has_history = not df.empty
        daily_shop_sales = pd.DataFrame()
        avg_cat_sales = {}
        
        recent_velocity = {}     
        historical_baseline = {} 
        
        # Default fallback ratio (Online vs Winkel)
        current_online_ratio = 0.15 

        if has_history:
            df['pickup_date'] = pd.to_datetime(df['pickup_date'])
            
            # Feature Engineering (Cyclical Time Encoding)
            # Dit helpt de AI om 'eind december' en 'begin januari' als dichtbij elkaar te zien
            df['month_sin'] = np.sin(2 * np.pi * df['pickup_date'].dt.month / 12)
            df['month_cos'] = np.cos(2 * np.pi * df['pickup_date'].dt.month / 12)
            df['day_sin'] = np.sin(2 * np.pi * df['pickup_date'].dt.dayofweek / 7)
            df['day_cos'] = np.cos(2 * np.pi * df['pickup_date'].dt.dayofweek / 7)
            df['date_ordinal'] = df['pickup_date'].apply(lambda x: x.toordinal())
            df['is_holiday'] = df['pickup_date'].apply(is_special_day)

            # Splitsen: Engine 1 traint puur op Winkelverkoop (Clean Data)
            df_shop = df[df['remarks'] == 'Winkelverkoop'].copy()
            df_online = df[df['remarks'] != 'Winkelverkoop'].copy()
            
            if not df_shop.empty:
                daily_shop_sales = df_shop.groupby([
                    'date_ordinal', 'month_sin', 'month_cos', 'day_sin', 'day_cos', 
                    'is_holiday', 'name', 'category'
                ])['quantity'].sum().reset_index()
                
                avg_cat_sales = daily_shop_sales.groupby('category')['quantity'].mean().to_dict()
                historical_baseline = daily_shop_sales.groupby('name')['quantity'].mean().to_dict()

                # --- RECENTE PRESTATIES (Velocity Check) ---
                cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=30)
                last_30_days_shop = df_shop[df_shop['pickup_date'] > cutoff_date]
                last_30_days_online = df_online[df_online['pickup_date'] > cutoff_date]

                if not last_30_days_shop.empty:
                    recent_velocity = (last_30_days_shop.groupby('name')['quantity'].sum() / 30.0).to_dict()
                    
                    # --- ZELFLERENDE ONLINE RATIO ---
                    # De AI leert: "Voor elke 100 broden in de winkel, worden er X online besteld"
                    total_shop_qty = last_30_days_shop['quantity'].sum()
                    total_online_qty = last_30_days_online['quantity'].sum() if not last_30_days_online.empty else 0
                    
                    if total_shop_qty > 0:
                        raw_ratio = total_online_qty / total_shop_qty
                        # Veiligheidsbegrenzing: Tussen 5% en 80%
                        current_online_ratio = max(0.05, min(0.80, raw_ratio))

        # ---------------------------------------------------------
        # STAP C: Harde Data (Reeds besteld voor de toekomst)
        # ---------------------------------------------------------
        future_sql = text("""
            SELECT orders.pickup_date, products.name, SUM(order_items.quantity) as total_ordered
            FROM order_items
            JOIN orders ON order_items.order_id = orders.id
            JOIN products ON order_items.product_id = products.id
            WHERE orders.status != 'cancelled' 
            AND orders.pickup_date > :today
            GROUP BY orders.pickup_date, products.name
        """)
        with db.engine.connect() as conn:
            df_future = pd.read_sql(future_sql, conn, params={'today': date.today()})
            
        future_map = {}
        if not df_future.empty:
            df_future['pickup_date'] = pd.to_datetime(df_future['pickup_date']).dt.date
            for _, row in df_future.iterrows():
                future_map[(row['pickup_date'], row['name'])] = row['total_ordered']

        # ---------------------------------------------------------
        # STAP D: DE VOORSPELLINGS LOOP (PER PRODUCT)
        # ---------------------------------------------------------
        forecast_results = []
        all_products = Product.query.filter_by(is_available=True).all()
        
        start_prediction = date.today() + timedelta(days=1)
        end_prediction = date.today() + timedelta(days=7)

        for product in all_products:
            model = None
            
            # Data voor Scaling & Trend
            prod_velocity = recent_velocity.get(product.name, 0.0)
            prod_history = historical_baseline.get(product.name, 1.0) 
            
            # --- ADAPTIVE SCALING (Crisis Management) ---
            # Als de verkoop plots instort of piekt (velocity vs history),
            # schaalt deze factor de AI-voorspelling bij.
            scaling_factor = 1.0
            if prod_history > 0.1: 
                scaling_factor = prod_velocity / prod_history
            # Begrens de factor (max 50% groei / max 70% krimp toegestaan in model)
            scaling_factor = max(0.3, min(1.5, scaling_factor))

            # Train AI (Random Forest)
            if has_history and not daily_shop_sales.empty:
                p_data = daily_shop_sales[daily_shop_sales['name'] == product.name].copy()
                if len(p_data) >= 5:
                    X = p_data[['date_ordinal', 'month_sin', 'month_cos', 'day_sin', 'day_cos', 'is_holiday']]
                    y = p_data['quantity']
                    # Recente data weegt exponentieel zwaarder
                    weights = np.exp(0.02 * (p_data['date_ordinal'] - p_data['date_ordinal'].max()))
                    
                    model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
                    model.fit(X, y, sample_weight=weights)

            raw_shop_forecast_week = 0 
            total_purchasing_advice_week = 0
            tomorrow_purchasing_advice = 0
            
            for i in range(1, 8):
                f_date = date.today() + timedelta(days=i)
                
                # --- ENGINE 1: WINKEL (Probabilistische AI) ---
                shop_pred = 0
                is_closed = (f_date.strftime('%Y-%m-%d') in closed_dates_list) or (f_date.weekday() in closed_weekdays)
                in_season = get_season_status(product, f_date)
                
                if not is_closed and in_season:
                    if model:
                        feat = pd.DataFrame({
                            'date_ordinal': [f_date.toordinal()],
                            'month_sin': [np.sin(2 * np.pi * f_date.month / 12)],
                            'month_cos': [np.cos(2 * np.pi * f_date.month / 12)],
                            'day_sin': [np.sin(2 * np.pi * f_date.weekday() / 7)],
                            'day_cos': [np.cos(2 * np.pi * f_date.weekday() / 7)],
                            'is_holiday': [is_special_day(f_date)]
                        })
                        base_ai = max(0, model.predict(feat)[0])
                        shop_pred = base_ai * scaling_factor
                    else:
                        # Cold Start (Geen data? Gebruik Categorie gemiddelde)
                        shop_pred = avg_cat_sales.get(product.category, 5) * scaling_factor
                        if f_date.weekday() >= 5: shop_pred *= 1.4

                raw_shop_forecast_week += shop_pred

                # --- ENGINE 2: INKOOP ADVIES (Deterministisch + Groei) ---
                
                # 1. Veiligheidsmarge voor de winkel (buffer voor onverwachte klanten)
                margin = 1.15 if f_date.weekday() >= 5 else 1.05
                shop_safe = int(np.ceil(shop_pred * margin))
                
                # 2. Harde Online Orders (Die staan al vast in DB)
                hard_online = int(future_map.get((f_date, product.name), 0))
                
                # 3. Verwachte Last-Minute Online Groei
                # We weten dat online bestellingen last-minute binnenkomen.
                # Dit modelleert die curve obv de 'learned ratio'.
                daily_growth_rate = 1.0 + current_online_ratio 
                growth = min((daily_growth_rate) ** (i - 1), 4.0) 
                
                proj_online = hard_online * growth
                
                # 4. Ghost Fallback (Verre toekomst, dag 3-7)
                # Als er nog 0 online orders zijn voor volgende week, schat het model
                # toch een percentage van de winkelverkoop in.
                if i > 2:
                    uncertainty = ((i - 1) / 7.0)
                    proj_online += (shop_pred * current_online_ratio) * uncertainty
                
                final_day_total = shop_safe + int(np.ceil(proj_online))
                
                total_purchasing_advice_week += final_day_total
                if i == 1: tomorrow_purchasing_advice = final_day_total

            # --- TREND ANALYSE ---
            # Vergelijkt AI-voorspelling met Historisch gemiddelde
            recent_week_norm = prod_velocity * 7 
            trend_txt = "stabiel ➡️"
            
            if recent_week_norm > 2: 
                diff = raw_shop_forecast_week - recent_week_norm
                if diff > (recent_week_norm * 0.20): trend_txt = "stijgend 📈"
                elif diff < -(recent_week_norm * 0.20): trend_txt = "dalend 📉"
            elif raw_shop_forecast_week > 3: 
                trend_txt = "nieuw 🔥"

            # Resultaten opslaan
            if total_purchasing_advice_week > 0:
                forecast_results.append({
                    'product_name': product.name,
                    'tomorrow': tomorrow_purchasing_advice,
                    'week_total': total_purchasing_advice_week,
                    'trend': trend_txt,
                    'debug_4week_avg': round(recent_week_norm, 1), 
                    'debug_raw_forecast': round(raw_shop_forecast_week, 1)
                })

        forecast_results.sort(key=lambda x: x['tomorrow'], reverse=True)

        # ---------------------------------------------------------
        # STAP E: Ingrediënten Berekening
        # ---------------------------------------------------------
        ing_tom = {} 
        ing_week = {}
        for item in forecast_results:
            p = Product.query.filter_by(name=item['product_name']).first()
            if p and p.ingredients:
                for r in p.ingredients:
                    n_tom = r.quantity_needed * Decimal(item['tomorrow'])
                    n_week = r.quantity_needed * Decimal(item['week_total'])
                    
                    if r.ingredient.name not in ing_tom:
                        base = {'amount': 0, 'unit': r.ingredient.unit, 'stock': r.ingredient.stock_quantity}
                        ing_tom[r.ingredient.name] = base.copy()
                        ing_week[r.ingredient.name] = base.copy()
                    
                    ing_tom[r.ingredient.name]['amount'] += n_tom
                    ing_week[r.ingredient.name]['amount'] += n_week

        def fmt(d):
            return sorted([
                {'name': k, 'amount': round(v['amount'],1), 'unit': v['unit'], 'stock': v['stock'], 
                 'status': 'Tekort ⚠️' if v['amount'] > v['stock'] else 'Voldoende ✅'}
                for k, v in d.items()
            ], key=lambda x: x['name'])

        shop_tomorrow = fmt(ing_tom)
        shop_week = fmt(ing_week)

        # Cache update
        _cached_forecast = (forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction)
        _last_calculation_time = datetime.now()
        
        return forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction

    except Exception as e:
        print(f"❌ CRITICAL FORECAST ERROR: {e}")
        traceback.print_exc()
        # Fallback om crash te voorkomen: geef lege lijsten en datum van vandaag terug
        return [], [], [], date.today(), date.today()

# ==============================================================================
#  MARKET BASKET ANALYSIS (Cart Recommendations)
# ==============================================================================

def get_cart_recommendations(current_cart_ids):
    """
    CONTENT-BASED RECOMMENDATION ENGINE (Smaak-Matcher)
    Bouwt een smaakprofiel op basis van categorie en ingrediënten.
    """
    if not current_cart_ids:
        return []

    # 1. Haal de producten in het mandje op
    cart_products = Product.query.filter(Product.id.in_(current_cart_ids)).all()
    if not cart_products: return []

    # 2. Bouw het "Smaakprofiel"
    active_categories = set()
    active_ingredients = set()
    
    for p in cart_products:
        if p.category:
            active_categories.add(p.category)
        for pi in p.ingredients:
            active_ingredients.add(pi.ingredient.id)

    # 3. Haal kandidaten op
    candidates = Product.query.filter(Product.id.notin_(current_cart_ids), Product.is_available==True).all()
    
    scored_candidates = []
    today = date.today()

    # 4. Het Puntensysteem
    for prod in candidates:
        # Check: Is het product uberhaupt beschikbaar?
        if not get_season_status(prod, today):
            continue

        score = 0
        
        # A. Categorie Match (+10)
        if prod.category in active_categories:
            score += 10
            
        # B. Ingrediënt Match (+2)
        for pi in prod.ingredients:
            if pi.ingredient.id in active_ingredients:
                score += 2
        
        # C. Strafpunten voor bulk (+/-)
        if prod.category == 'pistoles':
            score -= 2
        elif prod.category == 'brood':
            score -= 1

        # D. SEIZOENS-BOOST (+5) (NIEUW!)
        # Als het product specifieke datums heeft (dus geen 'altijd beschikbaar' product),
        # en het door de check hierboven is gekomen, dan is het een "Special".
        # Mensen kopen specials graag als extraatje.
        if prod.season_start:
            score += 4

        if score > 0:
            scored_candidates.append((prod, score))

    # 5. COMMERCIËLE SORTERING (Tie-Breaker Logic)
    def sort_key(item):
        prod, score = item
        is_luxe = 1 if prod.category in ['taart', 'koffiekoeken', 'gebak', 'seizoensgebak'] else 0
        price = float(prod.price)
        return (score, is_luxe, price)

    scored_candidates.sort(key=sort_key, reverse=True)
    
    return [item[0].id for item in scored_candidates[:3]]