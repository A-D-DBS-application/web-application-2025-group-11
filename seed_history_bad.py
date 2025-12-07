import random
import time
from datetime import datetime, timedelta, date
from decimal import Decimal
import holidays
from app import create_app
from app.models import db, Product, Order, OrderItem, Profile
import uuid

app = create_app()

# --- INSTELLINGEN VOOR HET SCENARIO ---
DAYS_BACK = 370       
DAYS_FORWARD = 7      # Wel toekomst, maar weinig (om de daling te accentueren)
CANCEL_RATE = 0.06    # Iets meer annuleringen

def get_weighted_product_list(products):
    """
    Manipuleert de populariteit om specifieke trends te forceren.
    """
    weighted_list = []
    
    for p in products:
        name = p.name.lower()
        cat = p.category.lower() if p.category else ""
        
        # Basis gewicht (Heel laag = Neiging tot dalen)
        weight = 1 

        # 1. STIJGEND / POPULAIR (Ondanks de crisis)
        # We zorgen dat deze boven de 50 stuks/week blijven
        if 'croissant' in name or 'chocoladekoek' in name:
            weight = 60 

        # 2. STABIEL (Net genoeg verkoop)
        elif 'boerenwit' in name or 'tijger' in name:
            weight = 20
        
        # 3. DALEND (De rest)
        # Taarten en luxe dingen worden wegbezuinigd door klanten
        elif 'taart' in cat or 'seizoen' in cat:
            weight = 2
        else:
            weight = 3 # Pistolets etc.
            
        weighted_list.extend([p] * weight)
        
    return weighted_list

def is_busy_day(d):
    be_holidays = holidays.BE(years=d.year)
    # Zelfs op feestdagen is het nu rustiger in dit scenario
    if d in be_holidays: return 1.5
    if d.weekday() >= 5: return 1.5 # Weekend
    return 0.8 # Doordeweeks

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
        print(f"--- 📉 STARTEN MET 'BAD SCENARIO' (Recessie Simulatie) ---")
        
        shop_profile = ensure_shop_profile()
        if not shop_profile: return
        
        products = Product.query.all()
        if not products:
            print("❌ Geen producten. Run eerst seed_extended.py!")
            return

        real_users = Profile.query.filter(Profile.id != shop_profile.id).all()
        if not real_users: real_users = [shop_profile]

        weighted_products = get_weighted_product_list(products)
        orders_created = 0
        
        for i in range(-DAYS_BACK, DAYS_FORWARD):
            pickup_date_obj = datetime.now() + timedelta(days=i) 
            d_date = pickup_date_obj.date()
            
            # 1. RECESSIE SIMULATIE (De "Bad" Factor)
            # Pas sinds 20 dagen geleden stort de boel in.
            # Hierdoor is het gemiddelde van de afgelopen maand (30 dgn) nog redelijk hoog,
            # maar de voorspelling voor volgende week wordt laag -> DALENDE TREND.
            recession_factor = 1.0
            if i > -20:
                recession_factor = 0.3 # Auw, 70% minder klanten!
            
            # 2. VOLUME BEPALEN
            volume = is_busy_day(d_date)
            
            if i > 0:
                # TOEKOMST: Er zijn wel orders, maar heel weinig (1 à 3 per dag)
                total_today = random.randint(1, 3)
            else:
                # VERLEDEN
                base_orders = random.randint(8, 25) # Normaal goede verkoop
                total_today = int(base_orders * volume * recession_factor)

            if total_today == 0: continue

            for _ in range(total_today):
                # 3. KLANT & DATUM BEPALEN
                if i > 0:
                    # Toekomst is altijd Online
                    is_online = True
                    customer = random.choice(real_users)
                    remarks = "Online (Toekomst)"
                    order_status = 'pending'
                    
                    # Online wordt 1 tot 5 dagen van tevoren besteld
                    days_before = random.randint(1, 5)
                    order_date = pickup_date_obj - timedelta(days=days_before)
                else:
                    # Verleden
                    if random.random() < 0.15:
                        is_online = True
                        customer = random.choice(real_users)
                        remarks = "Online"
                        days_before = random.randint(1, 5)
                        order_date = pickup_date_obj - timedelta(days=days_before)
                    else:
                        is_online = False
                        customer = shop_profile
                        remarks = "Winkelverkoop"
                        order_date = pickup_date_obj # Direct gekocht
                    
                    order_status = 'cancelled' if random.random() < CANCEL_RATE else 'picked_up'

                # Tijdstip finetunen
                order_date = order_date.replace(hour=random.randint(8, 18), minute=random.randint(0,59))

                order = Order(
                    user_id=customer.id,
                    status=order_status,
                    pickup_date=d_date,
                    order_date=order_date,
                    created_at=order_date,
                    total_price=0,
                    remarks=remarks
                )
                
                # 4. PRODUCTEN KIEZEN & KOPPELEN
                # Mensen kopen minder items per keer in recessie
                num_items = random.choices([1, 2, 3], weights=[50, 30, 20], k=1)[0]
                chosen = random.choices(weighted_products, k=num_items)
                
                order_total = Decimal(0)
                
                for prod in chosen:
                    # Aantallen ook lager
                    qty = 1
                    if prod.category == 'pistoles': qty = random.choice([2, 4]) # Geen zakken van 10 meer
                    
                    item_total = prod.price * Decimal(qty)
                    order_total += item_total
                    
                    # FIX: We gebruiken product_id i.p.v. het object om de SAWarning te voorkomen
                    item = OrderItem(
                        product_id=prod.id, 
                        quantity=qty, 
                        unit_price_at_order=prod.price
                    )
                    order.items.append(item)
                
                order.total_price = order_total
                db.session.add(order)
                orders_created += 1
            
            # Bulk commit (elke 30 dagen)
            if i % 30 == 0:
                try:
                    db.session.commit()
                    print("📉", end="", flush=True)
                except: db.session.rollback()

        db.session.commit()
        print(f"\n\n--- ✅ KLAAR! {orders_created} orders (Recessie Scenario) gegenereerd. ---")

if __name__ == "__main__":
    run_history_seeder()