import re
from typing import List, Set, Tuple, Dict, Optional, Any
import os, uuid
import pandas as pd
from sqlalchemy import text

import utils


def parse_query_groupby(query: str) -> Tuple[Set[str], Optional[str], Set[str], List[Dict[str, Any]], Optional[str]]:
    q = query.strip()
    m_sel = re.search(r"\bselect\s+(.*?)\s+from\b", q, re.I | re.S)
    if not m_sel:
        raise ValueError("SELECT ... FROM mancante.")
    sel_txt = m_sel.group(1)
    rest = q[m_sel.end():]

    # --- NUOVO: individua anche HAVING (oltre a WHERE e GROUP BY) ---
    markers = []   
    for name, pat in [
        ("where", r"\bwhere\b"),
        ("group by", r"\bgroup\s+by\b"),
        ("having", r"\bhaving\b"),
        ("order by", r"\border\s+by\b"),
        ("limit", r"\blimit\b"),
    ]:
        m = re.search(pat, rest, re.I)
        if m:
            markers.append((name, m.start(), m.end()))
    markers.sort(key=lambda x: x[1])

    where_clause = None
    group_by_txt = None
    having_txt = None

    if markers:
        for i, (name, s, e) in enumerate(markers):
            nxt_start = markers[i + 1][1] if i + 1 < len(markers) else len(rest)
            seg = rest[e:nxt_start].strip().rstrip(";").strip()
            if name == "where":
                where_clause = seg if seg else None
            elif name == "group by":
                group_by_txt = seg if seg else None
            elif name == "having":
                having_txt = seg if seg else None
    else:
        # nessun WHERE/GROUP BY/HAVING
        pass

    # --- SELECT: separo plain vs aggregazioni ---
    select_items = utils._split_outside_parents(sel_txt)
    select_plain: Set[str] = set()
    aggs: List[Dict[str, Any]] = []

    agg_re_full = re.compile(
        r"^(count|sum|avg|min|max)\s*\(\s*(distinct\s+)?(\*|[a-zA-Z_][\w\.]*)\s*\)\s*(?:as\s+([a-zA-Z_]\w*))?$",
        re.I
    )
    for it in select_items:
        it_norm = it.strip()
        m = agg_re_full.match(it_norm)
        if m:
            func = m.group(1).lower()
            distinct = bool(m.group(2))
            arg_raw = m.group(3)
            alias = m.group(4).lower() if m.group(4) else None
            arg = None if arg_raw == "*" else utils._unqualify(arg_raw)
            aggs.append({"func": func, "arg": arg, "distinct": distinct, "alias": alias})
        else:
            select_plain.add(utils._unqualify(it_norm))

    # --- GROUP BY: parse colonne ---
    group_by: Set[str] = set()
    if group_by_txt:
        cols = [tok for tok in utils._split_outside_parents(group_by_txt) if tok.strip()]
        group_by = {utils._unqualify(c) for c in cols}

    # vincolo SQL: le non aggregate in SELECT devono stare nel GROUP BY
    if select_plain - group_by:
        missing = ", ".join(sorted(select_plain - group_by))
        raise ValueError(f"Le colonne non aggregate in SELECT devono apparire nel GROUP BY (manca: {missing}).")

    # --- NUOVO: normalizzazione HAVING ---
    # 1) espandi alias delle aggregazioni della SELECT dentro il HAVING
    having_clause_norm = None
    if having_txt:
        alias_map = {}
        for a in aggs:
            if a.get("alias"):
                canon = f"{a['func']}(" + ("distinct " if a["distinct"] else "")
                canon += ("*" if a["arg"] is None else a["arg"]) + ")"
                alias_map[a["alias"]] = canon
        having_norm = having_txt
        for alias, repl in alias_map.items():
            having_norm = re.sub(rf"\b{re.escape(alias)}\b", repl, having_norm, flags=re.I)
        having_clause_norm = having_norm.strip()

        # 2) aggiungi alle aggregazioni anche quelle che compaiono SOLO nel HAVING
        agg_finder = re.compile(
            r"(count|sum|avg|min|max)\s*\(\s*(distinct\s+)?(\*|[a-zA-Z_][\w\.]*)\s*\)",
            re.I
        )
        for m in agg_finder.finditer(having_clause_norm):
            func = m.group(1).lower()
            distinct = bool(m.group(2))
            arg_raw = m.group(3)
            arg = None if arg_raw == "*" else utils._unqualify(arg_raw)
            if not any(a["func"] == func and a["arg"] == arg and a["distinct"] == distinct for a in aggs):
                aggs.append({"func": func, "arg": arg, "distinct": distinct, "alias": None})

    return select_plain, (where_clause or None), group_by, aggs, (having_clause_norm or None)

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



def classify_groupby_agg(group_by: Set[str], aggs: List[Dict[str, Any]],
                         Fo: Set[str], Fs: Set[str]) -> Dict[str, Set[str]]:

    G_owner = {g for g in group_by if g in Fo}
    G_server = {g for g in group_by if g in Fs}
    Agg_owner = {a["arg"] for a in aggs if a.get("arg") and a["arg"] in Fo}
    Agg_server = {a["arg"] for a in aggs if a.get("arg") and a["arg"] in Fs}
    return {
        "G_owner": G_owner, "G_server": G_server,
        "Agg_owner": Agg_owner, "Agg_server": Agg_server,
    }



def choose_strategy(classified, has_or, sel_attrs, Fo, Fs,
                    table="patients",
                    schema_owner="owner", schema_server="server",
                    bytes_owner=1.0, bytes_server=1.0,
                    groupby_info: dict | None = None,
                    has_having: bool = False) -> str:
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

    # --- NOVITÀ: vincoli dovuti a GROUP BY / AGG (SELECT ∪ HAVING) ---
    G_owner = set()
    G_server = set()
    Agg_owner = set()
    Agg_server = set()
    if groupby_info:
        G_owner = set(groupby_info.get("G_owner", set()))
        G_server = set(groupby_info.get("G_server", set()))
        Agg_owner = set(groupby_info.get("Agg_owner", set()))
        Agg_server = set(groupby_info.get("Agg_server", set()))

    # Il server può "chiudere" la query senza passare dall'owner
    # solo se: (a) nessun attributo selezionato sta su owner,
    #          (b) nessuna chiave di GB né argomento di aggregazione sta su owner.
    server_can_finish = (len(sel_owner) == 0) and (len(G_owner) == 0 and len(Agg_owner) == 0)

    # Simmetrico per l'owner: può chiudere solo se non ha bisogno di nulla dal server
    owner_can_finish = (len(sel_server) == 0) and (len(G_server) == 0 and len(Agg_server) == 0)

    # --- CASO con predicati misti in WHERE (Cso): serve ricomposizione ---
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

    # --- WHERE con OR: mantieni logica ma evita *-only se HAVING/GB richiedono l'altro lato ---
    if has_or:
        if Co and Cs:
            return "parallel"
        if Co:
            # "owner-only" solo se non richiede nulla dal server (GB/Agg/SELECT)
            return "owner-only" if owner_can_finish else "owner-server"
        if Cs:
            # "server-only" solo se non richiede nulla dall'owner (GB/Agg/SELECT)
            return "server-only" if server_can_finish else "server-owner"
        return "unknown"

    # --- WHERE senza OR ---
    if Co and not Cs:
        return "owner-only" if owner_can_finish else "owner-server"
    if Cs and not Co:
        return "server-only" if server_can_finish else "server-owner"
    if Co and Cs:
        f_o = _sel(Co, schema_owner)
        f_s = _sel(Cs, schema_server)
        cost_o = f_o * (bytes_owner + bytes_server)
        cost_s = f_s * (bytes_owner + bytes_server)
        print(f_o, f_s, cost_o, cost_s)
        return "owner-server" if cost_o < cost_s else "server-owner"

    return "unknown"


def render_aggs_sql(aggs: List[Dict[str, Any]], Fo: Set[str]) -> str:
    exprs = []
    for a in aggs:
        func = a["func"].upper()
        distinct = "DISTINCT " if a.get("distinct") else ""
        arg = a.get("arg")
        if arg is None:
            expr = f"{func}(*)"
            alias = a.get("alias") or f"{func.lower()}_all"
        else:
            qual = "o" if arg in Fo else "s"
            expr = f"{func}({distinct}{qual}.{arg})"
            alias = a.get("alias") or f"{func.lower()}_{arg}"
        exprs.append(f"{expr} AS {alias}")
    return ", ".join(exprs)


def generate_subqueries_gb(
        select_plain: Set[str], group_by: Set[str], aggs: List[Dict[str, Any]],
        Fo: Set[str], Fs: Set[str], strategy: str,
        Co: List[str] = None, Cs: List[str] = None, Cso: List[str] = None, has_or: bool = False,
        having_clause: str | None = None
) -> Tuple[str | None, str | None, str | None]:

    Co = Co or []
    Cs = Cs or []
    Cso = Cso or []

    join_o = " OR " if (has_or and not Cs and not Cso) else " AND "
    join_s = " OR " if (has_or and not Co and not Cso) else " AND "

    sel_plain = {c.lower() for c in select_plain}
    gb = {c.lower() for c in group_by}
    agg_args = {a["arg"] for a in aggs if a.get("arg")}

    need_fs = ((sel_plain | gb | agg_args) & Fs) - {'id'}
    need_fo = ((sel_plain | gb | agg_args) & Fo) - {'id'}

    Aqs = sorted(need_fs)
    Aqo = sorted(need_fo)

    gb_owner = [f"o.{c}" for c in sorted(gb & Fo)]
    gb_server = [f"s.{c}" for c in sorted(gb & Fs)]
    gb_all = gb_owner + gb_server
    gb_sql = ", ".join(gb_all)

    aggs_sql = render_aggs_sql(aggs, Fo)
    select_parts = []
    if gb_sql:
        select_parts.append(gb_sql)
    if aggs_sql:
        select_parts.append(aggs_sql)
    final_select = ", ".join(select_parts) if select_parts else aggs_sql

    # HAVING: da aggiungere SOLO sulla query che fa il GROUP BY/aggregazioni
    having_sql = f" HAVING {having_clause}" if having_clause else ""

    qs = qo = qso = None

    if strategy == "server-owner":
        proj_qs = ", ".join(["s.id"] + [f"s.{c}" for c in Aqs])
        qs = f"SELECT {proj_qs} FROM server.patients_server s"
        if Cs:
            qs += f" WHERE {join_s.join(Cs)}"

        # JOIN + (Co, Cso) a valle + GROUP BY (+ HAVING)
        qso = f"SELECT {final_select} FROM owner.patients_owner o JOIN Rs s USING (id)"
        where_parts = []
        if Co:
            where_parts.append(join_o.join(Co))
        if Cso:
            where_parts.append(" AND ".join(Cso))  # Cso sempre dopo join
        if where_parts:
            qso += " WHERE " + " AND ".join([p for p in where_parts if p])
        if gb_sql:
            qso += f" GROUP BY {gb_sql}"
        if having_clause:
            qso += having_sql  # HAVING valutata lato owner

    elif strategy == "owner-server":
        qo = "SELECT o.id FROM owner.patients_owner o"
        if Co:
            qo += f" WHERE {join_o.join(Co)}"

        proj_qs = ", ".join(["s.id"] + [f"s.{c}" for c in Aqs])
        qs = f"SELECT {proj_qs} FROM server.patients_server s JOIN Ro r USING (id)"
        if Cs:
            qs += f" WHERE {join_s.join(Cs)}"

        # JOIN finale + Cso + GROUP BY (+ HAVING)
        qso = f"SELECT {final_select} FROM owner.patients_owner o JOIN Rs s USING (id)"
        if Cso:
            qso += " WHERE " + " AND ".join(Cso)
        if gb_sql:
            qso += f" GROUP BY {gb_sql}"
        if having_clause:
            qso += having_sql

    elif strategy == "owner-only":
        needs_server = bool(((sel_plain | gb | agg_args) & Fs))
        if needs_server:
            qo = "SELECT o.id FROM owner.patients_owner o"
            if Co:
                qo += f" WHERE {join_o.join(Co)}"
            proj_qs = ", ".join(["s.id"] + [f"s.{c}" for c in Aqs])
            qs = f"SELECT {proj_qs} FROM server.patients_server s JOIN Ro r USING (id)"
            if Cs:
                qs += f" WHERE {join_s.join(Cs)}"
            qso = f"SELECT {final_select} FROM owner.patients_owner o JOIN Rs s USING (id)"
            where_parts = []
            if Cso:
                where_parts.append(" AND ".join(Cso))
            if where_parts:
                qso += " WHERE " + " AND ".join(where_parts)
            if gb_sql:
                qso += f" GROUP BY {gb_sql}"
            if having_clause:
                qso += having_sql
        else:
            # tutto su owner → GROUP BY (+ HAVING) su owner
            qo = f"SELECT {final_select} FROM owner.patients_owner o"
            if Co:
                qo += f" WHERE {join_o.join(Co)}"
            if gb_sql:
                qo += f" GROUP BY {gb_sql}"
            if having_clause:
                qo += having_sql

    elif strategy == "server-only":
        needs_owner = bool(((sel_plain | gb | agg_args) & Fo))
        if needs_owner:
            proj_qs = ", ".join(["s.id"] + [f"s.{c}" for c in Aqs])
            qs = f"SELECT {proj_qs} FROM server.patients_server s"
            if Cs:
                qs += f" WHERE {join_s.join(Cs)}"
            qso = f"SELECT {final_select} FROM owner.patients_owner o JOIN Rs s USING (id)"
            if Cso:
                qso += " WHERE " + " AND ".join(Cso)
            if gb_sql:
                qso += f" GROUP BY {gb_sql}"
            if having_clause:
                qso += having_sql
        else:
            # tutto su server → GROUP BY (+ HAVING) su server
            gb_only_s = ", ".join([f"s.{c}" for c in sorted(gb & Fs)])
            aggs_sql_s = render_aggs_sql(aggs, Fo)
            parts = []
            if gb_only_s:
                parts.append(gb_only_s)
            if aggs_sql_s:
                parts.append(aggs_sql_s)
            final_s = ", ".join(parts) if parts else aggs_sql_s
            qs = f"SELECT {final_s} FROM server.patients_server s"
            if Cs:
                qs += f" WHERE {join_s.join(Cs)}"
            if gb_only_s:
                qs += f" GROUP BY {gb_only_s}"
            if having_clause:
                qs += having_sql  # HAVING sul server

    elif strategy == "parallel":
        # estrazioni minime con pushdown Co/Cs
        proj_qo = ", ".join(["o.id"] + [f"o.{c}" for c in Aqo]) if Aqo else "o.id"
        qo = f"SELECT {proj_qo} FROM owner.patients_owner o"
        if Co:
            qo += f" WHERE {' OR '.join(Co) if has_or else ' AND '.join(Co)}"

        proj_qs = ", ".join(["s.id"] + [f"s.{c}" for c in Aqs]) if Aqs else "s.id"
        qs = f"SELECT {proj_qs} FROM server.patients_server s"
        if Cs:
            qs += f" WHERE {' OR '.join(Cs) if has_or else ' AND '.join(Cs)}"

        # join + Cso + GROUP BY (+ HAVING)
        qso = (
            "SELECT " + final_select +
            " FROM owner.patients_owner o"
            " JOIN Ro r USING (id)"
            " JOIN Rs s USING (id)"
        )
        if Cso:
            qso += " WHERE " + " AND ".join(Cso)
        if gb_sql:
            qso += f" GROUP BY {gb_sql}"
        if having_clause:
            qso += having_sql

    else:
        raise ValueError("Strategy must be one of: server-owner, owner-server, owner-only, server-only, parallel")

    return qs, qo, qso

def process_query_gb(query: str, Fo: Set[str], Fs: Set[str]) -> Dict[str, any]:

    # parse esteso: ora ritorna anche having_clause (alias già espansi)
    select_plain, where_clause, group_by, aggs, having_clause = parse_query_groupby(query)

    Co = Cs = Cso = []
    has_or = False
    if where_clause:
        conditions, has_or = extract_conditions(where_clause)
        classified_where = classify_conditions(conditions, Fo, Fs)
        Co, Cs, Cso = classified_where["Co"], classified_where["Cs"], classified_where["Cso"]

    # classif GB/AGG (aggs include anche quelle comparse solo in HAVING)
    classified_gb = classify_groupby_agg(group_by, aggs, Fo, Fs)
    groupby_info = {
        "G_owner": classified_gb.get("G_owner", set()),
        "G_server": classified_gb.get("G_server", set()),
        "Agg_owner": classified_gb.get("Agg_owner", set()),
        "Agg_server": classified_gb.get("Agg_server", set()),
    }

    # attributi coinvolti in select/groupby/agg
    sel_attrs = set(select_plain) | set(group_by) | {a["arg"] for a in aggs if a.get("arg")}

    # scelta strategia: passa anche groupby_info e has_having
    classified_where_for_strategy = {"Co": Co, "Cs": Cs, "Cso": Cso}
    strategy_key = choose_strategy(
        classified_where_for_strategy,
        has_or,
        sel_attrs,
        Fo, Fs,
        table="patients",
        schema_owner="owner",
        schema_server="server",
        bytes_owner=1.0,
        bytes_server=1.0,
        groupby_info=groupby_info,
        has_having=bool(having_clause)
    )
    strategy_eff = strategy_key

    # generazione subquery: propaga having_clause
    qs, qo, qso = generate_subqueries_gb(
        select_plain=select_plain,
        group_by=group_by,
        aggs=aggs,
        Fo=Fo, Fs=Fs,
        strategy=strategy_eff,
        Co=Co, Cs=Cs, Cso=Cso,
        has_or=has_or,
        having_clause=having_clause
    )

    return {
        "Query": query,
        "SELECT_PLAIN": select_plain,
        "WHERE": where_clause,
        "GROUP_BY": group_by,
        "HAVING": having_clause,
        "AGGS": aggs,
        "Classificazione_WHERE": {"Co": Co, "Cs": Cs, "Cso": Cso, "has_or": has_or},
        "Classificazione_GB": classified_gb,
        "Strategia": strategy_key,
        "Strategia_eff": strategy_eff,
        "qs": qs, "qo": qo, "qso": qso,
    }

def _replan_alternative_gb(plan: dict, Fo: set, Fs: set) -> dict | None:
    cur = plan.get("Strategia_eff") or plan.get("Strategia")
    alt = {"owner-server": "server-owner", "server-owner": "owner-server"}.get(cur)
    if not alt:
        return None

    qs, qo, qso = generate_subqueries_gb(
        select_plain=plan["SELECT_PLAIN"],
        group_by=plan["GROUP_BY"],
        aggs=plan["AGGS"],
        Fo=Fo,
        Fs=Fs,
        strategy=alt,
        Co=plan.get("Classificazione_WHERE", {}).get("Co", []),
        Cs=plan.get("Classificazione_WHERE", {}).get("Cs", []),
        Cso=plan.get("Classificazione_WHERE", {}).get("Cso", []),
        has_or=plan.get("Classificazione_WHERE", {}).get("has_or", False),
        having_clause=plan.get("HAVING")  # <-- propagate HAVING
    )
    return {"Strategia": alt, "qs": qs, "qo": qo, "qso": qso}

def evaluate_query_gb(query: str,
                      Fo: set, Fs: set,
                      tag: str | None = None,
                      schema: str = "work",
                      save_to: str | None = None,
                      also_compare_alt: bool = True) -> dict:
    plan = process_query_gb(query, Fo, Fs)
    sk = plan.get("Strategia_eff") or plan["Strategia"]

    tag = tag or uuid.uuid4().hex[:8]

    utils.run(f"CREATE SCHEMA IF NOT EXISTS {schema};")
    ro_name, rs_name, out_name = f"{schema}.ro_{tag}", f"{schema}.rs_{tag}", f"{schema}.out_{tag}"

    counts, sizes = {}, {}

    if sk == "owner-server":
        qo = utils._strip_semicolon(plan["qo"])
        qs = utils._strip_semicolon(plan["qs"])
        qso = utils._strip_semicolon(plan["qso"])

        utils.run(f"DROP TABLE IF EXISTS {ro_name}; CREATE TABLE {ro_name} AS {qo};")
        counts["ro"], sizes["ro"] = utils._count_table(ro_name), utils._size_table(ro_name)

        qs_mat = qs.replace(" Ro ", f" {ro_name} ")
        utils.run(f"DROP TABLE IF EXISTS {rs_name}; CREATE TABLE {rs_name} AS {qs_mat};")
        counts["rs"], sizes["rs"] = utils._count_table(rs_name), utils._size_table(rs_name)

        qso_mat = qso.replace(" Rs ", f" {rs_name} ")
        utils.run(f"DROP TABLE IF EXISTS {out_name}; CREATE TABLE {out_name} AS {qso_mat};")
        counts["out"], sizes["out"] = utils._count_table(out_name), utils._size_table(out_name)

    elif sk == "server-owner":
        qs = utils._strip_semicolon(plan["qs"])
        qso = utils._strip_semicolon(plan["qso"])

        utils.run(f"DROP TABLE IF EXISTS {rs_name}; CREATE TABLE {rs_name} AS {qs};")
        counts["rs"], sizes["rs"] = utils._count_table(rs_name), utils._size_table(rs_name)

        qso_mat = qso.replace(" Rs ", f" {rs_name} ")
        utils.run(f"DROP TABLE IF EXISTS {out_name}; CREATE TABLE {out_name} AS {qso_mat};")
        counts["out"], sizes["out"] = utils._count_table(out_name), utils._size_table(out_name)

    elif sk in ("owner-only", "server-only"):

        if plan["qo"]:
            qo = utils._strip_semicolon(plan["qo"])
            utils.run(f"DROP TABLE IF EXISTS {ro_name}; CREATE TABLE {ro_name} AS {qo};")
            counts["ro"], sizes["ro"] = utils._count_table(ro_name), utils._size_table(ro_name)

        if plan["qs"]:
            qs = utils._strip_semicolon(plan["qs"])
            qs_mat = qs.replace(" Ro ", f" {ro_name} ") if plan["qo"] else qs
            utils.run(f"DROP TABLE IF EXISTS {rs_name}; CREATE TABLE {rs_name} AS {qs_mat};")
            counts["rs"], sizes["rs"] = utils._count_table(rs_name), utils._size_table(rs_name)




    elif sk == "parallel":
        # materializza entrambi i lati, poi la query finale che li usa entrambi
        qo = utils._strip_semicolon(plan["qo"])
        qs = utils._strip_semicolon(plan["qs"])
        qso = utils._strip_semicolon(plan["qso"])

        utils.run(f"DROP TABLE IF EXISTS {ro_name}; CREATE TABLE {ro_name} AS {qo};")
        counts["ro"], sizes["ro"] = utils._count_table(ro_name), utils._size_table(ro_name)

        utils.run(f"DROP TABLE IF EXISTS {rs_name}; CREATE TABLE {rs_name} AS {qs};")
        counts["rs"], sizes["rs"] = utils._count_table(rs_name), utils._size_table(rs_name)

        qso_mat = (
            qso.replace(" Ro ", f" {ro_name} ")
               .replace(" Rs ", f" {rs_name} ")
        )
        utils.run(f"DROP TABLE IF EXISTS {out_name}; CREATE TABLE {out_name} AS {qso_mat};")
        counts["out"], sizes["out"] = utils._count_table(out_name), utils._size_table(out_name)

    else:
        raise ValueError(f"Strategia sconosciuta: {sk!r}")

    ship_ro, ship_rs = utils._ships(plan)
    net_bytes = utils._network_bytes_payload(
            ro_name if ship_ro else None,
            rs_name if ship_rs else None
    )

    alt_info = None
    if also_compare_alt and sk in ("owner-server", "server-owner"):
        alt = _replan_alternative_gb(plan, Fo, Fs)
        if alt:
            tag_alt = tag + "_alt"
            ro_alt, rs_alt, out_alt = f"{schema}.ro_{tag_alt}", f"{schema}.rs_{tag_alt}", f"{schema}.out_{tag_alt}"
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

            else:  # server-owner
                qs_alt = utils._strip_semicolon(alt["qs"])
                qso_alt = utils._strip_semicolon(alt["qso"])
                utils.run(f"DROP TABLE IF EXISTS {rs_alt}; CREATE TABLE {rs_alt} AS {qs_alt};")
                sizes_alt["rs"] = utils._size_table(rs_alt)
                qso_alt_mat = qso_alt.replace(" Rs ", f" {rs_alt} ")
                utils.run(f"DROP TABLE IF EXISTS {out_alt}; CREATE TABLE {out_alt} AS {qso_alt_mat};")

            ship_ro_alt, ship_rs_alt = utils._ships(alt)
            net_alt = utils._network_bytes_payload(
                 ro_alt if ship_ro_alt else None,
                rs_alt if ship_rs_alt else None
                )

            saving_ratio = None
            if net_alt and net_bytes:
                saving_ratio = 1 - (net_bytes / net_alt)
            alt_info = {
                "alt_strategy": alt["Strategia"],
                "alt_network_bytes": net_alt,
                "saving_pct": f"{saving_ratio*100:.1f}%" if saving_ratio is not None else None,
                "tables_alt": {"result_owner": ro_alt if "ro" in sizes_alt else None,
                               "result_server": rs_alt if "rs" in sizes_alt else None,
                               "result_out": out_alt}
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

def evaluate_queries_gb(queries: list[str],
                        Fo: set, Fs: set,
                        schema: str = "work",
                        save_to: str | None = None,
                        also_compare_alt: bool = True) -> pd.DataFrame:
    rows = []
    for i, q in enumerate(queries, 1):
        tag = f"hv{i:02d}"
        res = evaluate_query_gb(q, Fo, Fs, tag=tag, schema=schema,
                                save_to=save_to, also_compare_alt=also_compare_alt)
        rows.append(res["row"])
    return pd.DataFrame(rows)