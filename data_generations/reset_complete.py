from app import create_app
from app.models import db, Product, Ingredient, ProductIngredient, Order, OrderItem

app = create_app()

def reset_all():
    with app.app_context():
        print("--- 🗑️  ALLES VERWIJDEREN ---")
        try:
            # Volgorde is belangrijk ivm relaties!
            # 1. Verwijder orders en items
            db.session.query(OrderItem).delete()
            db.session.query(Order).delete()
            
            # 2. Verwijder recepten
            db.session.query(ProductIngredient).delete()
            
            # 3. Verwijder producten en ingrediënten
            db.session.query(Product).delete()
            db.session.query(Ingredient).delete()
            
            db.session.commit()
            print("--- ✅ KLAAR! DATABASE IS LEEG ---")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Fout: {e}")

if __name__ == "__main__":
    reset_all()