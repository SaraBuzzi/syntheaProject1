import Query1



def detect_case(query: str) -> int:
    q = query.lower()
    has_where  = " where " in q
    has_group  = " group by " in q
    has_having = " having " in q
    if not has_group and not has_where:
        return 1
    if has_group and not has_where and not has_having:
        return 2
    if has_group and has_where and not has_having:
        return 3
    if has_group and has_having:
        return 4
    return 4 if has_group else 1

def run_query_router(query, Fo, Fs, also_compare_alt=True):
    case = detect_case(query)
    if case == 1:
        return Query1.evaluate_query(query, Fo, Fs, tag='q01')
    if case == 2:
        return evaluate_query_gb(query, Fo, Fs, also_compare_alt=also_compare_alt)   # gestisce GB
    if case == 3:
        return evaluate_query_where_gb(query, Fo, Fs, also_compare_alt=also_compare_alt)
    # case 4
    return evaluate_query_gb(query, Fo, Fs, also_compare_alt=also_compare_alt)       # gestisce anche HAVING







