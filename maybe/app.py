# app.py
from pathlib import Path
import streamlit as st
from pandas import read_table

import engine, db_conn, utils

st.set_page_config(page_title="Query Demo", layout="wide")

st.title("Demo – Traduzione & Esecuzione Query")

with st.expander("Setup database", expanded=False):
    base = Path(__file__).resolve().parent
    sql_path = base / "sql" / "fragmentPatients.sql"

    if st.button("Esegui frammentazione (una tantum)"):
        try:
            db_conn.run_sql_file(sql_path)
            st.success("Frammentazione eseguita ✅")
        except Exception as e:
            st.error(f"Errore: {e}")

sql = st.text_area("Scrivi la query", height=160, placeholder="SELECT ...")

col_opts, col_run = st.columns([3, 1])
with col_opts:
    also_alt = st.checkbox("Confronta strategia alternativa", value=True)
with col_run:
    run = st.button("Esegui", type="primary", use_container_width=True)

if run and sql.strip():

    result = engine.run_query_router(sql)
    plan = result["plan"]
    row = result["row"]

    st.subheader("Strategia")
    st.caption(f"Scelta: **{row['strategy']}**  |  Alternativa: {row['alt_strategy'] or '—'}  "
               f"|  Risparmio (vs alt): {row['saving_pct'] or '—'}")

    st.subheader("Subquery generate")
    q1, q2, q3 = st.columns(3)
    q1.caption("Subquery lato owner")
    q1.code(plan.get("qo") or "—", language="sql")
    q2.caption("Subquery lato server")
    q2.code(plan.get("qs") or "—", language="sql")
    q3.caption("Query ricomposta (se necessaria)")
    q3.code(plan.get("qso") or "—", language="sql")

    st.subheader("Metriche")
    m1, m2, m3 = st.columns(3)
    m1.metric("Rows owner", row.get("result_owner"))
    m2.metric("Rows server", row.get("result_server"))
    m3.metric("Rows out", row.get("result_out"))
    st.metric("Network bytes", row.get("network_bytes"))

    if row.get("alt_network_bytes") is not None:
        st.metric("Alt network bytes", row["alt_network_bytes"])

    for key, titolo in [
        ("result_owner", "Tabella owner"),
        ("result_server", "Tabella server"),
        ("result_out", "Tabella risultato"),
    ]:
        tgt = result["tables"].get(key)
        if tgt is not None:  # ← NON usare "if tgt:"
            st.subheader(titolo)
            df = utils._load_output(tgt, preview_limit=1000)
            if df is not None and not df.empty:  # ← check esplicito
                st.dataframe(df, use_container_width=True)
            else:
                st.caption("Nessuna riga da mostrare.")

