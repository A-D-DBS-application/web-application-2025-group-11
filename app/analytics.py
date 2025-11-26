import pandas as pd
import numpy as np
from datetime import date, timedelta
from sklearn.linear_model import LinearRegression
from .models import db, Order, OrderItem, Product
from sqlalchemy import text

def generate_weekly_forecast():
    # 1. DATA OPHALEN (Raw SQL voor snelheid)
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

        # 2. GROEPEREN
        daily_sales = df.groupby(['pickup_date', 'name'])['quantity'].sum().reset_index()

        forecast_results = []
        unique_products = daily_sales['name'].unique()
        
        start_prediction = date.today() + timedelta(days=1)
        end_prediction = date.today() + timedelta(days=7)

        # 3. VOORSPELLEN (Linear Regression)
        for product_name in unique_products:
            product_data = daily_sales[daily_sales['name'] == product_name].copy()

            if len(product_data) < 5:
                continue

            product_data['date_ordinal'] = product_data['pickup_date'].apply(lambda x: x.toordinal())
            
            X = product_data[['date_ordinal']]
            y = product_data['quantity']

            model = LinearRegression()
            model.fit(X, y)

            total_predicted_week = 0
            
            for i in range(1, 8):
                future_date = date.today() + timedelta(days=i)
                future_ordinal = future_date.toordinal()
                prediction = model.predict([[future_ordinal]])
                qty = max(0, round(prediction[0]))
                total_predicted_week += qty

            last_week_avg = product_data.tail(7)['quantity'].sum()
            
            trend = "stabiel ➡️"
            if total_predicted_week > (last_week_avg * 1.1): trend = "stijgend 📈"
            if total_predicted_week < (last_week_avg * 0.9): trend = "dalend 📉"

            forecast_results.append({
                'product': product_name,
                'predicted_week': int(total_predicted_week),
                'trend': trend
            })

        forecast_results.sort(key=lambda x: x['predicted_week'], reverse=True)
        
        return forecast_results, start_prediction, end_prediction

    except Exception as e:
        print(f"Fout in algoritme: {e}")
        raise e