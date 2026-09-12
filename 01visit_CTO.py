# =====================================================
# CEIRR Tracker (VS Code Version - V1 to V5 Update)
# =====================================================

import pandas as pd
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Help static type checkers / linters recognize gspread, google auth, and gspread_dataframe during analysis
    import gspread  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
    from gspread_dataframe import get_as_dataframe, set_with_dataframe  # type: ignore
else:
    try:
        import gspread
    except Exception:
        # Runtime: gspread may be unavailable in some environments (linting/CI).
        # Defer import errors until execution where appropriate.
        gspread = None  # type: ignore

    try:
        from google.oauth2.service_account import Credentials
    except Exception:
        Credentials = None  # type: ignore

    try:
        from gspread_dataframe import get_as_dataframe, set_with_dataframe
    except Exception:
        get_as_dataframe = None  # type: ignore
        set_with_dataframe = None  # type: ignore

if get_as_dataframe is None or set_with_dataframe is None:
    raise ImportError("The gspread_dataframe package is required. Install it with pip install gspread-dataframe")

# =====================================================
# STEP 1: AUTHENTICATION (STREAMLIT SECRETS)
# =====================================================

import streamlit as st

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

gc = gspread.authorize(creds)

# =====================================================
# STEP 2: SHEET URLs
# =====================================================

REC_URL = "https://docs.google.com/spreadsheets/d/1WjvZ2eZEoN42WLlNoelD-aH8oOtwvYoKtgy7eZdPZmo/edit"
VAC_URL = "https://docs.google.com/spreadsheets/d/1_SB16T3QUfZJhXMyEPw5HuWUwUScIUAzfzezbFj4e-Q/edit"

TRACKER_URL = "https://docs.google.com/spreadsheets/d/1z3ey_vJrTNtbLAPlzRXYWEJFRY4_-89nvJLwmSBXRfs/edit"
LAB_URL = "https://docs.google.com/spreadsheets/d/1uEaBqs8DoSF4X88ERq6KfXo54Abj7qtft_0lx1dxaxU/edit"

# =====================================================
# STEP 3: OPEN SHEETS
# =====================================================

ws_rec = gc.open_by_url(REC_URL).worksheet("data")
ws_vac = gc.open_by_url(VAC_URL).worksheet("data")
ws_trk = gc.open_by_url(TRACKER_URL).worksheet("Database")
ws_lab = gc.open_by_url(LAB_URL).worksheet("COHORT Follow-up")

# =====================================================
# STEP 4: LOAD DATA
# =====================================================

df_rec = get_as_dataframe(ws_rec).dropna(how="all")
df_vac = get_as_dataframe(ws_vac).dropna(how="all")
df_trk = get_as_dataframe(ws_trk).dropna(how="all")
df_lab = get_as_dataframe(ws_lab).dropna(how="all")

# =====================================================
# STEP 5: CLEAN IDS
# =====================================================

for df in [df_rec, df_vac]:
    df["study_id"] = df["study_id"].astype(str).str.strip().str.upper()

df_trk["Screening ID"] = df_trk["Screening ID"].astype(str).str.strip().str.upper()
df_lab["Screening ID"] = df_lab["Screening ID"].astype(str).str.strip().str.upper()

# =====================================================
# STEP 6: NORMALIZER
# =====================================================

def normalize(col):
    return col.lower().replace(" ", "").replace("/", "").replace("(", "").replace(")", "")


# =====================================================
# STEP 7: V1 DATA (RECRUITMENT)
# =====================================================

df_rec_v1 = (
    df_rec[df_rec["Visit_1"] == 1]
    .sort_values("date_enrol")
    .drop_duplicates(subset="study_id", keep="last")[["study_id", "date_enrol"]]
    .rename(columns={"date_enrol": "new_date"})
)

# Convert to datetime
df_rec_v1["new_date"] = pd.to_datetime(df_rec_v1["new_date"], errors="coerce").dt.date

# =====================================================
# STEP 8: VISIT FUNCTION
# =====================================================

def get_visit_df(v):

    df = (
        df_vac[df_vac["current_visit"] == v]
        .sort_values("visit_date")
        .drop_duplicates(subset="study_id", keep="last")[["study_id", "visit_date"]]
        .rename(columns={"visit_date": "new_date"})
    )

    df["new_date"] = pd.to_datetime(df["new_date"], errors="coerce").dt.date

    return df

visit_map = {
    2: "v2d2date",
    3: "v3sdate",
    4: "v4d3date",
    5: "v5sdate"
}

# =====================================================
# STEP 9: CORE UPDATE FUNCTION
# =====================================================

def update_tracker(df_target, sheet, name):

    for col in df_target.columns:
        n = normalize(col)
        if n in ["v1d1date", "v2d2date", "v3sdate", "v4d3date", "v5sdate"]:
            df_target[col] = pd.to_datetime(df_target[col], errors="coerce").dt.date

    # ---------- V1 ----------
    v1_col = next((c for c in df_target.columns if normalize(c) == "v1d1date"), None)

    if v1_col:
        tmp = df_target.merge(df_rec_v1, left_on="Screening ID", right_on="study_id", how="left")
        tmp.loc[tmp["new_date"].notna(), v1_col] = tmp["new_date"]
        df_target = tmp.drop(columns=["study_id", "new_date"])

    # ---------- V2–V5 ----------
    for v, norm_col in visit_map.items():

        df_visit = get_visit_df(v)

        if df_visit.empty:
            print(f" {name}: No data for Visit {v}")
            continue

        tracker_col = next((c for c in df_target.columns if normalize(c) == norm_col), None)

        if not tracker_col:
            print(f" {name}: Missing column {norm_col}")
            continue

        tmp = df_target.merge(df_visit, left_on="Screening ID", right_on="study_id", how="left")
        tmp.loc[tmp["new_date"].notna(), tracker_col] = tmp["new_date"]

        df_target = tmp.drop(columns=["study_id", "new_date"])

     # ---------- CONVERT DATES TO CLEAN STRINGS BEFORE WRITE ----------
    for col in df_target.columns:
        n = normalize(col)
        if n in ["v1d1date", "v2d2date", "v3sdate", "v4d3date", "v5sdate"]:
            df_target[col] = pd.to_datetime(df_target[col], errors="coerce").dt.strftime("%Y-%m-%d")
            df_target[col] = df_target[col].replace("NaT", "")  # blank instead of NaT text

    # ---------- WRITE BACK ----------
    sheet.clear()
    set_with_dataframe(sheet, df_target, include_index=False, resize=True)

    print(f" {name} updated successfully - {len(df_target)} rows")
    return df_target

# =====================================================
# STEP 10: RUN FOR BOTH SHEETS
# =====================================================

df_trk = update_tracker(df_trk, ws_trk, "TRACKER")
df_lab = update_tracker(df_lab, ws_lab, "LAB")

# =====================================================
# DONE
# =====================================================

print("All updates completed successfully")