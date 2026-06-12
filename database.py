"""Accès à la base PostgreSQL Supabase du CDSS-TMP.

Cette couche remplace l'ancienne base SQLite locale (éphémère sur Streamlit
Cloud) par une base PostgreSQL Supabase persistante. Pour minimiser les
changements dans le reste du code, un adaptateur traduit automatiquement :
  - les placeholders «?» (style SQLite) vers «%s» (style psycopg2) ;
  - les noms de tables vers le schéma «cdss».

La chaîne de connexion est lue depuis les secrets Streamlit (st.secrets) ou
les variables d'environnement, et n'est JAMAIS écrite en dur dans le code.
"""
from __future__ import annotations

import os
import re

import psycopg2
import psycopg2.extras
import psycopg2.pool

# Schéma dédié au CDSS dans la base Supabase (isolé de la table patients).
SCHEMA = "cdss"

# Tables gérées par le CDSS — utilisées pour réécrire les requêtes vers le schéma.
_TABLES = ("scenarios_auc", "demandes", "utilisateurs", "audit_log")


class _Row(dict):
    """Ligne accessible par nom de colonne ('col') ET par index entier ([0]),
    pour compatibilité totale avec l'ancien code SQLite (fetchone()[0] etc.).
    Construite à partir d'un dict ordonné (les colonnes gardent leur ordre SQL).
    """

    def __init__(self, mapping):
        super().__init__(mapping)
        self._values = list(mapping.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

    def keys(self):
        return super().keys()


def _get_dsn() -> str:
    """Récupère la chaîne de connexion PostgreSQL.

    Ordre de priorité :
      1. st.secrets["SUPABASE_DB_URL"] (déploiement Streamlit Cloud)
      2. variable d'environnement SUPABASE_DB_URL (dev local)
    """
    try:
        import streamlit as st
        if "SUPABASE_DB_URL" in st.secrets:
            return st.secrets["SUPABASE_DB_URL"]
    except Exception:
        pass
    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        raise RuntimeError(
            "Chaîne de connexion Supabase introuvable. Définir SUPABASE_DB_URL "
            "dans les secrets Streamlit ou les variables d'environnement."
        )
    return dsn


def _adapt_query(query: str) -> str:
    """Traduit une requête SQLite vers PostgreSQL (placeholders + schéma)."""
    for tbl in _TABLES:
        query = re.sub(
            rf"(?<![\w.])({tbl})(?![\w.])",
            f"{SCHEMA}.{tbl}",
            query,
        )
    query = query.replace("?", "%s")
    return query


class _CursorWrapper:
    """Curseur psycopg2 adaptant les requêtes, interface compatible sqlite3."""

    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, query, params=None):
        adapted = _adapt_query(query)
        if params is None:
            self._cur.execute(adapted)
        else:
            self._cur.execute(adapted, params)
        return self

    def executemany(self, query, seq_of_params):
        adapted = _adapt_query(query)
        self._cur.executemany(adapted, seq_of_params)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return _Row(row) if row is not None else None

    def fetchall(self):
        return [_Row(r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __iter__(self):
        return iter(self._cur)

    def close(self):
        self._cur.close()


# Erreurs psycopg2 indiquant une connexion morte/périmée (Supabase ferme les
# connexions inactives) → on reconnecte et on réessaie une fois.
_TRANSIENT_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


class _ConnectionWrapper:
    """Connexion empruntée au pool, interface compatible sqlite3 + context manager.

    À la sortie du bloc « with » (ou au close()), la connexion est RENDUE au
    pool (et non fermée), pour éviter de repayer un handshake TLS à chaque requête.
    """

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def _reconnect(self) -> None:
        try:
            self._pool.putconn(self._conn, close=True)
        except Exception:
            pass
        self._conn = self._pool.getconn()

    def execute(self, query, params=None):
        for attempt in (1, 2):
            try:
                return _CursorWrapper(self._conn.cursor()).execute(query, params)
            except _TRANSIENT_ERRORS:
                if attempt == 2:
                    raise
                self._reconnect()

    def executemany(self, query, seq_of_params):
        for attempt in (1, 2):
            try:
                return _CursorWrapper(self._conn.cursor()).executemany(query, seq_of_params)
            except _TRANSIENT_ERRORS:
                if attempt == 2:
                    raise
                self._reconnect()

    def cursor(self):
        return _CursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def _release(self) -> None:
        """Rend la connexion au pool, transaction nettoyée."""
        if self._conn is None:
            return
        try:
            self._conn.rollback()  # purge toute transaction restée ouverte
        except Exception:
            pass
        try:
            self._pool.putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None

    def close(self):
        self._release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self._conn.commit()
        except Exception:
            pass
        self._release()
        return False


_pool = None


def _get_pool():
    """Pool de connexions partagé (créé paresseusement, persiste entre reruns)."""
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            1, 12,
            dsn=_get_dsn(),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _pool


def get_connection() -> _ConnectionWrapper:
    """Emprunte une connexion au pool Supabase (réutilisée, sans re-handshake).

    Interface compatible SQLite : get_connection().execute(...), fetchone()/
    fetchall() renvoient des dict-like indexables par nom OU index, et le bloc
    « with » committe automatiquement puis rend la connexion au pool.

    Le schéma `cdss` est ciblé directement par _adapt_query (préfixe des tables),
    donc aucun `SET search_path` n'est nécessaire (économise un aller-retour).
    """
    pool = _get_pool()
    return _ConnectionWrapper(pool.getconn(), pool)


def init_db() -> None:
    """Crée le schéma et les tables si nécessaire (idempotent)."""
    ddl = f"""
        CREATE SCHEMA IF NOT EXISTS {SCHEMA};

        CREATE TABLE IF NOT EXISTS {SCHEMA}.scenarios_auc (
            id                TEXT PRIMARY KEY,
            categorie         TEXT NOT NULL,
            contexte_clinique TEXT NOT NULL,
            variables_cles    TEXT NOT NULL,
            score_auc         INTEGER NOT NULL CHECK (score_auc BETWEEN 1 AND 9),
            classification    TEXT NOT NULL CHECK (classification IN ('A', 'MBA', 'RA')),
            source            TEXT NOT NULL,
            note_clinique     TEXT,
            classe_esc        TEXT,
            reference_esc     TEXT,
            conformite_esc    TEXT,
            divergence_esc    TEXT
        );

        CREATE TABLE IF NOT EXISTS {SCHEMA}.demandes (
            id                        TEXT PRIMARY KEY,
            date_creation             TIMESTAMPTZ NOT NULL DEFAULT now(),
            prescripteur              TEXT NOT NULL,
            donnees_patient           JSONB NOT NULL,
            scenario_id               TEXT REFERENCES {SCHEMA}.scenarios_auc(id),
            score_auc                 INTEGER,
            classification            TEXT,
            classe_esc                TEXT,
            conformite_esc            TEXT,
            statut                    TEXT NOT NULL DEFAULT 'En attente',
            justification_forcage     TEXT,
            decision_medecin          TEXT,
            classification_medecin    TEXT,
            timestamp_ouverture       TIMESTAMPTZ,
            timestamp_decision        TIMESTAMPTZ,
            duree_validation_secondes INTEGER,
            phase_etude               TEXT DEFAULT 'Audit'
        );

        CREATE TABLE IF NOT EXISTS {SCHEMA}.utilisateurs (
            username           TEXT PRIMARY KEY,
            password_hash      TEXT NOT NULL,
            role               TEXT NOT NULL CHECK (role IN ('admin', 'medecin_nucleaire')),
            nom_complet        TEXT,
            date_creation      TIMESTAMPTZ DEFAULT now(),
            derniere_connexion TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS {SCHEMA}.audit_log (
            id          BIGSERIAL PRIMARY KEY,
            timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
            utilisateur TEXT,
            role        TEXT,
            action      TEXT NOT NULL,
            module      TEXT,
            details     TEXT,
            demande_id  TEXT
        );
    """
    conn = psycopg2.connect(_get_dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Schéma {SCHEMA} initialisé sur Supabase.")
