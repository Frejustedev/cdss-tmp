"""CDSS-TMP — Application Streamlit principale."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import chercheur
import init_app
import medecin_nucleaire
import prescripteur
from database import get_connection, init_db

CLASSIFICATION_COLORS = {
    "A": "background-color: #d4edda; color: #155724; font-weight: 600;",
    "MBA": "background-color: #fff3cd; color: #856404; font-weight: 600;",
    "RA": "background-color: #f8d7da; color: #721c24; font-weight: 600;",
}

CATEGORIES = ["A", "B", "C", "D", "E", "F", "G", "H"]


def load_scenarios() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT id, categorie, contexte_clinique, variables_cles, "
            "score_auc, classification, source, note_clinique "
            "FROM scenarios_auc ORDER BY id",
            conn,
        )


def render_referentiel() -> None:
    st.header("Référentiel AUC ACCF/ASNC")

    col_cat, col_search = st.columns([1, 3])
    with col_cat:
        categorie = st.selectbox("Catégorie", ["Toutes", *CATEGORIES])
    with col_search:
        recherche = st.text_input("Recherche libre", placeholder="Mot-clé, contexte, variable…")

    df = load_scenarios()

    if categorie != "Toutes":
        df = df[df["categorie"].str.startswith(f"{categorie}.")]
    if recherche:
        mask = df.apply(
            lambda row: row.astype(str).str.contains(recherche, case=False, na=False).any(),
            axis=1,
        )
        df = df[mask]

    st.caption(f"{len(df)} scénario(s) affiché(s)")

    if df.empty:
        st.info(
            "Aucun scénario à afficher. La base est vide ou aucun résultat "
            "ne correspond au filtre."
        )
        return

    styled = df.style.map(
        lambda v: CLASSIFICATION_COLORS.get(v, ""),
        subset=["classification"],
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    with st.expander("Légende des classifications"):
        st.markdown(
            "- **A** — Appropriée (score 7-9)\n"
            "- **MBA** — Peut être appropriée (score 4-6)\n"
            "- **RA** — Rarement appropriée (score 1-3)"
        )


init_app.ensure_initialized()

st.set_page_config(
    page_title="CDSS-TMP",
    layout="wide",
)

st.title("CDSS-TMP — Évaluation des prescriptions de TMP")

st.sidebar.title("Menu")
module = st.sidebar.radio(
    "Modules",
    ("Accueil", "Prescripteur", "Médecin Nucléaire", "Chercheur", "Référentiel"),
)

if module == "Accueil":
    st.markdown(
        """
        Bienvenue dans le **CDSS-TMP**, système d'aide à la décision clinique
        pour les prescriptions de tomoscintigraphie myocardique de perfusion
        (TMP).

        Sélectionnez un module dans le menu latéral pour commencer.
        """
    )
    st.subheader("Modules disponibles")
    st.markdown(
        """
        - **Prescripteur** — saisie et évaluation d'une prescription
        - **Médecin Nucléaire** — validation et compte-rendu
        - **Chercheur** — analyse et export des données
        - **Référentiel** — AUC ACCF/ASNC 2023 et SPECT-MPI 2009
        """
    )
elif module == "Référentiel":
    render_referentiel()
elif module == "Prescripteur":
    prescripteur.render()
elif module == "Médecin Nucléaire":
    medecin_nucleaire.render()
elif module == "Chercheur":
    chercheur.render()
else:
    st.header(f"Module {module}")
    st.info("Module en cours de développement.")
