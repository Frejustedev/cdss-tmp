"""Initialisation automatique au premier démarrage (création + seed)."""
from pathlib import Path

from database import DB_PATH, init_db


def ensure_initialized() -> bool:
    """Crée la base SQLite et insère les 50 scénarios AUC si absents.

    - Si la base n'existe pas : on l'initialise et on lance le seed.
    - Si la base existe mais sans scénarios (table vide) : on lance le seed.

    Retourne True si une initialisation a été effectuée, False sinon.
    """
    if not Path(DB_PATH).exists():
        init_db()
        from seed_data import seed_scenarios
        seed_scenarios()
        return True

    init_db()
    from database import get_connection
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM scenarios_auc").fetchone()[0]
    if count == 0:
        from seed_data import seed_scenarios
        seed_scenarios()
        return True

    return False


if __name__ == "__main__":
    created = ensure_initialized()
    print("Base créée et seedée." if created else "Base déjà présente.")
