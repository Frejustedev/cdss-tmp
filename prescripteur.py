"""Module Prescripteur — workflow 5 étapes pour la demande de TMP."""
from __future__ import annotations

import json
import random
from datetime import datetime

import streamlit as st

from auth import log_action
from database import get_connection
from scoring import calculer_ppt, calculer_ppt_rfcl, match_scenario

SPECIALITES = [
    "Cardiologie", "Médecine interne", "Anesthésie-Réanimation",
    "Endocrinologie", "Chirurgie cardiaque", "Chirurgie vasculaire", "Autre",
]
FDR_OPTIONS = [
    "HTA", "Diabète type 1", "Diabète type 2", "Dyslipidémie",
    "Tabac actif", "Tabac sevré", "ATCD familial CAD précoce",
]
ATCD_OPTIONS = [
    "Aucun", "PCI antérieure", "CABG antérieur", "IDM antérieur",
    "Insuffisance cardiaque", "FA", "Valvulopathie",
]
CONTEXTES = [
    "1. Suspicion de CAD chez patient symptomatique (douleur thoracique, dyspnée d'effort, équivalent angineux)",
    "2. Patient asymptomatique (dépistage, bilan pré-opératoire, suivi systématique)",
    "3. Patient avec CAD connue (post-PCI, post-CABG, post-IDM, suivi de sténose)",
    "4. Insuffisance cardiaque / autre indication",
]
SYMPTOMES = [
    "Angor typique", "Angor atypique", "Douleur non angineuse",
    "Dyspnée seule", "Syncope d'effort",
]
DELAIS = ["Aiguë résolue", "Subaiguë", "Chronique"]
INDICATIONS_B = [
    "Dépistage",
    "Bilan pré-op chirurgie non cardiaque",
    "Bilan pré-op chirurgie cardiaque",
    "Pré-transplantation rénale",
    "Avant activité physique intense",
    "Autre",
]
TYPES_ATCD_C = [
    "PCI", "CABG", "IDM",
    "Sténose intermédiaire connue",
    "Coronarographie normale ancienne",
]
SOUS_INDICATIONS_D = [
    "IC de novo origine inconnue",
    "CMP non ischémique suivi",
    "FA de novo avec suspicion d'ischémie",
    "Répétition d'examen <12 mois",
]

CLASSIF_LABEL = {"A": "Appropriée", "MBA": "Peut être appropriée", "RA": "Rarement appropriée"}
CLASSIF_COLOR = {"A": "#28a745", "MBA": "#ffc107", "RA": "#dc3545"}


def _compter_fdr_rfcl(fdr_list) -> int:
    """Compte les facteurs de risque du modèle RF-CL parmi la liste saisie.

    Les 5 facteurs RF-CL (Winther 2020) : hypertension, diabète, dyslipidémie,
    tabagisme actif, antécédents familiaux de CAD précoce. Le tabac sevré et
    le diabète (type 1 ou 2) comptent chacun pour un facteur unique.
    """
    if not fdr_list:
        return 0
    fdr = set(fdr_list)
    nb = 0
    if "HTA" in fdr:
        nb += 1
    if "Diabète type 1" in fdr or "Diabète type 2" in fdr:
        nb += 1
    if "Dyslipidémie" in fdr:
        nb += 1
    if "Tabac actif" in fdr or "Tabac sevré" in fdr:
        nb += 1
    if "ATCD familial CAD précoce" in fdr:
        nb += 1
    return nb


def render() -> None:
    """Point d'entrée du module Prescripteur."""
    if "etape" not in st.session_state:
        st.session_state.etape = 1

    _render_progress()

    etape = st.session_state.etape
    if etape == 1:
        _render_etape1()
    elif etape == 2:
        _render_etape2()
    elif etape == 3:
        _render_etape3()
    elif etape == 4:
        _render_etape4()
    elif etape == 5:
        _render_etape5()


def _render_progress() -> None:
    labels = ["Patient", "Triage", "Questionnaire", "Résultat", "Soumission"]
    cols = st.columns(5)
    for i, (col, label) in enumerate(zip(cols, labels), start=1):
        with col:
            if i < st.session_state.etape:
                st.caption(f"✓ {i}. {label}")
            elif i == st.session_state.etape:
                st.markdown(f"**▶ {i}. {label}**")
            else:
                st.caption(f"{i}. {label}")
    st.divider()


# ===== ÉTAPE 1 — Identification patient =====
def _render_etape1() -> None:
    st.subheader("Étape 1 — Identification patient")

    if "patient_id" not in st.session_state:
        st.session_state.patient_id = f"CDSS-{datetime.now().year}-{random.randint(1000, 9999)}"
    if "start_time" not in st.session_state:
        st.session_state.start_time = datetime.now().isoformat(timespec="seconds")

    st.text_input("N° anonymisé", value=st.session_state.patient_id, disabled=True)

    st.markdown("**Prescripteur (obligatoire pour traçabilité)**")
    col_nom, col_spec = st.columns([2, 2])
    with col_nom:
        nom_prescripteur = st.text_input(
            "Nom du prescripteur",
            key="p_nom_prescripteur",
            placeholder="Prénom Nom",
            help="Nom du médecin prescrivant la TMP — minimum 3 caractères",
        )
    with col_spec:
        specialite = st.selectbox(
            "Spécialité",
            SPECIALITES,
            index=None,
            placeholder="Sélectionner…",
            key="p_specialite",
        )

    st.markdown("**Patient**")
    col_a, col_b, col_c = st.columns([2, 1, 2])
    with col_a:
        age = st.slider("Âge (ans)", 18, 100, 60, key="p_age")
    with col_b:
        sexe = st.radio("Sexe", ["H", "F"], index=None, key="p_sexe", horizontal=True)
    with col_c:
        imc = st.slider("IMC (kg/m², optionnel)", 15.0, 50.0, 25.0, step=0.1, key="p_imc")

    fdr = st.multiselect("Facteurs de risque cardiovasculaires", FDR_OPTIONS, key="p_fdr")
    atcd = st.multiselect("Antécédents cardiaques", ATCD_OPTIONS, key="p_atcd")

    st.divider()
    if st.button("Étape suivante →", type="primary"):
        manquants = []
        if not nom_prescripteur or len(nom_prescripteur.strip()) < 3:
            manquants.append("nom du prescripteur (≥3 caractères)")
        if sexe is None:
            manquants.append("sexe")
        if specialite is None:
            manquants.append("spécialité")
        if manquants:
            st.error(f"Champs obligatoires manquants : {', '.join(manquants)}.")
        else:
            st.session_state.patient_data = {
                "patient_id": st.session_state.patient_id,
                "prescripteur_nom": nom_prescripteur.strip(),
                "prescripteur_specialite": specialite,
                "specialite": specialite,  # alias legacy pour modules existants
                "age": age,
                "sexe": sexe,
                "imc": imc,
                "fdr": fdr,
                "atcd": atcd,
            }
            st.session_state.etape = 2
            st.rerun()


# ===== ÉTAPE 2 — Triage contextuel =====
def _render_etape2() -> None:
    st.subheader("Étape 2 — Triage contextuel")
    p = st.session_state.patient_data
    st.markdown(
        f"**Patient {p['patient_id']}** — {p['age']} ans, {p['sexe']} · "
        f"Prescripteur : {p['prescripteur_nom']} ({p['prescripteur_specialite']})"
    )

    contexte = st.radio(
        "Quelle est la situation clinique ?",
        CONTEXTES,
        index=None,
        key="t_contexte",
    )

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Retour"):
            st.session_state.etape = 1
            st.rerun()
    with col2:
        if st.button("Étape suivante →", type="primary"):
            if contexte is None:
                st.error("Veuillez choisir un contexte.")
            else:
                st.session_state.contexte = int(contexte[0])
                st.session_state.pop("reponses", None)
                st.session_state.pop("scenario_id", None)
                st.session_state.etape = 3
                st.rerun()


# ===== ÉTAPE 3 — Mini-questionnaire (branches) =====
def _render_etape3() -> None:
    st.subheader("Étape 3 — Questionnaire ciblé")
    ctx = st.session_state.contexte
    if ctx == 1:
        _branche_a()
    elif ctx == 2:
        _branche_b()
    elif ctx == 3:
        _branche_c()
    else:
        _branche_d()


def _nav_etape3(reponses_factory) -> None:
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Retour"):
            st.session_state.etape = 2
            st.rerun()
    with col2:
        if st.button("Étape suivante →", type="primary"):
            try:
                reponses = reponses_factory()
            except ValueError as exc:
                st.error(str(exc))
                return
            st.session_state.reponses = reponses
            st.session_state.pop("scenario_id", None)
            st.session_state.etape = 4
            st.rerun()


def _require(value, label):
    if value is None:
        raise ValueError(f"Champ obligatoire manquant : {label}.")
    return value


def _branche_a() -> None:
    st.markdown("### Branche A — Suspicion CAD symptomatique")
    p = st.session_state.patient_data

    symptome = st.selectbox("Type de symptôme", SYMPTOMES, index=None, placeholder="Sélectionner…", key="a_sym")
    delai = st.radio("Délai d'évolution", DELAIS, index=None, key="a_delai")

    ppt = None
    if symptome and symptome != "Syncope d'effort":
        nb_fdr = _compter_fdr_rfcl(p.get("fdr", []))
        rfcl = calculer_ppt_rfcl(p["age"], p["sexe"], symptome, nb_fdr)
        if rfcl:
            ppt, pct = rfcl
            st.info(
                f"PPT calculée (modèle RF-CL ESC 2024, version clinique sans CAC) "
                f"pour un patient {p['sexe']} de {p['age']} ans avec {nb_fdr} "
                f"facteur(s) de risque : **{ppt}** (≈ {pct:.0f} %)"
            )
        else:
            # Fallback : table Diamond-Forrester modifiée ESC 2019.
            ppt = calculer_ppt(p["age"], p["sexe"], symptome)
            if ppt:
                st.info(
                    f"PPT calculée (Diamond-Forrester modifié ESC 2019, fallback) "
                    f"pour un patient {p['sexe']} de {p['age']} ans : **{ppt}**"
                )

    ecg = st.radio(
        "ECG de repos interprétable",
        ["Oui", "Non"],
        index=None,
        key="a_ecg",
        help="Non si BBG, WPW, ST déprimé ≥1mm, HVG marquée, digitaliques",
    )
    effort = st.radio("Capable d'effort (≥4 METs)", ["Oui", "Non"], index=None, key="a_effort")
    vaso = st.radio("Suspicion d'angor vasospastique", ["Oui", "Non"], index=None, key="a_vaso")

    def factory():
        return {
            "branche": "A",
            "symptome": _require(symptome, "type de symptôme"),
            "delai": _require(delai, "délai d'évolution"),
            "ppt": ppt,
            "ecg_interpretable": _require(ecg, "ECG interprétable"),
            "capable_effort": _require(effort, "capacité d'effort"),
            "angor_vasospastique": _require(vaso, "angor vasospastique"),
        }

    _nav_etape3(factory)


def _branche_b() -> None:
    st.markdown("### Branche B — Patient asymptomatique")

    indication = st.radio("Indication", INDICATIONS_B, index=None, key="b_indic")

    risque_cv = score_calc = atherome = ecg_rep = None
    risque_chir = capacite = rcri = exam_recent = None

    if indication == "Dépistage":
        st.markdown("**Précisions dépistage**")
        risque_cv = st.radio(
            "Risque CV global",
            ["Faible", "Intermédiaire", "Élevé", "Diabétique"],
            index=None,
            key="b_risq_cv",
        )
        score_calc = st.radio(
            "Score calcique coronaire (CAC) connu",
            ["Non", "0", "1-99", "100-399", ">=400"],
            index=None,
            key="b_cac",
        )
        atherome = st.radio(
            "Athérosclérose extracardiaque connue", ["Oui", "Non"], index=None, key="b_ather",
        )
        ecg_rep = st.radio(
            "ECG de repos anormal isolé", ["Oui", "Non"], index=None, key="b_ecgrep",
        )
    elif indication == "Bilan pré-op chirurgie non cardiaque":
        st.markdown("**Précisions pré-opératoires**")
        risque_chir = st.radio(
            "Risque chirurgical",
            ["Faible", "Intermédiaire", "Haut risque"],
            index=None,
            key="b_risq_chir",
        )
        capacite = st.radio(
            "Capacité fonctionnelle",
            [">=4 METs", "<4 METs", "Inconnue"],
            index=None,
            key="b_capa",
        )
        rcri = st.radio(
            "Critères RCRI présents",
            ["0", "1", "2+"],
            index=None,
            key="b_rcri",
        )
        exam_recent = st.radio(
            "Examen normal récent (<1 mois)", ["Oui", "Non"], index=None, key="b_exam",
        )

    def factory():
        ind = _require(indication, "indication")
        base = {"branche": "B", "indication": ind}
        if ind == "Dépistage":
            base.update({
                "risque_cv": _require(risque_cv, "risque CV global"),
                "score_calcique": _require(score_calc, "score calcique"),
                "atherome_extracardiaque": _require(atherome, "athérome extracardiaque"),
                "ecg_repos_anormal": _require(ecg_rep, "ECG de repos anormal"),
            })
        elif ind == "Bilan pré-op chirurgie non cardiaque":
            base.update({
                "risque_chirurgical": _require(risque_chir, "risque chirurgical"),
                "capacite_fonctionnelle": _require(capacite, "capacité fonctionnelle"),
                "rcri": _require(rcri, "critères RCRI"),
                "examen_normal_recent": _require(exam_recent, "examen normal récent"),
            })
        return base

    _nav_etape3(factory)


def _branche_c() -> None:
    st.markdown("### Branche C — CAD connue")

    type_atcd = st.radio("Type d'antécédent", TYPES_ATCD_C, index=None, key="c_type")
    delai = st.slider("Délai depuis l'événement (mois)", 0, 240, 12, key="c_delai")
    sympt_nouv = st.radio("Symptômes nouveaux ou aggravés", ["Oui", "Non"], index=None, key="c_sympt")

    pci_complex = None
    if type_atcd == "PCI":
        pci_complex = st.radio(
            "PCI à haute complexité (tronc commun / IVA proximale)",
            ["Oui", "Non"], index=None, key="c_pci_complex",
        )

    test_effort = st.radio(
        "Test d'effort récent anormal", ["Oui", "Non", "Non fait"], index=None, key="c_eff",
    )
    tropo = st.radio(
        "Élévation troponine récente sans contexte aigu", ["Oui", "Non"], index=None, key="c_tropo",
    )

    viabilite = None
    if type_atcd == "IDM":
        viabilite = st.radio(
            "Recherche de viabilité myocardique", ["Oui", "Non"], index=None, key="c_via",
        )

    decision = st.radio(
        "Décision thérapeutique en attente", ["Oui", "Non"], index=None, key="c_decis",
    )

    def factory():
        base = {
            "branche": "C",
            "type_atcd": _require(type_atcd, "type d'antécédent"),
            "delai_mois": delai,
            "symptomes_nouveaux_aggraves": _require(sympt_nouv, "symptômes nouveaux ou aggravés"),
            "test_effort_recent_anormal": _require(test_effort, "test d'effort récent"),
            "elevation_troponine": _require(tropo, "élévation troponine"),
            "decision_therapeutique_attente": _require(decision, "décision thérapeutique en attente"),
        }
        if type_atcd == "PCI":
            base["pci_haute_complexite"] = _require(pci_complex, "PCI haute complexité")
        if type_atcd == "IDM":
            base["recherche_viabilite"] = _require(viabilite, "recherche viabilité")
        return base

    _nav_etape3(factory)


def _branche_d() -> None:
    st.markdown("### Branche D — Insuffisance cardiaque / autre")

    sous = st.radio("Sous-indication", SOUS_INDICATIONS_D, index=None, key="d_sous")
    fevg = st.slider("FEVG (%)", 10, 75, 50, key="d_fevg")
    tmp_norm = st.radio(
        "TMP normale récente (<12 mois)", ["Oui", "Non"], index=None, key="d_tmp_norm",
    )

    def factory():
        return {
            "branche": "D",
            "sous_indication": _require(sous, "sous-indication"),
            "fevg": fevg,
            "tmp_normale_recente": _require(tmp_norm, "TMP normale récente"),
        }

    _nav_etape3(factory)


# ===== ÉTAPE 4 — Résultat =====
def _render_etape4() -> None:
    st.subheader("Étape 4 — Résultat")

    if st.session_state.get("scenario_id") is None:
        sid = match_scenario(st.session_state.contexte, st.session_state.reponses)
        st.session_state.scenario_id = sid

    sid = st.session_state.scenario_id
    if sid is None:
        st.error(
            "Aucun scénario AUC correspondant n'a été trouvé. "
            "Vérifie tes réponses ou complète manuellement."
        )
        if st.button("← Retour"):
            st.session_state.etape = 3
            st.rerun()
        return

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, categorie, contexte_clinique, variables_cles, "
            "score_auc, classification, source, note_clinique, "
            "classe_esc, reference_esc, conformite_esc, divergence_esc "
            "FROM scenarios_auc WHERE id = ?", (sid,)
        ).fetchone()

    if row is None:
        st.error(f"Scénario {sid} introuvable en base.")
        return

    st.markdown(f"### Scénario identifié : `{row['id']}`")
    st.markdown(f"**Catégorie** : {row['categorie']}")
    st.markdown(f"**Contexte clinique** : {row['contexte_clinique']}")
    st.caption(f"Source : {row['source']}")

    score = row["score_auc"]
    classif = row["classification"]
    color = CLASSIF_COLOR[classif]
    label = CLASSIF_LABEL[classif]

    col_score, col_badge = st.columns([1, 2])
    with col_score:
        st.markdown(
            "<div style='text-align:center; color:#555; font-size:14px;'>SCORE AUC</div>"
            f"<div style='text-align:center; font-size:80px; font-weight:bold; "
            f"line-height:1; color:{color};'>{score}<span style='font-size:32px; color:#888;'>/9</span></div>",
            unsafe_allow_html=True,
        )
    with col_badge:
        st.markdown(
            f"<div style='background-color:{color}; color:white; padding:24px; "
            f"text-align:center; border-radius:10px; font-size:22px; font-weight:bold;'>"
            f"{classif} — {label}</div>",
            unsafe_allow_html=True,
        )

    st.markdown(f"**Note clinique** : {row['note_clinique']}")
    st.divider()

    # ----- Évaluation parallèle ESC (double évaluation AUC + ESC) -----
    _render_bloc_esc(row)
    st.divider()

    if classif == "RA":
        _render_alerte_alara(row)
    else:
        _render_protocole_suggere(row)


# Correspondance classe ESC -> conformité / couleur
_ESC_COLOR = {"Adhérent": "#28a745", "Non-adhérent": "#dc3545"}


def _render_bloc_esc(row) -> None:
    """Affiche l'évaluation parallèle selon les guidelines ESC."""
    classe = row["classe_esc"] if "classe_esc" in row.keys() else None
    conformite = row["conformite_esc"] if "conformite_esc" in row.keys() else None
    reference = row["reference_esc"] if "reference_esc" in row.keys() else None
    divergence = row["divergence_esc"] if "divergence_esc" in row.keys() else None

    if not classe:
        return

    st.markdown("#### Évaluation parallèle — Guidelines ESC")
    couleur = _ESC_COLOR.get(conformite, "#6c757d")

    col_classe, col_conf = st.columns([1, 2])
    with col_classe:
        st.markdown(
            "<div style='text-align:center; color:#555; font-size:14px;'>CLASSE ESC</div>"
            f"<div style='text-align:center; font-size:56px; font-weight:bold; "
            f"line-height:1.2; color:{couleur};'>{classe}</div>",
            unsafe_allow_html=True,
        )
    with col_conf:
        st.markdown(
            f"<div style='background-color:{couleur}; color:white; padding:18px; "
            f"text-align:center; border-radius:10px; font-size:20px; font-weight:bold;'>"
            f"{conformite}</div>",
            unsafe_allow_html=True,
        )

    if reference:
        st.caption(f"Référence ESC : {reference}")

    # Signaler une éventuelle divergence entre AUC et ESC
    if divergence and divergence != "Non":
        st.warning(
            f"**Divergence AUC ↔ ESC** : {divergence}\n\n"
            "Les deux référentiels ne concordent pas pour ce scénario. "
            "Le jugement clinique du médecin nucléaire est déterminant."
        )


def _render_protocole_suggere(row) -> None:
    st.markdown("#### Protocole d'acquisition suggéré")
    st.markdown("- **Protocole** : 1 jour stress-repos 99mTc-Sestamibi")

    ctx = st.session_state.contexte
    reponses = st.session_state.reponses
    modalite = None
    if ctx == 1:
        capable = reponses.get("capable_effort")
        if capable == "Oui":
            modalite = "Effort sur tapis"
        elif capable == "Non":
            modalite = "Stress pharmacologique (Régadénoson de préférence, ou Dipyridamole)"
    elif ctx == 2 and reponses.get("indication") == "Bilan pré-op chirurgie non cardiaque":
        capa = reponses.get("capacite_fonctionnelle")
        if capa == ">=4 METs":
            modalite = "Effort sur tapis si pas de CI à l'effort"
        elif capa in ("<4 METs", "Inconnue"):
            modalite = "Stress pharmacologique (Régadénoson de préférence, ou Dipyridamole)"

    if modalite:
        st.markdown(f"- **Modalité de stress** : {modalite}")
    else:
        st.markdown("- **Modalité de stress** : à déterminer par le médecin nucléaire selon le profil patient")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Retour"):
            st.session_state.etape = 3
            st.rerun()
    with col2:
        if st.button("Soumettre la demande →", type="primary"):
            st.session_state.etape = 5
            st.rerun()


def _render_alerte_alara(row) -> None:
    score = row["score_auc"]
    note = row["note_clinique"]

    st.markdown(
        f"""
<div style='background-color:#f8d7da; border-left:6px solid #dc3545;
            padding:18px; border-radius:6px;'>
  <h3 style='color:#721c24; margin-top:0;'>
    ⚠️ INDICATION RARELY APPROPRIATE (Score AUC : {score}/9)
  </h3>
  <p style='color:#721c24;'><strong>Note clinique justificative</strong> : {note}</p>
  <p style='color:#721c24;'><strong>Dose évitable estimée</strong> :
     10 mSv (protocole standard 1 jour stress-repos <sup>99m</sup>Tc-Sestamibi)</p>
  <p style='color:#721c24;'><strong>Recommandation</strong> : {note}</p>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown("")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Action recommandée**")
        if st.button("✗ Annuler la demande", type="primary"):
            patient_id = st.session_state.patient_data.get("patient_id", "?")
            sid = st.session_state.get("scenario_id", "?")
            log_action(
                "Annulation alerte ALARA", "Prescripteur",
                f"Patient: {patient_id}, Scénario: {sid}, Score: {score}/9",
                None,
            )
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    with col2:
        st.markdown("**Forcer malgré l'alerte ALARA**")
        justification = st.text_area(
            "Justification clinique obligatoire",
            key="forcage_text",
            placeholder="Préciser pourquoi la TMP reste indiquée malgré la classification RA…",
            height=100,
        )
        if st.button("Forcer et soumettre"):
            if not justification or len(justification.strip()) < 10:
                st.error("Justification trop courte (minimum 10 caractères).")
            else:
                st.session_state.forcage_justification = justification.strip()
                st.session_state.etape = 5
                st.rerun()

    st.divider()
    if st.button("← Retour aux questions"):
        st.session_state.etape = 3
        st.rerun()


# ===== ÉTAPE 5 — Soumission =====
def _render_etape5() -> None:
    st.subheader("Étape 5 — Soumission")

    if "demande_id" not in st.session_state:
        _persist_demande()

    st.success(f"✅ Demande {st.session_state.demande_id} soumise avec succès")
    p = st.session_state.patient_data
    st.markdown(f"- **Patient** : {p['patient_id']} ({p['age']} ans, {p['sexe']})")
    st.markdown(f"- **Prescripteur** : {p['prescripteur_nom']} ({p['prescripteur_specialite']})")
    st.markdown(f"- **Scénario** : {st.session_state.scenario_id}")
    st.markdown("- **Statut** : En attente (sera traité par le médecin nucléaire)")
    st.markdown(f"- **Temps total de saisie** : {st.session_state.demande_duration:.1f} s")
    if st.session_state.get("forcage_justification"):
        st.warning(
            f"Demande **forcée** malgré classification RA.\n\n"
            f"Justification : *{st.session_state.forcage_justification}*"
        )

    st.divider()
    if st.button("➕ Nouvelle demande", type="primary"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


def _persist_demande() -> None:
    end_time = datetime.now()
    start_time = datetime.fromisoformat(st.session_state.start_time)
    duration = (end_time - start_time).total_seconds()

    demande_id = f"DEM-{end_time.strftime('%Y%m%d-%H%M%S')}-{random.randint(100, 999)}"
    sid = st.session_state.scenario_id
    p = st.session_state.patient_data

    with get_connection() as conn:
        row = conn.execute(
            "SELECT score_auc, classification, classe_esc, conformite_esc "
            "FROM scenarios_auc WHERE id = ?", (sid,),
        ).fetchone()

        donnees = {
            **p,
            "contexte": st.session_state.contexte,
            "reponses": st.session_state.reponses,
            "start_time": st.session_state.start_time,
            "end_time": end_time.isoformat(timespec="seconds"),
            "duree_saisie_secondes": duration,
        }
        forcage = st.session_state.get("forcage_justification")

        conn.execute(
            "INSERT INTO demandes (id, date_creation, prescripteur, donnees_patient, "
            "scenario_id, score_auc, classification, classe_esc, conformite_esc, "
            "statut, justification_forcage) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                demande_id,
                end_time.isoformat(timespec="seconds"),
                p["prescripteur_specialite"],
                json.dumps(donnees, ensure_ascii=False),
                sid,
                row["score_auc"],
                row["classification"],
                row["classe_esc"] if "classe_esc" in row.keys() else None,
                row["conformite_esc"] if "conformite_esc" in row.keys() else None,
                "En attente",
                forcage,
            ),
        )

    st.session_state.demande_id = demande_id
    st.session_state.demande_duration = duration

    # Traçabilité : log d'audit
    log_action(
        "Soumission demande",
        "Prescripteur",
        f"Par: {p['prescripteur_nom']} ({p['prescripteur_specialite']}), "
        f"Score={row['score_auc']}/9, Class={row['classification']}, "
        f"Forçage={'oui' if forcage else 'non'}",
        demande_id,
    )
    if forcage:
        log_action(
            "Forçage RA", "Prescripteur",
            f"Justif: {forcage}", demande_id,
        )
