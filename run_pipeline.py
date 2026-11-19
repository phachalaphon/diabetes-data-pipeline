"""รัน pipeline ทั้งเส้นด้วยคำสั่งเดียว:  python run_pipeline.py"""
import logging
import sys
import time

import ingest
import publish
import transform

log = logging.getLogger("pipeline")

STEPS = [
    ("1/3 Ingest   (CSV -> raw_data)", ingest.main),
    ("2/3 Transform (raw_data -> production)", transform.main),
    ("3/3 Publish  (production -> Google Sheets)", publish.main),
]


def main():
    start = time.time()
    for name, fn in STEPS:
        log.info("===== %s =====", name)
        t0 = time.time()
        try:
            fn()
        except Exception:
            log.exception("ขั้นตอนล้มเหลว: %s -> หยุด pipeline", name)
            sys.exit(1)
        log.info("เสร็จ ใช้เวลา %.1f วินาที", time.time() - t0)
    log.info("Pipeline สำเร็จทั้งหมด ใช้เวลารวม %.1f วินาที", time.time() - start)


if __name__ == "__main__":
    main()
