import pandas as pd
import numpy as np
import holidays
from datetime import datetime, date, timedelta
from sklearn.ensemble import RandomForestRegressor
from .models import db, Order, OrderItem, Product, Ingredient
from sqlalchemy import text

# --- SIMPELE CACHE ---
_cached_forecast = None
_last_calculation_time = None

def is_special_day(d):
    """
    Bepaalt of een datum een speciale dag is voor de bakkerij.
    """
    # 1. Check officiële Belgische feestdagen
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return 1
    
    # 2. Vaste Datums (Bakkers toppers)
    if d.month == 12 and d.day == 6: return 1  # Sinterklaas
    if d.month == 2 and d.day == 14: return 1  # Valentijn
    if d.month == 1 and d.day == 6: return 1   # Driekoningen

    # 3. Variabele Zondagen
    if d.weekday() == 6: 
        # Moederdag (2e zondag mei)
        if d.month == 5 and 8 <= d.day <= 14: return 1
        # Vaderdag (2e zondag juni)
        if d.month == 6 and 8 <= d.day <= 14: return 1

    # 4. Verloren Maandag (Eerste maandag na Driekoningen)
    if d.month == 1 and d.weekday() == 0 and 7 <= d.day <= 13:
        return 1
        
    return 0

def generate_smart_forecast(force_refresh=False):
    global _cached_forecast, _last_calculation_time
    
    # 1. CHECK CACHE (Alleen als we NIET dwingen)
    if not force_refresh and _cached_forecast and _last_calculation_time:
        if datetime.now() - _last_calculation_time < timedelta(minutes=60):
            print("--- ⚡️ CACHE GEBRUIKT ---")
            return _cached_forecast

    print("--- 🧠 AI ALGORITME & INKOOP BEREKENING STARTEN ---")

    # 2. DATA OPHALEN (Alleen van het laatste jaar om crash te voorkomen)
    sql = text("""
        SELECT orders.pickup_date, products.name, order_items.quantity
        FROM order_items
        JOIN orders ON order_items.order_id = orders.id
        JOIN products ON order_items.product_id = products.id
        WHERE orders.status != 'cancelled'
        AND orders.pickup_date >= CURRENT_DATE - INTERVAL '370 days'
    """)

    try:
        with db.engine.connect() as conn:
            df = pd.read_sql(sql, conn)
            
        if df.empty:
            return [], [], [], date.today(), date.today()

        df['pickup_date'] = pd.to_datetime(df['pickup_date'])
        
        # --- FEATURE ENGINEERING ---
        df['weekday'] = df['pickup_date'].dt.dayofweek
        df['date_ordinal'] = df['pickup_date'].apply(lambda x: x.toordinal())
        df['is_holiday'] = df['pickup_date'].apply(is_special_day)

        daily_sales = df.groupby(['date_ordinal', 'weekday', 'is_holiday', 'name'])['quantity'].sum().reset_index()

        forecast_results = []
        unique_products = daily_sales['name'].unique()
        
        start_prediction = date.today() + timedelta(days=1)
        end_prediction = date.today() + timedelta(days=7)

        # --- DEEL A: VERKOOP VOORSPELLEN ---
        for product_name in unique_products:
            product_data = daily_sales[daily_sales['name'] == product_name].copy()
            
            if len(product_data) < 5: continue

            X = product_data[['date_ordinal', 'weekday', 'is_holiday']]
            y = product_data['quantity']

            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)

            total_predicted_week = 0
            predicted_tomorrow = 0
            
            for i in range(1, 8):
                future_date = date.today() + timedelta(days=i)
                
                future_features = pd.DataFrame({
                    'date_ordinal': [future_date.toordinal()],
                    'weekday': [future_date.weekday()],
                    'is_holiday': [is_special_day(future_date)]
                })
                
                prediction = model.predict(future_features)
                qty = max(0, round(prediction[0]))
                total_predicted_week += qty
                
                if i == 1: predicted_tomorrow = qty

            last_week_avg = product_data.tail(7)['quantity'].sum()
            trend = "stabiel ➡️"
            if total_predicted_week > (last_week_avg * 1.1): trend = "stijgend 📈"
            if total_predicted_week < (last_week_avg * 0.9): trend = "dalend 📉"

            forecast_results.append({
                'product_name': product_name,
                'tomorrow': int(predicted_tomorrow),
                'week_total': int(total_predicted_week),
                'trend': trend
            })

        forecast_results.sort(key=lambda x: x['tomorrow'], reverse=True)

        # --- DEEL B: INGREDIËNTEN BEREKENEN ---
        ing_tomorrow = {} 
        ing_week = {}

        for forecast_item in forecast_results:
            qty_tom = forecast_item['tomorrow']
            qty_week = forecast_item['week_total']

            product = Product.query.filter_by(name=forecast_item['product_name']).first()
            if product and product.ingredients:
                for rule in product.ingredients:
                    i_name = rule.ingredient.name
                    i_unit = rule.ingredient.unit
                    i_stock = rule.ingredient.stock_quantity

                    needed_tom = rule.quantity_needed * qty_tom
                    needed_week = rule.quantity_needed * qty_week

                    if i_name in ing_tomorrow: ing_tomorrow[i_name]['amount'] += needed_tom
                    else: ing_tomorrow[i_name] = {'amount': needed_tom, 'unit': i_unit, 'stock': i_stock}
                    
                    if i_name in ing_week: ing_week[i_name]['amount'] += needed_week
                    else: ing_week[i_name] = {'amount': needed_week, 'unit': i_unit, 'stock': i_stock}

        # Synchroniseren (zodat tabellen even lang zijn)
        all_ingredients = set(ing_tomorrow.keys()) | set(ing_week.keys())
        for name in all_ingredients:
            if name not in ing_tomorrow:
                ref = ing_week[name]
                ing_tomorrow[name] = {'amount': 0, 'unit': ref['unit'], 'stock': ref['stock']}
            if name not in ing_week:
                ref = ing_tomorrow[name]
                ing_week[name] = {'amount': 0, 'unit': ref['unit'], 'stock': ref['stock']}

        def format_list(d):
            lst = []
            for name, data in d.items():
                lst.append({
                    'name': name, 
                    'amount': round(data['amount'], 1), 
                    'unit': data['unit'], 
                    'stock': data['stock'],
                    'status': 'Tekort ⚠️' if data['amount'] > data['stock'] else 'Voldoende ✅'
                })
            return sorted(lst, key=lambda x: x['name'])

        shop_tomorrow = format_list(ing_tomorrow)
        shop_week = format_list(ing_week)

        # Cache update
        _cached_forecast = (forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction)
        _last_calculation_time = datetime.now()
        
        return forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction

    except Exception as e:
        print(f"Fout in algoritme: {e}")
        return [], [], [], date.today(), date.today()