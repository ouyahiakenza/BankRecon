import streamlit as st
import json
import pandas as pd
from collections import defaultdict
from datetime import datetime
from openpyxl import Workbook
from sklearn.metrics import accuracy_score, precision_score, recall_score

# === Interface ===
st.title("📁 Comparaison des relevés bancaires avec les factures extraites")

# 📂 Chargement automatique du fichier resultats.json depuis un chemin local
st.markdown("### 📂 Chargement automatique des factures extraites (resultats.json)")

resultats_json = None

# Charger automatiquement le fichier JSON depuis un chemin local
try:
    with open(r"C:\Users\HP\Documents\Projet Machine Learning\Projet_ML_Hetic\resultats.json", "r", encoding="utf-8") as f:
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
            # Lire le fichier CSV
            part_df = pd.read_csv(file)
            
            # Vérifier si la colonne 'source' existe dans le fichier et l'ajouter dans le DataFrame
            if 'source' in part_df.columns:
                # Si la colonne 'source' existe, on garde sa valeur exacte
                part_df["source"] = part_df["source"]
            else:
                # Si la colonne 'source' n'existe pas, on ajoute un message indiquant qu'elle est absente
                part_df["source"] = "Colonne 'source' non présente"
                
            # Ajouter les données du fichier CSV dans le DataFrame global
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
        return len(words1 & words2) >= 3  # Au moins 3 mots communs

    # Créer un dictionnaire des factures par montant
    factures_par_montant = defaultdict(list)
    for extrait in resultats_json:
        if "error" not in extrait:
            try:
                if isinstance(extrait["total"], str):
                    montant = float(extrait["total"].strip()) if extrait["total"].strip() else 0.0
                else:
                    montant = float(extrait["total"])
            except ValueError:
                montant = 0.0  # Si la conversion échoue, on assigne 0.0 par défaut
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

    # === Comparaison des 4 premiers chiffres ===
    def extract_first_4_digits(text):
        return text[:4] if text else ""

    df["source_first_4"] = df["source"].apply(lambda x: extract_first_4_digits(str(x)))
    df["facture_first_4"] = df["Facture associée"].apply(lambda x: extract_first_4_digits(str(x)))

    df["Match_4_digits"] = df["source_first_4"] == df["facture_first_4"]

    # Calcul des métriques : Précision, Rappel, Exactitude
    true_positives = df["Match_4_digits"].sum()  # Nombre de True dans "Match_4_digits"
    false_positives = df["Match_4_digits"].count() - true_positives  # Nombre de False dans "Match_4_digits"
    false_negatives = df[df["Match_4_digits"] == False].shape[0]  # Nombre de Faux Négatifs (lignes où "Match_4_digits" est False)
    true_negatives = 0  # Pas de vrais négatifs dans ce cas, pas de "négatifs" dans la logique de comparaison des factures

    # Calcul des métriques
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    accuracy = true_positives / df.shape[0]  # Exactitude : proportion de lignes correctement identifiées (True Positives sur l'ensemble)

    # Affichage des résultats
    st.markdown(f"📊 Précision : {precision * 100:.2f}%")
    st.markdown(f"📊 Rappel : {recall * 100:.2f}%")
    st.markdown(f"📊 Exactitude (Accuracy) : {accuracy * 100:.2f}%")

    # Afficher les lignes qui ont une correspondance incorrecte
    incorrect_matches = df[df["Match_4_digits"] == False]
    st.write(f"Lignes avec des correspondances incorrectes :")
    st.dataframe(incorrect_matches)

    st.markdown("### ✅ Résultats des métriques")
    st.write(f"📊 *Précision* : {precision * 100:.2f}%")
    st.write(f"📊 *Rappel* : {recall * 100:.2f}%")
    st.write(f"📊 *Exactitude (Accuracy)* : {accuracy * 100:.2f}%")

    # Affichage des résultats
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

# # Export Excel
#     if st.button("Exporter en Excel"):
#         excel_filename = "releve_match.xlsx"
#         with pd.ExcelWriter(excel_filename, engine="openpyxl") as writer:
#             df.to_excel(writer, index=False, sheet_name="Matching")
#         with open(excel_filename, "rb") as f:
#             st.download_button("📝 Télécharger le relevé enrichi (Excel)", f, file_name = excel_filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")



    # # Export JSON
    # if st.button("Exporter en JSON"):
    #     json_filename = "releve_match.json"
    #     df_to_json = df.to_dict(orient="records")
    #     with open(json_filename, "w", encoding="utf-8") as f:
    #         json.dump(df_to_json, f, ensure_ascii=False, indent=4)
    #     with open(json_filename, "rb") as f:
    #         st.download_button("📂 Télécharger le relevé enrichi (JSON)", f, file_name=json_filename, mime="application/json")