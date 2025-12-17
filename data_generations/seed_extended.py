from app import create_app
from app.models import db, Product, Ingredient, ProductIngredient
from decimal import Decimal

app = create_app()

# ==============================================================================
#  MASTER DATA: HET COMPLETE ASSORTIMENT (27 Producten)
# ==============================================================================
seed_data = [
    # --- 1. BROOD (Basis) ---
    {
        "name": "Boerenwit",
        "description": "Een klassiek wit vloerbrood, lekker luchtig en met een krokante korst.",
        "price": 2.80,
        "category": "brood",
        "allergens": "Gluten",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 500, "gram", "Gluten"), ("Water", 320, "ml", None), ("Gist", 10, "gram", None), ("Zout", 9, "gram", None)]
    },
    {
        "name": "Volkoren Tijger",
        "description": "Stevig volkorenbrood met een krokant tijgerpapje op de korst.",
        "price": 3.20,
        "category": "brood",
        "allergens": "Gluten, Sesam",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Volkorenmeel", 500, "gram", "Gluten"), ("Water", 300, "ml", None), ("Gist", 10, "gram", None), ("Rijstebloem", 20, "gram", None)]
    },
    {
        "name": "Speltbrood",
        "description": "Gezond en licht verteerbaar, gemaakt van 100% speltbloem.",
        "price": 3.50,
        "category": "brood",
        "allergens": "Gluten (Spelt)",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Speltbloem", 500, "gram", "Gluten"), ("Water", 300, "ml", None), ("Honing", 10, "gram", None)]
    },
    {
        "name": "Bruin Brood",
        "description": "Een voedzaam bruin brood voor elke dag.",
        "price": 2.90,
        "category": "brood",
        "allergens": "Gluten",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Volkorenmeel", 250, "gram", "Gluten"), ("Bloem (Tarwe)", 250, "gram", "Gluten"), ("Water", 320, "ml", None), ("Zout", 9, "gram", None)]
    },
    {
        "name": "Meergranenbrood",
        "description": "Rijkelijk gevuld met zonnebloempitten, lijnzaad en sesam.",
        "price": 3.40,
        "category": "brood",
        "allergens": "Gluten, Sesam",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Meergranenmeel", 500, "gram", "Gluten"), ("Zonnebloempitten", 30, "gram", None), ("Lijnzaad", 20, "gram", None), ("Water", 320, "ml", None)]
    },
    {
        "name": "Rozijnenbrood",
        "description": "Zoet brood gevuld met sappige rozijnen. Heerlijk bij het ontbijt.",
        "price": 3.80,
        "category": "brood",
        "allergens": "Gluten, Melk",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 400, "gram", "Gluten"), ("Rozijnen", 150, "gram", None), ("Melk", 200, "ml", "Melk"), ("Suiker", 30, "gram", None)]
    },

    # --- 2. PISTOLETS (Basis) ---
    {
        "name": "Keizerbroodje",
        "description": "Het bekende witte pistoletje met de typische stervorm bovenop.",
        "price": 0.70,
        "category": "pistolets",
        "allergens": "Gluten",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 60, "gram", "Gluten"), ("Water", 35, "ml", None), ("Gist", 2, "gram", None)]
    },
    {
        "name": "Tijgerpistolet",
        "description": "Witte pistolet met een extra krokant en gevlekt tijgerkorstje.",
        "price": 0.80,
        "category": "pistolets",
        "allergens": "Gluten",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 60, "gram", "Gluten"), ("Rijstebloem", 5, "gram", None)]
    },
    {
        "name": "Witte Pistolet",
        "description": "Klassiek zacht wit broodje.",
        "price": 0.65,
        "category": "pistolets",
        "allergens": "Gluten",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 60, "gram", "Gluten"), ("Water", 35, "ml", None), ("Gist", 2, "gram", None)]
    },
    {
        "name": "Bruine Pistolet",
        "description": "Gezond bruin pistoletje.",
        "price": 0.70,
        "category": "pistolets",
        "allergens": "Gluten",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Volkorenmeel", 60, "gram", "Gluten"), ("Water", 35, "ml", None), ("Gist", 2, "gram", None)]
    },
    {
        "name": "Meergranen Pistolet",
        "description": "Pistolet met granen en zaden topping.",
        "price": 0.85,
        "category": "pistolets",
        "allergens": "Gluten, Sesam",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Meergranenmeel", 60, "gram", "Gluten"), ("Zonnebloempitten", 5, "gram", None)]
    },

    # --- 3. KOFFIEKOEKEN (Basis) ---
    {
        "name": "Chocoladekoek",
        "description": "Luchtig bladerdeeg gevuld met twee staafjes pure chocolade.",
        "price": 1.60,
        "category": "koffiekoeken",
        "allergens": "Gluten, Melk, Ei, Soja",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 60, "gram", "Gluten"), ("Boter", 30, "gram", "Melk"), ("Chocolade", 15, "gram", "Soja, Melk")]
    },
    {
        "name": "Croissant",
        "description": "Klassieke franse croissant met echte hoeveboter.",
        "price": 1.50,
        "category": "koffiekoeken",
        "allergens": "Gluten, Melk, Ei",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 60, "gram", "Gluten"), ("Boter", 40, "gram", "Melk")]
    },
    {
        "name": "Boule de Berlin",
        "description": "Gefrituurde zachte bol gevuld met banketbakkersroom en bestrooid met poedersuiker.",
        "price": 2.20,
        "category": "koffiekoeken",
        "allergens": "Gluten, Melk, Ei",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 60, "gram", "Gluten"), ("Melk", 30, "ml", "Melk"), ("Vanillepudding", 40, "gram", "Melk, Ei")]
    },
    {
        "name": "Eclair",
        "description": "Soezendeeg gevuld met banketbakkersroom en afgewerkt met een laagje chocolade.",
        "price": 2.40,
        "category": "koffiekoeken",
        "allergens": "Gluten, Melk, Ei, Soja",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 40, "gram", "Gluten"), ("Vanillepudding", 50, "gram", "Melk, Ei"), ("Chocolade", 15, "gram", "Soja, Melk")]
    },
    {
        "name": "Lange Suisse",
        "description": "Langwerpige koffiekoek met rozijnen en een laagje suikerglazuur.",
        "price": 1.80,
        "category": "koffiekoeken",
        "allergens": "Gluten, Melk, Ei",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 60, "gram", "Gluten"), ("Boter", 30, "gram", "Melk"), ("Rozijnen", 15, "gram", None), ("Suiker", 10, "gram", None)]
    },
    {
        "name": "Appelflap",
        "description": "Driehoekig bladerdeeg gevuld met verse appelcompote.",
        "price": 1.90,
        "category": "koffiekoeken",
        "allergens": "Gluten, Melk",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 60, "gram", "Gluten"), ("Boter", 40, "gram", "Melk"), ("Appel", 50, "gram", None), ("Kaneel", 1, "gram", None)]
    },
    {
        "name": "Frangipane",
        "description": "Tartelette gevuld met amandelcrème en afgewerkt met glazuur.",
        "price": 2.50,
        "category": "koffiekoeken",
        "allergens": "Gluten, Melk, Ei, Noten",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 50, "gram", "Gluten"), ("Amandelmeel", 40, "gram", "Noten"), ("Suiker", 40, "gram", None), ("Abrikozenjam", 10, "gram", None)]
    },

    # --- 4. TAARTEN (Basis) ---
    {
        "name": "Aardbeientaart (4p)",
        "description": "Krokante zanddeegbodem met banketbakkersroom en verse aardbeien.",
        "price": 14.50,
        "category": "taart",
        "allergens": "Gluten, Melk, Ei",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 150, "gram", "Gluten"), ("Aardbeien", 300, "gram", None), ("Vanillepudding", 200, "gram", "Melk, Ei")]
    },
    {
        "name": "Slagroomtaart",
        "description": "Luchtige biscuit gevuld met slagroom en vers fruit.",
        "price": 16.00,
        "category": "taart",
        "allergens": "Gluten, Melk, Ei",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 150, "gram", "Gluten"), ("Slagroom", 400, "ml", "Melk"), ("Suiker", 50, "gram", None)]
    },
    {
        "name": "Rijsttaartje",
        "description": "Eenpersoons taartje met romige rijstpapvulling.",
        "price": 2.10,
        "category": "taart",
        "allergens": "Gluten, Melk, Ei",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 50, "gram", "Gluten"), ("Melk", 100, "ml", "Melk"), ("Rijst", 30, "gram", None), ("Suiker", 20, "gram", None)]
    },
    {
        "name": "Mattaart",
        "description": "Geraardsbergse specialiteit met wrongel en amandelen.",
        "price": 2.30,
        "category": "taart",
        "allergens": "Gluten, Melk, Ei, Noten",
        "season_start": None, "season_end": None,
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 50, "gram", "Gluten"), ("Melk", 50, "ml", "Melk"), ("Amandelmeel", 10, "gram", "Noten"), ("Eieren", 0.5, "stuks", "Ei")]
    },

    # --- 5. SEIZOEN: SINTERKLAAS (1 Nov - 6 Dec) ---
    {
        "name": "Grote Speculaaspop",
        "description": "Ambachtelijke speculaaspop van 25cm. Een klassieker voor in de schoen!",
        "price": 4.50,
        "category": "seizoensgebak", 
        "allergens": "Gluten, Melk, Ei",
        "season_start": "11-01", "season_end": "12-06",
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 150, "gram", "Gluten"), ("Speculaaskruiden", 5, "gram", None), ("Bruine Suiker", 80, "gram", None)]
    },
    {
        "name": "Marsepein Figuur",
        "description": "Handgemaakt varkentje van de fijnste Lübecker marsepein.",
        "price": 3.95,
        "category": "seizoensgebak",
        "allergens": "Noten (Amandel)",
        "season_start": "11-01", "season_end": "12-06",
        "image_url": "logo.png",
        "recipe": [("Amandelmeel", 50, "gram", "Noten"), ("Poedersuiker", 50, "gram", None)]
    },

    # --- 6. SEIZOEN: KERST (10 Dec - 31 Dec) ---
    {
        "name": "Kerststronk Mokka",
        "description": "Biscuitrol gevuld met rijke mokka-crème au beurre. Voor 4-6 personen.",
        "price": 18.50,
        "category": "taart",
        "allergens": "Gluten, Melk, Ei",
        "season_start": "12-10", "season_end": "12-31",
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 200, "gram", "Gluten"), ("Boter", 300, "gram", "Melk"), ("Koffie extract", 20, "ml", None)]
    },
    {
        "name": "Worstenbroodje (Kerst)",
        "description": "Speciaal voor kerstborrels en Verloren Maandag.",
        "price": 2.80,
        "category": "koffiekoeken",
        "allergens": "Gluten, Melk, Ei, Vlees",
        "season_start": "12-20", "season_end": "01-15",
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 80, "gram", "Gluten"), ("Gehakt (Varken/Rund)", 80, "gram", None)]
    },

    # --- 7. SEIZOEN: VALENTIJN (1 Feb - 15 Feb) ---
    {
        "name": "Hartjestaart",
        "description": "Rode fluwelen taart (Red Velvet) in de vorm van een hart.",
        "price": 12.00,
        "category": "taart",
        "allergens": "Gluten, Melk, Ei",
        "season_start": "02-01", "season_end": "02-15",
        "image_url": "logo.png",
        "recipe": [("Bloem (Tarwe)", 150, "gram", "Gluten"), ("Roomkaas", 200, "gram", "Melk"), ("Rode kleurstof", 2, "ml", None)]
    }
]

def run_seeder():
    with app.app_context():
        print("--- 🌱 STARTEN MET PRODUCTEN & RECEPTEN VULLEN ---")
        
        for item in seed_data:
            # 1. Zoek product of maak aan
            product = Product.query.filter(Product.name.ilike(item["name"])).first()
            
            if not product:
                product = Product(
                    name=item["name"],
                    description=item["description"],
                    price=Decimal(item["price"]),
                    category=item["category"],
                    allergens=item["allergens"],
                    season_start=item["season_start"],
                    season_end=item["season_end"],
                    image_url=item["image_url"],
                    is_available=True
                )
                db.session.add(product)
                db.session.flush()
                print(f"✅ NIEUW: {product.name}")
            else:
                # Update bestaande data als hij al bestaat (handig voor prijswijzigingen)
                product.description = item["description"]
                product.price = Decimal(item["price"])
                product.season_start = item["season_start"]
                product.season_end = item["season_end"]
                db.session.add(product)
                print(f"ℹ️ BESTAAT AL (UPDATED): {product.name}")

            # 2. Recept Koppelen
            # Eerst oude regels verwijderen om dubbels te voorkomen
            ProductIngredient.query.filter_by(product_id=product.id).delete()
            
            for ing_name, qty, unit, allergen in item["recipe"]:
                # Ingrediënt zoeken of maken
                ingredient = Ingredient.query.filter(Ingredient.name.ilike(ing_name)).first()
                
                if not ingredient:
                    ingredient = Ingredient(
                        name=ing_name,
                        stock_quantity=10000, # Startvoorraad 10kg
                        unit=unit,
                        threshold=1000,
                        allergen_info=allergen
                    )
                    db.session.add(ingredient)
                    db.session.flush()
                    print(f"   -> Nieuw ingrediënt: {ing_name}")
                
                # Koppeling maken
                link = ProductIngredient(
                    product_id=product.id,
                    ingredient_id=ingredient.id,
                    quantity_needed=Decimal(qty)
                )
                db.session.add(link)

        db.session.commit()
        print("\n--- 🚀 KLAAR! JE BAKKERIJ IS GEVULD MET 27 PRODUCTEN ---")

if __name__ == "__main__":
    run_seeder()