import random
import time
from datetime import datetime, timedelta, date
from decimal import Decimal
import holidays
from app import create_app
from app.models import db, Product, Order, OrderItem, Profile
import uuid

app = create_app()

# Instellingen
DAYS_BACK = 370       
DAYS_FORWARD = 7      
CANCEL_RATE = 0.04    

def get_season_weight(product, current_date):
    # 1. Harde Seizoenscheck
    if product.season_start and product.season_end:
        curr_md = current_date.strftime('%m-%d')
        start = product.season_start
        end = product.season_end
        
        in_season = False
        if start <= end:
            if start <= curr_md <= end: in_season = True
        else:
            if curr_md >= start or curr_md <= end: in_season = True
            
        if not in_season: return 0 

    # 2. Populariteit bepalen
    weight = 10 
    month = current_date.month
    day = current_date.day
    weekday = current_date.weekday()
    name = product.name.lower()
    cat = product.category.lower() if product.category else ""

    # Feestdagen boosts
    if (month == 11 and day >= 15) or (month == 12 and day <= 6):
        if 'speculaas' in name or 'marsepein' in name: weight = 300
    if (month == 12 and day >= 20) or (month == 1 and day <= 5):
        if 'kerst' in name or 'stronk' in name: weight = 250
        if 'worstenbrood' in name: weight = 150
    if month == 2 and 1 <= day <= 14:
        if 'hart' in name or 'liefde' in name: weight = 200
    if weekday >= 4: 
        if 'pistole' in cat or 'taart' in cat: weight += 50
        if 'brood' in cat: weight += 20

    return weight

def is_busy_day(d):
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return 2.5
    if d.month == 12 and d.day == 6: return 3.0
    if d.month == 12 and d.day in [24, 31]: return 4.0
    if d.weekday() >= 5: return 2.0 
    if d.weekday() == 4: return 1.2 
    return 0.8 

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
        print(f"--- 🚀 STARTEN MET SNELLE HISTORIE ({DAYS_BACK} dagen) ---")
        
        shop_profile = ensure_shop_profile()
        if not shop_profile: return
        
        products = Product.query.all()
        real_users = Profile.query.filter(Profile.id != shop_profile.id).all()
        if not real_users: real_users = [shop_profile]

        orders_created = 0
        
        # We verzamelen data in batches om netwerkverkeer te minimaliseren
        for i in range(-DAYS_BACK, DAYS_FORWARD):
            pickup_date_obj = datetime.now() + timedelta(days=i) 
            d_date = pickup_date_obj.date()
            
            volume_multiplier = is_busy_day(d_date)
            base_orders = random.randint(5, 15)
            total_today = int(base_orders * volume_multiplier)

            if total_today == 0: continue

            daily_products = []
            daily_weights = []
            for p in products:
                w = get_season_weight(p, d_date)
                if w > 0:
                    daily_products.append(p)
                    daily_weights.append(w)
            
            if not daily_products: continue

            for _ in range(total_today):
                # Klant & Status bepalen
                if i > 0: 
                    is_online = True; customer = random.choice(real_users)
                    remarks = "Online Bestelling"; order_status = 'pending'
                else: 
                    if random.random() < 0.2:
                        is_online = True; customer = random.choice(real_users); remarks = "Online"
                    else:
                        is_online = False; customer = shop_profile; remarks = "Winkelverkoop"
                    
                    order_status = 'cancelled' if random.random() < CANCEL_RATE else 'picked_up'

                order_placed_date = pickup_date_obj.replace(hour=random.randint(7, 18), minute=random.randint(0, 59))
                
                # OPTIMISATIE: Order object maken
                order = Order(
                    user_id=customer.id,
                    status=order_status,
                    pickup_date=d_date,
                    order_date=order_placed_date,  
                    created_at=order_placed_date,
                    total_price=0,
                    remarks=remarks
                )
                
                # Producten kiezen
                num_items = random.choices([1, 2, 3, 4, 5, 6], weights=[30, 30, 20, 10, 5, 5], k=1)[0]
                chosen_products = random.choices(daily_products, weights=daily_weights, k=num_items)
                
                order_total = Decimal(0)
                
                # OPTIMISATIE: Items direct koppelen aan de order in het geheugen
                # (Zonder eerst naar de database te gaan voor een ID)
                for prod in chosen_products:
                    if prod.category == 'pistoles': qty = random.choice([4, 6, 8, 10])
                    elif prod.category == 'koffiekoeken': qty = random.choice([2, 4, 6])
                    else: qty = random.choice([1, 1, 2])

                    item_total = prod.price * Decimal(qty)
                    order_total += item_total
                    
                    # Hier gebruiken we de relatie 'items' in plaats van los toevoegen
                    item = OrderItem(
                        product=prod, # We geven het hele product object mee
                        quantity=qty, 
                        unit_price_at_order=prod.price
                    )
                    order.items.append(item)
                
                order.total_price = order_total
                db.session.add(order) # Zet in de wachtrij
                orders_created += 1
            
            # Alleen elke 30 dagen echt naar de database sturen (Bulk Commit)
            if i % 30 == 0: 
                try:
                    db.session.commit()
                    print("█", end="", flush=True) # Blokje ipv puntje
                except Exception as e:
                    db.session.rollback()
                    print(f"Fout: {e}")

        # Laatste restje opslaan
        db.session.commit()
        print(f"\n\n--- ✅ KLAAR! {orders_created} orders gegenereerd. ---")

if __name__ == "__main__":
    run_history_seeder()