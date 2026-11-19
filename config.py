"""ค่าตั้งต้นและตัวช่วยเชื่อมต่อ Postgres ที่ทุกสคริปต์ใช้ร่วมกัน"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()

POSTGRES_USER = os.getenv("POSTGRES_USER", "diabetes_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "change_me")
POSTGRES_DB = os.getenv("POSTGRES_DB", "diabetes_db")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

CSV_PATH = os.getenv("CSV_PATH", "data/diabetes_dataset_with_notes.csv")
RAW_SCHEMA = "raw_data"
RAW_TABLE = os.getenv("RAW_TABLE", "diabetes_dataset_with_notes")
PROD_SCHEMA = "production"

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def get_engine():
    """สร้าง SQLAlchemy engine สำหรับต่อ PostgreSQL ใน Docker"""
    from sqlalchemy import create_engine

    url = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    return create_engine(url)


def copy_insert(table, conn, keys, data_iter):
    """ตัวช่วยให้ DataFrame.to_sql โหลดเข้า PostgreSQL ด้วย COPY (เร็วกว่า INSERT มาก)"""
    import csv
    from io import StringIO

    dbapi_conn = conn.connection
    with dbapi_conn.cursor() as cur:
        buf = StringIO()
        csv.writer(buf).writerows(data_iter)
        buf.seek(0)
        columns = ", ".join(f'"{k}"' for k in keys)
        table_name = f"{table.schema}.{table.name}" if table.schema else table.name
        cur.copy_expert(f"COPY {table_name} ({columns}) FROM STDIN WITH CSV", buf)
