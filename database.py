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


class _ConnectionWrapper:
    """Connexion psycopg2, interface compatible sqlite3 + context manager."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=None):
        cur = _CursorWrapper(self._conn.cursor())
        return cur.execute(query, params)

    def executemany(self, query, seq_of_params):
        cur = _CursorWrapper(self._conn.cursor())
        return cur.executemany(query, seq_of_params)

    def cursor(self):
        return _CursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False


def get_connection() -> _ConnectionWrapper:
    """Retourne une connexion à la base Supabase, accès par nom de colonne.

    Interface compatible avec l'ancien code SQLite : get_connection().execute(...),
    fetchone()/fetchall() renvoient des dict-like indexables par nom de colonne,
    et le bloc « with » committe automatiquement.
    """
    conn = psycopg2.connect(
        _get_dsn(),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    with conn.cursor() as c:
        c.execute(f"SET search_path TO {SCHEMA}, public")
    conn.commit()
    return _ConnectionWrapper(conn)


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
