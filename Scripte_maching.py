import streamlit as st
import json
import pandas as pd
from collections import defaultdict
from datetime import datetime
from openpyxl import Workbook
from sklearn.metrics import accuracy_score, precision_score, recall_score
import io  # Pour gérer l'export Excel en mémoire

# === Interface ===
st.title("📁 Comparaison des relevés bancaires avec les factures extraites")

# 📂 Chargement automatique du fichier resultats.json depuis un chemin local
st.markdown("### 📂 Chargement automatique des factures extraites (resultats.json)")

resultats_json = None

try:
    with open(r"resultats.json", "r", encoding="utf-8") as f:
        resultats_json = json.load(f)
    st.success(f"✅ {len(resultats_json)} factures chargées depuis resultats.json.")
except Exception as e:
    st.error(f"❌ Erreur lors du chargement de resultats.json : {e}")
    st.stop()

if resultats_json:
    st.json(resultats_json)

# 📄 Upload des relevés CSV
st.markdown("---")
st.markdown("### 📄 Upload des relevés bancaires")
uploaded_csvs = st.file_uploader("Upload des relevés (CSV)", type=["csv"], accept_multiple_files=True)
df = pd.DataFrame()

def load_csv_files():
    global df
    for file in uploaded_csvs:
        try:
            part_df = pd.read_csv(file)
            if 'source' in part_df.columns:
                part_df["source"] = part_df["source"]
            else:
                part_df["source"] = "Colonne 'source' non présente"
            df = pd.concat([df, part_df], ignore_index=True)
        except Exception as e:
            st.error(f"Erreur lecture {file.name} : {e}")
    if not df.empty:
        st.success("✅ Fichiers CSV combinés avec succès.")
        st.dataframe(df, use_container_width=True)

if st.button("Charger CSVs"):
    load_csv_files()

# === Logique de Matching ===
if not df.empty and resultats_json:
    def is_date_close(date1, date2):
        return date1 == date2

    def is_address_similar(addr1, addr2):
        if not addr1 or not addr2:
            return False
        words1 = set(addr1.lower().strip().replace(",", "").split())
        words2 = set(addr2.lower().strip().replace(",", "").split())
        return len(words1 & words2) >= 3

    factures_par_montant = defaultdict(list)
    for extrait in resultats_json:
        if "error" not in extrait:
            try:
                if isinstance(extrait["total"], str):
                    montant = float(extrait["total"].strip()) if extrait["total"].strip() else 0.0
                else:
                    montant = float(extrait["total"])
            except ValueError:
                montant = 0.0
            factures_par_montant[montant].append(extrait)

    used_factures = set()
    matched_factures = {}

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
                matched_factures[facture["image"]] = True
                return facture["image"]

        if factures_potentielles:
            facture = factures_potentielles[0]
            used_factures.add(facture["image"])
            matched_factures[facture["image"]] = True
            return facture["image"]

        return None

    df["Facture associée"] = df.apply(find_matching_facture, axis=1)
    df["Match"] = df["Facture associée"].notnull()

    def extract_first_4_digits(text):
        return text[:4] if text else ""

    df["source_first_4"] = df["source"].apply(lambda x: extract_first_4_digits(str(x)))
    df["facture_first_4"] = df["Facture associée"].apply(lambda x: extract_first_4_digits(str(x)))
    df["Match_4_digits"] = df["source_first_4"] == df["facture_first_4"]

    true_positives = df["Match_4_digits"].sum()
    false_positives = df["Match_4_digits"].count() - true_positives
    false_negatives = df[df["Match_4_digits"] == False].shape[0]
    true_negatives = 0

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    accuracy = true_positives / df.shape[0]

    st.markdown(f"📊 Précision : {precision * 100:.2f}%")
    st.markdown(f"📊 Rappel : {recall * 100:.2f}%")
    st.markdown(f"📊 Exactitude (Accuracy) : {accuracy * 100:.2f}%")

    incorrect_matches = df[df["Match_4_digits"] == False]
    st.write(f"Lignes avec des correspondances incorrectes :")
    st.dataframe(incorrect_matches)

    st.markdown("### ✅ Résultats des métriques")
    st.write(f"📊 Précision : {precision * 100:.2f}%")
    st.write(f"📊 Rappel : {recall * 100:.2f}%")
    st.write(f"📊 Exactitude (Accuracy) : {accuracy * 100:.2f}%")

    def color_rows(val):
        return ['background-color: lightgreen' if m else '' for m in val]

    styled_df = df.style.apply(color_rows, subset=["Match"])
    st.markdown("### ✅ Résultat de la comparaison")
    st.dataframe(styled_df, use_container_width=True)

    matched_df = df[df["Match"]]
    if not matched_df.empty:
        st.success(f"{len(matched_df)} lignes matchées avec des factures.")
        st.dataframe(matched_df, use_container_width=True)
    else:
        st.warning("Aucune correspondance trouvée.")

    # === Export Excel téléchargeable ===
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Matching")
    output.seek(0)

    st.download_button(
        label="📥 Télécharger le relevé enrichi (Excel)",
        data=output,
        file_name="releve_match.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )