import os
import re
import uuid
from typing import Tuple, Set, List, Dict

import pandas as pd

import utils



# SELECT FROM WHERE
def parse_query(query: str) -> Tuple[Set[str], str]:
    select_match = re.search(r"SELECT\s+(.*?)\s+FROM", query, flags=re.IGNORECASE | re.DOTALL)
    where_match = re.search(r"WHERE\s+(.*)", query, flags=re.IGNORECASE | re.DOTALL)
    if not select_match or not where_match:
        raise ValueError("La query deve contenere sia SELECT che WHERE.")

    select_fields = {tok.lower() for tok in re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', select_match.group(1))}
    where_clause = where_match.group(1).strip()
    return select_fields, where_clause


def extract_conditions(where_clause: str) -> Tuple[List[str], bool]:
    if " OR " in where_clause.upper():
        conditions = [c.strip() for c in re.split(r"\bOR\b", where_clause, flags=re.IGNORECASE)]
        return conditions, True
    else:
        conditions = [c.strip() for c in re.split(r"\bAND\b", where_clause, flags=re.IGNORECASE)]
        return conditions, False


def classify_conditions(conditions: List[str], Fo: Set[str], Fs: Set[str]) -> Dict[str, List[str]]:
    Co, Cs, Cso = [], [], []
    for cond in conditions:
        attrs = {tok.lower() for tok in re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', cond)}
        in_owner = attrs & Fo
        in_server = attrs & Fs
        if in_owner and in_server:
            Cso.append(cond)
        elif in_owner:
            Co.append(cond)
        elif in_server:
            Cs.append(cond)
    return {"Co": Co, "Cs": Cs, "Cso": Cso}



def choose_strategy(classified, has_or,sel_attrs,Fo,Fs,
                    table="patients",
                    schema_owner="owner", schema_server="server",
                    bytes_owner=1.0, bytes_server=1.0) -> str:
    Co = classified.get("Co", [])
    Cs = classified.get("Cs", [])
    Cso = classified.get("Cso", [])


    def _sel(preds: list[str], schema: str) -> float:
        s = 1.0
        for c in preds:
            s *= max(min(utils.calcola_selettivita(schema, table, c), 1.0), 1e-6)
        return s

    sel_owner = set()
    sel_server = set()
    if sel_attrs and Fo is not None and Fs is not None:
        sel_owner = (set(a.lower() for a in sel_attrs) & set(x.lower() for x in Fo)) - {"id"}
        sel_server = (set(a.lower() for a in sel_attrs) & set(x.lower() for x in Fs)) - {"id"}


    if Cso:

        if Co and not Cs:
            f_o = _sel(Co, schema_owner)
            cost_os = f_o * (bytes_server + bytes_owner)
            cost_so = bytes_server
            return "owner-server" if cost_os < cost_so else "server-owner"

        if Cs and not Co:
            return "server-owner"

        if Co and Cs:
            f_o = _sel(Co, schema_owner)
            f_s = _sel(Cs, schema_server)

            cost_os = f_o * (bytes_server + bytes_owner)
            cost_so = f_s * bytes_server
            return "owner-server" if cost_os < cost_so else "server-owner"

        return "server-owner"

    if has_or:
        if Co and Cs:
            return "parallel"
        if Co:
            return "owner-only"  if not sel_server else "owner-server"
        if Cs:
            return "server-only" if not sel_owner  else "server-owner"
        return "unknown"

    if Co and not Cs:
        return "owner-only"  if not sel_server else "owner-server"
    if Cs and not Co:
        return "server-only" if not sel_owner  else "server-owner"
    if Co and Cs:
        cost_o = _sel(Co, schema_owner) * bytes_owner
        cost_s = _sel(Cs, schema_server) * bytes_server
        return "owner-server" if cost_o < cost_s else "server-owner"

    return "unknown"


def generate_subqueries(Co, Cs, Cso, select_attrs, Fo, Fs, strategy, has_or=False):
    join_o = " OR " if (has_or and not Cs and not Cso) else " AND "
    join_s = " OR " if (has_or and not Co and not Cso) else " AND "

    sel_attrs = {a.lower() for a in select_attrs}

    sel_o = sorted(sel_attrs & Fo)
    sel_s = sorted((sel_attrs & Fs) - {'id'})

    fs_in_cso = {
        a.lower()
        for cond in Cso
        for a in re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', cond)
        if a.lower() in Fs
    }

    Aqs = sorted(((sel_attrs & Fs) | fs_in_cso) - {'id'})
    proj_owner_final = [f"o.{c}" for c in sel_o] if sel_o else ["o.id"]
    proj_server_final = [f"s.{c}" for c in sel_s]
    owner_final = ", ".join(proj_owner_final)
    server_final = ", ".join(proj_server_final)
    sel_both_list = ", ".join(proj_owner_final + proj_server_final)

    qs = qo = qso = None

    if strategy == "server-owner":
        # SERVER → OWNER
        proj_qs = ", ".join(["s.id"] + [f"s.{c}" for c in Aqs])
        qs = f"SELECT {proj_qs} FROM server.patients_server s" + (f" WHERE {' AND '.join(Cs)}" if Cs else "")
        qso = f"SELECT {sel_both_list} FROM owner.patients_owner o JOIN Rs s USING (id)" \
              + (f" WHERE {' AND '.join(Co + Cso)}" if (Co or Cso) else "")

    elif strategy == "owner-server":
        # OWNER → SERVER → JOIN
        qo = "SELECT o.id FROM owner.patients_owner o" + (f" WHERE {' AND '.join(Co)}" if Co else "")
        proj_qs = ", ".join(["s.id"] + [f"s.{c}" for c in Aqs])
        qs = f"SELECT {proj_qs} FROM server.patients_server s JOIN Ro r USING (id)" \
             + (f" WHERE {' AND '.join(Cs)}" if Cs else "")
        qso = f"SELECT {sel_both_list} FROM owner.patients_owner o JOIN Rs s USING (id)" \
              + (f" WHERE {' AND '.join(Cso)}" if Cso else "")

    elif strategy == "owner-only":
        qo = f"SELECT {owner_final} FROM owner.patients_owner o" \
              + (f" WHERE {join_o.join(Co)}" if Co else "")

    elif strategy == "server-only":
        server_proj = server_final if server_final else "s.id"
        qs = f"SELECT {server_proj} FROM server.patients_server s" \
              + (f" WHERE {join_s.join(Cs)}" if Cs else "")

    elif strategy == "parallel":
        sel_attrs = {a.lower() for a in select_attrs}
        owner_cols = [f"o.{c}" for c in sorted((sel_attrs & Fo) - {'id'})]
        server_cols = [f"s.{c}" for c in sorted((sel_attrs & Fs) - {'id'})]

        #  OWNER
        qo = "SELECT " + ", ".join(["o.id"] + owner_cols) + " FROM owner.patients_owner o" \
             + (f" WHERE {' OR '.join(Co)}" if Co else "")

        # SERVER
        qs = "SELECT " + ", ".join(["s.id"] + server_cols) + " FROM server.patients_server s" \
             + (f" WHERE {' OR '.join(Cs)}" if Cs else "")

        final_sel = []
        if 'id' in sel_attrs:
            final_sel.append("u.id AS id")
        final_sel += owner_cols + server_cols
        if not final_sel:
            final_sel = ["u.id AS id"]
        sel_final_sql = ", ".join(final_sel)

        qso = f"""
            WITH U AS (
            SELECT id FROM Ro
            UNION
            SELECT id FROM Rs
                            )
            SELECT {sel_final_sql}
            FROM U u
            JOIN owner.patients_owner o USING (id)
            JOIN server.patients_server s USING (id)
            """.strip()

    else:
        raise ValueError("Strategy must be one of: server-owner, owner-server, owner-only, server-only, parallel")

    return qs, qo, qso


def process_query(query: str, Fo: Set[str], Fs: Set[str]) -> Dict[str, any]:
    select_attrs, where = parse_query(query)
    conditions, has_or = extract_conditions(where)
    classified = classify_conditions(conditions, Fo, Fs)
    strategy = choose_strategy(classified, has_or, select_attrs, Fo, Fs)

    s = strategy.lower()
    if "parallel" in s:
        strategy_key = "parallel"
    elif "owner-server" in s:
        strategy_key = "owner-server"
    elif "server-owner" in s:
        strategy_key = "server-owner"
    elif "owner-only" in s:
        strategy_key = "owner-only"
    elif "server-only" in s:
        strategy_key = "server-only"
    else:
        strategy_key = "unknown"

    qs, qo, qso = generate_subqueries(
        classified["Co"], classified["Cs"], classified["Cso"],
        select_attrs, Fo, Fs,
        strategy_key,
        has_or=has_or
    )

    return {
        "Query": query,
        "SELECT": select_attrs,
        "WHERE": where,
        "Condizioni": conditions,
        "Classificazione": classified,
        "Strategia": strategy_key,
        "qs": qs,  # query lato server (può essere None)
        "qo": qo,  # query lato owner  (può essere None)
        "qso": qso,  # query che interpella entrambi (può essere None in parallel)
    }

def _replan_alternative(plan: dict, Fo: set, Fs: set) -> dict | None:
    Co = plan["Classificazione"]["Co"]
    Cs = plan["Classificazione"]["Cs"]

    alt = {"owner-server": "server-owner", "server-owner": "owner-server"}.get(plan["Strategia"].lower())
    if not alt:
        return None
    qs, qo, qso = generate_subqueries(Co, Cs, plan["Classificazione"]["Cso"], plan["SELECT"], Fo, Fs, alt)
    return {
        "Strategia": alt,
        "SELECT": plan["SELECT"],
        "Classificazione": plan["Classificazione"],
        "qs": qs, "qo": qo, "qso": qso
    }


def evaluate_query(query: str,
                   Fo: set, Fs: set,
                   tag: str | None = None,
                   schema: str = "work",
                   save_to: str | None = None,
                   also_compare_alt: bool = True) -> dict:
    plan = process_query(query, Fo, Fs)
    sk = plan["Strategia"]
    tag = tag or uuid.uuid4().hex[:8]

    utils.run(f"CREATE SCHEMA IF NOT EXISTS {schema};")

    ro_name = f"{schema}.ro_{tag}"
    rs_name = f"{schema}.rs_{tag}"
    out_name = f"{schema}.out_{tag}"

    counts, sizes = {}, {}

    if sk == "owner-server":
        qo = utils._strip_semicolon(plan["qo"])
        qs = utils._strip_semicolon(plan["qs"])
        qso = utils._strip_semicolon(plan["qso"])

        utils.run(f"DROP TABLE IF EXISTS {ro_name}; CREATE TABLE {ro_name} AS {qo};")
        counts["ro"] = utils._count_table(ro_name)
        sizes["ro"] = utils._size_table(ro_name)

        qs_mat = qs.replace(" Ro ", f" {ro_name} ")
        utils.run(f"DROP TABLE IF EXISTS {rs_name}; CREATE TABLE {rs_name} AS {qs_mat};")
        counts["rs"] = utils._count_table(rs_name)
        sizes["rs"] = utils._size_table(rs_name)

        qso_mat = qso.replace(" Rs ", f" {rs_name} ")
        utils.run(f"DROP TABLE IF EXISTS {out_name}; CREATE TABLE {out_name} AS {qso_mat};")
        counts["out"] = utils._count_table(out_name)
        sizes["out"] = utils._size_table(out_name)

    elif sk == "server-owner":
        qs = utils._strip_semicolon(plan["qs"])
        qso = utils._strip_semicolon(plan["qso"])

        utils.run(f"DROP TABLE IF EXISTS {rs_name}; CREATE TABLE {rs_name} AS {qs};")
        counts["rs"] = utils._count_table(rs_name)
        sizes["rs"] =utils._size_table(rs_name)

        qso_mat = qso.replace(" Rs ", f" {rs_name} ")
        utils.run(f"DROP TABLE IF EXISTS {out_name}; CREATE TABLE {out_name} AS {qso_mat};")
        counts["out"] = utils._count_table(out_name)
        sizes["out"] = utils._size_table(out_name)

    elif sk in ("owner-only", "server-only"):
        qso = utils._strip_semicolon(plan["qso"])
        utils.run(f"DROP TABLE IF EXISTS {out_name}; CREATE TABLE {out_name} AS {qso};")
        counts["out"] = utils._count_table(out_name)
        sizes["out"] = utils._size_table(out_name)

    elif sk == "parallel":
        if plan["qo"]:
            qo = utils._strip_semicolon(plan["qo"])
            utils.run(f"DROP TABLE IF EXISTS {ro_name}; CREATE TABLE {ro_name} AS {qo};")
            counts["ro"] = utils._count_table(ro_name)
            sizes["ro"] = utils._size_table(ro_name)
        if plan["qs"]:
            qs = utils._strip_semicolon(plan["qs"])
            utils.run(f"DROP TABLE IF EXISTS {rs_name}; CREATE TABLE {rs_name} AS {qs};")
            counts["rs"] = utils._count_table(rs_name)
            sizes["rs"] = utils._size_table(rs_name)

        if plan["qso"]:
            qso = utils._strip_semicolon(plan["qso"])
            qso_mat = utils._subst_token(qso, "Ro", ro_name)
            qso_mat = utils._subst_token(qso_mat, "Rs", rs_name)
            utils.run(f"DROP TABLE IF EXISTS {out_name}; CREATE TABLE {out_name} AS {qso_mat};")
            counts["out"] = utils._count_table(out_name)
            sizes["out"] = utils._size_table(out_name)

    net_bytes = utils._network_bytes_payload(
        ro_name if "ro" in sizes else None,
        rs_name if "rs" in sizes else None
    )

    alt_info = None
    if also_compare_alt and sk in ("owner-server", "server-owner"):
        alt = _replan_alternative(plan, Fo, Fs)
        if alt:
            tag_alt = tag + "_alt"
            ro_alt = f"{schema}.ro_{tag_alt}"
            rs_alt = f"{schema}.rs_{tag_alt}"
            out_alt = f"{schema}.out_{tag_alt}"
            sizes_alt = {}

            if alt["Strategia"] == "owner-server":
                qo_alt = utils._strip_semicolon(alt["qo"])
                qs_alt = utils._strip_semicolon(alt["qs"])
                qso_alt = utils._strip_semicolon(alt["qso"])

                utils.run(f"DROP TABLE IF EXISTS {ro_alt}; CREATE TABLE {ro_alt} AS {qo_alt};")
                sizes_alt["ro"] = utils._size_table(ro_alt)

                qs_alt_mat = qs_alt.replace(" Ro ", f" {ro_alt} ")
                utils.run(f"DROP TABLE IF EXISTS {rs_alt}; CREATE TABLE {rs_alt} AS {qs_alt_mat};")
                sizes_alt["rs"] = utils._size_table(rs_alt)

                qso_alt_mat = qso_alt.replace(" Rs ", f" {rs_alt} ")
                utils.run(f"DROP TABLE IF EXISTS {out_alt}; CREATE TABLE {out_alt} AS {qso_alt_mat};")

            elif alt["Strategia"] == "server-owner":
                qs_alt = utils._strip_semicolon(alt["qs"])
                utils.run(f"DROP TABLE IF EXISTS {rs_alt}; CREATE TABLE {rs_alt} AS {qs_alt};")
                sizes_alt["rs"] = utils._size_table(rs_alt)

                qso_alt = utils._strip_semicolon(alt["qso"])
                qso_alt_mat = qso_alt.replace(" Rs ", f" {rs_alt} ")
                utils.run(f"DROP TABLE IF EXISTS {out_alt}; CREATE TABLE {out_alt} AS {qso_alt_mat};")

            net_alt = utils._network_bytes_payload(
                ro_alt if "ro" in sizes_alt else None,
                rs_alt if "rs" in sizes_alt else None
            )

            saving_ratio = None
            if net_alt and net_bytes:
                saving_ratio = 1 - (net_bytes / net_alt)

            alt_info = {
                "alt_strategy": alt["Strategia"],
                "alt_network_bytes": net_alt,
                "saving_pct": f"{saving_ratio * 100:.1f}%" if saving_ratio is not None else None,
                "tables_alt": {"ro": ro_alt if "ro" in sizes_alt else None,
                               "rs": rs_alt if "rs" in sizes_alt else None,
                               "out": out_alt}
            }

    row = {
        "tag": tag,
        "query": plan["Query"],
        "strategy": sk,
        "result_owner": counts.get("ro"), "result_server": counts.get("rs"), "result_out": counts.get("out"),
        "network_bytes": net_bytes,
        "alt_strategy": alt_info["alt_strategy"] if alt_info else None,
        "alt_network_bytes": alt_info["alt_network_bytes"] if alt_info else None,
        "saving_pct": alt_info["saving_pct"] if alt_info else None
    }

    if save_to:
        save_to = os.path.abspath(save_to)
        df = pd.DataFrame([row])
        header = not os.path.exists(save_to)
        df.to_csv(save_to, mode="a", index=False, header=header)

    return {
        "plan": plan,
        "row": row,
        "tables": {"result_owner": ro_name if "ro" in counts else None,
                   "result_server": rs_name if "rs" in counts else None,
                   "result_out": out_name if "out" in counts else None},
        "alt": alt_info
    }


def evaluate_queries(queries: list[str],
                     Fo: set, Fs: set,
                     schema: str = "work",
                     save_to: str | None = None,
                     also_compare_alt: bool = True) -> pd.DataFrame:
    rows = []
    for i, q in enumerate(queries, 1):
        tag = f"q{i:02d}"
        res = evaluate_query(q, Fo, Fs, tag=tag, schema=schema,
                             save_to=save_to, also_compare_alt=also_compare_alt)
        rows.append(res["row"])
    df = pd.DataFrame(rows)
    return df