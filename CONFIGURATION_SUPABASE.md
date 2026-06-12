# Configuration de la base permanente Supabase — CDSS-TMP

Ce guide explique comment connecter ton CDSS à la base PostgreSQL **permanente**
hébergée sur Supabase (projet **ScintiFlow**, schéma `cdss`).

La base est déjà créée et contient les 50 scénarios AUC + ESC. Il te reste à
configurer la **chaîne de connexion** dans ton app, en local puis sur Streamlit
Cloud.

---

## 1. Récupérer ta chaîne de connexion Supabase

1. Va sur https://supabase.com/dashboard et ouvre le projet **ScintiFlow**.
2. Clique sur l'icône **Connect** (en haut) ou va dans **Project Settings → Database**.
3. Section **Connection string** → onglet **URI**.
4. Choisis le mode **Transaction pooler** (recommandé pour Streamlit Cloud, port 6543) ou **Session pooler** (port 5432).
5. Copie l'URI. Elle ressemble à :
   ```
   postgresql://postgres.zhvflbydddorvovjvkts:[YOUR-PASSWORD]@aws-0-eu-central-2.pooler.supabase.com:6543/postgres
   ```
6. Remplace `[YOUR-PASSWORD]` par le mot de passe de ta base (celui défini à la création du projet ScintiFlow ; si tu l'as oublié, tu peux le réinitialiser dans Project Settings → Database → Reset database password).

> ⚠️ Cette chaîne contient ton mot de passe : ne la mets JAMAIS dans le code ni sur GitHub. Elle va uniquement dans les secrets (voir ci-dessous).

---

## 2. Configuration en LOCAL (pour tester sur ton PC)

Crée un fichier `.streamlit/secrets.toml` dans ton dossier `CDSS-TMP` :

```toml
SUPABASE_DB_URL = "postgresql://postgres.zhvflbydddorvovjvkts:TON_MOT_DE_PASSE@aws-0-eu-central-2.pooler.supabase.com:6543/postgres"
```

**Important** : ajoute `.streamlit/secrets.toml` à ton `.gitignore` pour ne jamais le pousser sur GitHub. Vérifie que ton `.gitignore` contient :
```
.streamlit/secrets.toml
cdss_tmp.db
```

Alternative en local sans secrets.toml : définir une variable d'environnement
```bash
# Windows (PowerShell)
$env:SUPABASE_DB_URL="postgresql://..."
# puis : streamlit run app.py
```

---

## 3. Configuration sur STREAMLIT CLOUD (pour le déploiement)

1. Va sur https://share.streamlit.io et ouvre ton app CDSS.
2. Clique sur **Settings** (menu ⋮) → **Secrets**.
3. Colle exactement :
   ```toml
   SUPABASE_DB_URL = "postgresql://postgres.zhvflbydddorvovjvkts:TON_MOT_DE_PASSE@aws-0-eu-central-2.pooler.supabase.com:6543/postgres"
   ```
4. Sauvegarde. L'app redémarre automatiquement et se connecte à Supabase.

---

## 4. Lancement et vérification

En local :
```bash
streamlit run app.py
```

Au premier démarrage, `init_app.py` :
- vérifie que les tables existent (elles existent déjà) ;
- vérifie que les 50 scénarios sont présents (ils le sont) ;
- crée les 2 comptes par défaut (`admin` / `medecin_nucleaire`) s'ils n'existent pas encore.

Pour vérifier la connexion, va dans le module **Référentiel** : tu dois voir les 50 scénarios. Puis saisis une demande test via **Prescripteur** et vérifie qu'elle apparaît dans **Médecin Nucléaire** — et qu'elle persiste même après redémarrage de l'app.

---

## 5. Ce qui a changé dans le code

| Fichier | Changement |
|---------|------------|
| `database.py` | Réécrit : connexion PostgreSQL Supabase (psycopg2) au lieu de SQLite. Couche de compatibilité qui traduit `?`→`%s` et préfixe les tables par le schéma `cdss`. La connexion lit `SUPABASE_DB_URL` depuis les secrets. |
| `init_app.py` | Retrait de la dépendance au fichier SQLite local (`DB_PATH`). |
| `seed_data.py` | Upsert PostgreSQL (`ON CONFLICT`) au lieu de DELETE + INSERT. |
| `chercheur.py` / `medecin_nucleaire.py` | Lecture du JSONB (déjà un dict côté PostgreSQL) au lieu de `json.loads` sur une string. |
| `requirements.txt` | + `psycopg2-binary`. |

L'ancien `database.py` SQLite est conservé en `database_sqlite_backup.py` au cas où.

---

## 6. Avantages de cette architecture

- **Persistance totale** : les données survivent aux redémarrages, redéploiements et mises en veille de Streamlit Cloud.
- **Accès concurrent** : plusieurs prescripteurs peuvent saisir des demandes simultanément.
- **Sauvegardes automatiques** : Supabase sauvegarde quotidiennement (plan gratuit : 7 jours de rétention).
- **Isolation** : le schéma `cdss` est séparé de tes autres données (table `patients` de ScintiFlow intacte).
- **Visualisation** : tu peux consulter/éditer tes données directement dans le dashboard Supabase (Table Editor → schéma `cdss`).

---

## 7. Sécurité — à lire

Les tables `cdss` ont actuellement **RLS (Row Level Security) désactivé**. C'est acceptable dans ton cas car :
- ton app se connecte via la **connection string directe** (mot de passe), pas via la clé publique anon ;
- cette connection string reste dans les secrets, jamais exposée au navigateur ;
- l'accès aux modules sensibles est protégé par ton authentification bcrypt.

Si tu veux une sécurité renforcée (défense en profondeur), tu peux activer RLS avec des politiques — mais ce n'est pas nécessaire pour un déploiement Streamlit standard où seul le serveur accède à la base. À discuter si besoin.

⚠️ **Données patient** : même si les données sont anonymisées (numéros CDSS-2026-XXXX), assure-toi que ton mot de passe Supabase est robuste et que la connection string n'est jamais commitée.
