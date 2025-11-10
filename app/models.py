from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func


db = SQLAlchemy()

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    # Numeric(10, 2) zorgt dat 4.85 ook echt 4.85 blijft en niet 4.849999
    price = db.Column(db.Numeric(10, 2), nullable=False)
    # We slaan hier straks alleen de bestandsnaam op, bijv: 'zuurdesem.jpg'
    image_url = db.Column(db.Text)
    category = db.Column(db.Text)
    is_available = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Product {self.name}>'
    
class Profile(db.Model):
    __tablename__ = 'profiles'

    # We gebruiken UUID als primary key omdat deze moet matchen met auth.users
    id = db.Column(UUID(as_uuid=True), primary_key=True)
    full_name = db.Column(db.Text)
    phone_number = db.Column(db.Text)
    # server_default=func.now() laat de database automatisch de tijd invullen
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f'<Profile {self.full_name}>'
    
