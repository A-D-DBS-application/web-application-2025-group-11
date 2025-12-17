from app import create_app
from app.models import db, Product, Ingredient, ProductIngredient
from decimal import Decimal

app = create_app()

# ==========================================
# DE DATA LIJST (Vul dit aan waar nodig)
# ==========================================
# Formaat: "ProductNaam": [ ("Ingrediënt", Aantal, "Eenheid", "AllergeenInfo of None") ]

recipes_data = {
    "Volkoren Tijgerbrood": [
        ("Volkorenmeel", 500, "gram", "Gluten"),
        ("Water", 300, "ml", None),
        ("Gist", 10, "gram", None),
        ("Zout", 8, "gram", None),
        ("Rijstebloem", 20, "gram", None) # Voor het tijgerpapje
    ],
    "Chocoladekoek": [
        ("Bloem (Tarwe)", 60, "gram", "Gluten"),
        ("Boter", 30, "gram", "Melk"),
        ("Suiker", 10, "gram", None),
        ("Gist", 3, "gram", None),
        ("Chocolade", 15, "gram", "Soja, Melk"),
        ("Melk", 20, "ml", "Melk")
    ],
    "Boerenwit": [
        ("Bloem (Tarwe)", 500, "gram", "Gluten"),
        ("Water", 320, "ml", None),
        ("Gist", 10, "gram", None),
        ("Zout", 9, "gram", None),
        ("Boter", 10, "gram", "Melk")
    ],
    "Speltbrood": [
        ("Speltbloem", 500, "gram", "Gluten"),
        ("Water", 300, "ml", None),
        ("Gist", 10, "gram", None),
        ("Zout", 9, "gram", None),
        ("Honing", 10, "gram", None)
    ],
    "Rozijnenbrood": [
        ("Bloem (Tarwe)", 400, "gram", "Gluten"),
        ("Rozijnen", 200, "gram", None),
        ("Melk", 200, "ml", "Melk"),
        ("Suiker", 30, "gram", None),
        ("Boter", 30, "gram", "Melk"),
        ("Gist", 15, "gram", None),
        ("Kaneel", 2, "gram", None)
    ],
    "Keizerbroodje": [
        ("Bloem (Tarwe)", 60, "gram", "Gluten"),
        ("Water", 35, "ml", None),
        ("Gist", 2, "gram", None),
        ("Zout", 1, "gram", None)
    ],
    "Tijgerpistolet": [
        ("Bloem (Tarwe)", 60, "gram", "Gluten"),
        ("Water", 35, "ml", None),
        ("Gist", 2, "gram", None),
        ("Zout", 1, "gram", None),
        ("Rijstebloem", 5, "gram", None)
    ],
    "Achtje": [
        ("Bloem (Tarwe)", 60, "gram", "Gluten"),
        ("Boter", 30, "gram", "Melk"),
        ("Suiker", 15, "gram", None),
        ("Melk", 20, "ml", "Melk"),
        ("Vanillepudding", 30, "gram", "Melk, Eieren")
    ],
    "Appelflap": [
        ("Bloem (Tarwe)", 50, "gram", "Gluten"),
        ("Boter", 40, "gram", "Melk"),
        ("Appel", 60, "gram", None),
        ("Suiker", 10, "gram", None),
        ("Kaneel", 1, "gram", None)
    ],
    "Lange Suisse": [
        ("Bloem (Tarwe)", 60, "gram", "Gluten"),
        ("Boter", 25, "gram", "Melk"),
        ("Suiker", 15, "gram", None),
        ("Melk", 20, "ml", "Melk"),
        ("Rozijnen", 15, "gram", None),
        ("Vanillepudding", 20, "gram", "Melk, Eieren")
    ],
    # Voeg hier eventueel de eerste 4 producten toe als je die nog niet had gedaan
    "Zuurdesembrood": [
        ("Bloem (Tarwe)", 500, "gram", "Gluten"),
        ("Water", 350, "ml", None),
        ("Zout", 10, "gram", None)
    ],
    "Stokbrood": [
        ("Bloem (Tarwe)", 280, "gram", "Gluten"),
        ("Water", 180, "ml", None),
        ("Gist", 5, "gram", None),
        ("Zout", 5, "gram", None)
    ],
    "Chocoladebol": [
        ("Bloem (Tarwe)", 50, "gram", "Gluten"),
        ("Boter", 20, "gram", "Melk"),
        ("Room", 40, "ml", "Melk"),
        ("Chocolade", 30, "gram", "Soja, Melk"),
        ("Suiker", 10, "gram", None)
    ],
    "Croissant": [
        ("Bloem (Tarwe)", 60, "gram", "Gluten"),
        ("Boter", 40, "gram", "Melk"),
        ("Suiker", 8, "gram", None),
        ("Gist", 2, "gram", None),
        ("Melk", 15, "ml", "Melk")
    ]
}

def run_seeder():
    with app.app_context():
        print("--- STARTEN MET RECEPTEN INVULLEN ---")
        
        for prod_name, ingredients_list in recipes_data.items():
            # 1. Zoek het product
            # ilike zorgt dat 'Stokbrood' en 'stokbrood' allebei gevonden worden
            product = Product.query.filter(Product.name.ilike(prod_name)).first()
            
            if not product:
                print(f"❌ Product '{prod_name}' niet gevonden in DB. Sla over.")
                continue
                
            print(f"✅ Bezig met: {product.name}...")
            
            # Eerst oude receptregels verwijderen om dubbels te voorkomen?
            # Zet dit aan als je een schone lei wilt voor dit product:
            # ProductIngredient.query.filter_by(product_id=product.id).delete()
            
            for ing_name, qty, unit, allergen in ingredients_list:
                # 2. Zoek of maak ingrediënt
                ingredient = Ingredient.query.filter(Ingredient.name.ilike(ing_name)).first()
                
                if not ingredient:
                    ingredient = Ingredient(
                        name=ing_name,
                        stock_quantity=0,
                        unit=unit,
                        threshold=1000,
                        allergen_info=allergen # Hier voegen we de allergie direct toe!
                    )
                    db.session.add(ingredient)
                    db.session.flush() # Krijg ID
                    print(f"   -> Nieuw ingrediënt aangemaakt: {ing_name} (Allergenen: {allergen})")
                else:
                    # Update allergeen info als die er nog niet stond
                    if allergen and not ingredient.allergen_info:
                        ingredient.allergen_info = allergen
                        db.session.add(ingredient)
                        print(f"   -> Allergenen geüpdatet voor {ing_name}")

                # 3. Check of koppeling al bestaat
                existing_link = ProductIngredient.query.filter_by(
                    product_id=product.id, 
                    ingredient_id=ingredient.id
                ).first()

                if not existing_link:
                    new_link = ProductIngredient(
                        product_id=product.id,
                        ingredient_id=ingredient.id,
                        quantity_needed=Decimal(qty)
                    )
                    db.session.add(new_link)
                    print(f"   -> Gekoppeld: {qty} {unit} {ing_name}")
                else:
                    # Update hoeveelheid als het al bestaat
                    existing_link.quantity_needed = Decimal(qty)
                    print(f"   -> Recept geüpdatet: {qty} {unit} {ing_name}")

        db.session.commit()
        print("\n--- KLAAR! ALLE RECEPTEN ZIJN BIJGEWERKT ---")

if __name__ == "__main__":
    run_seeder()