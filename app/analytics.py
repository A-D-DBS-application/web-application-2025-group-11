import pandas as pd
import numpy as np
import holidays
from datetime import datetime, date, timedelta
from decimal import Decimal
from sklearn.ensemble import RandomForestRegressor
from .models import db, Order, OrderItem, Product, Ingredient
from sqlalchemy import text

# --- CACHE OPSLAG ---
_cached_forecast = None
_last_calculation_time = None

def is_special_day(d):
    """Bepaalt of een datum een speciale dag is."""
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return 1
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

    print("--- 🧠 AI TWIN-ENGINE STARTEN ---")

    # 2. DATA OPHALEN (Historie van 1 jaar)
    # We halen ALLES op, en splitsen het daarna in Python
    sql = text("""
        SELECT orders.pickup_date, orders.remarks, products.name, order_items.quantity
        FROM order_items
        JOIN orders ON order_items.order_id = orders.id
        JOIN products ON order_items.product_id = products.id
        WHERE orders.status != 'cancelled'
        AND orders.pickup_date >= CURRENT_DATE - INTERVAL '370 days'
        AND orders.pickup_date < CURRENT_DATE
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

        # --- SPLITSEN: WINKEL vs ONLINE ---
        # We filteren op de remarks 'Winkelverkoop' die de seeder gebruikt
        # df_shop = Data om de AI mee te trainen (het onvoorspelbare gedrag)
        df_shop = df[df['remarks'] == 'Winkelverkoop'].copy()
        
        # Groepeer de winkelverkoop per dag
        daily_shop_sales = df_shop.groupby(['date_ordinal', 'weekday', 'is_holiday', 'name'])['quantity'].sum().reset_index()

        # --- 3. HARDE BESTELLINGEN (TOEKOMST) ---
        # Dit zijn de orders die al in het systeem staan voor de komende week
        future_sql = text("""
            SELECT orders.pickup_date, products.name, SUM(order_items.quantity) as total_ordered
            FROM order_items
            JOIN orders ON order_items.order_id = orders.id
            JOIN products ON order_items.product_id = products.id
            WHERE orders.status != 'cancelled'
            AND orders.pickup_date > CURRENT_DATE
            GROUP BY orders.pickup_date, products.name
        """)
        
        with db.engine.connect() as conn:
            df_future = pd.read_sql(future_sql, conn)
            
        future_orders_map = {}
        if not df_future.empty:
            df_future['pickup_date'] = pd.to_datetime(df_future['pickup_date']).dt.date
            for index, row in df_future.iterrows():
                future_orders_map[(row['pickup_date'], row['name'])] = row['total_ordered']

        forecast_results = []
        unique_products = df['name'].unique() # Alle producten
        
        start_prediction = date.today() + timedelta(days=1)
        end_prediction = date.today() + timedelta(days=7)

        # --- A. VOORSPELLEN ---
        for product_name in unique_products:
            # Pak alleen de WINKEL historie van dit product
            product_data = daily_shop_sales[daily_shop_sales['name'] == product_name].copy()
            
            # Train model alleen als er genoeg winkeldata is
            model = None
            if len(product_data) >= 5:
                X = product_data[['date_ordinal', 'weekday', 'is_holiday']]
                y = product_data['quantity']
                model = RandomForestRegressor(n_estimators=100, random_state=42)
                model.fit(X, y)

            total_predicted_week = 0
            predicted_tomorrow = 0
            
            for i in range(1, 8):
                future_date = date.today() + timedelta(days=i)
                
                # 1. AI Voorspelling (Winkelverkoop / Walk-ins)
                shop_prediction = 0
                if model:
                    future_features = pd.DataFrame({
                        'date_ordinal': [future_date.toordinal()],
                        'weekday': [future_date.weekday()],
                        'is_holiday': [is_special_day(future_date)]
                    })
                    raw_pred = model.predict(future_features)[0]
                    shop_prediction = max(0, raw_pred)

                # 2. Veiligheidsmarge (10% extra op de gok)
                shop_qty_safe = int(np.ceil(shop_prediction * 1.10))

                # 3. Harde Bestellingen (Online / Vooraf besteld)
                online_orders = int(future_orders_map.get((future_date, product_name), 0))
                
                # 4. TWIN ENGINE FORMULE:
                # Totaal = (Gok voor de winkel) + (Harde zekerheid online)
                final_qty = shop_qty_safe + online_orders
                
                total_predicted_week += final_qty
                if i == 1: predicted_tomorrow = final_qty

            # Trend (Gebaseerd op totale volume in de data)
            trend = "stabiel ➡️"
            # Simpele logica: als weektotaal > 50 is het veel (kan je verfijnen)
            if total_predicted_week > 50: trend = "stijgend 📈"
            elif total_predicted_week < 10: trend = "dalend 📉"

            forecast_results.append({
                'product_name': product_name,
                'tomorrow': predicted_tomorrow,
                'week_total': total_predicted_week,
                'trend': trend
            })

        forecast_results.sort(key=lambda x: x['tomorrow'], reverse=True)

        # --- B. INGREDIËNTEN BEREKENEN ---
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

                    needed_tom = rule.quantity_needed * Decimal(qty_tom)
                    needed_week = rule.quantity_needed * Decimal(qty_week)

                    if i_name in ing_tomorrow: ing_tomorrow[i_name]['amount'] += needed_tom
                    else: ing_tomorrow[i_name] = {'amount': needed_tom, 'unit': i_unit, 'stock': i_stock}
                    
                    if i_name in ing_week: ing_week[i_name]['amount'] += needed_week
                    else: ing_week[i_name] = {'amount': needed_week, 'unit': i_unit, 'stock': i_stock}

        # Synchroniseren
        all_ingredients = set(ing_tomorrow.keys()) | set(ing_week.keys())
        for name in all_ingredients:
            if name not in ing_tomorrow:
                ref = ing_week[name]
                ing_tomorrow[name] = {'amount': Decimal(0), 'unit': ref['unit'], 'stock': ref['stock']}
            if name not in ing_week:
                ref = ing_tomorrow[name]
                ing_week[name] = {'amount': Decimal(0), 'unit': ref['unit'], 'stock': ref['stock']}

        def format_list(d):
            lst = []
            for name, data in d.items():
                lst.append({
                    'name': name, 'amount': round(data['amount'], 1), 'unit': data['unit'], 
                    'stock': data['stock'],
                    'status': 'Tekort ⚠️' if data['amount'] > data['stock'] else 'Voldoende ✅'
                })
            return sorted(lst, key=lambda x: x['name'])

        shop_tomorrow = format_list(ing_tomorrow)
        shop_week = format_list(ing_week)

        _cached_forecast = (forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction)
        _last_calculation_time = datetime.now()
        
        return forecast_results, shop_tomorrow, shop_week, start_prediction, end_prediction

    except Exception as e:
        print(f"Fout in algoritme: {e}")
        return [], [], [], date.today(), date.today()