"""
Insertion des 50 scénarios AUC dans la base SQLite cdss_tmp.db
Référentiels : AUC 2023 (Winchester JACC) + AUC 2009 SPECT-MPI (Hendel JACC)
Auteur : Dr. F. AGBOTON - CHU Mohamed Lamine Debaghine
"""

from database import get_connection, init_db

SCENARIOS = [
    # ===== A. DÉTECTION CAD - PATIENT SYMPTOMATIQUE =====
    ("S001", "A. Détection CAD - Patient symptomatique", "Douleur thoracique non aiguë / équivalent angineux - Probabilité pré-test FAIBLE - ECG interprétable - Capable d'effort", "Symptômes : Oui | PPT : Faible (<15%) | ECG interprétable : Oui | Capable d'effort : Oui", 3, "RA", "AUC 2023 / AUC 2009", "L'épreuve d'effort sur tapis SANS imagerie est suffisante. Imagerie non justifiée."),
    ("S002", "A. Détection CAD - Patient symptomatique", "Douleur thoracique non aiguë - Probabilité pré-test FAIBLE - ECG NON interprétable OU Incapable d'effort", "Symptômes : Oui | PPT : Faible | ECG ininterprétable OU incapacité d'effort", 7, "A", "AUC 2023 / AUC 2009", "Imagerie de stress justifiée car épreuve d'effort simple inadaptée."),
    ("S003", "A. Détection CAD - Patient symptomatique", "Douleur thoracique non aiguë - Probabilité pré-test INTERMÉDIAIRE - ECG interprétable - Capable d'effort", "Symptômes : Oui | PPT : Intermédiaire (15-85%) | ECG interprétable : Oui | Capable d'effort : Oui", 7, "A", "AUC 2023 / AUC 2009", "Indication phare. TMP d'effort recommandée."),
    ("S004", "A. Détection CAD - Patient symptomatique", "Douleur thoracique non aiguë - Probabilité pré-test INTERMÉDIAIRE - ECG NON interprétable OU Incapable d'effort", "Symptômes : Oui | PPT : Intermédiaire | ECG ininterprétable OU incapacité d'effort", 9, "A", "AUC 2023 / AUC 2009", "Indication forte. TMP avec stress pharmacologique (Dipyridamole / Adénosine / Régadénoson)."),
    ("S005", "A. Détection CAD - Patient symptomatique", "Douleur thoracique non aiguë - Probabilité pré-test ÉLEVÉE - ECG interprétable - Capable d'effort", "Symptômes : Oui | PPT : Élevée (>85%) | ECG interprétable : Oui | Capable d'effort : Oui", 7, "A", "AUC 2023 / AUC 2009", "TMP justifiée pour stratification du risque et localisation de l'ischémie."),
    ("S006", "A. Détection CAD - Patient symptomatique", "Douleur thoracique non aiguë - Probabilité pré-test ÉLEVÉE - ECG NON interprétable OU Incapable d'effort", "Symptômes : Oui | PPT : Élevée | ECG ininterprétable OU incapacité d'effort", 8, "A", "AUC 2023 / AUC 2009", "Forte indication. Discuter aussi la coronarographie directe selon profil."),
    ("S007", "A. Détection CAD - Patient symptomatique", "Suspicion d'angor vasospastique (Prinzmetal) - ECG normal de repos", "Symptômes : Oui (atypiques au repos) | Angor vasospastique suspecté", 4, "MBA", "AUC 2009", "Utilité limitée hors crise. Préférer Holter ECG / test à l'ergonovine."),
    ("S008", "A. Détection CAD - Patient symptomatique", "Douleur thoracique aiguë - SCA exclu - troponines négatives - ECG normal - Stratification ambulatoire à distance", "Douleur aiguë RÉSOLUE | SCA écarté | Stratification à distance", 7, "A", "AUC 2023", "Évaluation ambulatoire à distance après écartement SCA aux urgences."),
    ("S009", "A. Détection CAD - Patient symptomatique", "Dyspnée d'effort isolée - Probabilité pré-test INTERMÉDIAIRE de CAD - ECG ininterprétable", "Symptômes : Dyspnée d'effort | PPT : Intermédiaire | ECG ininterprétable", 7, "A", "AUC 2023 / AUC 2009", "La dyspnée d'effort peut être un équivalent angineux."),
    ("S010", "A. Détection CAD - Patient symptomatique", "Syncope d'effort sans cause évidente - Suspicion d'origine ischémique", "Syncope d'effort | Bilan cardiologique initial normal", 6, "MBA", "AUC 2009", "Indication discutable. Echocardiographie d'effort souvent préférée."),

    # ===== B. PATIENT ASYMPTOMATIQUE - DÉPISTAGE =====
    ("S011", "B. Patient asymptomatique - Dépistage", "Patient asymptomatique - Risque CV global FAIBLE (SCORE/Framingham)", "Symptômes : Non | Risque CV : Faible | Aucun FDR majeur", 1, "RA", "AUC 2023 / AUC 2009", "Dépistage non recommandé. Aucun bénéfice démontré."),
    ("S012", "B. Patient asymptomatique - Dépistage", "Patient asymptomatique - Risque CV global INTERMÉDIAIRE", "Symptômes : Non | Risque CV : Intermédiaire | Pas de diabète", 3, "RA", "AUC 2023 / AUC 2009", "Pas de bénéfice prouvé. Privilégier score calcique coronaire si stratification utile."),
    ("S013", "B. Patient asymptomatique - Dépistage", "Patient asymptomatique - Risque CV global ÉLEVÉ (incluant diabétique sans symptômes)", "Symptômes : Non | Risque CV : Élevé | OU Diabète asymptomatique", 5, "MBA", "AUC 2023", "Discutable. Études DIAD et BARI-2D : pas de bénéfice systématique chez diabétique asymptomatique."),
    ("S014", "B. Patient asymptomatique - Dépistage", "Patient asymptomatique - ECG anormal de repos isolé (anomalies ST/T non spécifiques)", "Symptômes : Non | ECG repos anormal isolé", 4, "MBA", "AUC 2009", "Selon nature des anomalies et contexte clinique."),
    ("S015", "B. Patient asymptomatique - Dépistage", "Patient asymptomatique - Score calcique coronaire (CAC) très élevé > 400", "Symptômes : Non | CAC > 400 Agatston", 6, "MBA", "AUC 2023", "Recherche d'ischémie silencieuse possible mais non systématique."),
    ("S016", "B. Patient asymptomatique - Dépistage", "Patient asymptomatique - Score calcique coronaire (CAC) 100-400", "Symptômes : Non | CAC 100-400 Agatston", 4, "MBA", "AUC 2023", "Stratification par TMP discutable, à individualiser."),
    ("S017", "B. Patient asymptomatique - Dépistage", "Patient asymptomatique - Athérosclérose extracardiaque connue (carotidienne, périphérique)", "Symptômes : Non | Maladie athéromateuse extracardiaque", 5, "MBA", "AUC 2009", "Patient considéré à risque équivalent CAD. Discussion au cas par cas."),
    ("S018", "B. Patient asymptomatique - Dépistage", "Patient asymptomatique avant initiation d'un programme d'activité physique INTENSE - Risque CV faible/intermédiaire", "Symptômes : Non | Activité physique intense planifiée | Risque CV faible-intermédiaire", 3, "RA", "AUC 2009", "Test d'effort sans imagerie suffisant si nécessaire."),

    # ===== C. BILAN PRÉOPÉRATOIRE =====
    ("S019", "C. Bilan préopératoire", "Chirurgie non cardiaque à risque FAIBLE - Patient asymptomatique", "Chirurgie : Risque faible (cataracte, endoscopie...) | Asymptomatique", 1, "RA", "AUC 2023 / AUC 2009", "Aucune indication. Recommandations ESC/AHA convergentes."),
    ("S020", "C. Bilan préopératoire", "Chirurgie non cardiaque à risque INTERMÉDIAIRE - Asymptomatique - Bonne capacité fonctionnelle (METs >= 4)", "Chirurgie : Risque intermédiaire | Asymptomatique | METs >= 4 | Sans FDR actif", 2, "RA", "AUC 2023", "Capacité fonctionnelle suffisante = pas d'indication d'imagerie."),
    ("S021", "C. Bilan préopératoire", "Chirurgie non cardiaque à risque INTERMÉDIAIRE - Asymptomatique - Capacité fonctionnelle INCONNUE ou < 4 METs - >= 1 FDR clinique (RCRI)", "Chirurgie : Risque intermédiaire | METs < 4 ou inconnu | >= 1 critère RCRI", 6, "MBA", "AUC 2023", "Sera utile si modifie la prise en charge. À discuter au cas par cas."),
    ("S022", "C. Bilan préopératoire", "Chirurgie non cardiaque à HAUT RISQUE (vasculaire majeure) - Capacité fonctionnelle réduite (< 4 METs)", "Chirurgie : Haut risque (vasculaire) | METs < 4 | >= 1 critère RCRI", 8, "A", "AUC 2023 / AUC 2009", "Indication classique. Modifie souvent la stratégie péri-opératoire."),
    ("S023", "C. Bilan préopératoire", "Chirurgie non cardiaque à HAUT RISQUE - Asymptomatique - Bonne capacité fonctionnelle (METs >= 4)", "Chirurgie : Haut risque | Asymptomatique | METs >= 4", 3, "RA", "AUC 2023", "Bonne tolérance fonctionnelle = pas d'indication même en chirurgie à haut risque."),
    ("S024", "C. Bilan préopératoire", "Transplantation rénale - Bilan pré-greffe chez patient diabétique ou avec FDR", "Pré-transplantation rénale | Diabète OU >= 2 FDR", 7, "A", "AUC 2009", "Pratique courante validée. Détection ischémie silencieuse."),
    ("S025", "C. Bilan préopératoire", "Bilan avant chirurgie cardiaque valvulaire - Évaluation coronarienne associée", "Chirurgie cardiaque valvulaire | Bilan coronarien", 4, "MBA", "AUC 2009", "Coronarographie habituellement préférée. TMP possible si CI à coronarographie."),
    ("S026", "C. Bilan préopératoire", "Bilan préopératoire moins de 1 mois après une coronarographie/TMP normale", "Examen normal récent (< 1 mois) | Pas de nouveau symptôme", 1, "RA", "AUC 2009", "Aucune indication. Redondance d'examen."),

    # ===== D. POST-REVASCULARISATION ASYMPTOMATIQUE =====
    ("S027", "D. Post-revascularisation asymptomatique", "Post-PCI (angioplastie) - Asymptomatique - < 2 ans après la procédure", "Post-PCI | Asymptomatique | Délai < 2 ans", 2, "RA", "AUC 2023 / AUC 2009", "Indication piège fréquente. Surveillance clinique suffit."),
    ("S028", "D. Post-revascularisation asymptomatique", "Post-PCI - Asymptomatique - >= 2 ans après la procédure", "Post-PCI | Asymptomatique | Délai >= 2 ans", 4, "MBA", "AUC 2023", "Surveillance pouvant être discutée. À pondérer selon complexité de la PCI."),
    ("S029", "D. Post-revascularisation asymptomatique", "Post-PCI de tronc commun OU lésion proximale IVA - Asymptomatique - Délai 6-12 mois", "Post-PCI haut risque (tronc commun / IVA proximale) | Asymptomatique | 6-12 mois", 6, "MBA", "AUC 2023", "Surveillance acceptable pour stent à risque élevé."),
    ("S030", "D. Post-revascularisation asymptomatique", "Post-CABG (pontage) - Asymptomatique - < 5 ans après la chirurgie", "Post-CABG | Asymptomatique | Délai < 5 ans", 3, "RA", "AUC 2023 / AUC 2009", "Surveillance clinique suffisante."),
    ("S031", "D. Post-revascularisation asymptomatique", "Post-CABG - Asymptomatique - >= 5 ans après la chirurgie", "Post-CABG | Asymptomatique | Délai >= 5 ans", 6, "MBA", "AUC 2023", "Risque accru de dysfonction des pontages veineux. TMP envisageable."),

    # ===== E. POST-REVASCULARISATION SYMPTOMATIQUE =====
    ("S032", "E. Post-revascularisation symptomatique", "Post-PCI - Symptômes récidivants (angor, dyspnée) - Quelque délai", "Post-PCI | Symptômes récidivants", 9, "A", "AUC 2023 / AUC 2009", "Indication forte. Recherche de resténose ou progression de la maladie."),
    ("S033", "E. Post-revascularisation symptomatique", "Post-CABG - Symptômes récidivants", "Post-CABG | Symptômes récidivants", 8, "A", "AUC 2023 / AUC 2009", "Recherche de dysfonction des greffons ou progression sur natifs."),
    ("S034", "E. Post-revascularisation symptomatique", "Post-revascularisation - Test d'effort anormal ou non concluant en suivi", "Post-revascularisation | Test d'effort anormal/équivoque", 8, "A", "AUC 2023", "Complément d'imagerie justifié."),
    ("S035", "E. Post-revascularisation symptomatique", "Post-PCI - Élévation des biomarqueurs cardiaques à distance sans contexte aigu", "Post-PCI | Élévation troponine à distance", 7, "A", "AUC 2009", "Recherche d'ischémie silencieuse."),
    ("S036", "E. Post-revascularisation symptomatique", "Post-revascularisation incomplète - Stratification du risque à distance", "Revascularisation incomplète documentée | Patient stable", 7, "A", "AUC 2009", "Évalue le retentissement fonctionnel des lésions non revascularisées."),

    # ===== F. POST-SCA / POST-IDM =====
    ("S037", "F. Post-syndrome coronarien aigu / post-IDM", "Post-IDM avec ST+ traité par angioplastie primaire - Coronarographie complète réalisée - Stratification pré-sortie", "STEMI traité | Coronarographie complète | Avant sortie", 3, "RA", "AUC 2009", "Anatomie déjà connue. TMP redondante sauf doute sur viabilité."),
    ("S038", "F. Post-syndrome coronarien aigu / post-IDM", "Post-IDM non revascularisé (thrombolyse seule ou non revascularisation) - Stratification du risque", "IDM non revascularisé | Stratification pré-sortie ou post-sortie précoce", 8, "A", "AUC 2009", "Indication forte. Recherche d'ischémie résiduelle."),
    ("S039", "F. Post-syndrome coronarien aigu / post-IDM", "Post-SCA non ST+ traité - Évaluation à distance (3-6 mois)", "Post-NSTEMI/SCA ST- traité | Évaluation à distance", 5, "MBA", "AUC 2009", "Selon revascularisation complète ou non."),
    ("S040", "F. Post-syndrome coronarien aigu / post-IDM", "Post-IDM - Recherche de viabilité myocardique (segments akinétiques)", "Post-IDM | FEVG abaissée | Segments akinétiques | Question viabilité", 7, "A", "AUC 2009", "Protocoles spécifiques (Thallium repos-redistribution ou TEP FDG)."),
    ("S041", "F. Post-syndrome coronarien aigu / post-IDM", "Patient stabilisé après SCA - Aucun symptôme nouveau - 1 mois après revascularisation complète", "Post-SCA revascularisé complet | Asymptomatique | 1 mois", 2, "RA", "AUC 2023", "Examen précoce non utile en l'absence de symptômes."),

    # ===== G. CAD CONNUE - SUIVI =====
    ("S042", "G. CAD connue - Suivi", "CAD connue - Modification ou aggravation des symptômes", "CAD connue | Symptômes nouveaux ou aggravés", 9, "A", "AUC 2023 / AUC 2009", "Indication forte. Recherche de progression / nouvelle ischémie."),
    ("S043", "G. CAD connue - Suivi", "CAD connue - Asymptomatique - Suivi de routine sans événement", "CAD connue | Asymptomatique | Pas d'événement intercurrent", 3, "RA", "AUC 2023 / AUC 2009", "Surveillance d'imagerie systématique non recommandée."),
    ("S044", "G. CAD connue - Suivi", "Sténose connue de gravité intermédiaire (40-70%) - Évaluation du retentissement ischémique", "Sténose intermédiaire 40-70% (coronarographie ou angio-TDM)", 8, "A", "AUC 2023 / AUC 2009", "Recherche d'ischémie pour guider revascularisation (concept FFR-équivalent fonctionnel)."),
    ("S045", "G. CAD connue - Suivi", "Coronarographie ancienne (> 2 ans) sans lésion significative - Patient asymptomatique", "Coro ancienne normale ou non significative | Asymptomatique", 2, "RA", "AUC 2009", "Pas d'indication. Réévaluer si nouveaux symptômes."),
    ("S046", "G. CAD connue - Suivi", "CAD connue - Évaluation avant changement majeur thérapeutique (escalade médicamenteuse vs revascularisation)", "CAD connue | Décision thérapeutique en attente | Apport diagnostique attendu", 6, "MBA", "AUC 2009", "À discuter en équipe (Heart Team)."),

    # ===== H. INSUFFISANCE CARDIAQUE / AUTRES =====
    ("S047", "H. Insuffisance cardiaque / autres indications", "Insuffisance cardiaque de novo - FEVG abaissée - Origine ischémique à déterminer", "IC nouvelle | FEVG < 50% | Étiologie inconnue", 8, "A", "AUC 2009", "Recherche d'origine ischémique. Alternative : coronarographie ou angio-TDM coronaire."),
    ("S048", "H. Insuffisance cardiaque / autres indications", "Cardiomyopathie connue (non ischémique documentée) - Suivi de routine", "CMP non ischémique documentée | Suivi stable", 2, "RA", "AUC 2009", "Aucune indication. IRM ou échographie préférées."),
    ("S049", "H. Insuffisance cardiaque / autres indications", "Évaluation de fibrillation auriculaire de novo - Recherche d'ischémie associée si suspicion clinique", "FA nouvelle | Symptômes évocateurs d'ischémie associés", 5, "MBA", "AUC 2009", "Selon contexte clinique. Pas systématique."),
    ("S050", "H. Insuffisance cardiaque / autres indications", "Demande de répétition d'examen < 12 mois après une TMP normale - Pas de nouveau symptôme", "TMP précédente normale | Délai < 12 mois | Pas de nouveau symptôme", 1, "RA", "AUC 2009", "Redondance d'examen. Irradiation évitable."),
]

def seed_scenarios():
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM scenarios_auc")
    cur.executemany(
        "INSERT INTO scenarios_auc (id, categorie, contexte_clinique, variables_cles, score_auc, classification, source, note_clinique) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        SCENARIOS
    )
    conn.commit()
    count = cur.execute("SELECT COUNT(*) FROM scenarios_auc").fetchone()[0]
    conn.close()
    print(f"Scénarios insérés : {count}")

if __name__ == "__main__":
    seed_scenarios()
