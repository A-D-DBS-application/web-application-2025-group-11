# bootstrap:
De applicatie werkt perfect voor ipad en computer (2 devices), de interface voor de klant werkt ook perfect op gsm maar alleen de interface speciaal voor de bakker zelf is niet optimaal op de gsm maar volgens ons is het niet belangrijk dat de bakker hiervoor zijn gsm kan gebruiken, aangezien het sowieso makkelijker gaat op een ipad of computer.


# inloggegevens voor gebruiken van de admin-functionaliteiten:
email: mathisdebaene@gmail.com
wachtwoord: mathis

Als er zelf een account aangemaakt wordt is het belangrijk dat je bevestigd via de mail die je van supabase krijgt.

# Figma protoype: 
https://www.figma.com/proto/eqcr3J30jhTZHAwjNnOGV8/Project-A-D?node-id=0-1&t=LtArySwhaOy5cONU-1, 
vanuit dit protype zijn we vertrokken voor het maken van onze website. Hoewel het toch wel verschilt van hoe onze website er nu uit ziet heeft dit toch de basis gevormd.

# Zie mapje Deliverables voor:
Screenshots/images of UI
(E)ER model
database dump
DDL model
ERD model
Feedback
Handover
Presentatie
Render link
User stories

# Hand-off: 
Bij het overdragen van de applicatie kan de partner het script reset_complete.py runnen, zodat de website helemaal leeg is (geen fictieve orders en producten meer). Op deze manier kan hij met een lege website beginnen en zelf al zijn producten toevoegen.

Het Profiel "winkelverkoop" is het profiel dat aan de kassa gelinkt moet worden bij deployment van de app. Om dit profiel over te zetten mag het oude profiel verwijderd worden uit de database (nu onder mail: emile.debourdeaudhuy+kassa@gmail.com) (dit gebeurt ook automatisch bij het runnen van reset_complete.py). 
Het is heel belangrijk dat er een profiel met de naam "Winkelverkoop" verbonden is aan de kassa omdat het algoritme hier naar kijkt voor de voorspelling van de verkoop in de winkel zelf (het email-adres maakt hiervoor niet zo uit, maar het moet wel een bestaand adres zijn om de mail te bevestigen).

# Installatie & Gebruiksinstructies

Volg onderstaande stappen om de Flask-applicatie lokaal te installeren en te configureren.

# 1. Omgeving opzetten
Open je terminal (of Git Bash) en voer de volgende commando's uit:

```bash
# Project downloaden
git clone https://github.com/A-D-DBS-application/web-application-2025-group-11.git
cd web-application-2025-group-11

# Virtuele omgeving aanmaken
python -m venv venv

# Activeren (Windows)
venv\Scripts\activate
# Activeren (macOS/Linux)
source venv/bin/activate

# Afhankelijkheden installeren
pip install -r requirements.txt

# Voer de seed-scripts uit om de tabellen te vullen met de benodigde data voor de bakkerij:
python data_generations/seed_recipes.py
python data_generations/seed_history.py

# App starten
python run.py




