# app.py
import streamlit as st
from engine import run_query_router

st.set_page_config(page_title="Query Demo", layout="wide")

st.title("Demo – Traduzione & Esecuzione Query")
mode = st.radio("Modalità", ["Auto", "Caso 1", "Caso 2", "Caso 3", "Caso 4"], horizontal=True)
sql = st.text_area("Scrivi la query", height=160, placeholder="SELECT ...")

col_opts, col_run = st.columns([3,1])
with col_opts:
    also_alt = st.checkbox("Confronta strategia alternativa", value=True)
with col_run:
    run = st.button("Esegui", type="primary", use_container_width=True)

if run and sql.strip():
    # Decidi il case
    if mode != "Auto":
        forced = int(mode.split()[-1])
        # chiama direttamente la funzione giusta se vuoi bypassare il router
        # app.py (o notebook)
        res = run_query_router(sql, Fo, Fs, also_compare_alt=True)

    else:
        result = run_query_router(sql, Fo, Fs, also_compare_alt=also_alt)

    plan = result["plan"]
    row  = result["row"]

    st.subheader("Strategia")
    st.caption(f"Scelta: **{row['strategy']}**  |  Alternativa: {row['alt_strategy'] or '—'}  "
               f"|  Risparmio (vs alt): {row['saving_pct'] or '—'}")

    st.subheader("Subquery generate")
    q1, q2, q3 = st.columns(3)
    q1.code(plan.get("qo") or "—", language="sql")
    q2.code(plan.get("qs") or "—", language="sql")
    q3.code(plan.get("qso") or "—", language="sql")

    st.subheader("Metriche")
    m1, m2, m3 = st.columns(3)
    m1.metric("Rows owner", row.get("result_owner"))
    m2.metric("Rows server", row.get("result_server"))
    m3.metric("Rows out", row.get("result_out"))
    st.metric("Network bytes", row.get("network_bytes"))

    if row.get("alt_network_bytes") is not None:
        st.metric("Alt network bytes", row["alt_network_bytes"])

    st.subheader("Tabella risultato")
    # se vuoi visualizzare il risultato finale:
    # df = read_table(result["tables"]["result_out"])  # tua util
    # st.dataframe(df)
