from IPython.core.display_functions import display
from sqlalchemy import create_engine, text
import pandas as pd


USER = "postgres"
HOST = "localhost"
PORT = "5432"
PASSWORD = "user"
DB_ADMIN_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/postgres"
engine_admin = create_engine(DB_ADMIN_URL, isolation_level="AUTOCOMMIT")
DB_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/synthea"
engine = create_engine(DB_URL)
print("Connesso al database synthea")

def run(sql_or_text, show=False):
    with engine.begin() as conn:
        stmt = text(sql_or_text) if isinstance(sql_or_text, str) else sql_or_text
        result = conn.execute(stmt)
        if result.returns_rows:
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            if show:
                display(df)
            return df
        return None

