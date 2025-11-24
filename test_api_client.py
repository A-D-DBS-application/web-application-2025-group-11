import requests
import json

# Dit script doet alsof het een extern kassasysteem is
BASE_URL = "http://127.0.0.1:5000/api"
API_KEY = "SaHo5ACiML8AdIW4"

# Headers (hier stoppen we de sleutel in)
headers = {
    'X-API-KEY': API_KEY,
    'Content-Type': 'application/json'
}

print("--- STAP 1: Alle producten ophalen ---")
response = requests.get(f"{BASE_URL}/products")
if response.status_code == 200:
    producten = response.json()
    print(f"✅ Gelukt! Ik zie {len(producten)} producten.")
    # We pakken het ID van het eerste product om te testen
    if producten:
        test_id = producten[0]['id']
        huidige_prijs = producten[0]['price']
        print(f"   We gaan product ID {test_id} ({producten[0]['name']}) aanpassen.")
        print(f"   Oude prijs: € {huidige_prijs}")
else:
    print("❌ Fout bij ophalen producten:", response.text)
    exit()

print("\n--- STAP 2: Prijs automatisch verhogen ---")
# We maken de prijs 1 euro duurder
nieuwe_prijs = huidige_prijs + 1.0

data = {
    "price": nieuwe_prijs
}

# We sturen een PUT verzoek (Update)
response = requests.put(
    f"{BASE_URL}/products/{test_id}", 
    data=json.dumps(data), 
    headers=headers
)

if response.status_code == 200:
    print(f"✅ {response.json()['message']}")
    print(f"   Nieuwe prijs in database: € {response.json()['new_price']}")
else:
    print("❌ Fout bij updaten:", response.text)