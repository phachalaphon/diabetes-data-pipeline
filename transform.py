"""Step 2: อ่าน raw_data -> Clean / Feature Engineering / Aggregate -> เขียนลง schema production

ฟังก์ชัน clean_and_engineer() และ build_aggregates() เป็นฟังก์ชันล้วนๆ (รับ/คืน DataFrame)
จึงทดสอบได้โดยไม่ต้องมีฐานข้อมูล
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("transform")

BMI_OUTLIER_THRESHOLD = 60  # BMI สูงกว่านี้ถือเป็นค่าสุดโต่ง (ข้อมูลมีค่าสูงสุด 95.69)

SMOKING_MAP = {
    "never": "Never",
    "current": "Current",
    "former": "Former",
    "not current": "Former",  # ทับซ้อนกับ former
    "ever": "Former",  # เคยสูบ (ไม่ระบุว่าปัจจุบันสูบหรือไม่) -> รวมเป็น Former
    "No Info": "Unknown",
}

# ประโยคแม่แบบใน clinical_notes -> ชื่อ flag
NOTE_KEYWORDS = {
    "note_elevated_glucose": "Elevated blood glucose",
    "note_high_hba1c": "High HbA1c",
    "note_smoking_history": "History of smoking",
    "note_obese": "Obese category",
    "note_overweight": "Overweight",
    "note_underweight": "Underweight",
    "note_healthy_bmi": "Healthy BMI",
    "note_hypertension": "History of hypertension",
    "note_cardiac": "Cardiac condition",
    "note_metabolic_syndrome": "metabolic syndrome",
    "note_elderly": "Elderly patient",
    "note_young": "Young patient",
}


# ---------------------------------------------------------------- Cleaning + Features
def clean_and_engineer(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()

    # --- Cleaning ---
    n0 = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    log.info("ลบแถวซ้ำ %s แถว", n0 - len(df))

    for col in ["age", "bmi", "hbA1c_level", "blood_glucose_level", "diabetes"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["year"] = df["year"].astype(int)
    df["gender"] = df["gender"].str.strip().str.title()
    df["location"] = df["location"].str.strip()
    df["clinical_notes"] = df["clinical_notes"].fillna("")

    # smoking_history: จัดกลุ่มใหม่
    df["smoking_group"] = df["smoking_history"].map(SMOKING_MAP).fillna("Unknown")

    # BMI outlier: เก็บค่าเดิมไว้ + flag + สร้าง bmi_clean ที่ cap ที่เพดาน
    df["bmi_outlier"] = (df["bmi"] > BMI_OUTLIER_THRESHOLD).astype(int)
    df["bmi_clean"] = df["bmi"].clip(upper=BMI_OUTLIER_THRESHOLD)

    # --- Feature Engineering ---
    race_cols = [c for c in df.columns if c.startswith("race:")]
    df["race"] = (
        df[race_cols].idxmax(axis=1).str.replace("race:", "", regex=False)
    )

    df["age_group"] = pd.cut(
        df["age"],
        bins=[-0.01, 17.99, 34.99, 49.99, 64.99, 200],
        labels=["0-17", "18-34", "35-49", "50-64", "65+"],
    ).astype(str)

    df["bmi_category"] = pd.cut(
        df["bmi_clean"],
        bins=[0, 18.5, 25, 30, 1000],
        right=False,
        labels=["Underweight", "Normal", "Overweight", "Obese"],
    ).astype(str)
    df["is_obese"] = (df["bmi_clean"] >= 30).astype(int)

    df["hba1c_category"] = pd.cut(
        df["hbA1c_level"],
        bins=[0, 5.7, 6.5, 100],
        right=False,
        labels=["Normal (<5.7)", "Prediabetes (5.7-6.4)", "Diabetes range (>=6.5)"],
    ).astype(str)

    df["glucose_category"] = pd.cut(
        df["blood_glucose_level"],
        bins=[0, 140, 200, 10000],
        right=False,
        labels=["Normal (<140)", "Elevated (140-199)", "High (>=200)"],
    ).astype(str)

    df["has_comorbidity"] = (
        (df["hypertension"] == 1) | (df["heart_disease"] == 1)
    ).astype(int)
    df["comorbidity_group"] = np.select(
        [
            (df["hypertension"] == 1) & (df["heart_disease"] == 1),
            (df["hypertension"] == 1),
            (df["heart_disease"] == 1),
        ],
        ["Both", "Hypertension only", "Heart disease only"],
        default="None",
    )

    df["diabetes_status"] = df["diabetes"].map({0: "Non-diabetic", 1: "Diabetic"})

    # keyword flags จาก clinical_notes (Text mining แบบ rule-based)
    notes_lower = df["clinical_notes"].str.lower()
    for flag, kw in NOTE_KEYWORDS.items():
        df[flag] = notes_lower.str.contains(kw.lower(), regex=False).astype(int)

    return df


# ---------------------------------------------------------------- Aggregation
def _rate_table(df: pd.DataFrame, by) -> pd.DataFrame:
    """ตารางสรุปมาตรฐาน: จำนวนผู้ป่วย / จำนวนเบาหวาน / อัตรา (%)"""
    g = df.groupby(by, observed=True).agg(
        patients=("diabetes", "size"), diabetic=("diabetes", "sum")
    )
    g["diabetes_rate_pct"] = (g["diabetic"] / g["patients"] * 100).round(2)
    return g.reset_index()


def build_aggregates(df: pd.DataFrame) -> dict:
    out = {}

    # Q1: อายุ x เพศ
    out["agg_age_gender"] = _rate_table(df, ["age_group", "gender"])

    # Q2: ปี และ รัฐ
    year_tbl = _rate_table(df, ["year"])
    # ปี 2020-2022 มีแถวน้อยมาก (<60) อัตรารายปีจึงไม่น่าเชื่อถือ -> flag ไว้ให้ Dashboard กรองได้
    year_tbl["reliable_sample"] = np.where(year_tbl["patients"] >= 1000, "Yes", "No (small n)")
    out["agg_year"] = year_tbl
    out["agg_state"] = _rate_table(df, ["location"]).sort_values(
        "diabetes_rate_pct", ascending=False
    )

    # Q3: Biomarker
    out["agg_biomarker_mean"] = (
        df.groupby("diabetes_status")
        .agg(
            patients=("diabetes", "size"),
            avg_hba1c=("hbA1c_level", "mean"),
            avg_glucose=("blood_glucose_level", "mean"),
            avg_bmi=("bmi_clean", "mean"),
        )
        .round(2)
        .reset_index()
    )
    corr = [
        {"biomarker": name, "correlation_with_diabetes": round(df[col].corr(df["diabetes"]), 4)}
        for name, col in [
            ("HbA1c", "hbA1c_level"),
            ("Blood Glucose", "blood_glucose_level"),
            ("BMI", "bmi_clean"),
        ]
    ]
    out["agg_biomarker_corr"] = (
        pd.DataFrame(corr).sort_values("correlation_with_diabetes", ascending=False)
    )
    bands = []
    for biomarker, col in [
        ("HbA1c", "hba1c_category"),
        ("Blood Glucose", "glucose_category"),
        ("BMI", "bmi_category"),
    ]:
        t = _rate_table(df, col).rename(columns={col: "band"})
        t.insert(0, "biomarker", biomarker)
        bands.append(t)
    out["agg_biomarker_band"] = pd.concat(bands, ignore_index=True)

    # Q4: โรคร่วม (พร้อม Relative Risk เทียบกลุ่ม None)
    com = _rate_table(df, "comorbidity_group")
    base = com.loc[com["comorbidity_group"] == "None", "diabetes_rate_pct"].iloc[0]
    com["relative_risk_vs_none"] = (com["diabetes_rate_pct"] / base).round(2)
    out["agg_comorbidity"] = com

    # Q5: การสูบบุหรี่ (กลุ่มใหม่ + ค่าเดิม)
    smoke = _rate_table(df, "smoking_group")
    smoke_raw = _rate_table(df, "smoking_history")
    out["agg_smoking"] = smoke
    out["agg_smoking_raw"] = smoke_raw

    # Q6: โรคอ้วนในผู้ป่วยเบาหวาน แยกตามอายุ
    ob = (
        df.groupby("age_group")
        .apply(
            lambda x: pd.Series(
                {
                    "patients": len(x),
                    "diabetic": int(x["diabetes"].sum()),
                    "diabetic_obese": int(((x["diabetes"] == 1) & (x["is_obese"] == 1)).sum()),
                    "all_obese": int(x["is_obese"].sum()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    ob["pct_obese_among_diabetic"] = (ob["diabetic_obese"] / ob["diabetic"] * 100).round(2)
    ob["pct_obese_among_all"] = (ob["all_obese"] / ob["patients"] * 100).round(2)
    out["agg_obesity_age"] = ob

    # Q7: Clinical notes vs ผลแล็บ/เบาหวานจริง
    rows = []
    for flag in NOTE_KEYWORDS:
        has = df[df[flag] == 1]
        no = df[df[flag] == 0]
        rows.append(
            {
                "note_keyword": flag.replace("note_", ""),
                "patients_flagged": len(has),
                "diabetes_rate_flagged_pct": round(has["diabetes"].mean() * 100, 2) if len(has) else None,
                "diabetes_rate_not_flagged_pct": round(no["diabetes"].mean() * 100, 2) if len(no) else None,
                "avg_hba1c_flagged": round(has["hbA1c_level"].mean(), 2) if len(has) else None,
                "avg_glucose_flagged": round(has["blood_glucose_level"].mean(), 1) if len(has) else None,
            }
        )
    out["agg_notes_validation"] = pd.DataFrame(rows)

    # ตารางความสอดคล้อง: ข้อความใน notes ตรงกับค่าจริงในคอลัมน์ structured หรือไม่
    checks = [
        ("note 'High HbA1c' vs hbA1c >= 6.5", df["note_high_hba1c"], df["hbA1c_level"] >= 6.5),
        ("note 'Elevated glucose' vs glucose >= 140", df["note_elevated_glucose"], df["blood_glucose_level"] >= 140),
        ("note 'Obese' vs BMI >= 30", df["note_obese"], df["is_obese"] == 1),
        ("note 'hypertension' vs hypertension = 1", df["note_hypertension"], df["hypertension"] == 1),
        ("note 'Cardiac' vs heart_disease = 1", df["note_cardiac"], df["heart_disease"] == 1),
        ("note 'smoking' vs smoking_group in (Current, Former)", df["note_smoking_history"], df["smoking_group"].isin(["Current", "Former"])),
    ]
    out["agg_notes_consistency"] = pd.DataFrame(
        [
            {"check": name, "match_pct": round((note.astype(bool) == truth).mean() * 100, 2)}
            for name, note, truth in checks
        ]
    )

    return out


# ---------------------------------------------------------------- Main (DB)
def main():
    from sqlalchemy import text

    import config

    engine = config.get_engine()
    log.info("อ่าน %s.%s", config.RAW_SCHEMA, config.RAW_TABLE)
    raw = pd.read_sql(f"SELECT * FROM {config.RAW_SCHEMA}.{config.RAW_TABLE}", engine)
    log.info("อ่านได้ %s แถว", f"{len(raw):,}")

    clean = clean_and_engineer(raw)
    aggs = build_aggregates(clean)

    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {config.PROD_SCHEMA}"))

    # ตารางระดับผู้ป่วย (ไม่รวม clinical_notes เพราะยาว) เก็บไว้ใน Postgres
    patient_cols = [c for c in clean.columns if c != "clinical_notes" and not c.startswith("race:")]
    clean[patient_cols].to_sql(
        "diabetes_clean", engine, schema=config.PROD_SCHEMA,
        if_exists="replace", index=False, chunksize=20_000, method=config.copy_insert,
    )
    log.info("เขียน production.diabetes_clean (%s แถว)", f"{len(clean):,}")

    for name, table in aggs.items():
        table.to_sql(name, engine, schema=config.PROD_SCHEMA, if_exists="replace", index=False)
        log.info("เขียน production.%s (%s แถว)", name, len(table))


if __name__ == "__main__":
    main()
