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
    st.subheader("A. Référentiels utilisés")
    refs = pd.DataFrame([
        {
            "Référentiel": "AUC Multimodalité Chronic Coronary Disease",
            "Année": "2023",
            "Auteurs": "Winchester DE et al.",
            "Journal": "JACC 2023",
            "Utilisation": "Référentiel principal actualisé",
        },
        {
            "Référentiel": "AUC SPECT-MPI dédiée",
            "Année": "2009",
            "Auteurs": "Hendel RC et al.",
            "Journal": "JACC 2009;53(25):2201-2229",
            "Utilisation": "Granularité spécifique TMP",
        },
        {
            "Référentiel": "AUC Multimodalité Stable Ischemic HD",
            "Année": "2013",
            "Auteurs": "Wolk MJ et al.",
            "Journal": "JACC 2014;63(4):380-406",
            "Utilisation": "Référentiel intermédiaire",
        },
    ])
    st.table(refs)

    st.divider()
    st.subheader("B. Justification du choix méthodologique")
    st.markdown(
        """
Le choix d'un référentiel américain (ACCF/ASNC) plutôt qu'européen (ESC) ou
français est **méthodologique, non géographique**. Les recommandations ESC sont
structurées en classes (I, IIa, IIb, III) et niveaux de preuve (A, B, C) :
elles guident la décision clinique mais ne fournissent pas d'outil de scoring
de l'appropriateness des prescriptions. À l'inverse, les AUC ACCF/ASNC sont
le seul référentiel international proposant une **cotation 1-9 par scénario
clinique** spécifiquement conçue pour évaluer la conformité des prescriptions
d'imagerie — ce qui est précisément l'objet de cette étude. C'est aussi le
référentiel utilisé par les études fondatrices du domaine (Doukky 2013,
FOCUS, Gibbons), garantissant la comparabilité des résultats.
"""
    )

    st.divider()
    st.subheader("C. Calcul de la probabilité pré-test (PPT)")
    st.markdown(
        """
La PPT est calculée selon la table de **Diamond-Forrester modifiée
recommandée par l'ESC 2019**, avec stratification opérationnelle en trois
catégories : **≤ 15 % (Faible)**, **16-50 % (Intermédiaire)**, **> 50 %
(Élevée)**. Ces seuils sont adaptés à la déflation des PPT observée dans
cette version par rapport à la table originale Diamond-Forrester 1979.
"""
    )

    st.divider()
    st.subheader("D. Bibliographie principale")
    st.markdown(
        """
1. **Winchester DE et al.** ACC/AHA/ASE/ASNC/ASPC/HFSA/HRS/SCAI/SCCT/SCMR/STS
   2023 Multimodality Appropriate Use Criteria for the Detection and Risk
   Assessment of Chronic Coronary Disease. *JACC* 2023.
2. **Hendel RC et al.** ACCF/ASNC/ACR/AHA/ASE/SCCT/SCMR/SNM 2009 Appropriate
   Use Criteria for Cardiac Radionuclide Imaging. *J Am Coll Cardiol.*
   2009;53(25):2201-2229.
3. **Doukky R et al.** Impact of Appropriate Use on the Prognostic Value of
   SPECT MPI. *Circulation* 2013;128(15):1634-1643.
4. **Duvall WL et al.** FOCUS: Formation of Optimal Cardiovascular Utilization
   Strategies. *JACC Cardiovasc Imaging* 2013;6(3):297-309.
5. **ICRP Publication 128.** Radiation Dose to Patients from
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

> *« Évaluation de l'impact d'un Système Informatisé d'Aide à la
> Prescription sur la conformité des demandes de tomoscintigraphie
> myocardique de perfusion aux critères d'utilisation appropriée. »*
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
- Évaluer l'impact du CDSS sur le taux de conformité des demandes de TMP aux
  AUC ACCF/ASNC.

**Objectifs secondaires**
- Audit clinique des prescriptions actuelles (Phase 1).
- Estimation de la dose efficace évitée (radioprotection).
- Comparaison du temps de validation médicale avant/après.
- Évaluation de l'acceptabilité par les prescripteurs.
"""
    )

    st.divider()
    st.subheader("D. Phases de l'étude")
    phases = pd.DataFrame([
        {"Phase": "Phase 1",
         "Description": "Audit rétrospectif — double évaluation en aveugle",
         "Durée": "2-3 mois",
         "Statut": "En cours"},
        {"Phase": "Phase 2",
         "Description": "Développement du CDSS",
         "Durée": "2-3 mois",
         "Statut": "✅ Terminé"},
        {"Phase": "Phase 3",
         "Description": "Étude prospective post-déploiement",
         "Durée": "3 mois",
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
ACCF/ASNC 2023. Si vous estimez que la classification ne reflète pas la réalité
clinique du patient, deux options existent :

1. **Côté Prescripteur** : utiliser le bouton « Forcer malgré l'alerte » avec
   justification clinique détaillée.
2. **Côté Médecin Nucléaire** : utiliser le bouton « Reclasser » avec
   commentaire motivé.

Tous les forçages et reclassements sont tracés pour analyse statistique.""",
        ),
        (
            "Comment est calculée la probabilité pré-test (PPT) ?",
            """La PPT est calculée automatiquement selon la table
Diamond-Forrester modifiée ESC 2019, basée sur l'âge, le sexe et le type de
symptômes (typique, atypique, douleur non angineuse, dyspnée). Les seuils
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
