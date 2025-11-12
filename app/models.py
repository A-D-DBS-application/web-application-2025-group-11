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
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # --- Relaties ---
    order_items = db.relationship('OrderItem', backref='product', lazy=True)

    # --- Methoden ---
    def __repr__(self):
        return f'<Product {self.name}>'


# ==============================================================================
#  PROFILE (USER) MODEL
# ==============================================================================

class Profile(db.Model):
    __tablename__ = 'profiles'

    # --- Kolommen ---
    id = db.Column(UUID(as_uuid=True), primary_key=True)
    full_name = db.Column(db.Text)
    phone_number = db.Column(db.Text)
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    # --- Relaties ---
    orders = db.relationship('Order', backref='profile', lazy=True)

    # --- Methoden ---
    def __repr__(self):
        return f'<Profile {self.full_name}>'


# ==============================================================================
#  ORDER MODEL
# ==============================================================================
    
class Order(db.Model):
    __tablename__ = 'orders'

    # --- Kolommen ---
    id = db.Column(db.BigInteger, primary_key=True)
    status = db.Column(db.Text, nullable=False, default='pending')
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    pickup_date = db.Column(db.Date)
    remarks = db.Column(db.Text)
    
    # --- Timestamps ---
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    order_date = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # --- Foreign Keys ---
    user_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey('profiles.id'), nullable=False)

    # --- Relaties ---
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

    # --- Methoden ---
    def __repr__(self):
        return f'<Order {self.id}>'


# ==============================================================================
#  ORDER ITEM MODEL
# ==============================================================================

class OrderItem(db.Model):
    __tablename__ = 'order_items'

    # --- Kolommen ---
    id = db.Column(db.BigInteger, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price_at_order = db.Column(db.Numeric(10, 2), nullable=False)

    # --- Foreign Keys ---
    order_id = db.Column(db.BigInteger, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.BigInteger, db.ForeignKey('products.id'), nullable=False)

    # --- Methoden ---
    def __repr__(self):
        return f'<OrderItem {self.id} (Order {self.order_id})>'