# CDSS-TMP — Système d'aide à la prescription de tomoscintigraphie myocardique de perfusion

**Auteur** : Dr. Babatoundé Fréjuste Pinocio AGBOTON
**Affiliation** : Service de Médecine Nucléaire, CHU Mohamed Lamine Debaghine (Bab El Oued)
**Année académique** : 2025-2026

## Description

Système d'aide à la décision clinique (CDSS) destiné à évaluer la pertinence des
prescriptions de tomoscintigraphie myocardique de perfusion (TMP). L'application
confronte chaque demande à 50 scénarios cliniques issus des recommandations
internationales et restitue une classification d'appropriateness (Appropriate /
May Be Appropriate / Rarely Appropriate) accompagnée d'une alerte ALARA en cas
d'indication non justifiée. Développé dans le cadre d'un mémoire de fin d'études
en médecine nucléaire.

## Référentiels utilisés

- **AUC 2023** — Winchester DE et al. *JACC* 2023 — Multimodality Appropriate Use
  Criteria for the detection and risk assessment of stable ischemic heart disease.
- **AUC 2009 SPECT-MPI** — Hendel RC et al. *JACC* 2009 — Appropriate Use Criteria
  for Cardiac Radionuclide Imaging.

## Stack technique

- **Python 3.12**
- **Streamlit** — interface web
- **SQLite** — persistance locale
- **pandas / scipy / scikit-learn** — analyse statistique
- **plotly** — visualisations interactives

## Lancement local

```bash
# Cloner le dépôt
git clone <URL_DU_REPO>
cd cdss-tmp

# Créer l'environnement virtuel
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
# ou : source venv/bin/activate  # Linux / macOS

# Installer les dépendances
pip install -r requirements.txt

# Lancer l'application
streamlit run app.py
```

L'application est accessible sur http://localhost:8501. La base SQLite et les
50 scénarios sont créés automatiquement au premier démarrage via `init_app.py`.

## Modules

- **Référentiel** — consultation et recherche dans les 50 scénarios AUC
- **Prescripteur** — wizard en 5 étapes pour la saisie d'une demande de TMP
- **Médecin Nucléaire** — tri, validation, rejet et reclassement des demandes
- **Chercheur** — tableau de bord analytique, tests statistiques (χ², Fisher,
  Wald, Mann-Whitney, κ de Cohen) et exports (Excel multi-feuilles, CSV, HTML)

## Avertissement

> Outil de recherche académique. Ne se substitue pas au jugement clinique du
> médecin responsable.
