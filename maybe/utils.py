import re
from typing import List

from sqlalchemy import text
from db_conn import run


# utils
def _strip_semicolon(sql: str) -> str:
    return re.sub(r';\s*$', '', sql.strip())

def _subst_token(sql: str, token: str, replacement: str) -> str:
    return re.sub(rf'\b{re.escape(token)}\b', replacement, sql)

def _count_table(tname: str) -> int:
    return int(run(f"SELECT COUNT(*) AS n FROM {tname};").iloc[0]["n"])


def _size_table(tname: str) -> int:
    return int(run(f"SELECT pg_total_relation_size('{tname}') AS bytes;").iloc[0]["bytes"])


def _table_cols(tname: str) -> list[str]:
    schema, table = tname.split(".", 1)
    df = run(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = '{schema}' AND table_name = '{table}'
        ORDER BY ordinal_position;
    """)
    return [] if df.empty else df["column_name"].tolist()


def _avg_row_bytes(tname: str) -> int:
    cols = _table_cols(tname)
    if not cols:
        return 0
    expr = " + ".join([f"COALESCE(pg_column_size({c}),0)" for c in cols])
    df = run(f"SELECT COALESCE(AVG({expr})::bigint, 0) AS avg_bytes FROM {tname};")
    return int(df.iloc[0]["avg_bytes"])


def _payload_bytes(tname: str) -> int:
    rows = _count_table(tname)
    return rows * _avg_row_bytes(tname)


def _network_bytes_payload(ro_name: str | None, rs_name: str | None) -> int:
    total = 0
    if ro_name:
        total += _payload_bytes(ro_name)
    if rs_name:
        total += _payload_bytes(rs_name)
    return total

def domini_from_pg_stats(schema: str, table: str) -> dict:
    if (schema or "").lower().startswith("owner"):
        return {}

    sql = f"""
    SELECT s.attname::text AS col,
           CASE
             WHEN s.n_distinct > 0
               THEN s.n_distinct::numeric
             ELSE (-s.n_distinct) * c.reltuples
           END AS est_distinct
    FROM pg_stats s
    JOIN pg_class c ON c.relname = s.tablename
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = s.schemaname
    WHERE s.schemaname = :schema AND s.tablename = :table;
    """
    rows = run(text(sql).bindparams(schema=schema, table=table), show=False)
    return {r.col.lower(): max(1, int(r.est_distinct or 1)) for _, r in rows.iterrows()}


def stima_selettivita(condizione: str, domini: dict) -> float:
    c = condizione.lower()
    for attr in domini:
        if attr.lower() in c:
            return 1 / domini[attr]
    return 0.5


def calcola_selettivita(schema: str, table: str, condizione: str,
                        domini: dict | None = None) -> float:
    schema_l = (schema or "").lower()
    is_owner = schema_l.startswith("owner") or schema_l == "o"

    domini_owner = {}
    domini_server = domini_from_pg_stats("server", "patients_server")
    domini = {**domini_owner, **domini_server}

    if is_owner:
        return stima_selettivita(condizione, domini or {})

    sql = f"""
        SELECT
            COUNT(*)::float AS total,
            COUNT(*) FILTER (WHERE {condizione})::float AS match
        FROM {schema}.{table}_{schema};
    """

    row = run(text(sql), show=False).iloc[0]
    total = float(row["total"])
    match = float(row["match"])
    if total <= 0:
        return 1.0
    return max(min(match / total, 1.0), 0.0)


def _unqualify(tok: str) -> str:
    tok = tok.strip().strip('"')
    return tok.split('.')[-1].lower() if '.' in tok else tok.lower()


def _split_outside_parents(s: str) -> List[str]:
    items, buf, d = [], [], 0
    for ch in s:
        if ch == '(':
            d += 1
        elif ch == ')':
            d = max(0, d - 1)
        if ch == ',' and d == 0:
            items.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append(''.join(buf).strip())
    return items


def _token_used(sql: str | None, token: str) -> bool:
    if not sql: return False
    # match "Ro" / "Rs" come identificatore o alias, non come sottostringa
    return re.search(rf'(?<!\w){token}(?!\w)', sql) is not None

def _ships(plan: dict) -> tuple[bool, bool]:
    # Ro viaggia se qs usa Ro; Rs viaggia se qso usa Rs
    return _token_used(plan.get("qs"), "Ro"), _token_used(plan.get("qso"), "Rs")

def _avg_payload_on(table_qual: str, cols: list[str]) -> int:
    if not cols: return 0
    expr = " + ".join([f"COALESCE(pg_column_size({c}),0)" for c in cols])
    df = run(f"SELECT COALESCE(AVG({expr})::bigint,0) AS b FROM {table_qual};")
    return int(df.iloc[0]["b"])

def _row_count_base(table_qual: str) -> int:
    df = run(f"SELECT COUNT(*) AS n FROM {table_qual};")
    return int(df.iloc[0]["n"])

def _num_groups(table_qual: str, keys: list[str]) -> int:
    if not keys: return 1
    cols = ", ".join(keys)
    df = run(f"SELECT COUNT(*) AS g FROM (SELECT DISTINCT {cols} FROM {table_qual}) t;")
    return int(df.iloc[0]["g"])

