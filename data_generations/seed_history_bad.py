import random
import time
import json
from datetime import datetime, timedelta, date
from decimal import Decimal
import holidays
from app import create_app
from app.models import db, Product, Order, OrderItem, Profile, AppSettings
import uuid

app = create_app()

# --- INSTELLINGEN ---
DAYS_BACK = 370       
DAYS_FORWARD = 14     
CANCEL_RATE = 0.05    

def get_recession_multiplier(day_index, total_days):
    """
    Simuleert een milde recessie.
    Start op 1.1 (Goed) -> Zakt langzaam naar 0.7 (Minder).
    """
    progress = day_index / total_days 
    start_factor = 1.1
    end_factor = 0.7 
    current = start_factor - (progress * (start_factor - end_factor))
    return max(0.5, current)

def get_schedule_constraints():
    closed_weekdays = []
    closed_dates = []
    try:
        settings = AppSettings.query.first()
        if settings:
            if settings.weekly_schedule_json:
                schedule = json.loads(settings.weekly_schedule_json)
                for day_idx, data in schedule.items():
                    if data.get('closed'): closed_weekdays.append(int(day_idx))
            if settings.closed_dates_json:
                closed_dates = json.loads(settings.closed_dates_json)
    except: pass
    return closed_weekdays, closed_dates

def is_shop_open(d, closed_weekdays, closed_dates):
    if d.weekday() in closed_weekdays: return False
    if d.strftime('%Y-%m-%d') in closed_dates: return False
    return True

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
    cat = product.category.lower() if product.category else ""
    # In een dipje blijft brood stabiel, luxe iets minder
    if 'brood' in cat: weight = 12
    elif 'taart' in cat: weight = 5 
    
    if d.weekday() >= 5: weight *= 1.3
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

def run_bad_seeder():
    with app.app_context():
        print(f"--- 📉 STARTEN MET 'MILD RECESSION' (REALISTIC ONLINE) ---")
        
        shop_profile = ensure_shop_profile()
        if not shop_profile: return
        
        all_products = Product.query.all()
        real_users = Profile.query.filter(Profile.id != shop_profile.id).all()
        if not real_users: real_users = [shop_profile]
        
        user_ids = [u.id for u in real_users]
        shop_id = shop_profile.id
        closed_weekdays, closed_dates = get_schedule_constraints()

        orders_created = 0
        total_days = DAYS_BACK + DAYS_FORWARD

        for i in range(-DAYS_BACK, DAYS_FORWARD + 1):
            pickup_date_obj = datetime.now() + timedelta(days=i) 
            d_date = pickup_date_obj.date()
            shop_is_open = is_shop_open(d_date, closed_weekdays, closed_dates)

            # Volume bepalen (70% Scenario)
            cur_idx = i + DAYS_BACK
            factor = get_recession_multiplier(cur_idx, total_days) 
            
            base_volume = random.randint(12, 20) 
            total_demand = int(base_volume * factor)

            if total_demand <= 0: continue

            daily_pool = []
            daily_weights = []
            for p in all_products:
                w = get_product_weight(p, d_date)
                if w > 0:
                    daily_pool.append(p)
                    daily_weights.append(w)
            
            if not daily_pool: continue

            for _ in range(total_demand):
                # ============================================
                # AANGEPASTE ONLINE KANS (REALISTISCHER)
                # ============================================
                if i > 0:
                    days_out = i
                    # Startkans verlaagd van 0.40 naar 0.22 (22%)
                    # Dit zorgt ervoor dat Online orders een minderheid blijven
                    prob_already_ordered = max(0.02, 0.22 - (days_out * 0.04))
                    
                    if random.random() < prob_already_ordered:
                        is_online = True
                        uid = random.choice(user_ids)
                        rem = "Online Bestelling"
                        status = 'pending'
                        order_date = pickup_date_obj - timedelta(days=random.randint(1, i))
                    else:
                        # Klant bestaat nog niet (komt in winkel of bestelt later)
                        continue 
                else:
                    # Verleden
                    if not shop_is_open:
                        is_online = True
                    else:
                        # Historisch online aandeel ook iets lager gezet (12%)
                        is_online = (random.random() < 0.12)

                    if is_online:
                        uid = random.choice(user_ids)
                        rem = "Online Bestelling"
                        status = 'picked_up'
                    else:
                        uid = shop_id
                        rem = "Winkelverkoop"
                        status = 'picked_up'
                    
                    order_date = pickup_date_obj

                if i <= 0 and random.random() < CANCEL_RATE:
                    status = 'cancelled'

                order = Order(
                    user_id=uid, status=status, pickup_date=d_date,
                    order_date=order_date, created_at=order_date,
                    remarks=rem, total_price=0
                )
                
                # Relatie gebruiken voor items
                num_lines = random.choices([1, 2, 3], weights=[65, 25, 10])[0]
                chosen = random.choices(daily_pool, weights=daily_weights, k=num_lines)
                chosen = list(set(chosen))
                
                calc_total = Decimal(0)
                for prod in chosen:
                    qty = 1
                    if 'pistolet' in prod.category: qty = random.choice([2, 4, 6])
                    
                    calc_total += prod.price * Decimal(qty)
                    order.items.append(OrderItem(product=prod, quantity=qty, unit_price_at_order=prod.price))
                
                order.total_price = calc_total
                db.session.add(order)
                orders_created += 1
            
            # Batch opslaan per 10 dagen
            if i % 10 == 0:
                try:
                    db.session.commit()
                    print("📉", end="", flush=True)
                except: db.session.rollback()

        db.session.commit()
        print(f"\n\n--- ✅ 70% SCENARIO (Minder Online) GESIMULEERD: {orders_created} orders. ---")

if __name__ == "__main__":
    run_bad_seeder()