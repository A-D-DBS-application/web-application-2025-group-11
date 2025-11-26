import pandas as pd
import numpy as np
from datetime import date, timedelta
from sklearn.ensemble import RandomForestRegressor
from .models import db, Order, OrderItem, Product
from sqlalchemy import text

# Dezelfde lijst als in je seeder, zodat de AI het patroon kan herkennen
HOLIDAYS = [
    (25, 12), # Kerst
    (1, 1),   # Nieuwjaar
    (31, 3),  # Pasen (ongeveer)
    (12, 5),  # Moederdag (ongeveer)
    (1, 11),  # Allerheiligen
    (15, 8),  # Moederdag (Antwerpen) / Maria Hemelvaart
    (21, 7),  # Nationale feestdag
]

def is_holiday(d):
    """Hulpprogramma: Geeft 1 terug als het een feestdag is, anders 0"""
    if (d.day, d.month) in HOLIDAYS:
        return 1
    return 0

def generate_smart_forecast():
    print("--- 🧠 AI ALGORITME (MET FEESTDAGEN) STARTEN ---")

    # 1. DATA OPHALEN
    sql = text("""
        SELECT 
            orders.pickup_date,
            products.name,
            order_items.quantity
        FROM order_items
        JOIN orders ON order_items.order_id = orders.id
        JOIN products ON order_items.product_id = products.id
        WHERE orders.status != 'cancelled'
    """)

    try:
        with db.engine.connect() as conn:
            df = pd.read_sql(sql, conn)
            
        if df.empty:
            return [], date.today(), date.today()

        df['pickup_date'] = pd.to_datetime(df['pickup_date'])

        # 2. FEATURE ENGINEERING
        # We voegen extra kennis toe aan de data
        df['weekday'] = df['pickup_date'].dt.dayofweek
        df['date_ordinal'] = df['pickup_date'].apply(lambda x: x.toordinal())
        
        # NIEUW: Vertel de AI of het een feestdag was
        df['is_holiday'] = df['pickup_date'].apply(is_holiday)

        # Groepeer per dag (en neem de features mee)
        # We gebruiken 'max' voor is_holiday en weekday omdat die hetzelfde zijn voor die dag
        daily_sales = df.groupby(['date_ordinal', 'weekday', 'is_holiday', 'name'])['quantity'].sum().reset_index()

        forecast_results = []
        unique_products = daily_sales['name'].unique()
        
        start_prediction = date.today() + timedelta(days=1)
        end_prediction = date.today() + timedelta(days=7)

        # 3. VOORSPELLEN
        for product_name in unique_products:
            product_data = daily_sales[daily_sales['name'] == product_name].copy()

            if len(product_data) < 5:
                continue

            # INPUT (X): Datum + Weekdag + IS HET FEESTDAG?
            X = product_data[['date_ordinal', 'weekday', 'is_holiday']]
            y = product_data['quantity']

            # Train het model
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)

            total_predicted_week = 0
            predicted_tomorrow = 0
            
            # Voorspel toekomst
            for i in range(1, 8):
                future_date = date.today() + timedelta(days=i)
                
                # We moeten voor de toekomst OOK berekenen of het een feestdag is
                future_is_holiday = is_holiday(future_date)
                
                future_features = pd.DataFrame({
                    'date_ordinal': [future_date.toordinal()],
                    'weekday': [future_date.weekday()],
                    'is_holiday': [future_is_holiday] # <--- Dit is de sleutel!
                })
                
                prediction = model.predict(future_features)
                qty = max(0, round(prediction[0]))
                
                total_predicted_week += qty
                
                if i == 1:
                    predicted_tomorrow = qty

            # Trend
            last_week_avg = product_data.tail(7)['quantity'].sum()
            trend = "stabiel ➡️"
            if total_predicted_week > (last_week_avg * 1.1): trend = "stijgend 📈"
            if total_predicted_week < (last_week_avg * 0.9): trend = "dalend 📉"

            forecast_results.append({
                'product': product_name,
                'tomorrow': int(predicted_tomorrow),
                'week_total': int(total_predicted_week),
                'trend': trend
            })

        forecast_results.sort(key=lambda x: x['tomorrow'], reverse=True)
        
        return forecast_results, start_prediction, end_prediction

    except Exception as e:
        print(f"Fout in algoritme: {e}")
        raise e