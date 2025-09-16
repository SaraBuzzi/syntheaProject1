# app.py
from pathlib import Path

import sqlalchemy
import streamlit as st
import engine, db_conn, utils

st.set_page_config(page_title="Query Demo", layout="wide")

st.title("Demo – Traduzione & Esecuzione Query")

with st.expander("Setup database", expanded=False):
    base = Path(__file__).resolve().parent
    sql_path = base / "sql" / "fragmentPatients.sql"

    if st.button("Esegui frammentazione (una tantum)"):
        try:
            db_conn.run_sql_file(sql_path)
            st.success("Frammentazione eseguita")
        except Exception as e:
            st.error(f"Errore: {e}")

sql = st.text_area("Scrivi la query", height=160, placeholder="SELECT ...")

col_opts, col_run = st.columns([3, 1])

with col_run:
    run = st.button("Esegui", type="primary", use_container_width=True)

if run:
    if not sql.strip():
        st.warning("Inserisci una query prima di eseguire.")
        st.stop()

    try:
        result = engine.run_query_router(sql)
        plan = result["plan"]
        row = result["row"]

        st.subheader("Strategia")

        if row['strategy'] == 'server-owner':
            st.caption(f"Scelta: **{row['strategy']}**  (server -> owner) ")
            st.caption(f"Alternativa: {row['alt_strategy'] or '—'}  "
                       f"|  Risparmio (vs alt): {row['saving_pct'] or '—'}")
        elif row['strategy'] == 'owner-server':
            st.caption(f"Scelta: **{row['strategy']}** (owner -> server -> owner)")
            st.caption(f"Alternativa: {row['alt_strategy'] or '—'}  "
                       f"|  Risparmio (vs alt): {row['saving_pct'] or '—'}")
        else:
            st.caption(f"Scelta: **{row['strategy']}**")

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

    except sqlalchemy.exc.ProgrammingError as e:
        # ProgrammingError spesso incapsula errori di sintassi del DB
        msg = str(getattr(e, "orig", e)).lower()
        if "syntax" in msg or "errore di sintassi" in msg:
            st.error("L'interrogazione scritta non è sintatticamente corretta.")
        else:
            st.error("La query non può essere eseguita.")
        with st.expander("Dettagli tecnici"):
            st.write(str(e))
        st.stop()

    except sqlalchemy.exc.DBAPIError as e:
        # Altri errori dal driver (connessione, permessi, ecc.)
        st.error("Si è verificato un errore durante l'esecuzione della query.")
        with st.expander("Dettagli tecnici"):
            st.write(str(e))
        st.stop()

    except Exception as e:
        # Fallback generico
        st.error("Errore imprevisto durante l'esecuzione.")
        with st.expander("Dettagli tecnici"):
            st.exception(e)
        st.stop()


# sql = st.text_area("Scrivi la query", height=160, placeholder="SELECT ...")
# col_opts, col_run = st.columns([3, 1])
#
# with col_run:
#         run = st.button("Esegui", type="primary", use_container_width=True)
#     if run is None:
#         st.subheader("L'interrogazione scritta non è sintatticamente corretta")
#     elif run and sql.strip():
#         result = engine.run_query_router(sql)
#         plan = result["plan"]
#         row = result["row"]
#
#         st.subheader("Strategia")
#
#         if row['strategy'] == 'server-owner':
#             st.caption(f"Scelta: **{row['strategy']}**  (server -> owner) ")
#             st.caption(f"Alternativa: {row['alt_strategy'] or '—'}  "
#                        f"|  Risparmio (vs alt): {row['saving_pct'] or '—'}")
#         elif row['strategy'] == 'owner-server':
#             st.caption(f"Scelta: **{row['strategy']}** (owner -> server -> owner)")
#             st.caption(f"Alternativa: {row['alt_strategy'] or '—'}  "
#                        f"|  Risparmio (vs alt): {row['saving_pct'] or '—'}")
#         else:
#             st.caption(f"Scelta: **{row['strategy']}**")
#
#         st.subheader("Subquery generate")
#         q1, q2, q3 = st.columns(3)
#         q1.caption("Subquery lato owner")
#         q1.code(plan.get("qo") or "—", language="sql")
#         q2.caption("Subquery lato server")
#         q2.code(plan.get("qs") or "—", language="sql")
#         q3.caption("Query ricomposta (se necessaria)")
#         q3.code(plan.get("qso") or "—", language="sql")
#
#         st.subheader("Metriche")
#         m1, m2, m3 = st.columns(3)
#         m1.metric("Rows owner", row.get("result_owner"))
#         m2.metric("Rows server", row.get("result_server"))
#         m3.metric("Rows out", row.get("result_out"))
#         st.metric("Network bytes", row.get("network_bytes"))
#
#         if row.get("alt_network_bytes") is not None:
#             st.metric("Alt network bytes", row["alt_network_bytes"])
#
#         for key, titolo in [
#             ("result_owner", "Tabella owner"),
#             ("result_server", "Tabella server"),
#             ("result_out", "Tabella risultato"),
#         ]:
#             tgt = result["tables"].get(key)
#             if tgt is not None:  # ← NON usare "if tgt:"
#                 st.subheader(titolo)
#                 df = utils._load_output(tgt, preview_limit=1000)
#                 if df is not None and not df.empty:  # ← check esplicito
#                     st.dataframe(df, use_container_width=True)
#                 else:
#                     st.caption("Nessuna riga da mostrare.")

