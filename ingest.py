"""Step 1: โหลด CSV ดิบจาก Kaggle เข้า PostgreSQL (schema raw_data)"""
import logging

import pandas as pd
from sqlalchemy import text

import config

log = logging.getLogger("ingest")


def main():
    log.info("อ่านไฟล์ CSV: %s", config.CSV_PATH)
    df = pd.read_csv(config.CSV_PATH)
    log.info("อ่านได้ %s แถว, %s คอลัมน์", f"{len(df):,}", df.shape[1])

    engine = config.get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {config.RAW_SCHEMA}"))

    # ข้อมูลดิบ: ไม่แก้ค่าใดๆ ทั้งสิ้น (replace เพื่อให้รันซ้ำได้ ไม่เกิดข้อมูลซ้ำ)
    df.to_sql(
        config.RAW_TABLE,
        engine,
        schema=config.RAW_SCHEMA,
        if_exists="replace",
        index=False,
        chunksize=20_000,
        method=config.copy_insert,
    )

    with engine.connect() as conn:
        n = conn.execute(
            text(f"SELECT COUNT(*) FROM {config.RAW_SCHEMA}.{config.RAW_TABLE}")
        ).scalar()
    if n != len(df):
        raise RuntimeError(f"จำนวนแถวไม่ตรงกัน: CSV={len(df)} แต่ในตาราง={n}")
    log.info("โหลดสำเร็จ: %s.%s (%s แถว)", config.RAW_SCHEMA, config.RAW_TABLE, f"{n:,}")


if __name__ == "__main__":
    main()
