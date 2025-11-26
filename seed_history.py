import random
from datetime import datetime, timedelta
from decimal import Decimal
from app import create_app
from app.models import db, Product, Order, OrderItem, Profile
import uuid

app = create_app()

# --- INSTELLINGEN ---
DAYS_BACK = 370  # We gaan ruim een jaar terug
# Feestdagen (Dag, Maand) waar het extra druk is
BUSY_HOLIDAYS = [
    (25, 12), # Kerst
    (1, 1),   # Nieuwjaar
    (31, 3),  # Pasen (ongeveer)
    (12, 5),  # Moederdag (ongeveer)
]

def ensure_shop_profile():
    """Maakt een speciaal profiel aan voor fysieke winkelverkoop."""
    # We zoeken op naam om dubbels te voorkomen
    shop_profile = Profile.query.filter_by(full_name="Winkelverkoop (Kassa)").first()
    
    if not shop_profile:
        # Omdat we geen user in Supabase Auth aanmaken, verzinnen we een random ID
        fake_id = uuid.uuid4()
        shop_profile = Profile(
            id=fake_id,
            full_name="Winkelverkoop (Kassa)",
            phone_number="0000000000"
        )
        db.session.add(shop_profile)
        db.session.commit()
        print("   -> Speciaal profiel 'Winkelverkoop (Kassa)' aangemaakt.")
    
    return shop_profile

def ensure_seasonal_products():
    """Zorgt dat marsepein en speculaas bestaan in de database."""
    seasonal = [
        {"name": "Marsepein Figuur", "price": 4.50, "category": "koffiekoeken"},
        {"name": "Grote Speculaas", "price": 3.00, "category": "koffiekoeken"},
        {"name": "Kerststronk", "price": 18.00, "category": "koffiekoeken"}
    ]
    
    for item in seasonal:
        # Check of het product al bestaat (hoofdletterongevoelig)
        exists = Product.query.filter(Product.name.ilike(item['name'])).first()
        if not exists:
            p = Product(
                name=item['name'], 
                price=Decimal(item['price']), 
                category=item['category'], 
                description="Seizoensspecialiteit",
                image_url="logo.png", 
                is_available=True
            )
            db.session.add(p)
            print(f"   -> Seizoensproduct aangemaakt: {item['name']}")
    
    db.session.commit()

def run_history_seeder():
    with app.app_context():
        print("--- 🕒 STARTEN MET HISTORIE GENEREREN ---")
        
        # 1. Voorbereiden
        ensure_seasonal_products()
        shop_profile = ensure_shop_profile()
        
        products = Product.query.all()
        # Haal echte gebruikers op (alles behalve de kassa)
        real_users = Profile.query.filter(Profile.full_name != "Winkelverkoop (Kassa)").all()
        
        if not products:
            print("❌ Geen producten gevonden! Voeg eerst producten toe.")
            return

        # Specifieke producten zoeken voor de logica
        marsepein = Product.query.filter(Product.name.ilike("Marsepein Figuur")).first()
        kerststronk = Product.query.filter(Product.name.ilike("Kerststronk")).first()
        speculaas = Product.query.filter(Product.name.ilike("Grote Speculaas")).first()

        orders_created = 0
        
        # 2. Loop door de dagen (van 370 dagen geleden tot gisteren)
        for i in range(DAYS_BACK, 0, -1):
            current_date = datetime.now() - timedelta(days=i)
            month = current_date.month
            day = current_date.day
            weekday = current_date.weekday() # 0=Maandag, 6=Zondag
            
            # --- A. BEPAAL DRUKTE ---
            # Weekend is drukker
            if weekday >= 5: 
                online_orders_count = random.randint(2, 6)
                walk_in_orders_count = random.randint(15, 30) # Zaterdag/Zondag is het druk in de winkel!
            elif weekday == 2: # Woensdagmiddag
                online_orders_count = random.randint(1, 3)
                walk_in_orders_count = random.randint(8, 15)
            else:
                online_orders_count = random.randint(0, 2)
                walk_in_orders_count = random.randint(5, 10)

            # Feestdagen boost (x3)
            is_holiday = False
            for h_day, h_month in BUSY_HOLIDAYS:
                if day == h_day and month == h_month:
                    online_orders_count *= 2
                    walk_in_orders_count *= 3
                    is_holiday = True

            # --- B. SEIZOENS LOGICA ---
            # Sinterklaas: 15 nov - 6 dec
            is_sinterklaas = (month == 11 and day >= 15) or (month == 12 and day <= 6)
            if is_sinterklaas:
                walk_in_orders_count += random.randint(5, 10) # Extra mensen voor snoepgoed

            # Kerst: 20 dec - 25 dec
            is_kerst = (month == 12 and day >= 20 and day <= 25)

            # Totaal aantal orders vandaag
            total_today = online_orders_count + walk_in_orders_count

            # --- C. MAAK DE ORDERS ---
            for k in range(total_today):
                # Wie is de klant?
                # De eerste paar zijn "Echte" online bestellingen, de rest is "Winkelverkoop"
                if k < online_orders_count and real_users:
                    customer = random.choice(real_users)
                    remarks = "Online bestelling"
                else:
                    customer = shop_profile
                    remarks = "Winkelverkoop"

                # Order aanmaken (Direct op 'picked_up' zetten want het is verleden tijd)
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
                
                # Wat kopen ze?
                num_items = random.randint(1, 5)
                if is_holiday: num_items += 3 # Grote feesten = veel eten
                
                order_total = Decimal(0)
                
                # 1. Seizoensproducten toevoegen?
                if is_sinterklaas and marsepein and random.random() > 0.6:
                    # 40% kans dat iemand marsepein koopt
                    qty = random.randint(1, 3)
                    db.session.add(OrderItem(order_id=order.id, product_id=marsepein.id, quantity=qty, unit_price_at_order=marsepein.price))
                    order_total += marsepein.price * Decimal(qty)

                if is_kerst and kerststronk and random.random() > 0.8:
                    # 20% kans op een stronk (duur!)
                    db.session.add(OrderItem(order_id=order.id, product_id=kerststronk.id, quantity=1, unit_price_at_order=kerststronk.price))
                    order_total += kerststronk.price

                # 2. Normale producten toevoegen
                for _ in range(num_items):
                    prod = random.choice(products)
                    
                    # Voorkom dat we seizoensdingen in de zomer verkopen
                    if prod.name in ["Marsepein Figuur", "Kerststronk", "Grote Speculaas"]:
                        continue
                    
                    qty = random.randint(1, 3)
                    
                    # In het weekend kopen mensen véél pistolets
                    if prod.category == 'pistoles' and weekday >= 5:
                        qty = random.randint(4, 8)

                    item_total = prod.price * Decimal(qty)
                    order_total += item_total
                    
                    order_item = OrderItem(
                        order_id=order.id,
                        product_id=prod.id,
                        quantity=qty,
                        unit_price_at_order=prod.price
                    )
                    db.session.add(order_item)
                
                # Update de totaalprijs
                order.total_price = order_total
                db.session.add(order)
                orders_created += 1
        
        db.session.commit()
        print(f"\n--- ✅ KLAAR! {orders_created} orders gegenereerd over {DAYS_BACK} dagen. ---")

if __name__ == "__main__":
    run_history_seeder()