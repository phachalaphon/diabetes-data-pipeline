# Diabetes Clinical Data Pipeline

Pipeline อัตโนมัติ: **Kaggle CSV → PostgreSQL (Docker) → Pandas Transform → Google Sheets → Looker Studio**

ชุดข้อมูล: *Diabetes Clinical Dataset with Physician Notes* (100,000 แถว, 17 คอลัมน์, ปี 2015–2022, สหรัฐอเมริกา)

## สถาปัตยกรรม

```
data/*.csv ──ingest.py──▶ Postgres raw_data.diabetes_dataset_with_notes
                              │
                         transform.py (pandas: clean + features + aggregate)
                              ▼
                         Postgres production.diabetes_clean + production.agg_*
                              │
                          publish.py (gspread)
                              ▼
                         Google Sheets (1 แผ่นต่อ 1 ตาราง agg_*)
                              ▼
                         Looker Studio Dashboard
```

## โครงสร้างไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `docker-compose.yml` | PostgreSQL 16 ใน Docker |
| `config.py` | อ่านค่าจาก `.env` + สร้าง DB engine |
| `ingest.py` | CSV → `raw_data` (ไม่แก้ข้อมูลดิบ) |
| `transform.py` | Cleaning, Feature Engineering, Aggregation → `production` |
| `publish.py` | `production.agg_*` → Google Sheets |
| `run_pipeline.py` | รัน 3 ขั้นตอนต่อเนื่อง |

## วิธีรัน

### 0) เตรียมเครื่อง
- ติดตั้ง Docker Desktop และ Python 3.10+
- วางไฟล์ CSV ที่ `data/diabetes_dataset_with_notes.csv` (ดาวน์โหลดจาก Kaggle)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env  แล้วแก้รหัสผ่านและ GOOGLE_SPREADSHEET_ID
```

### 1) เปิดฐานข้อมูล
```bash
docker compose up -d
docker compose ps                # รอจน STATUS เป็น healthy
```

### 2) ตั้งค่า Google API (ทำครั้งเดียว)
1. เข้า https://console.cloud.google.com → สร้าง Project ใหม่
2. เมนู **APIs & Services → Library** → เปิดใช้งาน **Google Sheets API** และ **Google Drive API**
3. **APIs & Services → Credentials → Create Credentials → Service Account** ตั้งชื่อแล้วกด Done
4. คลิก Service Account ที่สร้าง → แท็บ **Keys → Add Key → Create new key → JSON** ไฟล์จะถูกดาวน์โหลด
5. เปลี่ยนชื่อไฟล์เป็น `credentials.json` วางไว้ในโฟลเดอร์โปรเจค (**ห้าม commit** – อยู่ใน `.gitignore` แล้ว)
6. สร้าง Google Sheet เปล่าใน Google Drive ของคุณ → กด **Share** → ใส่อีเมลของ Service Account
   (ดูในไฟล์ `credentials.json` ที่ฟิลด์ `client_email`) ให้สิทธิ์ **Editor**
7. คัดลอก Spreadsheet ID จาก URL (`https://docs.google.com/spreadsheets/d/<ID>/edit`) ไปใส่ `GOOGLE_SPREADSHEET_ID` ใน `.env`

### 3) รัน pipeline
```bash
python run_pipeline.py
```
หรือรันทีละขั้นเพื่อดีบัก: `python ingest.py`, `python transform.py`, `python publish.py`

### 4) ตรวจผลลัพธ์ในฐานข้อมูล
```bash
docker exec -it diabetes_postgres psql -U diabetes_user -d diabetes_db -c "\dt production.*"
```

## ตารางที่ publish ไป Google Sheets

| แผ่น | ตอบคำถาม |
|---|---|
| `agg_age_gender` | Q1 กลุ่มเสี่ยงตามอายุ × เพศ |
| `agg_year`, `agg_state` | Q2 แนวโน้มรายปี / รายรัฐ |
| `agg_biomarker_mean`, `agg_biomarker_corr`, `agg_biomarker_band` | Q3 HbA1c vs Glucose vs BMI |
| `agg_comorbidity` | Q4 โรคร่วม (มี relative risk) |
| `agg_smoking`, `agg_smoking_raw` | Q5 การสูบบุหรี่ |
| `agg_obesity_age` | Q6 โรคอ้วนในผู้ป่วยเบาหวานตามอายุ |
| `agg_notes_validation`, `agg_notes_consistency` | Q7 Clinical notes |

## การทำความสะอาดข้อมูลที่ทำ
- ลบแถวซ้ำ (14 แถว) → ในตาราง production จึงมี 99,986 แถว
- `smoking_history`: รวม `ever`, `not current` เข้ากับ `Former`; `No Info` → `Unknown`
- BMI > 60 ถือเป็น outlier: เก็บค่าเดิมใน `bmi`, สร้าง `bmi_outlier` (flag) และ `bmi_clean` (cap ที่ 60)
- รวม `race:*` 5 คอลัมน์เป็นคอลัมน์เดียว `race`

## ข้อจำกัดของข้อมูล
- ชุดข้อมูลเป็น synthetic/augmented (เชื้อชาติกระจายเท่ากัน ~20%)
- ปี 2019 มี ~80% ของข้อมูลทั้งหมด ส่วนปี 2020–2022 มีน้อยกว่า 60 แถว → แนวโน้มรายปีมีข้อจำกัด (ดูคอลัมน์ `reliable_sample`)
- `clinical_notes` เป็นประโยคแม่แบบ 13 แบบ ไม่ใช่ข้อความอิสระ
