# db_conn.py
from sqlalchemy import create_engine, text, TextClause, ClauseElement
from pathlib import Path
import pandas as pd

USER = "postgres"
HOST = "localhost"
PORT = "5432"
PASSWORD = "user"
DB_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/synthea"

engine = create_engine(DB_URL, pool_pre_ping=True, future=True)

def run(sql_or_text, params: dict | None = None) -> pd.DataFrame | None:
    """Esegue una singola query. Ritorna DataFrame se ci sono righe, altrimenti None."""
    with engine.begin() as conn:
        # se è già un oggetto SQLAlchemy, usalo; altrimenti crea TextClause da stringa
        if isinstance(sql_or_text, (TextClause, ClauseElement)):
            stmt = sql_or_text
        else:
            stmt = text(str(sql_or_text))

        # se ti passano dei parametri, bindali qui (solo se non sono già bindati)
        if params:
            stmt = stmt.bindparams(**params)

        res = conn.execute(stmt)
        if res.returns_rows:
            return pd.DataFrame(res.fetchall(), columns=res.keys())
        return None

def run_sql_file(path: str | Path) -> None:
    """Esegue uno script .sql con più statement (DDL/DML)."""
    sql_text = Path(path).read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql_text)

