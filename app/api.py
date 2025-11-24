from flask import Blueprint, request, jsonify
from .models import Product, db
from config import Config

# 1. We maken een nieuwe 'Blueprint'. 
# Dit is een verzameling routes die allemaal beginnen met '/api'.
api = Blueprint('api', __name__, url_prefix='/api')

# --- HULPFUNCTIE: BEVEILIGING ---
def check_api_key():
    """
    Deze functie kijkt of het verzoek de juiste sleutel bevat.
    De sleutel moet in de 'Headers' zitten onder de naam 'X-API-KEY'.
    """
    key = request.headers.get('X-API-KEY')
    return key == Config.API_KEY

# --- ROUTE 1: LEZEN (GET) ---
# Een ander systeem vraagt: "Geef mij een lijst van al jouw producten"
@api.route('/products', methods=['GET'])
def get_products():
    # A. Haal alles op uit de database
    products = Product.query.all()
    
    # B. Zet de database-objecten om naar een lijst van woordenboeken (JSON)
    # Dit moet omdat JSON geen Python-objecten snapt.
    output = []
    for p in products:
        product_data = {
            'id': p.id,
            'name': p.name,
            'price': float(p.price), # We maken er een float van (getal met komma)
            'category': p.category,
            'is_available': p.is_available
        }
        output.append(product_data)

    # C. Stuur de lijst terug als JSON (tekstformaat voor machines)
    return jsonify(output)

# --- ROUTE 2: AANPASSEN (PUT) ---
# Een ander systeem zegt: "Update de prijs van product met ID X"
@api.route('/products/<int:id>', methods=['PUT'])
def update_product(id):
    # A. Eerst controleren: heb je de sleutel?
    if not check_api_key():
        # Code 401 betekent: "Niet toegestaan / Unauthorized"
        return jsonify({'error': 'Geen geldige API Key!'}), 401

    # B. Zoek het product in de database
    product = Product.query.get(id)
    if not product:
        # Code 404 betekent: "Niet gevonden"
        return jsonify({'error': 'Product ID bestaat niet'}), 404

    # C. Lees de data die de machine heeft meegestuurd
    data = request.get_json()

    # D. Update alleen wat er is meegestuurd
    if 'price' in data:
        print(f"DEBUG API: Prijs van {product.name} wordt aangepast naar {data['price']}")
        product.price = data['price']
    
    if 'name' in data:
        product.name = data['name']

    # E. Opslaan in de database
    try:
        db.session.commit()
        # Code 200 betekent: "Succes!"
        return jsonify({'message': f'Product {id} succesvol bijgewerkt!', 'new_price': float(product.price)}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500