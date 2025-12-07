import pandas as pd
import numpy as np
import holidays
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from sklearn.ensemble import RandomForestRegressor
from .models import db, Product, AppSettings
from sqlalchemy import text

# --- CACHE OPSLAG ---
_cached_forecast = None
_last_calculation_time = None

def is_special_day(d):
    """Bepaalt of een datum een speciale dag is."""
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return 1
    # Vaste feestdagen en periodes
    if d.month == 12 and d.day == 6: return 1  # Sinterklaas
    if d.month == 2 and d.day == 14: return 1  # Valentijn
    if d.month == 1 and d.day == 6: return 1   # Driekoningen
    if d.weekday() == 6: 
        if d.month == 5 and 8 <= d.day <= 14: return 1 # Moederdag
        if d.month == 6 and 8 <= d.day <= 14: return 1 # Vaderdag
    if d.month == 1 and d.weekday() == 0 and 7 <= d.day <= 13: return 1 # Verloren Maandag
    return 0

def generate_smart_forecast(force_refresh=False):
    global _cached_forecast, _last_calculation_time
    
    # 1. CHECK CACHE
    if not force_refresh and _cached_forecast and _last_calculation_time:
        if datetime.now() - _last_calculation_time < timedelta(minutes=60):
            print("--- ⚡️ CACHE GEBRUIKT ---")
            return _cached_forecast

    print("--- 🧠 AI TWIN-ENGINE STARTEN (WINKEL TREND ONLY) ---")

    # 2. SETTINGS OPHALEN
    settings = AppSettings.query.first()
    closed_dates_list = []
    closed_weekdays = [] 

    if settings:
        if settings.closed_dates_json:
            try: closed_dates_list = json.loads(settings.closed_dates_json)
            except: pass
        if settings.weekly_schedule_json:
            try:
                schedule = json.loads(settings.weekly_schedule_json)
                for day_idx, data in schedule.items():
                    if data.get('closed'): closed_weekdays.append(int(day_idx))
            except: pass

    # 3. HISTORIE OPHALEN
    sql = text("""
        SELECT orders.pickup_date, orders.remarks, products.name, order_items.quantity
        FROM order_items
        JOIN orders ON order_items.order_id = orders.id
        JOIN products ON order_items.product_id = products.id
        WHERE orders.pickup_date >= :start_date
        AND orders.pickup_date < :today
    """)
    # We halen ook 'cancelled' orders op (True Demand)
    params = {'start_date': date.today() - timedelta(days=370), 'today': date.today()}

    try:
        with db.engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
            
        has_history = not df.empty
        avg_shop_sales = {} # NIEUW: Alleen winkelgemiddelde
        daily_shop_sales = pd.DataFrame()

        if has_history:
            df['pickup_date'] = pd.to_datetime(df['pickup_date'])
            
            # Feature Engineering
            df['weekday'] = df['pickup_date'].dt.dayofweek
            df['date_ordinal'] = df['pickup_date'].apply(lambda x: x.toordinal())
            df['is_holiday'] = df['pickup_date'].apply(is_special_day)

            # Splitsen: We hebben de winkeldata nodig voor de trend-vergelijking
            df_shop = df[df['remarks'] == 'Winkelverkoop'].copy()
            
            if not df_shop.empty:
                daily_shop_sales = df_shop.groupby(['date_ordinal', 'weekday', 'is_holiday', 'name'])['quantity'].sum().reset_index()
                
                # --- TREND BASIS: WINKEL GEMIDDELDE (JAAR) ---
                # We berekenen hoe goed de WINKEL het normaal doet (zonder online orders)
                total_shop_sales = df_shop.groupby('name')['quantity'].sum()
                total_days = (df['pickup_date'].max() - df['pickup_date'].min()).days
                if total_days < 7: total_days = 7
                weeks_count = total_days / 7
                avg_shop_sales = total_shop_sales / weeks_count

        # 4. TOEKOMSTIGE ORDERS (HARDE DATA)
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
            
        future_orders_map = {}
        if not df_future.empty:
            df_future['pickup_date'] = pd.to_datetime(df_future['pickup_date']).dt.date
            for index, row in df_future.iterrows():
                future_orders_map[(row['pickup_date'], row['name'])] = row['total_ordered']

        if not has_history and not future_orders_map:
            return [], [], [], date.today(), date.today()

        forecast_results = []
        all_products = Product.query.filter_by(is_available=True).all()
        unique_products = [p.name for p in all_products]
        
        product_seasons = {p.name: (p.season_start, p.season_end) for p in all_products}
        
        start_prediction = date.today() + timedelta(days=1)
        end_prediction = date.today() + timedelta(days=7)

        # 5. VOORSPELLEN
        for product_name in unique_products:
            model = None
            if has_history and not daily_shop_sales.empty:
                product_data = daily_shop_sales[daily_shop_sales['name'] == product_name].copy()
                if len(product_data) >= 5:
                    X = product_data[['date_ordinal', 'weekday', 'is_holiday']]
                    y = product_data['quantity']
                    
                    # Exponentiële Weging
                    min_date = product_data['date_ordinal'].min()
                    max_date = product_data['date_ordinal'].max()
                    weights = np.ones(len(product_data))
                    if max_date > min_date:
                        weights = np.exp(0.05 * (product_data['date_ordinal'] - max_date))

                    model = RandomForestRegressor(n_estimators=100, random_state=42)
                    model.fit(X, y, sample_weight=weights)

            total_predicted_week = 0
            trend_predicted_week = 0 # NIEUW: Alleen winkelvoorspelling voor de trend
            predicted_tomorrow = 0
            
            for i in range(1, 8):
                future_date = date.today() + timedelta(days=i)
                future_date_str = future_date.strftime('%Y-%m-%d')
                
                is_closed = (future_date_str in closed_dates_list) or (future_date.weekday() in closed_weekdays)
                
                s_start, s_end = product_seasons.get(product_name, (None, None))
                in_season = True
                if s_start and s_end:
                    curr_md = future_date.strftime('%m-%d')
                    if s_start <= s_end: in_season = (s_start <= curr_md <= s_end)
                    else: in_season = (curr_md >= s_start or curr_md <= s_end)

                shop_prediction = 0
                if not is_closed and in_season and model:
                    future_features = pd.DataFrame({
                        'date_ordinal': [future_date.toordinal()],
                        'weekday': [future_date.weekday()],
                        'is_holiday': [is_special_day(future_date)]
                    })
                    raw_pred = model.predict(future_features)[0]
                    shop_prediction = max(0, raw_pred)

                # Veiligheidsmarge voor INKOOP
                shop_qty_safe = int(np.ceil(shop_prediction * 1.10)) if shop_prediction > 0 else 0
                
                # Online orders
                online_orders = int(future_orders_map.get((future_date, product_name), 0))
                
                # --- TREND: ALLEEN WINKEL (zonder online vervuiling) ---
                trend_predicted_week += shop_prediction

                # --- INKOOP: TOTAAL (Winkel + Online) ---
                final_qty = shop_qty_safe + online_orders
                
                total_predicted_week += final_qty
                if i == 1: predicted_tomorrow = final_qty

            # --- TREND ANALYSE ---
            # Vergelijk: Voorspelde Winkelverkoop VS Gemiddelde Winkelverkoop
            shop_avg = avg_shop_sales.get(product_name, 0) if has_history else 0
            trend = "stabiel ➡️"
            
            if shop_avg > 0:
                if trend_predicted_week > (shop_avg * 1.10): trend = "stijgend 📈"
                elif trend_predicted_week < (shop_avg * 0.90): trend = "dalend 📉"
            elif trend_predicted_week > 0:
                trend = "stijgend 📈"

            if total_predicted_week > 0 or shop_avg > 0:
                forecast_results.append({
                    'product_name': product_name,
                    'tomorrow': predicted_tomorrow,
                    'week_total': total_predicted_week,
                    'trend': trend,
                    # Debug Data (Winkel only)
                    'debug_history_avg': round(shop_avg, 1), 
                    'debug_raw_forecast': round(trend_predicted_week, 1)
                })

        forecast_results.sort(key=lambda x: x['tomorrow'], reverse=True)

        # Ingrediënten (Ongewijzigd)
        ing_tomorrow = {} 
        ing_week = {}

        for forecast_item in forecast_results:
            qty_tom = forecast_item['tomorrow']
            qty_week = forecast_item['week_total']
            product = Product.query.filter_by(name=forecast_item['product_name']).first()
            if product and product.ingredients:
                for rule in product.ingredients:
                    i_name = rule.ingredient.name
                    needed_tom = rule.quantity_needed * Decimal(qty_tom)
                    needed_week = rule.quantity_needed * Decimal(qty_week)
                    if i_name not in ing_tomorrow: ing_tomorrow[i_name] = {'amount': 0, 'unit': rule.ingredient.unit, 'stock': rule.ingredient.stock_quantity}
                    ing_tomorrow[i_name]['amount'] += needed_tom
                    if i_name not in ing_week: ing_week[i_name] = {'amount': 0, 'unit': rule.ingredient.unit, 'stock': rule.ingredient.stock_quantity}
                    ing_week[i_name]['amount'] += needed_week

        def format_list(d):
            lst = []
            for name, data in d.items():
                lst.append({'name': name, 'amount': round(data['amount'], 1), 'unit': data['unit'], 'stock': data['stock'], 'status': 'Tekort ⚠️' if data['amount'] > data['stock'] else 'Voldoende ✅'})
            return sorted(lst, key=lambda x: x['name'])

        shop_tomorrow = format_list(ing_tomorrow)
        shop_week = format_list(ing_week)

        _cached_forecast = (forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction)
        _last_calculation_time = datetime.now()
        
        return forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction

    except Exception as e:
        print(f"Fout in algoritme: {e}")
        return [], [], [], date.today(), date.today()