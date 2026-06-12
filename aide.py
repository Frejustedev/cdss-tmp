"""Module Aide & Documentation — guide utilisateur, méthodologie, FAQ."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render() -> None:
    st.header("📖 Aide & Documentation")

    tabs = st.tabs([
        "🧭 Guide d'utilisation",
        "📚 Référentiels & Méthodologie",
        "ℹ️ À propos de l'étude",
        "❓ FAQ",
    ])

    with tabs[0]:
        _onglet_guide()
    with tabs[1]:
        _onglet_referentiels()
    with tabs[2]:
        _onglet_a_propos()
    with tabs[3]:
        _onglet_faq()


# ===== ONGLET 1 — Guide d'utilisation =====
def _onglet_guide() -> None:
    st.subheader("A. Comment ça marche en 4 étapes")
    st.markdown(
        """
1. Le **prescripteur** saisit sa demande via le module Prescripteur.
2. Le **CDSS** calcule automatiquement le score AUC (1-9).
3. Si **Rarely Appropriate** : alerte ALARA + possibilité de forçage justifié.
4. Le **médecin nucléaire** trie et valide via son tableau de bord.
"""
    )

    st.divider()
    st.subheader("B. Pour les prescripteurs — pas à pas")
    st.markdown(
        """
1. Cliquer sur **Prescripteur** dans le menu latéral.
2. Renseigner l'identification patient (anonymisée).
3. Choisir le contexte clinique parmi 4 grandes catégories.
4. Répondre au mini-questionnaire ciblé.
5. Consulter le résultat : score AUC + classification (A / MBA / RA).
6. Si **Rarely Appropriate** : lire attentivement l'alerte ALARA.
7. Soit annuler (recommandé), soit forcer avec justification.
8. Soumettre la demande.
"""
    )

    st.divider()
    st.subheader("C. Pour les médecins nucléaires — pas à pas")
    st.markdown(
        """
1. Cliquer sur **Médecin Nucléaire** dans le menu latéral.
2. Consulter le tableau de bord trié par classification.
3. Déplier chaque demande pour voir les détails.
4. Actions possibles : **Valider** / **Rejeter** (avec motif) / **Reclasser**.
5. Le temps de validation est automatiquement chronométré.
6. Exporter en CSV si besoin pour analyse externe.
"""
    )

    st.divider()
    st.subheader("D. Comprendre les classifications AUC")

    col_a, col_mba, col_ra = st.columns(3)
    with col_a:
        st.markdown(
            """
<div style='background-color:#d4edda; padding:18px; border-radius:8px;
            border-left:5px solid #28a745; height:100%;'>
  <h4 style='color:#155724; margin-top:0;'>🟢 APPROPRIATE</h4>
  <p style='color:#155724; margin:0;'><strong>Score 7-9</strong></p>
  <p style='color:#155724;'>L'examen est généralement justifié.
     Bénéfice attendu &gt; risques. Réaliser selon protocole standard.</p>
</div>
""",
            unsafe_allow_html=True,
        )
    with col_mba:
        st.markdown(
            """
<div style='background-color:#fff3cd; padding:18px; border-radius:8px;
            border-left:5px solid #ffc107; height:100%;'>
  <h4 style='color:#856404; margin-top:0;'>🟡 MAY BE APPROPRIATE</h4>
  <p style='color:#856404; margin:0;'><strong>Score 4-6</strong></p>
  <p style='color:#856404;'>Indication discutable. À pondérer selon contexte
     clinique individuel. Discuter au cas par cas avec le médecin nucléaire.</p>
</div>
""",
            unsafe_allow_html=True,
        )
    with col_ra:
        st.markdown(
            """
<div style='background-color:#f8d7da; padding:18px; border-radius:8px;
            border-left:5px solid #dc3545; height:100%;'>
  <h4 style='color:#721c24; margin-top:0;'>🔴 RARELY APPROPRIATE</h4>
  <p style='color:#721c24; margin:0;'><strong>Score 1-3</strong></p>
  <p style='color:#721c24;'>Indication non justifiée selon les critères AUC.
     Privilégier une alternative ou la surveillance clinique.</p>
</div>
""",
            unsafe_allow_html=True,
        )


# ===== ONGLET 2 — Référentiels & Méthodologie =====
def _onglet_referentiels() -> None:
    st.subheader("A. Référentiels utilisés (double évaluation AUC + ESC)")
    refs = pd.DataFrame([
        {
            "Référentiel": "AUC SPECT-MPI dédiée",
            "Année": "2009",
            "Auteurs": "Hendel RC et al.",
            "Journal": "JACC 2009;53(23):2201-2229",
            "Utilisation": "Référentiel AUC principal (42 scénarios)",
        },
        {
            "Référentiel": "AUC préopératoire chirurgie non cardiaque",
            "Année": "2024",
            "Auteurs": "Doherty JU et al.",
            "Journal": "JACC 2024;84(15):1455-1491",
            "Utilisation": "AUC catégorie C préopératoire (8 scénarios)",
        },
        {
            "Référentiel": "ESC Syndromes Coronariens Chroniques",
            "Année": "2024",
            "Auteurs": "Vrints C et al.",
            "Journal": "Eur Heart J 2024;45(36):3415-3537",
            "Utilisation": "Conformité ESC (catégories A, B, D-H)",
        },
        {
            "Référentiel": "ESC Chirurgie non cardiaque",
            "Année": "2022",
            "Auteurs": "Halvorsen S et al.",
            "Journal": "Eur Heart J 2022;43(39):3826-3924",
            "Utilisation": "Conformité ESC préopératoire (catégorie C)",
        },
        {
            "Référentiel": "Modèle RF-CL (probabilité pré-test)",
            "Année": "2020",
            "Auteurs": "Winther S et al.",
            "Journal": "JACC 2020;76(21):2421-2432",
            "Utilisation": "PPT principale (classe I ESC 2024, sans CAC)",
        },
    ])
    st.table(refs)

    st.divider()
    st.subheader("B. Justification du choix méthodologique : double évaluation")
    st.markdown(
        """
Ce travail repose sur une **double évaluation parallèle**, inspirée de l'approche
de Liga & Gimelli (2024) :

- **Versant AUC (ACCF/ASNC)** : seul référentiel international proposant une
  **cotation 1-9 par scénario clinique**, conçue pour évaluer la conformité des
  prescriptions d'imagerie. C'est le référentiel des études fondatrices (Doukky
  2013, FOCUS, Gibbons), garantissant la **comparabilité internationale**.
- **Versant ESC** : les recommandations européennes (classes I, IIa, IIb, III)
  constituent la référence des **cardiologues prescripteurs** locaux. Évaluer la
  conformité ESC ancre l'audit dans leur pratique réelle.

L'AUC 2009 est retenue plutôt que l'AUC 2023 multimodale car elle est
**spécifiquement dédiée à l'imagerie radio-isotopique au 99mTc** et ne dépend
pas de modalités absentes au CHU Bab El Oued (CAC, coro-TDM, IRM).
"""
    )

    st.divider()
    st.subheader("C. Calcul de la probabilité pré-test (PPT)")
    st.markdown(
        """
La PPT est calculée selon le **modèle RF-CL ESC 2024** (Risk Factor-weighted
Clinical Likelihood, Winther 2020), recommandé en **classe I (niveau B)** par
les guidelines ESC 2024. Il s'agit de la **version clinique pure sans score
calcique** (le CAC n'étant pas disponible au CHU Bab El Oued) : la probabilité
est pondérée par l'âge, le sexe, le type de symptôme et le nombre de facteurs
de risque (HTA, diabète, dyslipidémie, tabac, antécédents familiaux).

En l'absence d'informations suffisantes, le système bascule sur la table
**Diamond-Forrester modifiée ESC 2019** (fallback). Stratification opérationnelle
en trois catégories : **≤ 15 % (Faible)**, **16-50 % (Intermédiaire)**,
**> 50 % (Élevée)**.
"""
    )

    st.divider()
    st.subheader("D. Bibliographie principale")
    st.markdown(
        """
1. **Hendel RC et al.** ACCF/ASNC/ACR/AHA/ASE/SCCT/SCMR/SNM 2009 Appropriate
   Use Criteria for Cardiac Radionuclide Imaging. *J Am Coll Cardiol.*
   2009;53(23):2201-2229.
2. **Doherty JU et al.** ACC/AHA/ASNC/HRS/SCAI/SCCT/SCMR/STS 2024 Appropriate
   Use Criteria for Multimodality Imaging in Cardiovascular Evaluation of
   Patients Undergoing Noncardiac Surgery. *J Am Coll Cardiol.*
   2024;84(15):1455-1491.
3. **Vrints C et al.** 2024 ESC Guidelines for the management of chronic
   coronary syndromes. *Eur Heart J.* 2024;45(36):3415-3537.
4. **Halvorsen S et al.** 2022 ESC Guidelines on cardiovascular assessment and
   management of patients undergoing non-cardiac surgery. *Eur Heart J.*
   2022;43(39):3826-3924.
5. **Winther S et al.** Incorporating Coronary Calcification Into Pre-Test
   Assessment of the Likelihood of Coronary Artery Disease. *J Am Coll Cardiol.*
   2020;76(21):2421-2432.
6. **Liga R, Gimelli A.** Impact of appropriateness in clinical practice. *Eur
   Heart J Imaging Methods Pract.* 2024;2(1):qyad036.
7. **Doukky R et al.** Impact of Appropriate Use on the Prognostic Value of
   SPECT MPI. *Circulation* 2013;128(15):1634-1643.
8. **Duvall WL et al.** FOCUS: Formation of Optimal Cardiovascular Utilization
   Strategies. *JACC Cardiovasc Imaging* 2013;6(3):297-309.
9. **ICRP Publication 128.** Radiation Dose to Patients from
   Radiopharmaceuticals. *Ann ICRP* 2015;44(2S).
"""
    )


# ===== ONGLET 3 — À propos de l'étude =====
def _onglet_a_propos() -> None:
    st.subheader("A. Contexte")
    st.markdown(
        """
Ce CDSS est développé dans le cadre du mémoire de fin d'études spécialisées
en Médecine Nucléaire de **Dr. Babatoundé Fréjuste Pinocio AGBOTON**,
intitulé :

> *« Audit de la conformité des prescriptions de tomoscintigraphie
> myocardique de perfusion aux critères d'utilisation appropriée et
> conception d'un système informatisé d'aide à la prescription (CDSS). »*
"""
    )

    st.divider()
    st.subheader("B. Auteur et encadrement")
    auteurs = pd.DataFrame([
        {"Rôle": "Auteur",
         "Nom": "Dr. Babatoundé Fréjuste Pinocio AGBOTON",
         "Affiliation": "Résident en Médecine Nucléaire"},
        {"Rôle": "Encadrement",
         "Nom": "Dr. LAMALI",
         "Affiliation": "Service de Médecine Nucléaire"},
        {"Rôle": "Service",
         "Nom": "Médecine Nucléaire",
         "Affiliation": "CHU Mohamed Lamine Debaghine (Bab El Oued)"},
        {"Rôle": "Année universitaire",
         "Nom": "2025-2026",
         "Affiliation": "Alger, Algérie"},
    ])
    st.table(auteurs)

    st.divider()
    st.subheader("C. Objectifs de l'étude")
    st.markdown(
        """
**Objectif principal**
- Auditer la conformité des prescriptions de TMP selon une **double évaluation
  AUC ACCF/ASNC + ESC**, et concevoir un CDSS d'aide à la prescription.

**Objectifs secondaires**
- Audit clinique rétrospectif des prescriptions actuelles.
- Mesure de la concordance entre les référentiels AUC et ESC (kappa de Cohen).
- Estimation de la dose efficace évitable (radioprotection).
- Validation technique du CDSS (concordance avec l'évaluation humaine experte).
"""
    )

    st.divider()
    st.subheader("D. Structure de l'étude")
    phases = pd.DataFrame([
        {"Volet": "Volet 1 — Audit",
         "Description": "Audit rétrospectif — double évaluation AUC + ESC en aveugle",
         "Statut": "En cours"},
        {"Volet": "Volet 2 — CDSS",
         "Description": "Conception, développement et validation technique du CDSS",
         "Statut": "✅ Réalisé"},
        {"Volet": "Perspective",
         "Description": "Étude prospective post-déploiement (perspective post-DES)",
         "Statut": "À venir"},
    ])
    st.table(phases)

    st.divider()
    st.subheader("E. Avertissement")
    st.error(
        "⚠️ **AVERTISSEMENT** : Cet outil est un instrument de recherche "
        "académique. Il ne se substitue **PAS** au jugement clinique du "
        "médecin responsable. La décision finale de réaliser ou non l'examen "
        "incombe toujours au médecin nucléaire validateur, conformément au "
        "principe de responsabilité médicale. Les données saisies sont "
        "strictement anonymisées."
    )


# ===== ONGLET 4 — FAQ =====
def _onglet_faq() -> None:
    faq = [
        (
            "Que faire si je suis en désaccord avec le score AUC calculé ?",
            """Le score AUC est calculé automatiquement selon les critères
ACCF/ASNC (AUC 2009 pour la SPECT-MPI, AUC 2024 pour le préopératoire). Si vous
estimez que la classification ne reflète pas la réalité
clinique du patient, deux options existent :

1. **Côté Prescripteur** : utiliser le bouton « Forcer malgré l'alerte » avec
   justification clinique détaillée.
2. **Côté Médecin Nucléaire** : utiliser le bouton « Reclasser » avec
   commentaire motivé.

Tous les forçages et reclassements sont tracés pour analyse statistique.""",
        ),
        (
            "Comment est calculée la probabilité pré-test (PPT) ?",
            """La PPT est calculée automatiquement selon le **modèle RF-CL ESC
2024** (Risk Factor-weighted Clinical Likelihood), version clinique sans score
calcique, basée sur l'âge, le sexe, le type de symptômes et le nombre de
facteurs de risque cardiovasculaires. En cas d'informations manquantes, le
système bascule sur la table Diamond-Forrester modifiée ESC 2019. Les seuils
opérationnels sont : **≤ 15 % (Faible)**, **16-50 % (Intermédiaire)**,
**> 50 % (Élevée)**.""",
        ),
        (
            "Que signifie « May Be Appropriate » (orange) ?",
            """Score AUC 4-6. L'indication n'est ni clairement justifiée, ni
clairement inappropriée. C'est une zone grise où le jugement clinique
individuel prime sur les recommandations générales. Discussion conseillée
entre prescripteur et médecin nucléaire.""",
        ),
        (
            "Les données patients sont-elles sécurisées ?",
            """Toutes les données sont strictement anonymisées avant saisie.
Aucune donnée nominative n'est conservée. Le numéro patient est généré
automatiquement (format `CDSS-YYYY-XXXX`). Les exports respectent les
principes de l'anonymisation par défaut.""",
        ),
        (
            "Puis-je utiliser ce CDSS dans mon propre service ?",
            """L'outil est actuellement en phase d'évaluation académique au
CHU Mohamed Lamine Debaghine. Pour toute demande d'utilisation externe,
contactez l'auteur. Le code source pourra être partagé sous licence
académique après soutenance du mémoire.""",
        ),
        (
            "Comment signaler un bug ou suggérer une amélioration ?",
            """Contactez l'auteur directement, ou si vous êtes utilisateur du
CHU, remontez via votre référent de service.""",
        ),
    ]

    for i, (q, r) in enumerate(faq, start=1):
        with st.expander(f"**Q{i}. {q}**"):
            st.markdown(r)
