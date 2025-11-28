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
    # 1. Check officiële Belgische feestdagen (Wettelijk: Kerst, Nieuwjaar, Pasen...)
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays:
        return 1
    
    # 2. Vaste Datums (Bakkers toppers)
    if d.month == 12 and d.day == 6: return 1  # Sinterklaas
    if d.month == 2 and d.day == 14: return 1  # Valentijn
    if d.month == 1 and d.day == 6: return 1   # Driekoningen

    # 3. Variabele Zondagen
    if d.weekday() == 6: # Zondag
        # Moederdag (2e zondag mei)
        if d.month == 5 and 8 <= d.day <= 14: return 1
        # Vaderdag (2e zondag juni)
        if d.month == 6 and 8 <= d.day <= 14: return 1

    # 4. Verloren Maandag (Eerste maandag na Driekoningen)
    # Dit is altijd een maandag tussen 7 en 13 januari
    if d.month == 1 and d.weekday() == 0 and 7 <= d.day <= 13:
        return 1
        
    return 0

def generate_smart_forecast():
    global _cached_forecast, _last_calculation_time
    
    # 1. CHECK CACHE (1 uur geldig)
    if _cached_forecast and _last_calculation_time:
        if datetime.now() - _last_calculation_time < timedelta(minutes=60):
            print("--- ⚡️ CACHE GEBRUIKT ---")
            return _cached_forecast

    print("--- 🧠 AI ALGORITME STARTEN ---")

    # 2. DATA OPHALEN
    sql = text("""
        SELECT orders.pickup_date, products.name, order_items.quantity
        FROM order_items
        JOIN orders ON order_items.order_id = orders.id
        JOIN products ON order_items.product_id = products.id
        WHERE orders.status != 'cancelled'
    """)

    try:
        with db.engine.connect() as conn:
            df = pd.read_sql(sql, conn)
            
        if df.empty:
            return [], [], date.today(), date.today()

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
            
            # Minimaal 5 dagen data nodig
            if len(product_data) < 5: continue

            X = product_data[['date_ordinal', 'weekday', 'is_holiday']]
            y = product_data['quantity']

            # Random Forest is slim genoeg om niet-lineaire patronen (zoals zondagen) te leren
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

        # --- DEEL B: INGREDIËNTEN BEREKENEN (MRP) ---
        ingredients_needed = {} 

        for forecast_item in forecast_results:
            qty_to_bake = forecast_item['tomorrow']
            if qty_to_bake == 0: continue

            product = Product.query.filter_by(name=forecast_item['product_name']).first()
            
            if product and product.ingredients:
                for rule in product.ingredients:
                    ing_name = rule.ingredient.name
                    amount_needed = rule.quantity_needed * qty_to_bake
                    unit = rule.ingredient.unit

                    if ing_name in ingredients_needed:
                        ingredients_needed[ing_name]['amount'] += amount_needed
                    else:
                        ingredients_needed[ing_name] = {
                            'amount': amount_needed,
                            'unit': unit,
                            'current_stock': rule.ingredient.stock_quantity
                        }

        shopping_list = []
        for name, data in ingredients_needed.items():
            shopping_list.append({
                'name': name,
                'amount': round(data['amount'], 1),
                'unit': data['unit'],
                'current_stock': data['current_stock'],
                'status': 'Tekort ⚠️' if data['amount'] > data['current_stock'] else 'Voldoende ✅'
            })
        
        shopping_list.sort(key=lambda x: x['name'])

        # Cache updaten
        _cached_forecast = (forecast_results, shopping_list, start_prediction, end_prediction)
        _last_calculation_time = datetime.now()
        
        return forecast_results, shopping_list, start_prediction, end_prediction

    except Exception as e:
        print(f"Fout in algoritme: {e}")
        return [], [], date.today(), date.today()