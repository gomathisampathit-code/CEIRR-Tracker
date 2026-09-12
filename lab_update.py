"""
CEIRR Complete Data Sync Script
Updates SCREENING sheet + COHORT Follow-up sheet
Runs in Visual Studio Code (Local Environment) and Streamlit Cloud
"""

import pandas as pd
import os
import importlib.util
from typing import TYPE_CHECKING
import streamlit as st

# Import gspread_formatting safely
cellFormat = None  # type: ignore
format_cell_range = None  # type: ignore

gsf_spec = importlib.util.find_spec("gspread_formatting")
if gsf_spec is not None:
    try:
        gsf = importlib.import_module("gspread_formatting")
        cellFormat = getattr(gsf, "cellFormat", None)
        format_cell_range = getattr(gsf, "format_cell_range", None)
    except Exception:
        cellFormat = None  # type: ignore
        format_cell_range = None  # type: ignore

if TYPE_CHECKING:
    import gspread  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
    from gspread_dataframe import get_as_dataframe, set_with_dataframe  # type: ignore
else:
    try:
        import gspread
    except Exception:
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
# STEP 1: AUTHENTICATION (STREAMLIT SECRETS / LOCAL FALLBACK)
# =====================================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = None

# 1. Try loading from Streamlit Secrets (Cloud Environment)
try:
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )
except Exception:
    # If st.secrets isn't configured or throws an error locally, ignore it and fall back
    pass

# 2. Fallback to local file if Secrets are missing (Local Desktop Environment)
if creds is None:
    local_path = "service_account.json"
    if os.path.exists(local_path):
        creds = Credentials.from_service_account_file(local_path, scopes=SCOPES)
    else:
        raise FileNotFoundError(
            "❌ Could not find credentials!\n"
            "Locally: Make sure 'service_account.json' is inside your project folder.\n"
            "Cloud: Make sure 'gcp_service_account' is configured in Streamlit Secrets."
        )

gc = gspread.authorize(creds)
print("✅ Authentication successful")


# =====================================================
# STEP 2: Configuration - Sheet URLs
# =====================================================
SCREENING_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BAByzSVh6gq03R_KcsWyFwISgM52NgWxcI_nXHzwRTw/edit?usp=sharing"
RECRUITMENT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1WjvZ2eZEoN42WLlNoelD-aH8oOtwvYoKtgy7eZdPZmo/edit?usp=sharing"
VACCINATION_SHEET_URL = "https://docs.google.com/spreadsheets/d/1_SB16T3QUfZJhXMyEPw5HuWUwUScIUAzfzezbFj4e-Q/edit?usp=sharing"
DEST_SHEET_URL_lab = "https://docs.google.com/spreadsheets/d/1uEaBqs8DoSF4X88ERq6KfXo54Abj7qtft_0lx1dxaxU/edit?usp=sharing"

# =====================================================
# STEP 3: Helper Functions
# =====================================================
def normalize(col):
    """Normalize column names for matching"""
    return col.lower().replace(" ", "").replace("/", "").replace("(", "").replace(")", "")


def col_letter(n):
    """Convert column number to letter (1->A, 27->AA)"""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def format_sheet(sheet, num_cols, num_rows):
    """Apply formatting to sheet"""
    if cellFormat is not None and format_cell_range is not None:
        try:
            fmt = cellFormat(horizontalAlignment="LEFT", wrapStrategy="CLIP")
            last_col = col_letter(num_cols)
            format_cell_range(sheet, f"A1:{last_col}{num_rows+1}", fmt)
            return True
        except Exception as fmt_error:
            print(f"Formatting skipped: {str(fmt_error)}")
            return False
    else:
        print("gspread_formatting not available - skipping formatting")
        return False


def clean_id_series(series):
    """Standardizes IDs to prevent matching misses due to float conversions or whitespace"""
    return series.astype(str).str.strip().str.replace(r'\.0$', '', regex=True)


# =====================================================
# STEP 4: UPDATE SCREENING SHEET
# =====================================================
def update_screening_sheet():
    """Update SCREENING sheet with basic screening data"""
    # print("\n" + "="*70)
    print("PDATING SCREENING SHEET")
    # print("="*70)
    
    try:
        # Open sheets
        print("Opening SCREENING source sheet...")
        screening_sheet = gc.open_by_url(SCREENING_SHEET_URL).worksheet("data")
        dest_screening = gc.open_by_url(DEST_SHEET_URL_lab).worksheet("SCREENING")
        print("Sheets opened successfully")
        
        # Read source
        print("Reading screening source data...")
        df_source = get_as_dataframe(screening_sheet).dropna(how="all")
        df_source.columns = df_source.columns.str.strip().str.lower()
        print(f"Read {len(df_source)} records from source")
        
        # Column mapping
        columns_map = {
            "study_id": "Screening ID",
            "sample_col_str": "Incharge",
            "family_willing_visit": "willing to visit",
        }
        
        available_columns = [c for c in columns_map if c in df_source.columns]
        df_partial = df_source[available_columns].rename(columns=columns_map)
        
        # Standardize IDs for seamless mapping
        df_partial["Screening ID"] = clean_id_series(df_partial["Screening ID"])
        
        # Map willing to visit values (1 = Yes, 0 = No)
        if "willing to visit" in df_partial.columns:
            df_partial["willing to visit"] = df_partial["willing to visit"].map({
                1: "Yes", 
                0: "No",
                "1": "Yes",
                "0": "No"
            })
        
        # Add empty columns for user input
        df_partial["Result Type"] = ""
        df_partial["Result"] = ""
        df_partial["Decision"] = ""
        df_partial["Reason"] = ""
        df_partial["Date of confirmed visit"] = ""
        
        # Add S.No
        df_partial.insert(0, "S.No", range(1, len(df_partial) + 1))
        
        # Preserve existing user-entered data
        print("Reading existing SCREENING sheet data...")
        try:
            df_existing = get_as_dataframe(dest_screening).dropna(how="all")
            if not df_existing.empty and len(df_existing) > 0:
                df_existing.columns = df_existing.columns.str.strip()
                df_existing["Screening ID"] = clean_id_series(df_existing["Screening ID"])
                
                # User-entered columns to preserve
                user_cols = ["Result Type", "Result", "Decision", "Reason", "Date of confirmed visit"]
                
                for col in user_cols:
                    if col in df_existing.columns:
                        existing_map = dict(zip(df_existing["Screening ID"], df_existing[col]))
                        df_partial[col] = df_partial["Screening ID"].map(existing_map).fillna("")
                
                print(f"Preserved existing user data from {len(df_existing)} records")
            else:
                print("No existing data found - columns will be empty for new entries")
        except Exception as e:
            print(f"Could not read existing data: {str(e)}")
        
        # Reorder columns
        df_lab_export = df_partial[[
            "S.No", 
            "Screening ID", 
            "Incharge", 
            "Result Type", 
            "Result", 
            "willing to visit", 
            "Decision", 
            "Reason", 
            "Date of confirmed visit"
        ]]
        
        # Write to sheet
        print("Writing to SCREENING sheet...")
        dest_screening.clear()
        set_with_dataframe(dest_screening, df_lab_export, include_index=False)
        
        # Format
        format_sheet(dest_screening, len(df_lab_export.columns), len(df_lab_export))
        
        # Success message
        print("SCREENING sheet updated successfully!")
        print(f"Rows: {len(df_lab_export)} | Columns: {len(df_lab_export.columns)}")
        
        return True
        
    except Exception as e:
        print(f"Error updating SCREENING sheet: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


# =====================================================
# STEP 5: UPDATE COHORT FOLLOW-UP SHEET
# =====================================================
def update_cohort_sheet():
    """Update COHORT Follow-up sheet with visit dates"""
    # print("\n" + "="*70)
    print("UPDATING COHORT FOLLOW-UP SHEET")
    # print("="*70)
    
    try:
        # Open sheets
        print("Opening all source sheets...")
        screening_sheet = gc.open_by_url(SCREENING_SHEET_URL).worksheet("data")
        recruitment_sheet = gc.open_by_url(RECRUITMENT_SHEET_URL).worksheet("data")
        vaccination_sheet = gc.open_by_url(VACCINATION_SHEET_URL).worksheet("data")
        dest_cohort = gc.open_by_url(DEST_SHEET_URL_lab).worksheet("COHORT Follow-up")
        print("Sheets opened successfully")
        
        # Read all source data
        print("Reading source data...")
        df_screening = get_as_dataframe(screening_sheet).dropna(how="all")
        df_screening.columns = df_screening.columns.str.strip().str.lower()
        
        df_recruitment = get_as_dataframe(recruitment_sheet).dropna(how="all")
        df_recruitment.columns = df_recruitment.columns.str.strip().str.lower()
        
        df_vaccination = get_as_dataframe(vaccination_sheet).dropna(how="all")
        df_vaccination.columns = df_vaccination.columns.str.strip().str.lower()
        
        print(f"Read {len(df_screening)} screening records")
        print(f"Read {len(df_recruitment)} recruitment records")
        print(f"Read {len(df_vaccination)} vaccination records")
        
        # Build base dataframe from RECRUITMENT sheet (ONLY recruitment records)
        print("Building base dataframe from RECRUITMENT records...")
        df_recruitment["study_id"] = clean_id_series(df_recruitment["study_id"])
        
        # Identify the correct Recruitment ID column from the recruitment sheet
        rec_id_col = "recruitment_id" if "recruitment_id" in df_recruitment.columns else "study_id"
        if rec_id_col in df_recruitment.columns:
            df_recruitment[rec_id_col] = clean_id_series(df_recruitment[rec_id_col])
        
        # Pull distinct matched records
        df_cohort = df_recruitment[["study_id", rec_id_col]].drop_duplicates(subset="study_id", keep="first").copy()
        df_cohort.rename(columns={"study_id": "Screening ID", rec_id_col: "Recruitment ID"}, inplace=True)
        
        # Add Incharge from SCREENING sheet
        print("Adding Incharge from SCREENING sheet...")
        df_screening_data = df_screening[["study_id", "sample_col_str"]].copy()
        df_screening_data["study_id"] = clean_id_series(df_screening_data["study_id"])
        df_screening_data = df_screening_data.drop_duplicates(subset="study_id", keep="first")
        df_screening_data = df_screening_data.rename(columns={"sample_col_str": "Incharge"})
        
        df_cohort = df_cohort.merge(
            df_screening_data,
            left_on="Screening ID",
            right_on="study_id",
            how="left"
        )
        if "study_id" in df_cohort.columns:
            df_cohort.drop(columns=["study_id"], inplace=True)
        
        # Initialize user data columns (will be populated below from existing sheet)
        df_cohort["Result"] = ""
        df_cohort["Cohort"] = ""
        df_cohort["Decision"] = ""
        df_cohort["Reason"] = ""
        df_cohort["Date of confirmed visit"] = ""
        
        # Extract V1/D1 dates from RECRUITMENT sheet
        print("Extracting Visit 1 (V1/D1) dates...")
        df_rec_v1 = (
            df_recruitment[df_recruitment["visit_1"] == 1]
            .drop_duplicates(subset="study_id", keep="last")[["study_id", "date_enrol"]]
            .rename(columns={"date_enrol": "(V1/D1) date"})
        )
        df_rec_v1["study_id"] = clean_id_series(df_rec_v1["study_id"])
        
        df_cohort = df_cohort.merge(
            df_rec_v1,
            left_on="Screening ID",
            right_on="study_id",
            how="left"
        )
        if "study_id" in df_cohort.columns:
            df_cohort.drop(columns=["study_id"], inplace=True)
        
        # Extract V2-V5 dates from VACCINATION sheet
        visit_column_map = {
            2: "(V2/D2) date",
            3: "(V3) date",
            4: "(V4/D3) date",
            5: "(V5) date"
        }
        
        for visit_no, col_name in visit_column_map.items():
            print(f"Extracting Visit {visit_no}...")
            df_vaccination["study_id"] = clean_id_series(df_vaccination["study_id"])
            df_visit = (
                df_vaccination[df_vaccination["current_visit"] == visit_no]
                .drop_duplicates(subset="study_id", keep="last")[["study_id", "visit_date"]]
                .rename(columns={"visit_date": col_name})
            )
            
            if not df_visit.empty:
                df_visit["study_id"] = clean_id_series(df_visit["study_id"])
                df_cohort = df_cohort.merge(
                    df_visit,
                    left_on="Screening ID",
                    right_on="study_id",
                    how="left"
                )
                if "study_id" in df_cohort.columns:
                    df_cohort.drop(columns=["study_id"], inplace=True)
            else:
                df_cohort[col_name] = ""
                print(f"No records for Visit {visit_no}")
        
        # Add S.No
        df_cohort.insert(0, "S.No", range(1, len(df_cohort) + 1))
        
        # Reorder columns to structural specifications
        required_columns = [
            "S.No",
            "Screening ID",
            "Recruitment ID",
            "Incharge",
            "Result",
            "Cohort",
            "Decision",
            "Reason",
            "(V1/D1) date",
            "(V2/D2) date",
            "(V3) date",
            "(V4/D3) date",
            "(V5) date",
            "Date of confirmed visit"
        ]
        df_cohort_export = df_cohort[[col for col in required_columns if col in df_cohort.columns]].copy()
        
        # Preserve existing user-entered data securely
        print("Reading existing COHORT data...")
        try:
            df_existing = get_as_dataframe(dest_cohort).dropna(how="all")
            if not df_existing.empty and len(df_existing) > 0:
                df_existing.columns = df_existing.columns.str.strip()
                df_existing["Screening ID"] = clean_id_series(df_existing["Screening ID"])
                
                # User columns to map back over dynamically fetched dates
                user_cols = ["Result", "Cohort", "Decision", "Reason", "Date of confirmed visit"]
                
                for col in user_cols:
                    if col in df_existing.columns:
                        existing_map = dict(zip(df_existing["Screening ID"], df_existing[col]))
                        df_cohort_export[col] = df_cohort_export["Screening ID"].map(existing_map).fillna("")
                
                print(f"Preserved existing user data from {len(df_existing)} records")
            else:
                print("No existing data found - columns will be empty for new entries")
        except Exception as e:
            print(f"Could not read existing data: {str(e)}")
        
        # Write back to destinations
        print("Writing to COHORT Follow-up sheet...")
        dest_cohort.clear()
        set_with_dataframe(dest_cohort, df_cohort_export, include_index=False)
        
        # Format layout
        format_sheet(dest_cohort, len(df_cohort_export.columns), len(df_cohort_export))
        
        # Success summary
        print("COHORT Follow-up sheet updated successfully!")
        print(f"Rows: {len(df_cohort_export)} | Columns: {len(df_cohort_export.columns)}")
        
        return True
        
    except Exception as e:
        print(f"Error updating COHORT sheet: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


# =====================================================
# STEP 6: Main Entry Point
# =====================================================
def main():
    """Run both sheet updates"""
    # print("\n" + "="*70)
    print("CEIRR DATA SYNC - COMPLETE")
    # print("="*70)
    
    success_screening = update_screening_sheet()
    success_cohort = update_cohort_sheet()
    
    # Final summary
    # print("\n" + "="*70)
    if success_screening and success_cohort:
        print("ALL SHEETS UPDATED SUCCESSFULLY!")
        # print("="*70)
        print("Summary:")
        print("SCREENING sheet updated")
        print("COHORT Follow-up sheet updated")
        return True
    else:
        print("SOME UPDATES FAILED")
        print("="*70)
        if not success_screening:
            print("SCREENING sheet failed")
        if not success_cohort:
            print("COHORT Follow-up sheet failed")
        return False


# =====================================================
# STEP 7: Run Script
# =====================================================
if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
