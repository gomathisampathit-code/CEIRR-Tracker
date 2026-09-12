# =====================================================
# IMPORTS
# =====================================================
import pandas as pd
import gspread  # type: ignore[import]
import datetime as dt
import re


try:
    from google.oauth2.service_account import Credentials  # type: ignore[import]
except Exception:  # pragma: no cover - fallback for environments without google-auth
    class Credentials:  # lightweight shim to provide a clear error if used
        @staticmethod
        def from_service_account_file(*args, **kwargs):
            raise RuntimeError(
                "google-auth is required. Install with: pip install google-auth google-auth-oauthlib"
            )
from gspread_dataframe import get_as_dataframe  # type: ignore[import]

import importlib

try:
    _platypus = importlib.import_module("reportlab.platypus")
    _lib = importlib.import_module("reportlab.lib")
    SimpleDocTemplate = getattr(_platypus, "SimpleDocTemplate")
    Table = getattr(_platypus, "Table")
    TableStyle = getattr(_platypus, "TableStyle")
    Paragraph = getattr(_platypus, "Paragraph")
    Spacer = getattr(_platypus, "Spacer")
    PageBreak = getattr(_platypus, "PageBreak")
    colors = importlib.import_module("reportlab.lib.colors")
    getSampleStyleSheet = getattr(importlib.import_module("reportlab.lib.styles"), "getSampleStyleSheet")
    cm = getattr(importlib.import_module("reportlab.lib.units"), "cm")
    landscape = getattr(importlib.import_module("reportlab.lib.pagesizes"), "landscape")
    A4 = getattr(importlib.import_module("reportlab.lib.pagesizes"), "A4")
except Exception:  # pragma: no cover - allow environments without reportlab
    # Lightweight stubs so the module can be imported in environments
    # without reportlab installed (e.g., static analysis / tests).
    class SimpleDocTemplate:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    class Table:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    class TableStyle:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    class Paragraph:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    class Spacer:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass


    class PageBreak:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

    class colors:  # type: ignore
        black = None

    def getSampleStyleSheet():  # type: ignore
        return {}

    cm = 1
    landscape = None
    A4 = None

try:
    from streamlit import table
except Exception:
    def table(*args, **kwargs):
        return None


# =====================================================
# CONFIG
# =====================================================
DEST_SHEET_URL = "https://docs.google.com/spreadsheets/d/1z3ey_vJrTNtbLAPlzRXYWEJFRY4_-89nvJLwmSBXRfs/edit?usp=sharing"
SHEET_NAME = "Database"

import streamlit as st

visit_colors = {
    1: "#F2BE2D",
    2: "#63AFED",
    3: "#DC338E",
    4: "#508E21",
    5: "#A9FFFF"
}


# =====================================================
# AUTH (LOCAL)
# =====================================================
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
# LOAD DATA
# =====================================================
ws = gc.open_by_url(DEST_SHEET_URL).worksheet(SHEET_NAME)
df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how="all")


# =====================================================
# DATE CLEANING
# =====================================================
df["Date of Collection"] = pd.to_datetime(df["Date of Collection"], errors="coerce")
df["Date of Recruitment"] = pd.to_datetime(df["Date of Recruitment"], errors="coerce")

df["Visit 1 - 1D Notification"] = pd.to_datetime(
    df["Visit 1 - 1D Notification"], errors="coerce"
)

for col in [
    "Visit 2 - 2D Notification",
    "Visit 3 - S Notification",
    "Visit 4 - 3D Notification",
    "Visit 5 - S Notification"
]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")


# =====================================================
# WEEK LOGIC (SATURDAY → NEXT SUNDAY)
# =====================================================
#today = dt.date.today()

#start_date = today - dt.timedelta(days=(today.weekday() + 2) % 7)
#end_date = start_date + dt.timedelta(days=8)

today = dt.date.today()

# Upcoming Sunday
days_until_sunday = (6 - today.weekday()) % 7
start_date = today + dt.timedelta(days=days_until_sunday)

# Next Saturday
end_date = start_date + dt.timedelta(days=6)


def in_week(x):
    if pd.isna(x):
        return False
    return start_date <= x.date() <= end_date


print(f"Week Range: {start_date} to {end_date}")


# =====================================================
# PHONE FORMATTER
# =====================================================
def format_phone(phone):
    if pd.isna(phone):
        return ""
    nums = re.findall(r"\d+", str(phone))
    nums = [n for n in nums if len(n) >= 7]
    return " / ".join(nums)


# =====================================================
# MASTER LIST
# =====================================================
all_rows = []


# =====================================================
# VISIT 1 (SCREENING)
# =====================================================
v1 = df[df["Visit 1 - 1D Notification"].apply(in_week)].copy()

if not v1.empty:
    v1["Date of Collection/Recruitment"] = v1["Date of Collection"]

    v1["Notification Date"] = v1["Visit 1 - 1D Notification"]
    v1["_Visit_Color_Hex"] = visit_colors[1]

    v1["Phone Numbers"] = (
        v1[["Phone no.1", "Phone no.2"]]
        .fillna("")
        .astype(str)
        .agg(" / ".join, axis=1)
        .apply(format_phone)
    )

    all_rows.extend(v1.to_dict("records"))

v1_check = df[
    (df["Visit 1 - 1D Notification"].notna()) &
    (df["Visit 1 - 1D Notification"].dt.date >= start_date) &
    (df["Visit 1 - 1D Notification"].dt.date <= end_date)
]

print(f"\nVisit 1 records in week: {len(v1_check)}")
print(
    v1_check[
        ["Screening ID", "Visit 1 - 1D Notification"]
    ].to_string(index=False)
)

# =====================================================
# VISIT 2–5 (COHORT)
# =====================================================
visit_map = {
    "Visit 2 - 2D Notification": 2,
    "Visit 3 - S Notification": 3,
    "Visit 4 - 3D Notification": 4,
    "Visit 5 - S Notification": 5
}

for col, vnum in visit_map.items():

    if col not in df.columns:
        continue

    temp = df[df[col].apply(in_week)].copy()

    if temp.empty:
        continue

    temp["Date of Collection/Recruitment"] = temp["Date of Recruitment"]

    temp["Notification Date"] = temp[col]
    temp["_Visit_Color_Hex"] = visit_colors[vnum]

    temp["Phone Numbers"] = (
        temp[["Phone no.1", "Phone no.2"]]
        .fillna("")
        .astype(str)
        .agg(" / ".join, axis=1)
        .apply(format_phone)
    )

    # Correct Aravind dates for each visit
    if vnum == 2:
        temp["Aravind Available date1"] = temp["Aravind Visit2 date1"]
        temp["Aravind Available date2"] = temp["Aravind Visit2 date2"]

    elif vnum == 3:
        temp["Aravind Available date1"] = temp["Aravind Visit3 date1"]
        temp["Aravind Available date2"] = temp["Aravind Visit3 date2"]

    elif vnum == 4:
        temp["Aravind Available date1"] = temp["Aravind Visit4 date1"]
        temp["Aravind Available date2"] = temp["Aravind Visit4 date2"]

    elif vnum == 5:
        temp["Aravind Available date1"] = temp["Aravind Visit5 date1"]
        temp["Aravind Available date2"] = temp["Aravind Visit5 date2"]

    all_rows.extend(temp.to_dict("records"))  


# =====================================================
# FINAL DATAFRAME
# =====================================================
final_df = pd.DataFrame(all_rows)

if final_df.empty:
    print("No records found for this week.")
    exit()


# Fill missing columns
cols = [
    "Screening ID",
    "Recruitment ID",
    "Date of Collection/Recruitment",
    "Result",
    "Name",
    "Parents name",
    "Age",
    "Location",
    "Phone Numbers",
    "Incharge",
    "Notification Date",
    "Aravind Available date1",
    "Aravind Available date2",
    "_Visit_Color_Hex"
]

for c in cols:
    if c not in final_df.columns:
        final_df[c] = ""


# Combine name field
final_df["Name/Parent Name/Age/Location"] = (
    final_df["Name"].astype(str)
    + " (" + final_df["Parents name"].astype(str) + ") / "
    + final_df["Age"].astype(str) + " / "
    + final_df["Location"].astype(str)
)


final_df = final_df[[
    "Screening ID",
    "Recruitment ID",
    "Date of Collection/Recruitment",
    "Result",
    "Name/Parent Name/Age/Location",
    "Phone Numbers",
    "Incharge",
    "Notification Date",
    "Aravind Available date1",
    "Aravind Available date2",
    "_Visit_Color_Hex"
]]


# =====================================================
# PDF FUNCTION
# =====================================================

final_df["_Visit_Color_Hex"] = final_df.get("_Visit_Color_Hex", "#FFFFFF")

def create_pdf(df, filename, date_range, report_title):

    doc = SimpleDocTemplate(
        filename,
        pagesize=landscape(A4),
        leftMargin=10,
        rightMargin=10,
        topMargin=50,
        bottomMargin=110
    )

    styles = getSampleStyleSheet()

    title_style = styles["Heading1"]
    title_style.alignment = 1

    normal = styles["Normal"]
    normal.fontSize = 8

    display_df = df.copy()
    visible_cols = [c for c in display_df.columns if c != "_Visit_Color_Hex"]

    # Format dates
    for col in visible_cols:
        if pd.api.types.is_datetime64_any_dtype(display_df[col]):
            display_df[col] = display_df[col].dt.strftime("%Y-%m-%d")

    # ---------- Column Width ----------
    page_width = landscape(A4)[0]
    usable_width = page_width - 40

    base_widths = []

    for col in visible_cols:

        if "Name" in col:
            base_widths.append(6)

        elif "Phone" in col:
            base_widths.append(4)

        elif "Notification" in col or "Visit reminder" in col:
            base_widths.append(3)

        else:
            base_widths.append(2.5)

    scale = usable_width / sum(base_widths)
    col_widths = [w * scale for w in base_widths]

    # Notification column
    color_column = None

    if "Notification Date" in visible_cols:
        color_column = "Notification Date"

    elif "Date of confirmed visit" in visible_cols:
        color_column = "Date of confirmed visit"

    # ---------- Header ----------
    def header(canvas, doc):

        canvas.saveState()

        canvas.setFont("Helvetica-Bold",14)
        canvas.drawCentredString(420,575,report_title)

        canvas.setFont("Helvetica",9)
        canvas.drawString(
            30,
            555,
            f"Date of preparation: {dt.date.today().strftime('%d/%m/%y')}"
        )

        canvas.drawRightString(
            820,
            555,
            "Nurse Name: __________________"
        )

        canvas.restoreState()

    # ---------- Footer ----------
    def footer(canvas, doc):

        canvas.saveState()

        y=80

        canvas.setFont("Helvetica-Bold",8)
        canvas.drawString(30,y+55,"Details of visit:")

        legend=[
            ("V1: Screening",visit_colors[1]),
            ("V2: Dose 2",visit_colors[2]),
            ("V3: Sample",visit_colors[3]),
            ("V4: Dose 3",visit_colors[4]),
            ("V5: Sample",visit_colors[5]),
        ]

        x=30

        for text,color in legend:

            canvas.setFillColor(colors.HexColor(color))
            canvas.rect(x,y+35,120,15,fill=1)

            canvas.setFillColor(colors.black)
            canvas.setFont("Helvetica",7)

            canvas.drawString(x+3,y+39,text)

            x+=120

        canvas.setFont("Helvetica",7)

        canvas.drawString(
            30,
            y+20,
            "- For Call list – Kindly tick the confirmed Aravind date."
        )

        canvas.drawString(
            30,
            y+10,
            "- For Visit list – Call parents one day before confirmed visit."
        )

        canvas.drawString(
            30,
            y,
            "- Note comments against child record."
        )

        canvas.drawString(
            30,
            y-10,
            "- Update WhatsApp IORV group daily."
        )

        canvas.restoreState()

    # =====================================================
    # TABLES (10 RECORDS PER PAGE)
    # =====================================================

    elements=[]

    rows_per_page=10

    for start in range(0,len(display_df),rows_per_page):

        page_df=display_df.iloc[start:start+rows_per_page]

        table_data=[
            [Paragraph(str(c),normal) for c in visible_cols]
        ]

        for _,row in page_df.iterrows():

            table_data.append([
                Paragraph("" if pd.isna(row[c]) else str(row[c]),normal)
                for c in visible_cols
            ])

        table=Table(
            table_data,
            colWidths=col_widths,
            repeatRows=1
        )

        style=TableStyle([

            ("GRID",(0,0),(-1,-1),0.3,colors.grey),

            ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),

            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),

            ("FONTSIZE",(0,0),(-1,-1),8),

            ("ALIGN",(0,0),(-1,-1),"CENTER"),

            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),

        ])

        if color_column:

            notif_col=visible_cols.index(color_column)

            for r in range(len(page_df)):

                #clr=df.iloc[start+r]["_Visit_Color_Hex"]
                #clr = page_df.iloc[r]["_Visit_Color_Hex"]
                clr = page_df.iloc[r].get("_Visit_Color_Hex", "#FFFFFF")

                if pd.notna(clr):

                    style.add(
                        "BACKGROUND",
                        (notif_col,r+1),
                        (notif_col,r+1),
                        colors.HexColor(clr)
                    )

        table.setStyle(style)

        elements.append(table)

        if start+rows_per_page < len(display_df):

            elements.append(PageBreak())

    doc.build(
    elements,
    onFirstPage=lambda c, d: (
        header(c, d),
        footer(c, d)
    ),
    onLaterPages=lambda c, d: (
        header(c, d),
        footer(c, d)
    )
)

    print("PDF Created:",filename)


# =====================================================
# GENERATE PDF
# =====================================================
file_name = f"CEIRR_Screening_COHORT_Call_List{start_date}_to_{end_date}.pdf"

create_pdf(final_df, file_name, f"{start_date} to {end_date}", f"CEIRR Screening & COHORT Call List {start_date} to {end_date}")

# =====================================================
# VISIT LIST PDF
# =====================================================

visit_df = df.copy()

visit_df["Decision"] = (
    visit_df["Decision"]
    .astype(str)
    .str.strip()
    .str.lower()
)

visit_df = visit_df[
    visit_df["Decision"] == "yes"
].copy()

visit_df["Date of confirmed visit"] = pd.to_datetime(
    visit_df["Date of confirmed visit"],
    errors="coerce"
)

visit_df = visit_df[
    visit_df["Date of confirmed visit"].notna()
    & (visit_df["Date of confirmed visit"].dt.date >= start_date)
    & (visit_df["Date of confirmed visit"].dt.date <= end_date)
].copy()

completed_visit_cols = [
    "(V1/D1) date",
    "(V2/D2) date",
    "(V3/S) date",
    "(V4/D3) date",
]

def get_visit_order(row):
    filled = 0
    for c in completed_visit_cols:
        if c in visit_df.columns and pd.notna(row.get(c)) and str(row.get(c)).strip() != "":
            filled += 1
    return min(filled + 1, 5)

visit_df["Visit_Order"] = visit_df.apply(get_visit_order, axis=1)

EXCLUDED_FROM_V4_V5 = {
    "C-P002", "C-P003", "C-P009", "C-P011", "C-P013", "C-P015",
    "C-P016", "C-P017", "C-P019", "C-P022", "C-P023", "C-P024",
    "C-T003", "C-T011", "C-T019", "C-T049", "C-T052", "C-T060",
    "C-T067", "C-T068", "C-T071", "C-T072", "C-T078", "C-T081",
}
 
is_excluded_id = (
    visit_df["Recruitment ID"]
    .astype(str)
    .str.strip()
    .str.upper()
    .isin(EXCLUDED_FROM_V4_V5)
)
 
is_v4_or_v5 = visit_df["Visit_Order"].isin([4, 5])
 
visit_df = visit_df[~(is_excluded_id & is_v4_or_v5)].copy()
                                         
visit_df = visit_df.sort_values("Visit_Order")

visit_df["Date of Collection/Recruitment"] = visit_df["Date of Recruitment"]

visit_df.loc[
    visit_df["Recruitment ID"].isna()
    | (visit_df["Recruitment ID"].astype(str).str.strip() == ""),
    "Date of Collection/Recruitment"
] = visit_df["Date of Collection"]

visit_df["Name/Parent Name/Age/Location"] = (
    visit_df["Name"].astype(str)
    + " ("
    + visit_df["Parents name"].astype(str)
    + ") / "
    + visit_df["Age"].astype(str)
    + " / "
    + visit_df["Location"].astype(str)
)

visit_df["Phone Numbers"] = (
    visit_df[["Phone no.1", "Phone no.2"]]
    .fillna("")
    .astype(str)
    .agg(" / ".join, axis=1)
    .apply(format_phone)
)

visit_df["Visit reminder"] = (
    visit_df["Date of confirmed visit"]
    - pd.Timedelta(days=1)
)

visit_df["_Visit_Color_Hex"] = visit_colors[2]

visit_df.loc[
    visit_df["Recruitment ID"].isna()
    | (visit_df["Recruitment ID"].astype(str).str.strip() == ""),
    "_Visit_Color_Hex"
] = visit_colors[1]


visit_df = visit_df[
    [
        "Screening ID",
        "Recruitment ID",
        "Date of Collection/Recruitment",
        "Result",
        "Name/Parent Name/Age/Location",
        "Phone Numbers",
        "Incharge",
        "Date of confirmed visit",
        "Visit reminder",
        "_Visit_Color_Hex"
    ]
]


if visit_df.empty:

    print("No Visit List records found.")

else:

    visit_file_name = (
        f"CEIRR_Screening_COHORT_Visit_List_{start_date}_to_{end_date}.pdf"
    )

    create_pdf(
        visit_df,
        visit_file_name,
        f"{start_date} to {end_date}",
        f"CEIRR Screening & COHORT Visit List {start_date} to {end_date}"
    )

    print(f"Visit PDF Created: {visit_file_name}")


print("DONE")

# =====================================================
# SEND EMAIL
# =====================================================
from mail_04 import send_mail
import os

# make sure BOTH files exist from your PDF code
file_name = os.path.abspath(file_name)

visit_file_name = (
    os.path.abspath(visit_file_name)
    if visit_file_name else None
)

# send BOTH attachments
send_mail(
    start_date,
    end_date,
    os.path.abspath(file_name),
    os.path.abspath(visit_file_name) if visit_file_name else None
)
