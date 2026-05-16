"""Authentification (bcrypt) + traçabilité (audit_log)."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

import bcrypt
import streamlit as st

from database import get_connection

SESSION_KEY = "auth_user"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def log_action(action: str, module: str | None,
               details: str | None, demande_id: str | None) -> None:
    """Insère une ligne dans audit_log avec utilisateur courant + horodatage."""
    user = get_current_user()
    username = user["username"] if user else None
    role = user["role"] if user else None
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_log "
            "(timestamp, utilisateur, role, action, module, details, demande_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                username,
                role,
                action,
                module,
                details,
                demande_id,
            ),
        )


def login(username: str, password: str) -> tuple[bool, str | None, str | None]:
    """Authentifie l'utilisateur. Retourne (success, role, nom_complet)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash, role, nom_complet FROM utilisateurs "
            "WHERE username = ?",
            (username,),
        ).fetchone()

    if row is None or not verify_password(password, row["password_hash"]):
        log_action("Tentative échouée", "Auth", f"Identifiant: {username}", None)
        return False, None, None

    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute(
            "UPDATE utilisateurs SET derniere_connexion = ? WHERE username = ?",
            (now, username),
        )

    st.session_state[SESSION_KEY] = {
        "username": username,
        "role": row["role"],
        "nom_complet": row["nom_complet"],
    }
    log_action("Connexion", "Auth", "", None)
    return True, row["role"], row["nom_complet"]


def logout() -> None:
    log_action("Déconnexion", "Auth", "", None)
    if SESSION_KEY in st.session_state:
        del st.session_state[SESSION_KEY]


def get_current_user() -> dict | None:
    return st.session_state.get(SESSION_KEY)


def is_authenticated() -> bool:
    return get_current_user() is not None


def require_role(allowed_roles: Iterable[str]) -> bool:
    """Vrai ssi l'utilisateur est connecté ET a un rôle autorisé."""
    user = get_current_user()
    return user is not None and user["role"] in set(allowed_roles)


def render_login_form(target_module: str = "ce module") -> None:
    """Affiche le formulaire de connexion."""
    st.markdown("# 🔐 Connexion requise")
    st.markdown(f"L'accès à **{target_module}** nécessite une authentification.")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Identifiant", key="login_username")
        password = st.text_input("Mot de passe", type="password", key="login_password")
        submit = st.form_submit_button("Se connecter", type="primary")

    if submit:
        success, role, nom = login(username.strip(), password)
        if success:
            st.success(f"Bienvenue, {nom} ({role}).")
            st.rerun()
        else:
            st.error("Identifiants incorrects.")

    st.caption("Retour : sélectionne « Accueil » dans le menu latéral.")


def render_access_denied(required_role_label: str = "administrateurs") -> None:
    user = get_current_user()
    log_action(
        "Accès refusé",
        "Auth",
        f"Rôle insuffisant ({user['role'] if user else 'anonyme'})",
        None,
    )
    st.error(
        f"⛔ Accès refusé. Ce module est réservé aux {required_role_label}."
    )
    st.caption("Retour : sélectionne « Accueil » dans le menu latéral.")


def render_sidebar_status() -> None:
    """Bloc statut connexion en bas de la sidebar."""
    user = get_current_user()
    st.sidebar.divider()
    if user:
        st.sidebar.markdown(f"👤 **{user['nom_complet']}**")
        st.sidebar.caption(f"Rôle : `{user['role']}`")
        if st.sidebar.button("🚪 Se déconnecter", use_container_width=True):
            logout()
            st.rerun()
    else:
        st.sidebar.caption("🔓 Non connecté")
