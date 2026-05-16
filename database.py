"""Initialisation et accès à la base SQLite du CDSS-TMP."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "cdss_tmp.db"


def get_connection() -> sqlite3.Connection:
    """Retourne une connexion à la base, avec accès par nom de colonne."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Crée les tables si elles n'existent pas + applique les migrations.

    Idempotent.
    """
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scenarios_auc (
                id                TEXT PRIMARY KEY,
                categorie         TEXT NOT NULL,
                contexte_clinique TEXT NOT NULL,
                variables_cles    TEXT NOT NULL,
                score_auc         INTEGER NOT NULL CHECK (score_auc BETWEEN 1 AND 9),
                classification    TEXT NOT NULL CHECK (classification IN ('A', 'MBA', 'RA')),
                source            TEXT NOT NULL,
                note_clinique     TEXT
            );

            CREATE TABLE IF NOT EXISTS demandes (
                id                    TEXT PRIMARY KEY,
                date_creation         TEXT NOT NULL,
                prescripteur          TEXT NOT NULL,
                donnees_patient       TEXT NOT NULL,
                scenario_id           TEXT,
                score_auc             INTEGER,
                classification        TEXT,
                statut                TEXT NOT NULL,
                justification_forcage TEXT,
                FOREIGN KEY (scenario_id) REFERENCES scenarios_auc(id)
            );
            """
        )
        _migrate_demandes(conn)


def _migrate_demandes(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes des modules Médecin Nucléaire et Chercheur si absentes."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(demandes)")}
    additions = {
        "decision_medecin": "TEXT",
        "classification_medecin": "TEXT",
        "timestamp_ouverture": "TEXT",
        "timestamp_decision": "TEXT",
        "duree_validation_secondes": "INTEGER",
        "phase_etude": "TEXT DEFAULT 'Phase 3'",
    }
    for col, sql_type in additions.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE demandes ADD COLUMN {col} {sql_type}")
    # Backfill : les lignes pré-existantes peuvent avoir phase_etude NULL.
    conn.execute("UPDATE demandes SET phase_etude = 'Phase 3' WHERE phase_etude IS NULL")


if __name__ == "__main__":
    init_db()
    print(f"Base initialisee : {DB_PATH}")
