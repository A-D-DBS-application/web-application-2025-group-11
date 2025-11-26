import random
from datetime import datetime, timedelta
from decimal import Decimal
from app import create_app
from app.models import db, Product, Order, OrderItem, Profile

app = create_app()

DAYS_BACK = 370 
BUSY_HOLIDAYS = [(25, 12), (1, 1), (31, 3), (12, 5)]

def ensure_seasonal_products():
    seasonal = [
        {"name": "Marsepein Figuur", "price": 4.50, "category": "koffiekoeken"},
        {"name": "Grote Speculaas", "price": 3.00, "category": "koffiekoeken"},
        {"name": "Kerststronk", "price": 18.00, "category": "koffiekoeken"}
    ]
    for item in seasonal:
        exists = Product.query.filter(Product.name.ilike(item['name'])).first()
        if not exists:
            p = Product(
                name=item['name'], price=Decimal(item['price']), 
                category=item['category'], description="Seizoensspecialiteit",
                image_url="logo.png", is_available=True
            )
            db.session.add(p)
    db.session.commit()

def run_history_seeder():
    with app.app_context():
        print("--- 🕒 STARTEN MET HISTORIE GENEREREN ---")
        
        ensure_seasonal_products()
        
        # Zoek de gebruiker die je net hebt aangemaakt
        shop_profile = Profile.query.filter(Profile.full_name.ilike("%Winkel%")).first()
        
        if not shop_profile:
            print("❌ FOUT: Kan profiel 'Winkelverkoop' niet vinden!")
            print("👉 Maak eerst een account aan via de website!")
            return

        print(f"✅ Account gevonden: {shop_profile.full_name}")
        
        products = Product.query.all()
        real_users = Profile.query.filter(Profile.id != shop_profile.id).all()
        if not real_users: real_users = [shop_profile] # Fallback

        marsepein = Product.query.filter(Product.name.ilike("%Marsepein%")).first()
        kerststronk = Product.query.filter(Product.name.ilike("%Kerststronk%")).first()

        orders_created = 0
        
        for i in range(DAYS_BACK, 0, -1):
            current_date = datetime.now() - timedelta(days=i)
            month = current_date.month
            day = current_date.day
            weekday = current_date.weekday() 
            
            # DRUKTE BEPALEN
            if weekday >= 5: # Weekend
                online_count = random.randint(2, 5)
                walk_in_count = random.randint(10, 20)
            else:
                online_count = random.randint(0, 2)
                walk_in_count = random.randint(4, 10)

            is_holiday = False
            for h_day, h_month in BUSY_HOLIDAYS:
                if day == h_day and month == h_month:
                    online_count *= 2
                    walk_in_count *= 3
                    is_holiday = True

            is_sinterklaas = (month == 11 and day >= 15) or (month == 12 and day <= 6)
            is_kerst = (month == 12 and day >= 20 and day <= 25)

            total_today = online_count + walk_in_count

            for k in range(total_today):
                if k < online_count:
                    customer = random.choice(real_users)
                    remarks = "Online bestelling"
                else:
                    customer = shop_profile
                    remarks = "Winkelverkoop"

                order = Order(
                    user_id=customer.id,
                    status='picked_up',
                    pickup_date=current_date.date(),
                    order_date=current_date,
                    total_price=0,
                    remarks=remarks
                )
                db.session.add(order)
                db.session.flush()
                
                num_items = random.randint(1, 5)
                if is_holiday: num_items += 3
                
                order_total = Decimal(0)
                
                if is_sinterklaas and marsepein and random.random() > 0.6:
                    qty = random.randint(1, 3)
                    db.session.add(OrderItem(order_id=order.id, product_id=marsepein.id, quantity=qty, unit_price_at_order=marsepein.price))
                    order_total += marsepein.price * Decimal(qty)

                for _ in range(num_items):
                    prod = random.choice(products)
                    if prod.name in ["Marsepein Figuur", "Kerststronk", "Grote Speculaas"]: continue
                    
                    qty = random.randint(1, 3)
                    if prod.category == 'pistoles' and weekday >= 5: qty = 6 

                    item_total = prod.price * Decimal(qty)
                    order_total += item_total
                    db.session.add(OrderItem(order_id=order.id, product_id=prod.id, quantity=qty, unit_price_at_order=prod.price))
                
                order.total_price = order_total
                db.session.add(order)
                orders_created += 1
        
        db.session.commit()
        print(f"\n--- ✅ KLAAR! {orders_created} orders gegenereerd. ---")

if __name__ == "__main__":
    run_history_seeder()