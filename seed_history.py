import random
import time
import math
from datetime import datetime, timedelta, date
from decimal import Decimal
import holidays
from app import create_app
from app.models import db, Product, Order, OrderItem, Profile
import uuid

app = create_app()

# --- INSTELLINGEN ---
DAYS_BACK = 375       
DAYS_FORWARD = 14     
CANCEL_RATE = 0.03    

# --- TRENDS ---
TRENDS = {
    "Zuurdesembrood": "rising",   
    "Eclair": "falling",          
    "Boerenwit": "stable"         
}

def get_trend_multiplier(product_name, day_index, total_days):
    trend_type = TRENDS.get(product_name, "stable")
    progress = day_index / total_days 
    
    if trend_type == "rising": return 0.5 + progress  
    elif trend_type == "falling": return 1.5 - progress
    return 1.0

def is_busy_day(d):
    be_holidays = holidays.BE(years=d.year)
    if d in be_holidays: return 2.0  
    if d.weekday() == 5: return 1.8  # Zaterdag
    if d.weekday() == 6: return 1.6  # Zondag
    if d.weekday() == 2: return 0.7  # Woensdag
    return 1.0

def get_product_weight(product, d):
    # Seizoenscheck
    if product.season_start and product.season_end:
        curr_md = d.strftime('%m-%d')
        in_season = False
        if product.season_start <= product.season_end:
            if product.season_start <= curr_md <= product.season_end: in_season = True
        else:
            if curr_md >= product.season_start or curr_md <= product.season_end: in_season = True
        if not in_season: return 0

    weight = 10
    name = product.name.lower()
    cat = product.category.lower() if product.category else ""
    weekday = d.weekday()

    if 'pistole' in cat:
        if weekday >= 5: weight *= 4 
    elif 'koffiekoeken' in cat:
        if weekday == 6: weight *= 3
    elif 'brood' in cat:
        if weekday >= 5: weight *= 1.5
    
    month, day = d.month, d.day
    if month == 12 and day <= 6 and ('speculaas' in name or 'marsepein' in name):
        weight *= 20 
    if month == 2 and day == 14 and ('hart' in name or 'valentijn' in name):
        weight *= 20

    return weight

def ensure_shop_profile():
    shop_profile = Profile.query.filter(Profile.full_name.ilike("%Winkel%")).first()
    if not shop_profile:
        try:
            # type: ignore
            p = Profile(id=uuid.uuid4(), full_name="Winkelverkoop", is_admin=False)
            db.session.add(p)
            db.session.commit()
            return p
        except: return None
    return shop_profile

def run_history_seeder():
    with app.app_context():
        print(f"--- 📊 GEAVANCEERDE DATA GENERATIE (CORRECTED ONLINE) ---")
        
        shop_profile = ensure_shop_profile()
        if not shop_profile: return
        
        all_products = Product.query.all()
        if not all_products:
            print("❌ Geen producten gevonden.")
            return

        real_users = Profile.query.filter(Profile.id != shop_profile.id).all()
        if not real_users: real_users = [shop_profile]
        
        # Realisme: Vaste klanten
        split_idx = max(1, int(len(real_users) * 0.2))
        regulars = real_users[:split_idx]
        occasionals = real_users[split_idx:]
        
        shop_id = shop_profile.id
        orders_created = 0
        total_days = DAYS_BACK + DAYS_FORWARD

        # Cache
        product_cache = [(p, p.category.lower() if p.category else "") for p in all_products]

        for i in range(-DAYS_BACK, DAYS_FORWARD + 1):
            pickup_date_obj = datetime.now() + timedelta(days=i) 
            d_date = pickup_date_obj.date()
            
            base_volume = random.randint(15, 25)
            day_multiplier = is_busy_day(d_date)
            
            # Seizoensgolf (Piek in winter)
            day_of_year = d_date.timetuple().tm_yday
            seasonal_wave = 1.0 + 0.2 * math.cos(2 * math.pi * (day_of_year - 355) / 365)
            
            total_orders_today = int(base_volume * day_multiplier * seasonal_wave)
            if total_orders_today <= 0: continue

            # Gewichten per dag
            daily_pool = []
            daily_weights = []
            current_day_index = i + DAYS_BACK
            
            for p, cat in product_cache:
                w = get_product_weight(p, d_date)
                trend_mult = get_trend_multiplier(p.name, current_day_index, total_days)
                final_weight = w * trend_mult
                if final_weight > 0:
                    daily_pool.append(p)
                    daily_weights.append(final_weight)

            if not daily_pool: continue

            for _ in range(total_orders_today):
                # ============================================
                # CORRECTIE: ONLINE KANS IN DE TOEKOMST
                # ============================================
                if i > 0:
                    days_out = i
                    # Kans dat iemand NU al besteld heeft voor dag X
                    # Dag 1 (Morgen): ~25% kans (realistisch voor bakker)
                    # Dag 7: ~5% kans
                    prob_already_ordered = max(0.05, 0.25 - (days_out * 0.04))
                    
                    if random.random() < prob_already_ordered:
                        is_online = True
                        # Kies klant
                        if regulars and random.random() < 0.7: uid = random.choice(regulars).id
                        elif occasionals: uid = random.choice(occasionals).id
                        else: uid = shop_id
                        
                        rem = "Online Bestelling"
                        order_date = pickup_date_obj - timedelta(days=random.randint(1, i)) # Vandaag of eerder
                        status = 'pending'
                    else:
                        # Deze klant heeft nog NIET besteld (of komt naar de winkel).
                        # We slaan hem over in de DB -> De AI zal dit gat vullen.
                        continue
                else:
                    # Verleden: Alles staat vast
                    is_online = (random.random() < 0.20) # 20% van historie is online

                    if is_online:
                        if regulars and random.random() < 0.7: uid = random.choice(regulars).id
                        elif occasionals: uid = random.choice(occasionals).id
                        else: uid = shop_id
                        rem = "Online Bestelling"
                        order_date = pickup_date_obj - timedelta(days=random.randint(1, 4))
                        status = 'picked_up'
                    else:
                        uid = shop_id
                        rem = "Winkelverkoop"
                        order_date = pickup_date_obj
                        status = 'picked_up'

                if i <= 0 and random.random() < CANCEL_RATE:
                    status = 'cancelled'

                # Order object (geen flush)
                order = Order(
                    user_id=uid, status=status, pickup_date=d_date,
                    order_date=order_date, created_at=order_date,
                    total_price=0, remarks=rem
                )

                # Items
                if d_date.weekday() == 6:
                    num_lines = random.choices([2, 3, 4, 5], weights=[10, 30, 40, 20])[0]
                else:
                    num_lines = random.choices([1, 2, 3], weights=[50, 40, 10])[0]
                
                chosen_prods = random.choices(daily_pool, weights=daily_weights, k=num_lines)
                chosen_prods = list(set(chosen_prods))
                
                calc_total = Decimal(0)

                for prod in chosen_prods:
                    qty = 1
                    cat = prod.category.lower() if prod.category else ""
                    if 'pistole' in cat: qty = random.choice([4, 6, 8, 10])
                    elif 'koffiekoeken' in cat: qty = random.choice([2, 4])
                    else: qty = random.choice([1, 1, 2])
                    
                    price = prod.price * Decimal(qty)
                    calc_total += price
                    
                    item = OrderItem(product=prod, quantity=qty, unit_price_at_order=prod.price)
                    order.items.append(item)
                
                order.total_price = calc_total
                db.session.add(order)
                orders_created += 1
            
            # Batch Commit
            if i % 10 == 0:
                print(".", end="", flush=True)
                try: db.session.commit()
                except: db.session.rollback()

        db.session.commit()
        print(f"\n\n--- ✅ KLAAR! {orders_created} realistische orders gegenereerd. ---")

if __name__ == "__main__":
    run_history_seeder()