# Déploiement CDSS-TMP

## URL de production

**https://cdss-tmp.streamlit.app**

Hébergement : Streamlit Community Cloud (gratuit, lié au repo GitHub
[Frejustedev/cdss-tmp](https://github.com/Frejustedev/cdss-tmp)).

## Mise à jour du code

Streamlit Community Cloud **redéploie automatiquement** à chaque push sur la
branche `main`. Aucune action manuelle n'est requise.

```bash
# Depuis le dossier local CDSS-TMP/ :
git add <fichiers modifiés>           # ou git add . si tout est légitime
git commit -m "Description du changement"
git push
```

Temps typique de redéploiement : **1 à 3 minutes**, plus long si
`requirements.txt` change (recompilation des dépendances). Suivi en direct
sur [share.streamlit.io](https://share.streamlit.io) → *My apps* → *Logs*.

## ⚠ Persistance des données — la BDD SQLite est éphémère

Le conteneur Streamlit Cloud n'a **pas de disque persistant**. À chaque
redémarrage :

- La base `cdss_tmp.db` est recréée vide.
- Les 50 scénarios AUC sont réinjectés automatiquement par
  [`init_app.py`](init_app.py).
- **Les demandes saisies par les prescripteurs sont perdues.**

### Causes de redémarrage du conteneur

- Push de code sur `main` (redéploiement)
- Inactivité prolongée (> 7 jours → *sleep mode* Streamlit Cloud)
- Maintenance / mise à jour de la plateforme
- Modification des secrets ou variables d'environnement

## Procédure de sauvegarde recommandée

À effectuer **régulièrement** pendant les phases d'inclusion du mémoire :

1. Ouvrir https://cdss-tmp.streamlit.app
2. Module **Chercheur** → onglet **Exports**
3. Télécharger les 3 formats :
   - **Excel multi-feuilles** — backup officiel auditable
     (Demandes / Statistiques / Phase1_vs_Phase3 / Forcages)
   - **CSV brut** — pour analyses externes (R, SPSS, Python)
   - **HTML synthétique** — pour archivage des rapports périodiques
4. Conserver dans un dossier daté local : `backups/AAAA-MM-JJ/`

### Fréquence conseillée

| Contexte | Fréquence |
|---|---|
| Phase d'inclusion active (saisies quotidiennes) | Après chaque session significative |
| Phase de routine | Minimum 1 fois par semaine |
| Avant un redéploiement (push de code) | Systématique |
| Avant une absence prolongée (> 5 jours) | Systématique |

## Restauration de données depuis un export

La restauration n'est pas automatisée. Pour réinjecter des données archivées
en cas d'analyse longitudinale :

1. Récupérer l'export Excel ou CSV.
2. Écrire un script d'import ponctuel inspiré de [`seed_data.py`](seed_data.py)
   qui parcourt les lignes et fait `INSERT INTO demandes (...)`.
3. Exécuter en local sur la copie locale de la base, ou pousser le script
   pour une réinjection lors du prochain démarrage.

## Compte de service

- GitHub : [Frejustedev](https://github.com/Frejustedev)
- Streamlit Cloud : connecté via OAuth GitHub (compte `frejustedev`)
- Aucune clé API / secret nécessaire pour l'application telle qu'elle est
  (pas de SMS, pas d'envoi mail, pas d'auth externe).
