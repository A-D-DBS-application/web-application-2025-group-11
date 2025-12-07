import random
import time
from datetime import datetime, timedelta, date
from decimal import Decimal
import holidays
from app import create_app
from app.models import db, Product, Order, OrderItem, Profile
import uuid

app = create_app()

# --- INSTELLINGEN ---
DAYS_BACK = 370       
DAYS_FORWARD = 7      
CANCEL_RATE = 0.05    

def is_busy_day(d):
    """Geeft een multiplier voor feestdagen."""
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return 1.8
    if d.weekday() >= 5: return 1.4
    if d.weekday() == 2: return 0.7
    return 1.0

def ensure_shop_profile():
    shop_profile = Profile.query.filter(Profile.full_name.ilike("%Winkel%")).first()
    if not shop_profile:
        try:
            # type: ignore
            p = Profile(full_name="Winkelverkoop", id=uuid.uuid4(), is_admin=False)
            db.session.add(p)
            db.session.commit()
            return p
        except: return None
    return shop_profile

def run_history_seeder():
    with app.app_context():
        print(f"--- 📉 STARTEN MET 'REALISTISCHE DIP' SEED (SAFE MODE) ---")
        
        shop_profile = ensure_shop_profile()
        if not shop_profile: return
        
        # We halen producten op als simpele dictionaries om sessie-conflicten te voorkomen
        db_products = Product.query.all()
        if not db_products:
            print("❌ Geen producten gevonden.")
            return

        # Cache product data in geheugen (voorkomt queries in loop)
        products_data = []
        for p in db_products:
            products_data.append({
                'id': p.id,
                'name': p.name,
                'category': p.category,
                'price': p.price
            })

        real_users = Profile.query.filter(Profile.id != shop_profile.id).all()
        if not real_users: real_users = [shop_profile]
        
        # Cache user IDs
        user_ids = [u.id for u in real_users]
        shop_id = shop_profile.id

        orders_created = 0
        
        # Gewogen lijst maken (brood populairder)
        weighted_products = []
        for p in products_data:
            weight = 1
            if 'brood' in p['name'].lower(): weight = 8
            elif 'pistolet' in p['name'].lower(): weight = 5
            elif 'koek' in p['name'].lower(): weight = 3
            weighted_products.extend([p] * weight)

        for i in range(-DAYS_BACK, DAYS_FORWARD + 1):
            pickup_date_obj = datetime.now() + timedelta(days=i) 
            d_date = pickup_date_obj.date()
            
            # --- DIP LOGICA ---
            market_condition = 1.0
            if i > -42:
                days_into_dip = i + 42
                drop = (days_into_dip / 42) * 0.4
                market_condition = 1.0 - drop
                if market_condition < 0.6: market_condition = 0.6

            # Volume
            day_factor = is_busy_day(d_date)
            base_volume = random.randint(12, 22)
            total_today = int(base_volume * day_factor * market_condition)

            if total_today == 0 and i > 0 and random.random() < 0.3: total_today = 1
            if total_today == 0: continue

            for _ in range(total_today):
                # Klant bepalen
                if i > 0:
                    is_online = True
                    customer_id = random.choice(user_ids)
                    remarks = "Online"
                    status = 'pending'
                    days_before = random.randint(1, 3)
                    order_date = pickup_date_obj - timedelta(days=days_before)
                else:
                    if random.random() < 0.2:
                        is_online = True
                        customer_id = random.choice(user_ids)
                        remarks = "Online"
                        order_date = pickup_date_obj - timedelta(days=random.randint(1, 3))
                    else:
                        is_online = False
                        customer_id = shop_id
                        remarks = "Winkelverkoop"
                        order_date = pickup_date_obj
                    
                    status = 'cancelled' if random.random() < CANCEL_RATE else 'picked_up'

                order_date = order_date.replace(hour=random.randint(8, 17), minute=random.randint(0,59))

                # 1. ORDER MAKEN
                order = Order(
                    user_id=customer_id,
                    status=status,
                    pickup_date=d_date,
                    order_date=order_date,
                    created_at=order_date,
                    total_price=0,
                    remarks=remarks
                )
                db.session.add(order)
                
                # 2. FLUSH: Zorg dat order een ID krijgt!
                # Dit is de cruciale stap die de crash voorkomt
                db.session.flush()

                # 3. ITEMS TOEVOEGEN
                avg_items = 3 if market_condition > 0.8 else 2
                num_items = max(1, int(random.gauss(avg_items, 1)))
                chosen = random.choices(weighted_products, k=num_items)
                
                total_price = Decimal(0)
                
                for prod in chosen:
                    qty = 1
                    if prod['category'] == 'pistoles': qty = random.choice([4, 6])
                    
                    total_price += prod['price'] * Decimal(qty)
                    
                    # Expliciet koppelen via order_id
                    item = OrderItem(
                        order_id=order.id,  # Nu bestaat order.id zeker!
                        product_id=prod['id'],
                        quantity=qty,
                        unit_price_at_order=prod['price']
                    )
                    db.session.add(item)

                # Totaalprijs updaten
                order.total_price = total_price
                orders_created += 1
            
            # Bulk commit (minder vaak flush is sneller, maar we flushen nu per order)
            # Dus we committen per dag om de transactie klein te houden
            if i % 10 == 0:
                try:
                    db.session.commit()
                    print("📉", end="", flush=True)
                except Exception as e:
                    db.session.rollback()
                    print(f"Fout: {e}")

        db.session.commit()
        print(f"\n\n--- ✅ KLAAR! {orders_created} orders gegenereerd (Dip Scenario). ---")

if __name__ == "__main__":
    run_history_seeder()