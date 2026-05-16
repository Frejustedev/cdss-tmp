"""Calcul de la probabilité pré-test (PPT) et matching scénario AUC."""
from __future__ import annotations

from database import get_connection

# Probabilité pré-test d'atteinte coronarienne obstructive — ESC 2019 Table 4
# (Knuuti J. et al., 2019 ESC Guidelines for the diagnosis and management of
# chronic coronary syndromes). Valeurs en pourcentages, par tranche d'âge.
# Format : (age_min, age_max, ppt_pct)
PPT_TABLE = {
    "typique": {
        "H": [(30, 39, 3),  (40, 49, 22), (50, 59, 32), (60, 69, 44), (70, 150, 52)],
        "F": [(30, 39, 5),  (40, 49, 10), (50, 59, 13), (60, 69, 16), (70, 150, 27)],
    },
    "atypique": {
        "H": [(30, 39, 4),  (40, 49, 10), (50, 59, 17), (60, 69, 26), (70, 150, 34)],
        "F": [(30, 39, 3),  (40, 49, 6),  (50, 59, 6),  (60, 69, 11), (70, 150, 19)],
    },
    "non_angineuse": {
        "H": [(30, 39, 1),  (40, 49, 3),  (50, 59, 11), (60, 69, 22), (70, 150, 24)],
        "F": [(30, 39, 1),  (40, 49, 2),  (50, 59, 3),  (60, 69, 6),  (70, 150, 10)],
    },
    "dyspnee": {
        "H": [(30, 39, 0),  (40, 49, 12), (50, 59, 20), (60, 69, 27), (70, 150, 32)],
        "F": [(30, 39, 3),  (40, 49, 3),  (50, 59, 9),  (60, 69, 14), (70, 150, 12)],
    },
}

# Mappe les libellés UI vers les clés de PPT_TABLE.
SYMPTOME_TO_KEY = {
    "Angor typique": "typique",
    "Angor atypique": "atypique",
    "Douleur non angineuse": "non_angineuse",
    "Dyspnée seule": "dyspnee",
}

# Seuils de bucketisation. ESC 2019 propose ≤5% / 5-15% / >15% (low /
# low-intermediate / intermediate-high). Pour pouvoir activer les 3 buckets
# UI (Faible/Intermédiaire/Élevée) avec les valeurs ESC 2019 (max ≈52%), on
# adapte : ≤15% Faible, 16-50% Intermédiaire, >50% Élevée.
_SEUIL_FAIBLE = 15
_SEUIL_ELEVEE = 50


def calculer_ppt(age: int, sexe: str, symptomes: str) -> str | None:
    """Retourne 'Faible', 'Intermédiaire' ou 'Élevée'.

    age      : entier (ans).
    sexe     : 'H' ou 'F'.
    symptomes: libellé UI ('Angor typique', 'Angor atypique',
               'Douleur non angineuse', 'Dyspnée seule').
    Retourne None si symptômes hors table (ex. 'Syncope d'effort').
    """
    sym_key = SYMPTOME_TO_KEY.get(symptomes)
    if sym_key is None or sexe not in ("H", "F"):
        return None

    ranges = PPT_TABLE[sym_key][sexe]
    ppt_pct = next((p for lo, hi, p in ranges if lo <= age <= hi), None)
    if ppt_pct is None:
        # Patient < 30 ans : on prend la tranche la plus basse.
        ppt_pct = ranges[0][2]

    if ppt_pct <= _SEUIL_FAIBLE:
        return "Faible"
    if ppt_pct <= _SEUIL_ELEVEE:
        return "Intermédiaire"
    return "Élevée"


def match_scenario(contexte: int, reponses: dict) -> str | None:
    """Mappe (contexte, réponses) vers un ID de scénario AUC (S001-S050).

    contexte : 1=symptomatique CAD, 2=asymptomatique, 3=CAD connue, 4=IC/autre.
    reponses : dict des réponses de l'étape 3.

    Retourne l'ID du scénario (vérifié présent en BDD) ou None.
    """
    if contexte == 1:
        sid = _match_branche_a(reponses)
    elif contexte == 2:
        sid = _match_branche_b(reponses)
    elif contexte == 3:
        sid = _match_branche_c(reponses)
    elif contexte == 4:
        sid = _match_branche_d(reponses)
    else:
        return None

    if sid is None:
        return None

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM scenarios_auc WHERE id = ?", (sid,)
        ).fetchone()
    return sid if row else None


def _match_branche_a(r: dict) -> str | None:
    """Branche A — Suspicion CAD symptomatique → S001-S010."""
    if r.get("angor_vasospastique") == "Oui":
        return "S007"
    if r.get("delai") == "Aiguë résolue":
        return "S008"
    if r.get("symptome") == "Syncope d'effort":
        return "S010"

    ppt = r.get("ppt")
    ecg_ok = r.get("ecg_interpretable") == "Oui"
    effort_ok = r.get("capable_effort") == "Oui"
    able = ecg_ok and effort_ok

    # Dyspnée d'effort isolée + PPT intermédiaire + ECG ininterprétable → S009
    if r.get("symptome") == "Dyspnée seule" and ppt == "Intermédiaire" and not ecg_ok:
        return "S009"

    if ppt == "Faible":
        return "S001" if able else "S002"
    if ppt == "Intermédiaire":
        return "S003" if able else "S004"
    if ppt == "Élevée":
        return "S005" if able else "S006"

    return None


def _match_branche_b(r: dict) -> str | None:
    """Branche B — Patient asymptomatique → S011-S026."""
    indication = r.get("indication")

    if indication == "Pré-transplantation rénale":
        return "S024"
    if indication == "Bilan pré-op chirurgie cardiaque":
        return "S025"
    if indication == "Avant activité physique intense":
        return "S018"

    if indication == "Dépistage":
        # Éléments paracliniques d'abord (plus discriminants).
        score = r.get("score_calcique")
        if score == ">=400":
            return "S015"
        if score == "100-399":
            return "S016"
        if r.get("atherome_extracardiaque") == "Oui":
            return "S017"
        if r.get("ecg_repos_anormal") == "Oui":
            return "S014"

        risque = r.get("risque_cv")
        if risque == "Faible":
            return "S011"
        if risque == "Intermédiaire":
            return "S012"
        if risque in ("Élevé", "Diabétique"):
            return "S013"
        return None

    if indication == "Bilan pré-op chirurgie non cardiaque":
        if r.get("examen_normal_recent") == "Oui":
            return "S026"
        risque_chir = r.get("risque_chirurgical")
        capacite = r.get("capacite_fonctionnelle")
        rcri_present = r.get("rcri") in ("1", "2+")

        if risque_chir == "Faible":
            return "S019"
        if risque_chir == "Haut risque":
            if capacite == ">=4 METs":
                return "S023"
            return "S022" if rcri_present else "S023"
        if risque_chir == "Intermédiaire":
            if capacite == ">=4 METs":
                return "S020"
            if rcri_present or capacite in ("<4 METs", "Inconnue"):
                return "S021"
        return None

    return None


def _match_branche_c(r: dict) -> str | None:
    """Branche C — CAD connue → S027-S046 (+ S042 si symptômes nouveaux)."""
    type_atcd = r.get("type_atcd")
    delai = r.get("delai_mois", 0)
    sympt = r.get("symptomes_nouveaux_aggraves") == "Oui"

    # Priorité absolue : aggravation symptomatique.
    if sympt:
        if type_atcd == "PCI":
            return "S032"
        if type_atcd == "CABG":
            return "S033"
        return "S042"

    # Éléments cliniques particuliers.
    if r.get("test_effort_recent_anormal") == "Oui":
        return "S034"
    if r.get("elevation_troponine") == "Oui":
        return "S035"
    if type_atcd == "IDM" and r.get("recherche_viabilite") == "Oui":
        return "S040"
    if type_atcd == "Sténose intermédiaire connue":
        return "S044"
    if r.get("decision_therapeutique_attente") == "Oui":
        return "S046"
    if type_atcd == "Coronarographie normale ancienne":
        return "S045"

    # Branches par type d'antécédent (patient asymptomatique stable).
    if type_atcd == "PCI":
        if r.get("pci_haute_complexite") == "Oui" and 6 <= delai <= 12:
            return "S029"
        return "S027" if delai < 24 else "S028"

    if type_atcd == "CABG":
        return "S030" if delai < 60 else "S031"

    if type_atcd == "IDM":
        return "S041" if delai <= 1 else "S038"

    return "S043"


def _match_branche_d(r: dict) -> str | None:
    """Branche D — IC / autre → S047-S050."""
    sous = r.get("sous_indication")

    if sous == "Répétition d'examen <12 mois" and r.get("tmp_normale_recente") == "Oui":
        return "S050"
    if sous == "IC de novo origine inconnue":
        return "S047"
    if sous == "CMP non ischémique suivi":
        return "S048"
    if sous == "FA de novo avec suspicion d'ischémie":
        return "S049"

    return None
