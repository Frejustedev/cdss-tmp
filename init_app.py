"""Initialisation automatique au premier démarrage (tables + scénarios + comptes)."""
from datetime import datetime

import bcrypt

from database import get_connection, init_db

# Comptes par défaut créés au premier démarrage. Mots de passe HASHÉS (bcrypt)
# avant insertion en BDD — jamais stockés en clair.
DEFAULT_USERS = [
    {
        "username": "admin",
        "password": "CDSS-admin-2026",
        "role": "admin",
        "nom_complet": "Dr. Frejuste AGBOTON",
    },
    {
        "username": "medecin_nucleaire",
        "password": "CDSS-medecin-2026",
        "role": "medecin_nucleaire",
        "nom_complet": "Médecin Nucléaire",
    },
]


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _seed_users() -> int:
    """Insère les comptes par défaut s'ils n'existent pas. Retourne le nombre créé."""
    created = 0
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        for u in DEFAULT_USERS:
            row = conn.execute(
                "SELECT username FROM utilisateurs WHERE username = ?",
                (u["username"],),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO utilisateurs "
                    "(username, password_hash, role, nom_complet, date_creation) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        u["username"],
                        _hash_password(u["password"]),
                        u["role"],
                        u["nom_complet"],
                        now,
                    ),
                )
                created += 1
    return created


def ensure_initialized() -> bool:
    """Crée la base, seed les scénarios AUC et les comptes par défaut si absents.

    Retourne True si une initialisation significative a été effectuée
    (scénarios re-seedés), False sinon.
    """
    init_db()  # idempotent, crée toutes les tables si absentes

    with get_connection() as conn:
        scen_count = conn.execute("SELECT COUNT(*) AS n FROM scenarios_auc").fetchone()["n"]

    if scen_count == 0:
        from seed_data import seed_scenarios
        seed_scenarios()

    _seed_users()

    return scen_count == 0


if __name__ == "__main__":
    created = ensure_initialized()
    print("Base créée et seedée." if created else "Base déjà présente.")
