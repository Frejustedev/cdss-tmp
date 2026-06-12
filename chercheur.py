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

from auth import log_action
from database import get_connection

CLASSIFICATIONS = ["A", "MBA", "RA"]
COLOR_CLASSIF = {"A": "#28a745", "MBA": "#ffc107", "RA": "#dc3545"}
LABEL_CLASSIF = {"A": "Appropriate", "MBA": "May Be Appropriate", "RA": "Rarely Appropriate"}
DOSE_PAR_TMP_MSV = 12.9  # mSv évitables (protocole 1 jour stress-repos 99mTc-Sestamibi, ICRP 128)
FDR_OPTIONS = [
    "HTA", "Diabète type 1", "Diabète type 2", "Dyslipidémie",
    "Tabac actif", "Tabac sevré", "ATCD familial CAD précoce",
]
PHASE_UI_TO_DB = {
    "Toutes": None,
    "Audit (rétrospectif)": "Audit",
    "Prospective (post-DES)": "Prospective",
}


def _fmt_dt(val, length: int = 16) -> str:
    """Formate une date BDD (datetime PostgreSQL ou string ISO SQLite) + None."""
    if val is None:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d %H:%M" if length >= 16 else "%Y-%m-%d")
    return str(val)[:length].replace("T", " ")


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
        "Audit vs Prospective",
        "Analyses détaillées",
        "Concordance & contournement",
        "Concordance AUC ↔ ESC",
        "Exports",
        "🔍 Audit Log",
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
        _onglet_concordance_esc(df)
    with tabs[5]:
        _onglet_exports(df, df_all)
    with tabs[6]:
        _onglet_audit_log()


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
            f"{r['id']} — {_fmt_dt(r['date_creation'], 10)} — {r['phase_etude'] or 'NULL'}"
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
            ["Audit", "Prospective"],
            horizontal=True,
            key="ch_new_phase",
        )

        if st.button("Appliquer le changement de phase"):
            if not selected:
                st.warning("Sélectionne au moins une demande.")
            else:
                ids = [id_map[s] for s in selected]
                with get_connection() as conn:
                    olds = {
                        r["id"]: r["phase_etude"]
                        for r in conn.execute(
                            f"SELECT id, phase_etude FROM demandes "
                            f"WHERE id IN ({','.join('?' * len(ids))})",
                            ids,
                        )
                    }
                    conn.executemany(
                        "UPDATE demandes SET phase_etude = ? WHERE id = ?",
                        [(new_phase, i) for i in ids],
                    )
                for did in ids:
                    log_action(
                        "Modification phase étude", "Chercheur",
                        f"{olds.get(did, 'NULL')} → {new_phase}", did,
                    )
                st.success(f"{len(ids)} demande(s) marquée(s) comme {new_phase}.")
                st.rerun()


# ===== Chargement des demandes =====
def _parse_donnees(s):
    if not s:
        return {}
    # PostgreSQL JSONB renvoie déjà un dict ; SQLite renvoyait une string.
    if isinstance(s, dict):
        return s
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
        SELECT d.*, s.categorie AS scenario_categorie, s.source AS scenario_source,
               s.classe_esc AS scenario_classe_esc,
               s.conformite_esc AS scenario_conformite_esc,
               s.divergence_esc AS scenario_divergence_esc
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
    # Conformité ESC effective : celle de la demande, sinon celle du scénario.
    if "conformite_esc" in df.columns:
        df["conformite_esc_eff"] = df["conformite_esc"].fillna(
            df.get("scenario_conformite_esc")
        )
    else:
        df["conformite_esc_eff"] = df.get("scenario_conformite_esc")
    return df


# ===== ONGLET 1 — Vue d'ensemble =====
def _onglet_vue_ensemble(df: pd.DataFrame, df_all: pd.DataFrame) -> None:
    if df.empty:
        st.info("Aucune demande dans le filtre actuel.")
        return

    total = len(df)
    counts = {c: int((df["classification_effective"] == c).sum()) for c in CLASSIFICATIONS}
    pct = {c: counts[c] / total * 100 if total else 0 for c in CLASSIFICATIONS}

    df_p1 = df_all[df_all["phase_etude"] == "Audit"] if not df_all.empty else df_all
    df_p3 = df_all[df_all["phase_etude"] == "Prospective"] if not df_all.empty else df_all
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
        d = f"{delta_pct['A']:+.1f}% vs Audit" if delta_pct["A"] is not None else None
        st.metric("🟢 Appropriate", f"{counts['A']} ({pct['A']:.0f}%)", delta=d)
    with cols[2]:
        d = f"{delta_pct['MBA']:+.1f}% vs Audit" if delta_pct["MBA"] is not None else None
        st.metric("🟡 May Be Appropriate", f"{counts['MBA']} ({pct['MBA']:.0f}%)", delta=d)
    with cols[3]:
        d = f"{delta_pct['RA']:+.1f}% vs Audit" if delta_pct["RA"] is not None else None
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
            help="(RA rejetées par le médecin) × 12,9 mSv (1 jour stress-repos 99mTc, ICRP 128).",
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


# ===== ONGLET 2 — Audit vs Prospective =====
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

    df_p1 = df_all[df_all["phase_etude"] == "Audit"]
    df_p3 = df_all[df_all["phase_etude"] == "Prospective"]
    n1, n3 = len(df_p1), len(df_p3)

    if n1 == 0 or n3 == 0:
        st.info(
            f"Données insuffisantes pour comparaison "
            f"(Audit : {n1} demandes, Prospective : {n3}). "
            "Marque au moins quelques demandes comme Audit via le panneau "
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
            "Audit": f"{x1/n1*100:.1f}% ({x1}/{n1})",
            "Prospective": f"{x3/n3*100:.1f}% ({x3}/{n3})",
            "Différence (Prospective − Audit)": f"{diff*100:+.1f}%",
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
            "Audit": f"{t1.mean():.0f} s (n={len(t1)})",
            "Prospective": f"{t3.mean():.0f} s (n={len(t3)})",
            "Différence (Prospective − Audit)": f"{t3.mean() - t1.mean():+.0f} s",
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
        f"{ra_p1/n1*100:.1f}% (Audit) à {ra_p3/n3*100:.1f}% (Prospective), "
        f"différence {diff*100:+.1f}% (IC 95% [{lo*100:.1f}, {hi*100:.1f}], p={p_value:.3f})."
        f"</div>",
        unsafe_allow_html=True,
    )

    st.divider()
    st.subheader("Distribution par classification : Audit vs Prospective")
    bars = []
    for ph, df_ph in (("Audit", df_p1), ("Prospective", df_p3)):
        for c in CLASSIFICATIONS:
            bars.append({
                "Phase": ph,
                "Classification": LABEL_CLASSIF[c],
                "Effectif": int((df_ph["classification_effective"] == c).sum()),
            })
    fig = px.bar(
        pd.DataFrame(bars), x="Classification", y="Effectif", color="Phase",
        barmode="group",
        color_discrete_map={"Audit": "#6c757d", "Prospective": "#0d6efd"},
    )
    st.plotly_chart(fig, use_container_width=True)

    if len(t1) > 0 and len(t3) > 0:
        st.subheader("Temps de validation : Audit vs Prospective")
        box_df = pd.concat([
            pd.DataFrame({"Phase": "Audit", "Durée (s)": t1}),
            pd.DataFrame({"Phase": "Prospective", "Durée (s)": t3}),
        ])
        fig2 = px.box(
            box_df, x="Phase", y="Durée (s)", color="Phase",
            color_discrete_map={"Audit": "#6c757d", "Prospective": "#0d6efd"},
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


# ===== ONGLET — Concordance AUC ↔ ESC (hypothèse H2) =====
def _onglet_concordance_esc(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("Aucune demande à analyser.")
        return

    st.subheader("Concordance entre les référentiels AUC et ESC (hypothèse H2)")
    st.caption(
        "Cet onglet mesure l'accord entre la classification AUC (binarisée "
        "Appropriée / Non-appropriée) et la conformité ESC (Adhérent / Non-adhérent), "
        "conformément à l'approche de Liga & Gimelli (2024)."
    )

    if "conformite_esc_eff" not in df.columns:
        st.info("Aucune donnée ESC disponible.")
        return

    sub = df[df["conformite_esc_eff"].notna() & df["classification_effective"].notna()].copy()
    if len(sub) < 2:
        st.info(
            f"Pas assez de demandes évaluées sur les deux référentiels "
            f"({len(sub)} demande(s)). Saisis quelques demandes via le module "
            "Prescripteur pour activer cette analyse."
        )
        return

    # Binarisation AUC : A => "Appropriée" ; MBA et RA => "Non-appropriée".
    # (MBA est rapproché de Non-appropriée pour un parallèle binaire avec l'ESC.)
    def auc_binaire(c):
        return "Appropriée" if c == "A" else "Non-appropriée"

    def esc_binaire(c):
        return "Appropriée" if c == "Adhérent" else "Non-appropriée"

    sub["auc_bin"] = sub["classification_effective"].apply(auc_binaire)
    sub["esc_bin"] = sub["conformite_esc_eff"].apply(esc_binaire)

    labels_bin = ["Appropriée", "Non-appropriée"]
    cm = confusion_matrix(sub["auc_bin"], sub["esc_bin"], labels=labels_bin)
    cm_df = pd.DataFrame(
        cm,
        index=[f"AUC {l}" for l in labels_bin],
        columns=[f"ESC {l}" for l in labels_bin],
    )
    st.markdown("**Matrice de concordance AUC × ESC**")
    st.dataframe(cm_df, use_container_width=True)

    # Taux de concordance brut + kappa de Cohen.
    concordants = int((sub["auc_bin"] == sub["esc_bin"]).sum())
    taux = concordants / len(sub) * 100

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Taux de concordance brut", f"{taux:.1f} %",
                  delta=f"{concordants}/{len(sub)} demandes")
    with col2:
        homogene = sub["auc_bin"].nunique() < 2 or sub["esc_bin"].nunique() < 2
        try:
            kappa = cohen_kappa_score(sub["auc_bin"], sub["esc_bin"], labels=labels_bin)
        except (ValueError, TypeError):
            kappa = float("nan")
        # cohen_kappa_score renvoie NaN (sans lever) quand une seule classe est
        # présente (cas fréquent en début d'étude) : 0/0. On le traite à part
        # pour ne pas afficher un faux « accord excellent ».
        if homogene or kappa is None or np.isnan(kappa):
            st.metric("Kappa de Cohen (AUC ↔ ESC)", "N/A",
                      delta="Variabilité insuffisante", delta_color="off")
        else:
            if kappa < 0.20:
                interp = "léger"
            elif kappa < 0.40:
                interp = "faible"
            elif kappa < 0.60:
                interp = "modéré"
            elif kappa < 0.80:
                interp = "substantiel"
            else:
                interp = "excellent"
            st.metric("Kappa de Cohen (AUC ↔ ESC)", f"{kappa:.3f}",
                      delta=f"Accord {interp}")

    st.caption(
        "Interprétation selon Landis & Koch (1977). L'hypothèse H2 du mémoire "
        "attend un kappa > 0,60 (accord substantiel)."
    )

    st.divider()
    st.subheader("Demandes divergentes (AUC ≠ ESC)")
    divergentes = sub[sub["auc_bin"] != sub["esc_bin"]]
    if divergentes.empty:
        st.success("Aucune demande divergente : AUC et ESC concordent sur tous les cas évalués.")
    else:
        cols_aff = ["id", "scenario_id", "classification_effective",
                    "conformite_esc_eff", "scenario_divergence_esc"]
        cols_aff = [c for c in cols_aff if c in divergentes.columns]
        aff = divergentes[cols_aff].rename(columns={
            "classification_effective": "Classif. AUC",
            "conformite_esc_eff": "Conformité ESC",
            "scenario_divergence_esc": "Type de divergence",
        })
        st.dataframe(aff, use_container_width=True, hide_index=True)


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

    # Excel/openpyxl rejette les datetimes tz-aware. Les colonnes TIMESTAMPTZ
    # (date_creation, timestamp_ouverture/decision) reviennent tz-aware de
    # PostgreSQL → on retire le fuseau avant l'écriture.
    for col in flat.columns:
        s = flat[col]
        if isinstance(s.dtype, pd.DatetimeTZDtype):
            flat[col] = s.dt.tz_localize(None)
        elif s.dtype == object:
            flat[col] = s.map(
                lambda v: v.replace(tzinfo=None)
                if hasattr(v, "tzinfo") and getattr(v, "tzinfo", None) is not None
                else v
            )

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
    df_p1 = df[df["phase_etude"] == "Audit"]
    df_p3 = df[df["phase_etude"] == "Prospective"]
    if not df_p1.empty and not df_p3.empty:
        for c in CLASSIFICATIONS:
            comp_rows.append({
                "Classification": c,
                "Audit": f"{(df_p1['classification_effective']==c).mean()*100:.1f}%",
                "Prospective": f"{(df_p3['classification_effective']==c).mean()*100:.1f}%",
            })

    forc = df[df["justification_forcage"].notna()][
        ["id", "specialite", "classification", "justification_forcage", "statut", "decision_medecin"]
    ]

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        flat.to_excel(writer, sheet_name="Demandes", index=False)
        pd.DataFrame(stats_rows).to_excel(writer, sheet_name="Statistiques", index=False)
        if comp_rows:
            pd.DataFrame(comp_rows).to_excel(writer, sheet_name="Audit_vs_Prospective", index=False)
        else:
            pd.DataFrame([{"Note": "Audit ou Prospective sans données"}]).to_excel(
                writer, sheet_name="Audit_vs_Prospective", index=False)
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
  <div class="kpi"><div class="v">{dose} mSv</div><div class="l">Dose évitée (RA rejetées × 12,9)</div></div>
  <div class="kpi"><div class="v">{en_attente}</div><div class="l">En attente</div></div>
</div>
"""]

    df_p1 = df[df["phase_etude"] == "Audit"]
    df_p3 = df[df["phase_etude"] == "Prospective"]
    parts.append("<h2>Comparaison Audit vs Prospective</h2>")
    if df_p1.empty or df_p3.empty:
        parts.append(
            f"<p>Données insuffisantes (Audit : {len(df_p1)}, Prospective : {len(df_p3)}).</p>"
        )
    else:
        parts.append("<table><tr><th>Classification</th><th>Audit</th><th>Prospective</th></tr>")
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
        "Audit_vs_Prospective · Forcages"
    )
    src = df_all if not df_all.empty else df
    excel_bytes = _build_excel_export(src)
    if st.download_button(
        "📥 Télécharger Excel complet",
        data=excel_bytes,
        file_name=f"CDSS-TMP_export_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ):
        log_action("Export Excel", "Chercheur", f"{len(src)} demandes", None)

    st.markdown("### 📊 2. Export CSV brut")
    st.caption("Une feuille unique avec toutes les colonnes — pour R / SPSS / Python externe.")
    src_csv = df if not df.empty else df_all
    csv_bytes = src_csv.to_csv(index=False).encode("utf-8-sig")
    if st.download_button(
        "📊 Télécharger CSV",
        data=csv_bytes,
        file_name=f"CDSS-TMP_brut_{ts}.csv",
        mime="text/csv",
    ):
        log_action("Export CSV", "Chercheur", f"{len(src_csv)} demandes", None)

    st.markdown("### 📄 3. Rapport HTML synthétique")
    st.caption("Téléchargez le HTML puis Ctrl+P → « Enregistrer en PDF » dans le navigateur.")
    src_html = df_all if not df_all.empty else df
    html = _build_html_report(src_html)
    if st.download_button(
        "📄 Télécharger HTML",
        data=html.encode("utf-8"),
        file_name=f"CDSS-TMP_rapport_{ts}.html",
        mime="text/html",
    ):
        log_action("Export HTML", "Chercheur", f"{len(src_html)} demandes", None)


def _onglet_audit_log() -> None:
    """Onglet Audit Log — visible uniquement par les admins (filtré par auth dans app.py)."""
    st.subheader("🔍 Audit Log")
    st.caption(
        "Trace de toutes les actions sensibles : connexions, soumissions, "
        "validations, rejets, reclassements, modifications de phase, exports."
    )

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC"
        ).fetchall()

    if not rows:
        st.info("Aucune action loguée pour le moment.")
        return

    df = pd.DataFrame([dict(r) for r in rows])

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        date_debut = st.date_input("Du", value=None, key="audit_dd")
    with col2:
        date_fin = st.date_input("Au", value=None, key="audit_df")
    with col3:
        users = sorted({u for u in df["utilisateur"].dropna().tolist()})
        user_filter = st.selectbox("Utilisateur", ["Tous"] + users, key="audit_user")
    with col4:
        modules = sorted({m for m in df["module"].dropna().tolist()})
        module_filter = st.selectbox("Module", ["Tous"] + modules, key="audit_module")
    with col5:
        actions = sorted({a for a in df["action"].dropna().tolist()})
        action_filter = st.selectbox("Action", ["Toutes"] + actions, key="audit_action")

    filtered = df.copy()
    if date_debut:
        filtered = filtered[pd.to_datetime(filtered["timestamp"]).dt.date >= date_debut]
    if date_fin:
        filtered = filtered[pd.to_datetime(filtered["timestamp"]).dt.date <= date_fin]
    if user_filter != "Tous":
        filtered = filtered[filtered["utilisateur"] == user_filter]
    if module_filter != "Tous":
        filtered = filtered[filtered["module"] == module_filter]
    if action_filter != "Toutes":
        filtered = filtered[filtered["action"] == action_filter]

    st.caption(f"{len(filtered)} action(s) sur {len(df)} totale(s)")
    st.dataframe(
        filtered[["timestamp", "utilisateur", "role", "action", "module",
                  "details", "demande_id"]],
        use_container_width=True, hide_index=True,
    )

    csv = filtered.to_csv(index=False).encode("utf-8-sig")
    if st.download_button(
        "📥 Export Audit Log CSV",
        data=csv,
        file_name=f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    ):
        log_action(
            "Export Audit Log", "Chercheur",
            f"{len(filtered)} lignes", None,
        )
