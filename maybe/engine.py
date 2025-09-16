from sqlalchemy import text
import pandas as pd

import Query1, Query3, Query2, Query2W

Fo = {
    "id", "birthdate", "ssn", "drivers", "passport",
    "first", "middle", "last", "maiden",
    "address", "city", "fips", "zip", "lat", "lon",
    "income"
}

Fs = {
    "id", "deathdate", "gender", "race", "ethnicity", "marital",
    "prefix", "suffix", "birthplace", "state", "county",
    "healthcare_expenses", "healthcare_coverage"
}


def run(sql_or_text: str, params: dict | None = None) -> pd.DataFrame | None:

    with engine.begin() as conn:
        res = conn.execute(text(sql_or_text), params or {})
        if res.returns_rows:
            return pd.DataFrame(res.fetchall(), columns=res.keys())
        return None




def detect_case(query: str) -> int:
    q = query.lower()
    has_where  = " where " in q
    has_group  = " group by " in q
    has_having = " having " in q
    if not has_group and not has_having and has_where:
        return 1
    if has_group and not has_where and not has_having:
        return 2
    if has_group and has_where and not has_having:
        return 3
    if has_where and has_group and has_having:
        return 4
    return 5

def run_query_router(query, also_compare_alt=True):
    case = detect_case(query)
    if case == 1:
        return Query1.evaluate_query(query, Fo, Fs, tag='case1')
    if case == 2:
        return Query2.evaluate_query_gb(query, Fo, Fs, tag="case2")   # gestisce GB
    if case == 3:
        return Query2W.evaluate_query_gb(query, Fo, Fs, tag="case3")
    if case == 4:
        return Query3.evaluate_query_gb(query, Fo, Fs, tag="case4")       # gestisce anche HAVING
    return None







