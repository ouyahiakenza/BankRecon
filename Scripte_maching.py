import streamlit as st
import json
import pandas as pd
import os
import io
from collections import defaultdict
from datetime import datetime
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils.dataframe import dataframe_to_rows
from sklearn.metrics import accuracy_score, precision_score, recall_score

# Définir le dossier contenant les images (ici "receipts")
IMAGES_FOLDER = r"C:\Users\HP\Documents\Projet Machine Learning\Projet\dataset\receipts"

# === Interface ===
st.title("📁 Comparaison des relevés bancaires avec les factures extraites")

# --- Chargement du fichier JSON ---
st.markdown("### 📂 Chargement automatique des factures extraites (resultats.json)")
try:
    with open("resultats.json", "r", encoding="utf-8") as f:
        resultats_json = json.load(f)
    st.success(f"✅ {len(resultats_json)} factures chargées depuis resultats.json.")
except Exception as e:
    st.error(f"❌ Erreur lors du chargement de resultats.json : {e}")
    st.stop()

st.json(resultats_json)

# --- Upload des fichiers CSV ---
st.markdown("---")
st.markdown("### 📄 Upload des relevés bancaires")
uploaded_csvs = st.file_uploader("Upload des relevés (CSV)", type=["csv"], accept_multiple_files=True)
df = pd.DataFrame()

def load_csv_files():
    global df
    for file in uploaded_csvs:
        try:
            part_df = pd.read_csv(file)
            if 'source' not in part_df.columns:
                part_df["source"] = "Colonne 'source' non présente"
            df = pd.concat([df, part_df], ignore_index=True)
        except Exception as e:
            st.error(f"Erreur lecture {file.name} : {e}")
    if not df.empty:
        st.success("✅ Fichiers CSV combinés avec succès.")
        st.dataframe(df, use_container_width=True)

if st.button("Charger CSVs"):
    load_csv_files()

# --- Logique de Matching ---
if not df.empty and resultats_json:
    # Fonctions d'aide pour le matching
    def is_date_close(date1, date2):
        return date1 == date2

    def is_address_similar(addr1, addr2):
        if not addr1 or not addr2:
            return False
        words1 = set(addr1.lower().strip().replace(",", "").split())
        words2 = set(addr2.lower().strip().replace(",", "").split())
        return len(words1 & words2) >= 3

    # Regrouper les factures par montant
    factures_par_montant = defaultdict(list)
    for extrait in resultats_json:
        if "error" not in extrait:
            try:
                montant = float(extrait["total"].strip()) if isinstance(extrait["total"], str) else float(extrait["total"])
            except ValueError:
                montant = 0.0
            factures_par_montant[montant].append(extrait)

    used_factures = set()
    def find_matching_facture(row):
        montant_csv = float(row["amount"])
        date_csv = str(row["date"])
        adresse_csv = str(row["vendor"]).lower()
        if montant_csv not in factures_par_montant:
            return None
        factures_potentielles = [fact for fact in factures_par_montant[montant_csv] if fact["image"] not in used_factures]
        for condition in [
            lambda facts: [fact for fact in facts if is_date_close(fact["date"], date_csv)],
            lambda facts: [fact for fact in facts if is_address_similar(fact.get("address", ""), adresse_csv)]
        ]:
            filtered_facts = condition(factures_potentielles)
            if filtered_facts:
                facture = filtered_facts[0]
                used_factures.add(facture["image"])
                return facture["image"]
        if factures_potentielles:
            facture = factures_potentielles[0]
            used_factures.add(facture["image"])
            return facture["image"]
        return None

    df["Facture associée"] = df.apply(find_matching_facture, axis=1)
    df["Match"] = df["Facture associée"].notnull()

    def extract_first_4_digits(text):
        return text[:4] if text else ""

    df["source_first_4"] = df["source"].apply(lambda x: extract_first_4_digits(str(x)))
    df["facture_first_4"] = df["Facture associée"].apply(lambda x: extract_first_4_digits(str(x)))
    df["Match_4_digits"] = df["source_first_4"] == df["facture_first_4"]

    # Calcul des métriques
    true_positives = df["Match_4_digits"].sum()
    false_positives = df["Match_4_digits"].count() - true_positives
    false_negatives = df[df["Match_4_digits"] == False].shape[0]
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    accuracy = true_positives / df.shape[0]

    st.markdown("### ✅ Résultats des métriques")
    st.write(f"📊 Précision : {precision * 100:.2f}%")
    st.write(f"📊 Rappel : {recall * 100:.2f}%")
    st.write(f"📊 Exactitude (Accuracy) : {accuracy * 100:.2f}%")

    st.markdown("### ✅ Résultat de la comparaison")
    st.dataframe(df, use_container_width=True)

    # Ajout d'une colonne pour un lien vers l'onglet Excel (le nom de l'onglet sera le nom de l'image)
    def make_hyperlink(sheet_name):
        return f"#'{sheet_name}'!A1" if sheet_name else ""
    df["Lien Image"] = df["Facture associée"].apply(lambda img: make_hyperlink(img) if pd.notna(img) else "")

    # --- Export Excel avec images ---
    # Ici, on utilise un buffer et pd.ExcelWriter pour créer un onglet "Matching"
    # Ensuite, on ajoute un onglet pour chaque image via openpyxl

    # Création du buffer
    output = io.BytesIO()

    # Création du workbook avec openpyxl
    wb = Workbook()
    ws_main = wb.active
    ws_main.title = "Matching"

    # Écriture du DataFrame dans l'onglet "Matching"
    # On utilise la fonction dataframe_to_rows pour convertir le DataFrame en lignes
    for row in dataframe_to_rows(df, index=False, header=True):
        ws_main.append(row)

    # Création d'un onglet par image matchée
    for image_name in df["Facture associée"].dropna().unique():
        image_path = os.path.join(IMAGES_FOLDER, image_name)
        if os.path.exists(image_path):
            # Limiter le nom de la feuille à 31 caractères
            sheet_title = image_name[:31]
            ws_img = wb.create_sheet(title=sheet_title)
            try:
                img = XLImage(image_path)
                img.anchor = "A1"
                ws_img.add_image(img)
            except Exception as e:
                st.warning(f"Erreur avec l'image {image_path} : {e}")
        else:
            st.warning(f"Image non trouvée : {image_path}")

    # Enregistrer le workbook dans le buffer
    wb.save(output)
    output.seek(0)

    # Bouton de téléchargement
    st.download_button(
        label="📥 Télécharger le relevé enrichi (Excel)",
        data=output.getvalue(),
        file_name="releve_match.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )