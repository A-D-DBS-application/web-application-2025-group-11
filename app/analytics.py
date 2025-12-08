import pandas as pd
import numpy as np
import holidays
import json
import traceback
from datetime import datetime, date, timedelta
from decimal import Decimal
from sklearn.ensemble import RandomForestRegressor
from .models import db, Product, AppSettings
from sqlalchemy import text

# --- GLOBAL CACHE ---
# Voorkomt dat we bij elke page refresh zware berekeningen doen.
# Cache wordt na 60 minuten ongeldig verklaard.
_cached_forecast = None
_last_calculation_time = None

def is_special_day(d):
    """
    Feature Engineering: Kent gewichten toe aan dagen.
    Random Forest leert hierdoor dat feestdagen = meer omzet.
    """
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return 1.8
    
    # Decembermaand (Kerstperiode) is drukker
    if d.month == 12:
        if d.day <= 6: return 1.5  # Sinterklaas
        if d.day >= 20: return 1.6 # Kerst
        return 1.2 # Gewone decemberdagen
        
    # Commerciële hoogdagen
    if d.month == 2 and d.day == 14: return 1.3  # Valentijn
    if d.month == 1 and d.day == 6: return 1.4   # Driekoningen
    
    # Variabele zondagen (Moederdag/Vaderdag)
    if d.weekday() == 6 and d.month in [5, 6] and 8 <= d.day <= 14: return 1.5
    
    # Verloren Maandag (Maandag na Driekoningen)
    if d.month == 1 and d.weekday() == 0 and 7 <= d.day <= 13: return 1.6
    
    return 0

def get_season_status(product, d):
    """
    Filtert producten die niet beschikbaar zijn in het huidige seizoen.
    Voorkomt dat de AI 'Speculaas' voorspelt in juli.
    """
    if not product.season_start or not product.season_end: return True
    
    curr_md = d.strftime('%m-%d')
    if product.season_start <= product.season_end:
        return product.season_start <= curr_md <= product.season_end
    else:
        # Seizoen loopt over jaarwisseling heen (bv. Nov -> Jan)
        return curr_md >= product.season_start or curr_md <= product.season_end

def generate_smart_forecast(force_refresh=False):
    global _cached_forecast, _last_calculation_time
    
    # 1. Cache Check
    if not force_refresh and _cached_forecast and _last_calculation_time:
        if datetime.now() - _last_calculation_time < timedelta(minutes=60):
            return _cached_forecast

    print("--- 🧠 AI TWIN-ENGINE: ADAPTIVE SCALING ACTIVE ---")

    try:
        # 2. Settings Ophalen (Sluitingsdagen)
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

        # 3. Historische Data Ophalen (Training Set)
        # We kijken 370 dagen terug om jaarlijkse patronen te vangen
        start_date_db = date.today() - timedelta(days=370)
        
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
        
        # Statistieken voor Adaptive Scaling
        recent_velocity = {}    # Realiteit (Laatste 30 dagen)
        historical_baseline = {} # Geheugen (Vorig jaar)

        if has_history:
            df['pickup_date'] = pd.to_datetime(df['pickup_date'])
            
            # --- Feature Engineering ---
            # Cyclische tijdskenmerken (Sinus/Cosinus) zorgen voor betere overgangen tussen dec/jan
            df['month_sin'] = np.sin(2 * np.pi * df['pickup_date'].dt.month / 12)
            df['month_cos'] = np.cos(2 * np.pi * df['pickup_date'].dt.month / 12)
            df['day_sin'] = np.sin(2 * np.pi * df['pickup_date'].dt.dayofweek / 7)
            df['day_cos'] = np.cos(2 * np.pi * df['pickup_date'].dt.dayofweek / 7)
            
            df['date_ordinal'] = df['pickup_date'].apply(lambda x: x.toordinal())
            df['is_holiday'] = df['pickup_date'].apply(is_special_day)

            # Engine 1 traint ENKEL op Winkelverkoop (puur consumentengedrag)
            df_shop = df[df['remarks'] == 'Winkelverkoop'].copy()
            
            if not df_shop.empty:
                daily_shop_sales = df_shop.groupby([
                    'date_ordinal', 'month_sin', 'month_cos', 'day_sin', 'day_cos', 
                    'is_holiday', 'name', 'category'
                ])['quantity'].sum().reset_index()
                
                # Fallback voor nieuwe producten
                avg_cat_sales = daily_shop_sales.groupby('category')['quantity'].mean().to_dict()

                # --- ADAPTIVE SCALING METRICS ---
                # 1. Baseline: Hoeveel verkopen we gemiddeld van dit product?
                historical_baseline = daily_shop_sales.groupby('name')['quantity'].mean().to_dict()

                # 2. Velocity: Hoeveel verkochten we de afgelopen 30 dagen?
                last_30_days = df_shop[df_shop['pickup_date'] > (pd.Timestamp.now() - pd.Timedelta(days=30))]
                if not last_30_days.empty:
                    # Delen door 30.0 geeft het échte daggemiddelde (inclusief 0-dagen)
                    recent_velocity = (last_30_days.groupby('name')['quantity'].sum() / 30.0).to_dict()

        # 4. Toekomstige Online Orders (Engine 2)
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

        # 5. Voorspelling Genereren
        forecast_results = []
        all_products = Product.query.filter_by(is_available=True).all()
        
        start_prediction = date.today() + timedelta(days=1)
        end_prediction = date.today() + timedelta(days=7)

        for product in all_products:
            model = None
            
            prod_velocity = recent_velocity.get(product.name, 0.0)
            prod_history = historical_baseline.get(product.name, 1.0) 
            
            # --- SCALING FACTOR BEREKENING ---
            # Verhouding: (Huidige Prestatie) / (Historische Prestatie)
            # Als we 20% minder verkopen dan vorig jaar, wordt de factor 0.8
            scaling_factor = 1.0
            if prod_history > 0.1: # Voorkom deling door 0
                scaling_factor = prod_velocity / prod_history
            
            # Begrenzing (Clamping): Factor mag niet extremer zijn dan 0.3x of 1.5x
            # Dit voorkomt dat het model op hol slaat bij nieuwe/seizoensproducten
            scaling_factor = max(0.3, min(1.5, scaling_factor))

            if has_history and not daily_shop_sales.empty:
                p_data = daily_shop_sales[daily_shop_sales['name'] == product.name].copy()
                # Minimaal 5 datapunten nodig voor een betrouwbaar model
                if len(p_data) >= 5:
                    X = p_data[['date_ordinal', 'month_sin', 'month_cos', 'day_sin', 'day_cos', 'is_holiday']]
                    y = p_data['quantity']
                    
                    # Exponentiële weging: Recente data weegt zwaarder in training
                    weights = np.exp(0.02 * (p_data['date_ordinal'] - p_data['date_ordinal'].max()))
                    
                    model = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42)
                    model.fit(X, y, sample_weight=weights)

            raw_shop_forecast_week = 0 
            total_purchasing_advice_week = 0
            tomorrow_purchasing_advice = 0
            
            for i in range(1, 8):
                f_date = date.today() + timedelta(days=i)
                
                # --- ENGINE 1: WINKEL VOORSPELLING (AI) ---
                shop_pred = 0
                
                # Check constraints
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
                        
                        # Pas de Scaling Factor toe
                        # De AI herinnert zich het 'goede' jaar, wij schalen het naar de huidige realiteit
                        shop_pred = base_ai * scaling_factor
                        
                    else:
                        # Cold Start Fallback (gemiddelde van categorie)
                        shop_pred = avg_cat_sales.get(product.category, 5) * scaling_factor
                        if f_date.weekday() >= 5: shop_pred *= 1.4

                # Opslaan voor Trend Analyse (Puur Winkelgedrag)
                raw_shop_forecast_week += shop_pred

                # --- ENGINE 2: INKOOP ADVIES (CALCULATOR) ---
                # 1. Veiligheidsmarge voor winkel (15% in weekend, 5% in week)
                margin = 1.15 if f_date.weekday() >= 5 else 1.05
                shop_safe = int(np.ceil(shop_pred * margin))
                
                # 2. Harde Online Orders
                hard_online = int(future_map.get((f_date, product.name), 0))
                
                # 3. Groeimodel voor Online (Hoe verder weg, hoe meer we verwachten)
                growth_exponent = (1.15) ** (i - 1)
                proj_online = hard_online * growth_exponent
                
                # 4. Ghost Fallback (Alleen voor > 2 dagen vooruit)
                # Als er nog 0 online orders zijn, schatten we in op basis van winkelverkoop
                if i > 2:
                    uncertainty = ((i - 1) / 7.0)
                    proj_online += (shop_pred * 0.15) * uncertainty
                
                final_day_total = shop_safe + int(np.ceil(proj_online))
                
                total_purchasing_advice_week += final_day_total
                if i == 1: tomorrow_purchasing_advice = final_day_total

            # --- TREND ANALYSE ---
            # Eerlijke vergelijking: (Voorspelde Winkelweek) vs (Afgelopen Winkelweek)
            # We vergelijken 'raw_shop_forecast' (AI output) met 'prod_velocity * 7' (Realiteit)
            
            recent_week_norm = prod_velocity * 7 
            trend_txt = "stabiel ➡️"
            
            if recent_week_norm > 2: # Minimaal volume check
                diff = raw_shop_forecast_week - recent_week_norm
                threshold = recent_week_norm * 0.20 # 20% afwijking nodig voor trend
                
                if diff > threshold: trend_txt = "stijgend 📈"
                elif diff < -threshold: trend_txt = "dalend 📉"
            
            elif raw_shop_forecast_week > 3:
                trend_txt = "nieuw 🔥"

            # Alleen toevoegen als er actie nodig is
            if total_purchasing_advice_week > 0:
                forecast_results.append({
                    'product_name': product.name,
                    'tomorrow': tomorrow_purchasing_advice,
                    'week_total': total_purchasing_advice_week,
                    'trend': trend_txt,
                    # Debug Data voor Dashboard (Eerlijke cijfers)
                    'debug_4week_avg': round(recent_week_norm, 1), 
                    'debug_raw_forecast': round(raw_shop_forecast_week, 1)
                })

        forecast_results.sort(key=lambda x: x['tomorrow'], reverse=True)

        # 6. Ingrediënten Berekening
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

        # Caching
        _cached_forecast = (forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction)
        _last_calculation_time = datetime.now()
        
        return forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction

    except Exception as e:
        print(f"❌ CRITICAL FORECAST ERROR: {e}")
        traceback.print_exc()
        # Fallback bij crash: Lege lijsten zodat site blijft werken
        return [], [], [], date.today(), date.today()