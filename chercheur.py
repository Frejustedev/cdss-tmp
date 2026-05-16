"""Module Chercheur — tableau de bord analytique pour le mémoire."""
from __future__ import annotations

import io
import json
from datetime import date, datetime
from math import sqrt

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from scipy import stats as scipy_stats
from sklearn.metrics import cohen_kappa_score, confusion_matrix

from database import get_connection

CLASSIFICATIONS = ["A", "MBA", "RA"]
COLOR_CLASSIF = {"A": "#28a745", "MBA": "#ffc107", "RA": "#dc3545"}
LABEL_CLASSIF = {"A": "Appropriate", "MBA": "May Be Appropriate", "RA": "Rarely Appropriate"}
DOSE_PAR_TMP_MSV = 10  # mSv évitables (1 jour stress-repos 99mTc-Sestamibi)
FDR_OPTIONS = [
    "HTA", "Diabète type 1", "Diabète type 2", "Dyslipidémie",
    "Tabac actif", "Tabac sevré", "ATCD familial CAD précoce",
]
PHASE_UI_TO_DB = {
    "Toutes": None,
    "Phase 1 (rétrospectif)": "Phase 1",
    "Phase 3 (prospectif)": "Phase 3",
}


def render() -> None:
    st.header("Module Chercheur — Tableau de bord analytique")

    phase, date_debut, date_fin = _render_filtre_global()
    _render_gestion_phases()

    st.divider()

    df = _load_demandes(phase=phase, date_debut=date_debut, date_fin=date_fin)
    df_all = _load_demandes(phase="Toutes", date_debut=date_debut, date_fin=date_fin)

    st.caption(
        f"📊 {len(df)} demande(s) selon le filtre actuel "
        f"(sur {len(df_all)} dans la fenêtre temporelle)."
    )

    tabs = st.tabs([
        "Vue d'ensemble",
        "Phase 1 vs Phase 3",
        "Analyses détaillées",
        "Concordance & contournement",
        "Exports",
    ])

    with tabs[0]:
        _onglet_vue_ensemble(df, df_all)
    with tabs[1]:
        _onglet_comparaison(df_all)
    with tabs[2]:
        _onglet_analyses(df)
    with tabs[3]:
        _onglet_concordance(df)
    with tabs[4]:
        _onglet_exports(df, df_all)


# ===== Filtre global =====
def _render_filtre_global():
    st.markdown("#### Filtre global")
    col1, col2, col3 = st.columns(3)
    with col1:
        phase = st.selectbox(
            "Phase d'étude",
            list(PHASE_UI_TO_DB.keys()),
            index=0,
            key="ch_phase",
        )
    with col2:
        date_debut = st.date_input(
            "Date début", value=date(2026, 1, 1), key="ch_date_debut"
        )
    with col3:
        date_fin = st.date_input(
            "Date fin", value=date.today(), key="ch_date_fin"
        )
    return phase, date_debut, date_fin


def _render_gestion_phases() -> None:
    with st.expander("🔧 Gérer les phases des demandes (marquage rétroactif)"):
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, date_creation, phase_etude FROM demandes "
                "ORDER BY date_creation DESC"
            ).fetchall()
        if not rows:
            st.caption("Aucune demande en base.")
            return

        options = [
            f"{r['id']} — {(r['date_creation'] or '')[:10]} — {r['phase_etude'] or 'NULL'}"
            for r in rows
        ]
        id_map = {opt: r["id"] for opt, r in zip(options, rows)}

        selected = st.multiselect(
            "Sélectionner les demandes à reclasser",
            options,
            key="ch_phase_select",
        )
        new_phase = st.radio(
            "Phase à assigner",
            ["Phase 1", "Phase 3"],
            horizontal=True,
            key="ch_new_phase",
        )

        if st.button("Appliquer le changement de phase"):
            if not selected:
                st.warning("Sélectionne au moins une demande.")
            else:
                ids = [id_map[s] for s in selected]
                with get_connection() as conn:
                    conn.executemany(
                        "UPDATE demandes SET phase_etude = ? WHERE id = ?",
                        [(new_phase, i) for i in ids],
                    )
                st.success(f"{len(ids)} demande(s) marquée(s) comme {new_phase}.")
                st.rerun()


# ===== Chargement des demandes =====
def _parse_donnees(s):
    if not s:
        return {}
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return {}


def _load_demandes(phase="Toutes", date_debut=None, date_fin=None) -> pd.DataFrame:
    where = []
    params: list = []
    db_phase = PHASE_UI_TO_DB.get(phase)
    if db_phase:
        where.append("d.phase_etude = ?")
        params.append(db_phase)
    if date_debut:
        where.append("date(d.date_creation) >= date(?)")
        params.append(date_debut.isoformat())
    if date_fin:
        where.append("date(d.date_creation) <= date(?)")
        params.append(date_fin.isoformat())

    where_sql = " AND ".join(where) if where else "1=1"
    sql = f"""
        SELECT d.*, s.categorie AS scenario_categorie, s.source AS scenario_source
        FROM demandes d
        LEFT JOIN scenarios_auc s ON d.scenario_id = s.id
        WHERE {where_sql}
        ORDER BY d.date_creation ASC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    parsed = df["donnees_patient"].apply(_parse_donnees)
    df["age"] = parsed.apply(lambda d: d.get("age"))
    df["sexe"] = parsed.apply(lambda d: d.get("sexe"))
    df["imc"] = parsed.apply(lambda d: d.get("imc"))
    df["fdr"] = parsed.apply(lambda d: d.get("fdr") or [])
    df["atcd"] = parsed.apply(lambda d: d.get("atcd") or [])
    df["specialite"] = parsed.apply(lambda d: d.get("specialite"))
    df["reponses"] = parsed.apply(lambda d: d.get("reponses") or {})
    df["duree_saisie"] = parsed.apply(lambda d: d.get("duree_saisie_secondes"))
    df["classification_effective"] = df["classification_medecin"].fillna(df["classification"])
    return df


# ===== ONGLET 1 — Vue d'ensemble =====
def _onglet_vue_ensemble(df: pd.DataFrame, df_all: pd.DataFrame) -> None:
    if df.empty:
        st.info("Aucune demande dans le filtre actuel.")
        return

    total = len(df)
    counts = {c: int((df["classification_effective"] == c).sum()) for c in CLASSIFICATIONS}
    pct = {c: counts[c] / total * 100 if total else 0 for c in CLASSIFICATIONS}

    df_p1 = df_all[df_all["phase_etude"] == "Phase 1"] if not df_all.empty else df_all
    df_p3 = df_all[df_all["phase_etude"] == "Phase 3"] if not df_all.empty else df_all
    delta_pct = {c: None for c in CLASSIFICATIONS}
    if len(df_p1) > 0 and len(df_p3) > 0:
        for c in CLASSIFICATIONS:
            p1 = (df_p1["classification_effective"] == c).mean() * 100
            p3 = (df_p3["classification_effective"] == c).mean() * 100
            delta_pct[c] = p3 - p1

    # Ligne 1
    cols = st.columns(4)
    with cols[0]:
        st.metric("Demandes totales", total)
    with cols[1]:
        d = f"{delta_pct['A']:+.1f}% vs P1" if delta_pct["A"] is not None else None
        st.metric("🟢 Appropriate", f"{counts['A']} ({pct['A']:.0f}%)", delta=d)
    with cols[2]:
        d = f"{delta_pct['MBA']:+.1f}% vs P1" if delta_pct["MBA"] is not None else None
        st.metric("🟡 May Be Appropriate", f"{counts['MBA']} ({pct['MBA']:.0f}%)", delta=d)
    with cols[3]:
        d = f"{delta_pct['RA']:+.1f}% vs P1" if delta_pct["RA"] is not None else None
        st.metric(
            "🔴 Rarely Appropriate ⚠️",
            f"{counts['RA']} ({pct['RA']:.0f}%)",
            delta=d,
            delta_color="inverse",
            help="Critère de jugement principal — une baisse est favorable.",
        )

    # Ligne 2
    cols = st.columns(4)
    duree_mean = df["duree_validation_secondes"].dropna().mean()
    duree_str = f"{duree_mean:.0f} s" if not pd.isna(duree_mean) else "—"

    nb_ra = int((df["classification_effective"] == "RA").sum())
    nb_ra_forces = int(
        ((df["classification_effective"] == "RA") & df["justification_forcage"].notna()).sum()
    )
    taux_forc = nb_ra_forces / nb_ra * 100 if nb_ra else 0

    nb_ra_rejetees = int(
        ((df["classification_effective"] == "RA") & (df["statut"] == "Rejetée")).sum()
    )
    dose_evitee = nb_ra_rejetees * DOSE_PAR_TMP_MSV

    nb_attente = int((df["statut"] == "En attente").sum())

    with cols[0]:
        st.metric("Temps moyen validation", duree_str)
    with cols[1]:
        st.metric(
            "Taux de contournement",
            f"{taux_forc:.0f}% ({nb_ra_forces}/{nb_ra})",
            help="% des RA forcées par le prescripteur.",
        )
    with cols[2]:
        st.metric(
            "Dose efficace cumulée évitée",
            f"{dose_evitee} mSv",
            help="(RA rejetées par le médecin) × 10 mSv (1 jour stress-repos 99mTc).",
        )
    with cols[3]:
        st.metric("Demandes en attente", nb_attente)

    st.divider()
    st.subheader("Répartition par classification")

    plot_rows = [
        {
            "Classification": LABEL_CLASSIF[c],
            "Effectif": counts[c],
            "Pourcentage": pct[c],
            "Etiquette": f"{counts[c]} ({pct[c]:.1f}%)",
        }
        for c in CLASSIFICATIONS
    ]
    fig = px.bar(
        pd.DataFrame(plot_rows),
        y="Classification",
        x="Effectif",
        text="Etiquette",
        orientation="h",
        color="Classification",
        color_discrete_map={LABEL_CLASSIF[c]: COLOR_CLASSIF[c] for c in CLASSIFICATIONS},
    )
    fig.update_traces(textposition="auto")
    fig.update_layout(showlegend=False, height=300)
    st.plotly_chart(fig, use_container_width=True)


# ===== ONGLET 2 — Phase 1 vs Phase 3 =====
def _wald_diff_proportions(x1, n1, x2, n2):
    """Différence p1-p2 + IC 95% Wald avec correction de continuité."""
    p1, p2 = x1 / n1, x2 / n2
    diff = p1 - p2
    se = sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) if n1 and n2 else 0
    cc = 0.5 * (1 / n1 + 1 / n2) if n1 and n2 else 0
    return diff, diff - 1.96 * se - cc, diff + 1.96 * se + cc


def _test_proportions(x1, n1, x2, n2):
    """Retourne (p_value, test_name) selon chi2 ou Fisher."""
    table = np.array([[x1, n1 - x1], [x2, n2 - x2]])
    if table.min() < 5:
        _, p_value = scipy_stats.fisher_exact(table)
        return p_value, "Fisher"
    _, p_value, _, _ = scipy_stats.chi2_contingency(table)
    return p_value, "χ²"


def _onglet_comparaison(df_all: pd.DataFrame) -> None:
    if df_all.empty:
        st.info("Aucune demande dans la période sélectionnée.")
        return

    df_p1 = df_all[df_all["phase_etude"] == "Phase 1"]
    df_p3 = df_all[df_all["phase_etude"] == "Phase 3"]
    n1, n3 = len(df_p1), len(df_p3)

    if n1 == 0 or n3 == 0:
        st.info(
            f"Données insuffisantes pour comparaison "
            f"(Phase 1 : {n1} demandes, Phase 3 : {n3}). "
            "Marque au moins quelques demandes comme Phase 1 via le panneau "
            "« Gérer les phases » en haut pour activer cette analyse."
        )
        return

    rows = []
    for c in CLASSIFICATIONS:
        x1 = int((df_p1["classification_effective"] == c).sum())
        x3 = int((df_p3["classification_effective"] == c).sum())
        diff, lo, hi = _wald_diff_proportions(x3, n3, x1, n1)
        p_value, test_name = _test_proportions(x1, n1, x3, n3)
        rows.append({
            "Indicateur": f"Taux {c}",
            "Phase 1": f"{x1/n1*100:.1f}% ({x1}/{n1})",
            "Phase 3": f"{x3/n3*100:.1f}% ({x3}/{n3})",
            "Différence (P3-P1)": f"{diff*100:+.1f}%",
            "IC 95%": f"[{lo*100:.1f}, {hi*100:.1f}]",
            "p-value": f"p={p_value:.3f} ({test_name})",
        })

    # Temps de validation
    t1 = df_p1["duree_validation_secondes"].dropna().to_numpy()
    t3 = df_p3["duree_validation_secondes"].dropna().to_numpy()
    if len(t1) >= 2 and len(t3) >= 2:
        normal_1 = scipy_stats.shapiro(t1).pvalue > 0.05 if len(t1) >= 3 else False
        normal_3 = scipy_stats.shapiro(t3).pvalue > 0.05 if len(t3) >= 3 else False
        if normal_1 and normal_3:
            p_t = scipy_stats.ttest_ind(t1, t3, equal_var=False).pvalue
            test_t_name = "t Student"
        else:
            p_t = scipy_stats.mannwhitneyu(t1, t3, alternative="two-sided").pvalue
            test_t_name = "Mann-Whitney"
        rows.append({
            "Indicateur": "Temps validation moyen",
            "Phase 1": f"{t1.mean():.0f} s (n={len(t1)})",
            "Phase 3": f"{t3.mean():.0f} s (n={len(t3)})",
            "Différence (P3-P1)": f"{t3.mean() - t1.mean():+.0f} s",
            "IC 95%": "—",
            "p-value": f"p={p_t:.3f} ({test_t_name})",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Verdict
    st.divider()
    st.subheader("Verdict — critère de jugement principal (taux RA)")
    ra_p1 = int((df_p1["classification_effective"] == "RA").sum())
    ra_p3 = int((df_p3["classification_effective"] == "RA").sum())
    diff, lo, hi = _wald_diff_proportions(ra_p3, n3, ra_p1, n1)
    p_value, _ = _test_proportions(ra_p1, n1, ra_p3, n3)

    if diff < 0 and p_value < 0.05:
        color, verdict = "#28a745", "Réduction statistiquement significative des RA."
    elif diff < 0:
        color, verdict = "#ffc107", "Tendance à la réduction mais non significative."
    else:
        color, verdict = "#dc3545", "Pas de réduction observée."

    st.markdown(
        f"<div style='background-color:{color}; color:white; padding:18px; border-radius:8px;'>"
        f"<strong>{verdict}</strong><br/>"
        f"La proportion de Rarely Appropriate est passée de "
        f"{ra_p1/n1*100:.1f}% (Phase 1) à {ra_p3/n3*100:.1f}% (Phase 3), "
        f"différence {diff*100:+.1f}% (IC 95% [{lo*100:.1f}, {hi*100:.1f}], p={p_value:.3f})."
        f"</div>",
        unsafe_allow_html=True,
    )

    st.divider()
    st.subheader("Distribution par classification : Phase 1 vs Phase 3")
    bars = []
    for ph, df_ph in (("Phase 1", df_p1), ("Phase 3", df_p3)):
        for c in CLASSIFICATIONS:
            bars.append({
                "Phase": ph,
                "Classification": LABEL_CLASSIF[c],
                "Effectif": int((df_ph["classification_effective"] == c).sum()),
            })
    fig = px.bar(
        pd.DataFrame(bars), x="Classification", y="Effectif", color="Phase",
        barmode="group",
        color_discrete_map={"Phase 1": "#6c757d", "Phase 3": "#0d6efd"},
    )
    st.plotly_chart(fig, use_container_width=True)

    if len(t1) > 0 and len(t3) > 0:
        st.subheader("Temps de validation : Phase 1 vs Phase 3")
        box_df = pd.concat([
            pd.DataFrame({"Phase": "Phase 1", "Durée (s)": t1}),
            pd.DataFrame({"Phase": "Phase 3", "Durée (s)": t3}),
        ])
        fig2 = px.box(
            box_df, x="Phase", y="Durée (s)", color="Phase",
            color_discrete_map={"Phase 1": "#6c757d", "Phase 3": "#0d6efd"},
        )
        st.plotly_chart(fig2, use_container_width=True)


# ===== ONGLET 3 — Analyses détaillées =====
def _onglet_analyses(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Aucune demande à analyser.")
        return

    # Section A
    st.subheader("A. Par spécialité prescripteur")
    spec_rows = []
    for spec, g in df.groupby("specialite", dropna=False):
        spec_rows.append({
            "Spécialité": spec or "Non renseignée",
            "Total": len(g),
            "% A": (g["classification_effective"] == "A").mean() * 100,
            "% MBA": (g["classification_effective"] == "MBA").mean() * 100,
            "% RA": (g["classification_effective"] == "RA").mean() * 100,
        })
    spec_df = pd.DataFrame(spec_rows).sort_values("% RA", ascending=False)
    st.dataframe(spec_df, use_container_width=True, hide_index=True)

    stack_rows = []
    for _, row in spec_df.iterrows():
        for c in CLASSIFICATIONS:
            stack_rows.append({
                "Spécialité": row["Spécialité"],
                "Classification": LABEL_CLASSIF[c],
                "Pourcentage": row[f"% {c}"],
            })
    fig = px.bar(
        pd.DataFrame(stack_rows), x="Spécialité", y="Pourcentage",
        color="Classification",
        color_discrete_map={LABEL_CLASSIF[c]: COLOR_CLASSIF[c] for c in CLASSIFICATIONS},
    )
    st.plotly_chart(fig, use_container_width=True)

    # Section B
    st.divider()
    st.subheader("B. Par catégorie clinique AUC")
    cat_rows = []
    for cat, g in df.groupby("scenario_categorie", dropna=False):
        cat_rows.append({
            "Catégorie": cat or "Non renseignée",
            "Total": len(g),
            "A": int((g["classification_effective"] == "A").sum()),
            "MBA": int((g["classification_effective"] == "MBA").sum()),
            "RA": int((g["classification_effective"] == "RA").sum()),
        })
    cat_df = pd.DataFrame(cat_rows)
    if not cat_df.empty:
        st.dataframe(cat_df, use_container_width=True, hide_index=True)
        heat = cat_df.set_index("Catégorie")[["A", "MBA", "RA"]]
        fig = px.imshow(
            heat, text_auto=True, aspect="auto", color_continuous_scale="Reds",
            labels=dict(x="Classification", y="Catégorie", color="Effectif"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Section C
    st.divider()
    st.subheader("C. Par facteur de risque cardiovasculaire")
    fdr_sel = st.selectbox(
        "Sélectionner un FDR", ["—"] + FDR_OPTIONS, index=0, key="ch_fdr_sel",
    )
    if fdr_sel != "—":
        df_fdr = df.copy()
        df_fdr["has_fdr"] = df_fdr["fdr"].apply(lambda l: fdr_sel in (l or []))
        cmp = []
        for label, sub in (
            (f"Avec {fdr_sel}", df_fdr[df_fdr["has_fdr"]]),
            (f"Sans {fdr_sel}", df_fdr[~df_fdr["has_fdr"]]),
        ):
            n = len(sub)
            cmp.append({
                "Groupe": label,
                "N": n,
                "% A": (sub["classification_effective"] == "A").mean() * 100 if n else 0,
                "% MBA": (sub["classification_effective"] == "MBA").mean() * 100 if n else 0,
                "% RA": (sub["classification_effective"] == "RA").mean() * 100 if n else 0,
            })
        st.dataframe(pd.DataFrame(cmp), use_container_width=True, hide_index=True)

    # Section D
    st.divider()
    st.subheader("D. Distribution des scores AUC")
    scores = df["score_auc"].dropna()
    if scores.empty:
        st.caption("Pas de scores à afficher.")
    else:
        fig = px.histogram(
            df, x="score_auc", nbins=9, range_x=[0.5, 9.5],
            title="Distribution des scores AUC (1-9)",
        )
        fig.update_xaxes(dtick=1)
        fig.add_vline(x=3.5, line_dash="dash", line_color="red",
                      annotation_text="RA / MBA")
        fig.add_vline(x=6.5, line_dash="dash", line_color="green",
                      annotation_text="MBA / A")
        st.plotly_chart(fig, use_container_width=True)


# ===== ONGLET 4 — Concordance & contournement =====
def _onglet_concordance(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Aucune demande à analyser.")
        return

    st.subheader("A. Concordance CDSS vs reclassement médecin")
    reclasses = df[df["classification_medecin"].notna() & df["classification"].notna()]
    if len(reclasses) < 2:
        st.info(
            f"Aucun reclassement médecin pour le moment ({len(reclasses)} reclassement(s)). "
            "Reclasse au moins quelques demandes via le module Médecin Nucléaire pour "
            "activer cette analyse."
        )
    else:
        y_true = reclasses["classification"].tolist()
        y_pred = reclasses["classification_medecin"].tolist()
        cm = confusion_matrix(y_true, y_pred, labels=CLASSIFICATIONS)
        cm_df = pd.DataFrame(
            cm,
            index=[f"CDSS {c}" for c in CLASSIFICATIONS],
            columns=[f"Médecin {c}" for c in CLASSIFICATIONS],
        )
        st.markdown(
            "**Matrice de confusion** (lignes : classification automatique CDSS ; "
            "colonnes : reclassement médecin)"
        )
        st.dataframe(cm_df, use_container_width=True)

        try:
            kappa = cohen_kappa_score(y_true, y_pred, labels=CLASSIFICATIONS, weights="linear")
        except (ValueError, TypeError):
            kappa = cohen_kappa_score(y_true, y_pred, labels=CLASSIFICATIONS)

        if kappa < 0.40:
            interp = "faible"
        elif kappa < 0.60:
            interp = "modéré"
        elif kappa < 0.80:
            interp = "substantiel"
        else:
            interp = "excellent"

        st.metric(
            "Coefficient kappa de Cohen (pondéré linéaire)",
            f"{kappa:.3f}",
            delta=f"Accord {interp}",
        )

    st.divider()
    st.subheader("B. Analyse du contournement (forçage de RA)")

    ra = df[df["classification"] == "RA"]
    ra_forcees = ra[ra["justification_forcage"].notna()]
    nb_ra, nb_forc = len(ra), len(ra_forcees)
    pct_forc = nb_forc / nb_ra * 100 if nb_ra else 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("RA totales", nb_ra)
    with col2:
        st.metric("RA forcées", f"{nb_forc} ({pct_forc:.0f}%)")

    if ra_forcees.empty:
        st.caption("Aucune demande RA forcée pour le moment.")
    else:
        st.markdown("**Justifications de forçage**")
        for _, row in ra_forcees.iterrows():
            spec = row.get("specialite") or "spécialité inconnue"
            st.markdown(
                f"<div style='background-color:#fff3cd; padding:10px; margin:4px 0; "
                f"border-left:4px solid #ffc107; border-radius:4px;'>"
                f"<strong>{row['id']}</strong> ({spec}) — "
                f"<em>{row['justification_forcage']}</em>"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("**Forçage par spécialité**")
        forc_spec = ra_forcees.groupby("specialite", dropna=False).size().reset_index(name="Forçages")
        st.dataframe(forc_spec, use_container_width=True, hide_index=True)

        st.markdown("**Décision finale du médecin nucléaire sur les RA forcées**")
        decisions = ra_forcees.groupby("statut", dropna=False).size().reset_index(name="Effectif")
        st.dataframe(decisions, use_container_width=True, hide_index=True)


# ===== ONGLET 5 — Exports =====
def _build_excel_export(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    flat = df.copy()
    flat["fdr_str"] = flat["fdr"].apply(lambda l: ", ".join(l) if l else "")
    flat["atcd_str"] = flat["atcd"].apply(lambda l: ", ".join(l) if l else "")
    flat["reponses_json"] = flat["reponses"].apply(
        lambda d: json.dumps(d, ensure_ascii=False)
    )
    drop_cols = ["fdr", "atcd", "reponses", "donnees_patient"]
    flat = flat.drop(columns=[c for c in drop_cols if c in flat.columns])

    total = len(df)
    stats_rows = [{"Indicateur": "Total demandes", "Valeur": total}]
    for c in CLASSIFICATIONS:
        n = int((df["classification_effective"] == c).sum())
        stats_rows.append({
            "Indicateur": f"% {c}",
            "Valeur": f"{n/total*100:.1f}% ({n}/{total})" if total else "—",
        })
    dv = df["duree_validation_secondes"].dropna()
    stats_rows.append({
        "Indicateur": "Temps moyen validation (s)",
        "Valeur": f"{dv.mean():.1f}" if not dv.empty else "—",
    })

    comp_rows = []
    df_p1 = df[df["phase_etude"] == "Phase 1"]
    df_p3 = df[df["phase_etude"] == "Phase 3"]
    if not df_p1.empty and not df_p3.empty:
        for c in CLASSIFICATIONS:
            comp_rows.append({
                "Classification": c,
                "Phase 1": f"{(df_p1['classification_effective']==c).mean()*100:.1f}%",
                "Phase 3": f"{(df_p3['classification_effective']==c).mean()*100:.1f}%",
            })

    forc = df[df["justification_forcage"].notna()][
        ["id", "specialite", "classification", "justification_forcage", "statut", "decision_medecin"]
    ]

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        flat.to_excel(writer, sheet_name="Demandes", index=False)
        pd.DataFrame(stats_rows).to_excel(writer, sheet_name="Statistiques", index=False)
        if comp_rows:
            pd.DataFrame(comp_rows).to_excel(writer, sheet_name="Phase1_vs_Phase3", index=False)
        else:
            pd.DataFrame([{"Note": "Phase 1 ou Phase 3 sans données"}]).to_excel(
                writer, sheet_name="Phase1_vs_Phase3", index=False)
        if not forc.empty:
            forc.to_excel(writer, sheet_name="Forcages", index=False)
        else:
            pd.DataFrame([{"Note": "Aucune justification de forçage"}]).to_excel(
                writer, sheet_name="Forcages", index=False)

    return buf.getvalue()


def _build_html_report(df: pd.DataFrame) -> str:
    total = len(df)
    if total == 0:
        return "<html><body><p>Aucune donnée disponible.</p></body></html>"

    counts = {c: int((df["classification_effective"] == c).sum()) for c in CLASSIFICATIONS}
    pct = {c: counts[c] / total * 100 for c in CLASSIFICATIONS}
    dv = df["duree_validation_secondes"].dropna()
    duree_str = f"{dv.mean():.0f} s" if not dv.empty else "N/A"
    nb_ra = int((df["classification_effective"] == "RA").sum())
    nb_ra_force = int(
        ((df["classification_effective"] == "RA") & df["justification_forcage"].notna()).sum()
    )
    nb_ra_rejet = int(
        ((df["classification_effective"] == "RA") & (df["statut"] == "Rejetée")).sum()
    )
    dose = nb_ra_rejet * DOSE_PAR_TMP_MSV
    en_attente = int((df["statut"] == "En attente").sum())

    parts = [f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>CDSS-TMP — Rapport synthétique</title>
<style>
body {{ font-family: -apple-system, Segoe UI, sans-serif; max-width: 900px;
        margin: 30px auto; padding: 0 20px; color: #333; }}
h1 {{ color: #0d6efd; border-bottom: 2px solid #0d6efd; padding-bottom: 10px; }}
h2 {{ color: #495057; margin-top: 30px; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }}
.kpi {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center;
        border-left: 4px solid #0d6efd; }}
.kpi .v {{ font-size: 28px; font-weight: bold; color: #0d6efd; }}
.kpi .l {{ font-size: 12px; color: #6c757d; margin-top: 4px; }}
.a {{ border-left-color: #28a745; }} .a .v {{ color: #28a745; }}
.mba {{ border-left-color: #ffc107; }} .mba .v {{ color: #ffc107; }}
.ra {{ border-left-color: #dc3545; }} .ra .v {{ color: #dc3545; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
th, td {{ border: 1px solid #dee2e6; padding: 8px; text-align: left; }}
th {{ background: #e9ecef; }}
.meta {{ color: #6c757d; font-size: 12px; }}
</style></head>
<body>
<h1>CDSS-TMP — Rapport synthétique</h1>
<p class="meta">Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — Total : {total} demande(s)</p>

<h2>Indicateurs principaux</h2>
<div class="kpis">
  <div class="kpi"><div class="v">{total}</div><div class="l">Demandes totales</div></div>
  <div class="kpi a"><div class="v">{counts['A']}</div><div class="l">Appropriate ({pct['A']:.0f}%)</div></div>
  <div class="kpi mba"><div class="v">{counts['MBA']}</div><div class="l">May Be Appropriate ({pct['MBA']:.0f}%)</div></div>
  <div class="kpi ra"><div class="v">{counts['RA']}</div><div class="l">Rarely Appropriate ({pct['RA']:.0f}%)</div></div>
</div>
<div class="kpis">
  <div class="kpi"><div class="v">{duree_str}</div><div class="l">Temps moyen validation</div></div>
  <div class="kpi"><div class="v">{nb_ra_force}/{nb_ra}</div><div class="l">RA forcées (contournement)</div></div>
  <div class="kpi"><div class="v">{dose} mSv</div><div class="l">Dose évitée (RA rejetées × 10)</div></div>
  <div class="kpi"><div class="v">{en_attente}</div><div class="l">En attente</div></div>
</div>
"""]

    df_p1 = df[df["phase_etude"] == "Phase 1"]
    df_p3 = df[df["phase_etude"] == "Phase 3"]
    parts.append("<h2>Comparaison Phase 1 vs Phase 3</h2>")
    if df_p1.empty or df_p3.empty:
        parts.append(
            f"<p>Données insuffisantes (Phase 1 : {len(df_p1)}, Phase 3 : {len(df_p3)}).</p>"
        )
    else:
        parts.append("<table><tr><th>Classification</th><th>Phase 1</th><th>Phase 3</th></tr>")
        for c in CLASSIFICATIONS:
            p1 = (df_p1["classification_effective"] == c).mean() * 100
            p3 = (df_p3["classification_effective"] == c).mean() * 100
            parts.append(
                f"<tr><td>{LABEL_CLASSIF[c]}</td><td>{p1:.1f}%</td><td>{p3:.1f}%</td></tr>"
            )
        parts.append("</table>")

    parts.append("</body></html>")
    return "".join(parts)


def _onglet_exports(df: pd.DataFrame, df_all: pd.DataFrame) -> None:
    st.subheader("Exports")
    if df.empty and df_all.empty:
        st.info("Aucune donnée à exporter.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    st.markdown("### 📥 1. Export Excel complet (multi-feuilles)")
    st.caption(
        "Feuilles : Demandes (données brutes + JSON déplié) · Statistiques · "
        "Phase1_vs_Phase3 · Forcages"
    )
    excel_bytes = _build_excel_export(df_all if not df_all.empty else df)
    st.download_button(
        "📥 Télécharger Excel complet",
        data=excel_bytes,
        file_name=f"CDSS-TMP_export_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.markdown("### 📊 2. Export CSV brut")
    st.caption("Une feuille unique avec toutes les colonnes — pour R / SPSS / Python externe.")
    csv_bytes = (df if not df.empty else df_all).to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📊 Télécharger CSV",
        data=csv_bytes,
        file_name=f"CDSS-TMP_brut_{ts}.csv",
        mime="text/csv",
    )

    st.markdown("### 📄 3. Rapport HTML synthétique")
    st.caption("Téléchargez le HTML puis Ctrl+P → « Enregistrer en PDF » dans le navigateur.")
    html = _build_html_report(df_all if not df_all.empty else df)
    st.download_button(
        "📄 Télécharger HTML",
        data=html.encode("utf-8"),
        file_name=f"CDSS-TMP_rapport_{ts}.html",
        mime="text/html",
    )
