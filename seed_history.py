import random
import time
from datetime import datetime, timedelta
from decimal import Decimal
import holidays
from app import create_app
from app.models import db, Product, Order, OrderItem, Profile
import uuid

app = create_app()

DAYS_BACK = 370 
DAYS_FORWARD = 7 

def is_special_day(d):
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return True
    if d.month == 5 and d.weekday() == 6 and 8 <= d.day <= 14: return True 
    return False

def ensure_shop_profile():
    shop_profile = Profile.query.filter(Profile.full_name.ilike("%Winkel%")).first()
    if not shop_profile:
        print("❌ FOUT: Kan profiel 'Winkelverkoop' niet vinden! Maak dit eerst aan.")
        return None
    return shop_profile

def run_history_seeder():
    with app.app_context():
        print("--- 🕒 STARTEN MET HISTORIE & TOEKOMST GENEREREN ---")
        
        shop_profile = ensure_shop_profile()
        if not shop_profile: return
        
        products = Product.query.all()
        real_users = Profile.query.filter(Profile.id != shop_profile.id).all()
        if not real_users: real_users = [shop_profile]

        orders_created = 0
        
        # Loop van 1 jaar geleden tot 1 week in de toekomst
        for i in range(-DAYS_BACK, DAYS_FORWARD):
            current_date = datetime.now() + timedelta(days=i) 
            d_date = current_date.date()
            
            month = current_date.month
            day = current_date.day
            weekday = current_date.weekday() 
            
            # DRUKTE
            holiday_multiplier = 1
            if is_special_day(d_date): holiday_multiplier = 3

            if weekday >= 5: # Weekend
                online = random.randint(2, 6) * holiday_multiplier
                walk_in = random.randint(15, 30) * holiday_multiplier
            elif weekday == 2:
                online = random.randint(1, 3)
                walk_in = random.randint(8, 15)
            else:
                online = random.randint(0, 2)
                walk_in = random.randint(5, 10)

            if i > 0:
                walk_in = 0 
                status = 'pending'
            else:
                status = 'picked_up'

            total_today = online + walk_in

            for k in range(total_today):
                if k < online:
                    customer = random.choice(real_users)
                    remarks = "Online"
                else:
                    customer = shop_profile
                    remarks = "Winkelverkoop"

                order = Order(
                    user_id=customer.id,
                    status=status,
                    pickup_date=d_date,
                    order_date=current_date, 
                    total_price=0,
                    remarks=remarks
                )
                db.session.add(order)
                db.session.flush()
                
                num_items = random.randint(1, 5)
                order_total = Decimal(0)
                
                for _ in range(num_items):
                    prod = random.choice(products)
                    qty = random.randint(1, 3)
                    if prod.category == 'pistoles' and weekday >= 5: qty = 6 

                    item_total = prod.price * Decimal(qty)
                    order_total += item_total
                    db.session.add(OrderItem(order_id=order.id, product_id=prod.id, quantity=qty, unit_price_at_order=prod.price))
                
                order.total_price = order_total
                db.session.add(order)
                orders_created += 1
            
            # --- BELANGRIJKE VERANDERING: OPSLAAN PER DAG ---
            # We slaan de data elke dag op, in plaats van alles in 1 keer.
            # Dit voorkomt dat de database verbinding verbroken wordt.
            try:
                db.session.commit()
                # Print een puntje voor elke dag zodat je ziet dat hij leeft
                print(".", end="", flush=True) 
            except Exception as e:
                db.session.rollback()
                print(f"Fout bij dag {d_date}: {e}")

        print(f"\n\n--- ✅ KLAAR! {orders_created} orders gegenereerd. ---")

if __name__ == "__main__":
    run_history_seeder()