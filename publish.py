"""Step 3: ส่งตารางสรุปจาก schema production ไป Google Sheets

ส่งเฉพาะตารางสรุป (agg_*) ซึ่งมีขนาดเล็กมาก จึงไม่ชนข้อจำกัด 10 ล้านเซลล์ของ Google Sheets
และ Looker Studio โหลดเร็ว
"""
import logging

import pandas as pd
from sqlalchemy import text

import config

log = logging.getLogger("publish")


def main():
    import gspread
    from gspread_dataframe import set_with_dataframe

    if not config.GOOGLE_SPREADSHEET_ID or "ใส่_ID" in config.GOOGLE_SPREADSHEET_ID:
        raise RuntimeError("ยังไม่ได้ตั้งค่า GOOGLE_SPREADSHEET_ID ในไฟล์ .env")

    engine = config.get_engine()
    with engine.connect() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_name LIKE 'agg\\_%' ORDER BY table_name"
                ),
                {"s": config.PROD_SCHEMA},
            )
        ]
    if not tables:
        raise RuntimeError("ไม่พบตาราง agg_* ใน schema production (รัน transform.py ก่อน)")

    gc = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)
    sh = gc.open_by_key(config.GOOGLE_SPREADSHEET_ID)
    existing = {ws.title: ws for ws in sh.worksheets()}

    for name in tables:
        df = pd.read_sql(f"SELECT * FROM {config.PROD_SCHEMA}.{name}", engine)
        ws = existing.get(name) or sh.add_worksheet(
            title=name, rows=max(len(df) + 10, 100), cols=max(df.shape[1] + 2, 10)
        )
        ws.clear()
        set_with_dataframe(ws, df, include_index=False, resize=True)
        log.info("ส่งแผ่น '%s' (%s แถว x %s คอลัมน์)", name, len(df), df.shape[1])

    log.info("เสร็จสิ้น: https://docs.google.com/spreadsheets/d/%s", config.GOOGLE_SPREADSHEET_ID)


if __name__ == "__main__":
    main()
