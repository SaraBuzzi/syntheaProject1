import re
from typing import List, Set, Tuple, Dict, Optional, Any
import os, uuid
import pandas as pd
import utils

# SELECT FROM GROUP BY

def parse_query_groupby(query: str) -> Tuple[Set[str], Set[str], List[Dict[str, Any]]]:

    q = query.strip()
    m_sel = re.search(r"\bselect\s+(.*?)\s+from\b", q, re.I | re.S)
    if not m_sel:
        raise ValueError("SELECT ... FROM mancante.")
    sel_txt = m_sel.group(1)
    rest = q[m_sel.end():]


    m_gb = re.search(r"\bgroup\s+by\b", rest, re.I)


    group_by_txt = None
    if m_gb:
        group_by_txt = rest[m_gb.end():].strip()
        group_by_txt = re.sub(r';\s*$', '', group_by_txt, flags=re.S)

    # SELECT: separo plain vs aggregazioni
    select_items = _split_outside_parents(sel_txt)
    select_plain: Set[str] = set()
    aggs: List[Dict[str, Any]] = []

    agg_re = re.compile(
        r"^(count|sum|avg|min|max)\s*\(\s*(distinct\s+)?(\*|[a-zA-Z_][\w\.]*)\s*\)\s*(?:as\s+([a-zA-Z_]\w*))?$",
        re.I
    )
    for it in select_items:
        it_norm = it.strip()
        m = agg_re.match(it_norm)
        if m:
            func = m.group(1).lower()
            distinct = bool(m.group(2))
            arg_raw = m.group(3)
            alias = m.group(4).lower() if m.group(4) else None
            arg = None if arg_raw == '*' else _unqualify(arg_raw)
            aggs.append({"func": func, "arg": arg, "distinct": distinct, "alias": alias})
        else:

            select_plain.add(_unqualify(it_norm))

    group_by: Set[str] = set()
    if group_by_txt:
        cols = [tok for tok in _split_outside_parents(group_by_txt) if tok.strip()]
        group_by = {_unqualify(c) for c in cols}


    if select_plain - group_by:
        missing = ", ".join(sorted(select_plain - group_by))
        raise ValueError(f"Le colonne non aggregate in SELECT devono apparire nel GROUP BY (manca: {missing}).")

    return select_plain, group_by, aggs





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



