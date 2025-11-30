from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

db = SQLAlchemy()

# ==============================================================================
#  PRODUCT MODEL
# ==============================================================================

class Product(db.Model):
    __tablename__ = 'products'

    # --- Kolommen ---
    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    image_url = db.Column(db.Text)
    category = db.Column(db.Text)
    allergens = db.Column(db.Text) # Handmatige allergenen (fallback)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    
    # --- Relaties ---
    ingredients = db.relationship('ProductIngredient', backref='product', lazy=True, cascade='all, delete-orphan')
    order_items = db.relationship('OrderItem', backref='product', lazy=True)

    # --- SLIMME ALLERGENEN FUNCTIE ---
    @property
    def calculated_allergens(self):
        found_allergens = set()
        
        # 1. Check Recept (Ingrediënten koppeling)
        for rule in self.ingredients:
            if rule.ingredient.allergen_info:
                parts = rule.ingredient.allergen_info.split(',')
                for part in parts:
                    found_allergens.add(part.strip())
        
        # 2. Check Handmatig veld (Excel/Admin input)
        if self.allergens:
            parts = self.allergens.split(',')
            for part in parts:
                found_allergens.add(part.strip())

        # 3. Geef resultaat
        if not found_allergens:
            return None
            
        return ", ".join(sorted(found_allergens))

    def __repr__(self):
        return f'<Product {self.name}>'


# ==============================================================================
#  PROFILE (USER) MODEL
# ==============================================================================

class Profile(db.Model):
    __tablename__ = 'profiles'

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    full_name = db.Column(db.Text)
    phone_number = db.Column(db.Text)
    is_admin = db.Column(db.Boolean, default=False)
    
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())
    orders = db.relationship('Order', backref='profile', lazy=True)

    def __repr__(self):
        return f'<Profile {self.full_name}>'

# ==============================================================================
#  ORDER MODEL
# ==============================================================================
    
class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.BigInteger, primary_key=True)
    status = db.Column(db.Text, nullable=False, default='pending')
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    pickup_date = db.Column(db.Date)
    remarks = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    order_date = db.Column(db.DateTime(timezone=True), server_default=func.now())

    user_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('profiles.id'), nullable=False)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Order {self.id}>'


# ==============================================================================
#  ORDER ITEM MODEL
# ==============================================================================

class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.BigInteger, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price_at_order = db.Column(db.Numeric(10, 2), nullable=False)

    order_id = db.Column(db.BigInteger, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.BigInteger, db.ForeignKey('products.id'), nullable=False)

    def __repr__(self):
        return f'<OrderItem {self.id} (Order {self.order_id})>'
    
# =========================================
# ERP SYSTEEM: VOORRAAD & RECEPTEN
# =========================================

class Ingredient(db.Model):
    __tablename__ = 'ingredients'

    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    stock_quantity = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    unit = db.Column(db.Text, nullable=False)
    threshold = db.Column(db.Numeric(10, 2), default=1000)
    allergen_info = db.Column(db.Text) # Opslag voor 'Gluten', 'Melk', etc.

    def __repr__(self):
        return f'<Ingredient {self.name}>'

class ProductIngredient(db.Model):
    __tablename__ = 'product_ingredients'

    id = db.Column(db.BigInteger, primary_key=True)
    product_id = db.Column(db.BigInteger, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    ingredient_id = db.Column(db.BigInteger, db.ForeignKey('ingredients.id'), nullable=False)
    quantity_needed = db.Column(db.Numeric(10, 2), nullable=False)

    ingredient = db.relationship('Ingredient')

    def __repr__(self):
        return f'<ReceptRegel: {self.quantity_needed} van {self.ingredient_id}>'
    
# =========================================
# SETTINGS
# =========================================

class AppSettings(db.Model):
    __tablename__ = 'app_settings'

    id = db.Column(db.BigInteger, primary_key=True)
    welcome_title = db.Column(db.Text)
    welcome_text = db.Column(db.Text)
    intro_text = db.Column(db.Text)
    deadline_hour = db.Column(db.Integer, default=17)
    
    # Contactgegevens
    phone_number = db.Column(db.Text)
    email_address = db.Column(db.Text)
    address_text = db.Column(db.Text)
    opening_hours = db.Column(db.Text) #mag eig weg, maar als fallback voor nu laten staan
    weekly_schedule_json = db.Column(db.Text)