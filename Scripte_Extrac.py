import streamlit as st
import base64
import json
import re
from dotenv import load_dotenv
from mistralai import Mistral
import time
import os
import subprocess

# Charger les variables d'environnement
load_dotenv()
api_key = os.getenv("CLE_API")

if not api_key:
    st.error("❌ Clé API Mistral non trouvée. Ajoutez-la dans un fichier .env.")
    st.stop()

client = Mistral(api_key=api_key)

# --- Fonctions utilitaires ---
def encode_image_from_bytes(image_bytes):
    return base64.b64encode(image_bytes).decode('utf-8')

def extract_json_from_text(text):
    """Essaie d'extraire un bloc JSON même s'il y a du texte autour."""
    try:
        json_match = re.search(r"\{.*?\}", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass
    return None

def generate_empty_result(image_name):
    """Retourne un dictionnaire vide pour garder la même structure."""
    return {
        "image": image_name,
        "nom": "",
        "adresse": "",
        "date": "",
        "total": ""
    }

def extract_text_from_image_bytes(image_bytes, filename="image.jpg"):
    try:
        with open("context.txt", "r", encoding="utf-8") as file:
            context = file.read()
        with open("prompt.txt", "r", encoding="utf-8") as file:
            prompt = file.read()

        base64_image = encode_image_from_bytes(image_bytes)

        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": context}]
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                ]
            }
        ]

        chat_response = client.chat.complete(
            model="pixtral-12b-2409",
            messages=messages,
            response_format={"type": "json_object"}
        )

        extracted_text = chat_response.choices[0].message.content.strip()
        data = extract_json_from_text(extracted_text)

        if data:
            data["image"] = filename
            return data
        else:
            # Retourne un dictionnaire avec les clés vides
            return generate_empty_result(filename)

    except Exception as e:
        # En cas d’erreur, retourne aussi un JSON vide avec le nom de l’image
        return generate_empty_result(filename)

# --- INTERFACE STREAMLIT ---
st.title("📤 Extraction de factures avec Mistral AI")
st.markdown("1️⃣ Uploadez vos factures au format image (JPEG/JPG)")

uploaded_images = st.file_uploader("Glissez-déposez des factures (images)", type=["jpg", "jpeg"], accept_multiple_files=True)

results = []

if uploaded_images:
    with st.spinner("🔍 Analyse des images en cours..."):
        for image in uploaded_images:
            image_bytes = image.read()
            result = extract_text_from_image_bytes(image_bytes, image.name)
            results.append(result)
            time.sleep(5)  # Facultatif, selon les quotas API

    st.success("✅ Analyse terminée !")

    for res in results:
        st.subheader(f"🖼 {res['image']}")
        st.json(res)

    # Export JSON
    result_json = json.dumps(results, indent=4, ensure_ascii=False)
    st.download_button("📥 Télécharger les résultats JSON", result_json, file_name="resultats_factures.json", mime="application/json")

# 💾 Sauvegarde locale
if results:
    with open("Resultats.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    print("✅ Fichier resultats.json créé avec succès.")
else:
    print("⚠ Aucune donnée extraite.")

# Lancer un autre script si besoin
if st.button("Maching"):
    subprocess.Popen(["streamlit", "run", "Scripte_maching.py"])
    st.success("Script exécuté avec succès !")

