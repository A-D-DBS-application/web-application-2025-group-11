from app import create_app
from app.models import db, Order, OrderItem

app = create_app()

def clear_data():
    with app.app_context():
        print("--- 🗑️  BESTELLINGEN VERWIJDEREN ---")
        try:
            db.session.query(OrderItem).delete()
            db.session.query(Order).delete()
            db.session.commit()
            print("--- ✅ KLAAR! DATABASE IS SCHOON ---")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Fout: {e}")

if __name__ == "__main__":
    clear_data()