"""Module Médecin Nucléaire — dashboard de tri et validation des demandes."""
from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from auth import log_action
from database import get_connection

EMOJI_CLASSIF = {"A": "🟢", "MBA": "🟡", "RA": "🔴"}
LABEL_CLASSIF = {
    "A": "Appropriate",
    "MBA": "May Be Appropriate",
    "RA": "Rarely Appropriate",
}
STATUTS = ["En attente", "Validée", "Rejetée", "Toutes"]
TRIS = [
    "Plus récentes d'abord",
    "Plus anciennes d'abord",
    "Par classification (RA d'abord)",
]
ACTIVITES_TMC = "Stress 350 MBq / Repos 1100 MBq (poids-dépendant)"


def _fmt_dt(val, length: int = 16) -> str:
    """Formate une date issue de la BDD pour l'affichage.

    PostgreSQL (TIMESTAMPTZ) renvoie un objet datetime ; l'ancien SQLite
    renvoyait une string ISO. Gère les deux cas + None.
    """
    if val is None:
        return ""
    if hasattr(val, "strftime"):  # datetime (PostgreSQL)
        return val.strftime("%Y-%m-%d %H:%M" if length >= 16 else "%Y-%m-%d")
    return str(val)[:length].replace("T", " ")  # string ISO (SQLite legacy)


def _safe_get(row, key, default=None):
    """Accès sûr à une colonne d'un sqlite3.Row (retourne default si absente)."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def render() -> None:
    """Point d'entrée du module Médecin Nucléaire."""
    st.header("Module Médecin Nucléaire — Tri des demandes")

    _render_metrics()
    st.divider()

    filtre_statut, filtres_classif, tri = _render_filtres()
    st.divider()

    demandes = _fetch_demandes(filtre_statut, filtres_classif, tri)
    st.caption(f"{len(demandes)} demande(s) affichée(s)")

    if not demandes:
        st.info("Aucune demande à afficher avec ces filtres.")
        return

    for d in demandes:
        _render_demande(d)

    st.divider()
    _render_export(demandes)


def _render_metrics() -> None:
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM demandes WHERE statut = 'En attente'"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT COALESCE(classification_medecin, classification) AS cl, COUNT(*) AS n "
            "FROM demandes WHERE statut = 'En attente' GROUP BY cl"
        ).fetchall()
        esc_rows = conn.execute(
            "SELECT conformite_esc AS c, COUNT(*) AS n "
            "FROM demandes WHERE statut = 'En attente' AND conformite_esc IS NOT NULL "
            "GROUP BY conformite_esc"
        ).fetchall()

    counts = {"A": 0, "MBA": 0, "RA": 0}
    for r in rows:
        if r["cl"] in counts:
            counts[r["cl"]] = r["n"]

    esc_counts = {"Adhérent": 0, "Non-adhérent": 0}
    for r in esc_rows:
        if r["c"] in esc_counts:
            esc_counts[r["c"]] = r["n"]
    total_esc = esc_counts["Adhérent"] + esc_counts["Non-adhérent"]

    def fmt(n: int) -> str:
        if total == 0:
            return f"{n}"
        return f"{n} ({n / total * 100:.0f}%)"

    cols = st.columns(4)
    with cols[0]:
        st.metric("Demandes en attente", total)
    with cols[1]:
        st.metric("🟢 Appropriate", fmt(counts["A"]))
    with cols[2]:
        st.metric("🟡 May Be Appropriate", fmt(counts["MBA"]))
    with cols[3]:
        st.metric("🔴 Rarely Appropriate", fmt(counts["RA"]))

    # Seconde ligne : métriques ESC (double évaluation)
    if total_esc > 0:
        cols2 = st.columns(4)
        with cols2[0]:
            st.metric("Évaluées vs ESC", total_esc)
        with cols2[1]:
            taux_adh = esc_counts["Adhérent"] / total_esc * 100
            st.metric("✅ Adhérent ESC", f"{esc_counts['Adhérent']} ({taux_adh:.0f}%)")
        with cols2[2]:
            taux_nonadh = esc_counts["Non-adhérent"] / total_esc * 100
            st.metric("❌ Non-adhérent ESC", f"{esc_counts['Non-adhérent']} ({taux_nonadh:.0f}%)")


def _render_filtres():
    col_statut, col_tri = st.columns([2, 3])
    with col_statut:
        filtre_statut = st.selectbox(
            "Filtrer par statut", STATUTS, index=0, key="mn_filtre_statut",
        )
    with col_tri:
        tri = st.selectbox("Tri", TRIS, index=0, key="mn_tri")

    st.markdown("**Classifications à afficher**")
    col_a, col_mba, col_ra = st.columns(3)
    with col_a:
        filt_a = st.checkbox("🟢 A — Appropriate", value=True, key="mn_filt_a")
    with col_mba:
        filt_mba = st.checkbox("🟡 MBA — May Be Appropriate", value=True, key="mn_filt_mba")
    with col_ra:
        filt_ra = st.checkbox("🔴 RA — Rarely Appropriate", value=True, key="mn_filt_ra")

    filtres_classif = []
    if filt_a:
        filtres_classif.append("A")
    if filt_mba:
        filtres_classif.append("MBA")
    if filt_ra:
        filtres_classif.append("RA")

    return filtre_statut, filtres_classif, tri


def _fetch_demandes(filtre_statut: str, filtres_classif: list[str], tri: str):
    if not filtres_classif:
        return []

    where = []
    params: list = []

    if filtre_statut != "Toutes":
        where.append("d.statut = ?")
        params.append(filtre_statut)

    placeholders = ",".join("?" * len(filtres_classif))
    where.append(
        f"COALESCE(d.classification_medecin, d.classification) IN ({placeholders})"
    )
    params.extend(filtres_classif)

    order_by = {
        "Plus récentes d'abord": "d.date_creation DESC",
        "Plus anciennes d'abord": "d.date_creation ASC",
        "Par classification (RA d'abord)": (
            "CASE COALESCE(d.classification_medecin, d.classification) "
            "WHEN 'RA' THEN 1 WHEN 'MBA' THEN 2 WHEN 'A' THEN 3 ELSE 4 END, "
            "d.date_creation DESC"
        ),
    }[tri]

    sql = f"""
        SELECT d.*,
               s.contexte_clinique, s.categorie, s.source, s.note_clinique,
               s.variables_cles, s.reference_esc, s.divergence_esc
        FROM demandes d
        LEFT JOIN scenarios_auc s ON d.scenario_id = s.id
        WHERE {' AND '.join(where)}
        ORDER BY {order_by}
    """

    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def _render_demande(d) -> None:
    classif_effective = d["classification_medecin"] or d["classification"] or "A"
    emoji = EMOJI_CLASSIF.get(classif_effective, "⚪")
    date_court = _fmt_dt(d["date_creation"], 16)
    titre = (
        f"{emoji} {d['id']} │ {date_court} │ Score {d['score_auc']}/9 │ "
        f"{d['scenario_id']} │ statut : {d['statut']}"
    )

    with st.expander(titre, expanded=False):
        if d["timestamp_ouverture"] is None:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE demandes SET timestamp_ouverture = now() WHERE id = ?",
                    (d["id"],),
                )

        try:
            raw = d["donnees_patient"]
            # PostgreSQL JSONB renvoie déjà un dict ; SQLite renvoyait une string.
            donnees = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})
        except (json.JSONDecodeError, TypeError):
            donnees = {}

        col_pat, col_eval = st.columns(2)

        with col_pat:
            st.markdown("**Patient**")
            st.markdown(f"- N° anonymisé : `{donnees.get('patient_id', '—')}`")
            st.markdown(
                f"- Âge : {donnees.get('age', '—')} ans │ Sexe : {donnees.get('sexe', '—')} "
                f"│ IMC : {donnees.get('imc', '—')}"
            )
            fdr = donnees.get("fdr") or []
            atcd = donnees.get("atcd") or []
            st.markdown(f"- FDR : {', '.join(fdr) if fdr else 'aucun signalé'}")
            st.markdown(f"- ATCD : {', '.join(atcd) if atcd else 'aucun signalé'}")
            nom_presc = donnees.get("prescripteur_nom") or "—"
            spec = donnees.get("prescripteur_specialite") or donnees.get("specialite") or "—"
            st.markdown(f"- Prescripteur : **{nom_presc}** ({spec})")

            st.markdown("**Données cliniques saisies**")
            reponses = donnees.get("reponses") or {}
            if not reponses:
                st.caption("Aucune donnée clinique disponible.")
            for k, v in reponses.items():
                if k == "branche":
                    continue
                label = k.replace("_", " ").capitalize()
                st.markdown(f"- {label} : {v}")
            duree_saisie = donnees.get("duree_saisie_secondes")
            if duree_saisie is not None:
                st.caption(f"Temps de saisie prescripteur : {duree_saisie:.1f} s")

        with col_eval:
            st.markdown("**Évaluation AUC**")
            st.markdown(f"- Scénario : `{d['scenario_id']}`")
            st.markdown(f"- Catégorie : {d['categorie'] or '—'}")
            st.markdown(f"- Contexte clinique : {d['contexte_clinique'] or '—'}")
            st.markdown(f"- **Score : {d['score_auc']}/9**")
            st.markdown(
                f"- Classification automatique : **{d['classification']} "
                f"— {LABEL_CLASSIF.get(d['classification'], '?')}**"
            )
            if d["classification_medecin"]:
                st.markdown(
                    f"- Reclassement médecin : **{d['classification_medecin']} "
                    f"— {LABEL_CLASSIF.get(d['classification_medecin'], '?')}**"
                )
            st.markdown(f"- Source : {d['source'] or '—'}")
            st.markdown(f"- Note clinique : {d['note_clinique'] or '—'}")

            # Évaluation parallèle ESC (double évaluation)
            classe_esc = _safe_get(d, "classe_esc")
            if classe_esc:
                conf_esc = _safe_get(d, "conformite_esc")
                ref_esc = _safe_get(d, "reference_esc")
                div_esc = _safe_get(d, "divergence_esc")
                st.markdown("**Évaluation ESC (parallèle)**")
                st.markdown(f"- Classe ESC : **{classe_esc}**")
                st.markdown(f"- Conformité : **{conf_esc or '—'}**")
                if ref_esc:
                    st.markdown(f"- Référence : {ref_esc}")
                if div_esc and div_esc != "Non":
                    st.markdown(
                        f"<div style='background-color:#fff3cd; padding:8px; border-radius:6px; "
                        f"border-left:4px solid #ffc107; margin-top:4px;'>"
                        f"<strong>Divergence AUC ↔ ESC :</strong> {div_esc}</div>",
                        unsafe_allow_html=True,
                    )

        if d["justification_forcage"]:
            st.markdown(
                f"<div style='background-color:#f8d7da; padding:12px; border-radius:6px; "
                f"border-left:5px solid #dc3545; margin-top:8px;'>"
                f"<strong>⚠️ Demande forcée par le prescripteur malgré classification RA</strong>"
                f"<br/><em>Justification : {d['justification_forcage']}</em>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.divider()

        if d["statut"] == "En attente":
            _render_actions(d)
        else:
            _render_decision_info(d)

        if d["statut"] == "Validée":
            st.divider()
            _render_protocole(donnees)


def _render_actions(d) -> None:
    demande_id = d["id"]
    action_key = f"mn_action_{demande_id}"
    if action_key not in st.session_state:
        st.session_state[action_key] = None

    current = st.session_state[action_key]

    if current is None:
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ VALIDER", key=f"mn_valid_{demande_id}", type="primary",
                         use_container_width=True):
                _perform_action(d, statut="Validée", commentaire=None, reclass=None)
                st.success("Demande validée.")
                st.rerun()
        with col2:
            if st.button("❌ REJETER", key=f"mn_rej_btn_{demande_id}",
                         use_container_width=True):
                st.session_state[action_key] = "rejet"
                st.rerun()
        with col3:
            if st.button("🔄 RECLASSER", key=f"mn_recl_btn_{demande_id}",
                         use_container_width=True):
                st.session_state[action_key] = "reclassement"
                st.rerun()

    elif current == "rejet":
        st.markdown("**Rejet de la demande**")
        motif = st.text_area(
            "Motif du rejet (≥ 10 caractères)",
            key=f"mn_motif_{demande_id}",
            height=100,
            placeholder="Exemple : indication non justifiée selon le référentiel, alternative plus pertinente…",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Confirmer le rejet", key=f"mn_conf_rej_{demande_id}",
                         type="primary"):
                if len(motif.strip()) < 10:
                    st.error("Motif trop court (minimum 10 caractères).")
                else:
                    _perform_action(d, statut="Rejetée",
                                    commentaire=motif.strip(), reclass=None)
                    st.session_state[action_key] = None
                    st.success("Demande rejetée.")
                    st.rerun()
        with c2:
            if st.button("Annuler", key=f"mn_cancel_rej_{demande_id}"):
                st.session_state[action_key] = None
                st.rerun()

    elif current == "reclassement":
        st.markdown("**Reclassement de la demande**")
        new_classif = st.selectbox(
            "Nouvelle classification",
            ["A", "MBA", "RA"],
            index=None,
            placeholder="Sélectionner…",
            key=f"mn_new_classif_{demande_id}",
        )
        commentaire = st.text_area(
            "Commentaire justifiant le reclassement (≥ 10 caractères)",
            key=f"mn_comm_{demande_id}",
            height=100,
            placeholder="Préciser le motif clinique du reclassement…",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Confirmer le reclassement",
                         key=f"mn_conf_recl_{demande_id}", type="primary"):
                if new_classif is None:
                    st.error("Choisir une nouvelle classification.")
                elif len(commentaire.strip()) < 10:
                    st.error("Commentaire trop court (minimum 10 caractères).")
                else:
                    _perform_action(d, statut="Validée",
                                    commentaire=commentaire.strip(),
                                    reclass=new_classif)
                    st.session_state[action_key] = None
                    st.success(f"Demande reclassée en {new_classif} et validée.")
                    st.rerun()
        with c2:
            if st.button("Annuler", key=f"mn_cancel_recl_{demande_id}"):
                st.session_state[action_key] = None
                st.rerun()


def _perform_action(d, statut: str, commentaire: str | None, reclass: str | None) -> None:
    """Persiste la décision médecin.

    timestamp_decision et la durée de validation sont calculés côté serveur
    PostgreSQL (now()) pour éviter toute ambiguïté de fuseau horaire avec les
    colonnes TIMESTAMPTZ.
    """
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE demandes
               SET statut = ?,
                   decision_medecin = ?,
                   classification_medecin = ?,
                   timestamp_decision = now(),
                   duree_validation_secondes =
                       GREATEST(0, EXTRACT(EPOCH FROM (now() - timestamp_ouverture)))::int
             WHERE id = ?
            """,
            (statut, commentaire, reclass, d["id"]),
        )

    # Traçabilité
    if reclass:
        log_action(
            "Reclassement demande", "Médecin Nucléaire",
            f"De {d['classification']} vers {reclass}: {commentaire}",
            d["id"],
        )
    elif statut == "Rejetée":
        log_action(
            "Rejet demande", "Médecin Nucléaire",
            f"Motif: {commentaire}",
            d["id"],
        )
    elif statut == "Validée":
        log_action(
            "Validation demande", "Médecin Nucléaire",
            "", d["id"],
        )


def _render_decision_info(d) -> None:
    statut = d["statut"]
    date_dec = _fmt_dt(d["timestamp_decision"], 16)
    if statut == "Validée":
        st.success(f"✅ Demande validée le {date_dec}")
    elif statut == "Rejetée":
        st.error(f"❌ Demande rejetée le {date_dec}")
    else:
        st.info(f"Statut : {statut}")

    if d["decision_medecin"]:
        st.markdown(f"**Commentaire médecin** : {d['decision_medecin']}")
    if d["duree_validation_secondes"] is not None:
        st.caption(f"Durée d'évaluation médecin : {d['duree_validation_secondes']} s")


def _render_protocole(donnees: dict) -> None:
    """Suggère un protocole d'acquisition à partir des données du prescripteur."""
    reponses = donnees.get("reponses") or {}
    capable_effort = reponses.get("capable_effort")
    capacite_fonc = reponses.get("capacite_fonctionnelle")

    if capable_effort == "Oui":
        modalite = "Effort sur tapis"
    elif capable_effort == "Non":
        modalite = "Stress pharmacologique (Régadénoson de préférence, ou Dipyridamole)"
    elif capacite_fonc == ">=4 METs":
        modalite = "Effort sur tapis (si pas de CI à l'effort)"
    elif capacite_fonc in ("<4 METs", "Inconnue"):
        modalite = "Stress pharmacologique (Régadénoson de préférence, ou Dipyridamole)"
    else:
        modalite = "À déterminer selon profil patient"

    st.markdown("**Protocole d'acquisition suggéré**")
    st.markdown(f"- Modalité de stress : **{modalite}**")
    st.markdown("- Radiopharmaceutique : **99mTc-Sestamibi 1 jour stress-repos**")
    st.markdown(f"- Activité suggérée : **{ACTIVITES_TMC}**")


def _render_export(demandes) -> None:
    rows = [{
        "id": d["id"],
        "date_creation": d["date_creation"],
        "prescripteur": d["prescripteur"],
        "scenario_id": d["scenario_id"],
        "score_auc": d["score_auc"],
        "classification_auto": d["classification"],
        "classification_medecin": d["classification_medecin"],
        "classe_esc": _safe_get(d, "classe_esc"),
        "conformite_esc": _safe_get(d, "conformite_esc"),
        "statut": d["statut"],
        "justification_forcage": d["justification_forcage"],
        "decision_medecin": d["decision_medecin"],
        "timestamp_ouverture": d["timestamp_ouverture"],
        "timestamp_decision": d["timestamp_decision"],
        "duree_validation_secondes": d["duree_validation_secondes"],
    } for d in demandes]

    df = pd.DataFrame(rows)
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    filename = f"demandes_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    if st.download_button(
        "📥 Exporter en CSV",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
    ):
        log_action("Export CSV", "Médecin Nucléaire", f"{len(rows)} lignes", None)
