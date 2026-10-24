"""
05_visit_lists.py
Creates three PDFs from the CEIRR Google Sheet, in the same layout as the
weekly call list:

    CEIRR visit1 list.pdf -> records after CEIR-<START_AFTER>, V1 not done, due <= DUE_CUTOFF
    CEIRR visit2 list.pdf -> whole sheet: V1 done, V2 not done, due <= DUE_CUTOFF (incl. overdue)
    CEIRR visit3 list.pdf -> whole sheet: V2 done, V3 not done, due <= DUE_CUTOFF (incl. overdue)

Run:  python 05_visit_lists.py
The Google Sheet must be shared with your service-account e-mail (Viewer is enough).
"""
import os
import re
import datetime as dt
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

# ----------------------------------------------------------------- CONFIG --
SHEET_URL = "https://docs.google.com/spreadsheets/d/1z3ey_vJrTNtbLAPlzRXYWEJFRY4_-89nvJLwmSBXRfs/edit?usp=sharing"   # full URL or just the sheet id
WORKSHEET_NAME = Database            # e.g. "COHORT Follow-up"; None = first tab
CREDS_FILE = os.environ.get("gcp_service_account", "service_account.json")

START_AFTER = 1025               # Visit-1 list only looks at CEIR-numbers > this. None = no limit
DUE_CUTOFF = dt.date(2026, 12, 14)
OUT_DIR = "."

# Rows whose "Decision" matches this are left out (drop-outs etc.). Edit to match your sheet.
EXCLUDE_DECISION = r"withdr|drop|refus|declin|not willing|not interested|lost|death|ineligible"

# Visit-1 fallback when the sheet's own notification/Aravind columns are blank
V1_NOTIF_DAYS, V1_ARAVIND1_DAYS, V1_ARAVIND2_DAYS = 14, 21, 22   # as seen in your call list

VISITS = {
    1: dict(date="(V1/D1) date", prev=None,
            notif="Visit 1 - 1D Notification",
            a1="Aravind Available date1", a2="Aravind Available date2"),
    2: dict(date="(V2/D2) date", prev="(V1/D1) date",
            notif="Visit 2 - 2D Notification",
            a1="Aravind Visit2 date1", a2="Aravind Visit2 date2"),
    3: dict(date="(V3/S) date", prev="(V2/D2) date",
            notif="Visit 3 - S Notification",
            a1="Aravind Visit3 date1", a2="Aravind Visit3 date2"),
}


# ------------------------------------------------------------ LOAD SHEET --
def load_sheet() -> pd.DataFrame:
    import gspread
    gc = gspread.service_account(filename=CREDS_FILE)
    sh = gc.open_by_url(SHEET_URL) if SHEET_URL.startswith("http") else gc.open_by_key(SHEET_URL)
    ws = sh.worksheet(WORKSHEET_NAME) if WORKSHEET_NAME else sh.sheet1
    values = ws.get_all_values()
    headers, seen = [], {}
    for h in values[0]:
        h = " ".join(h.split())
        seen[h] = seen.get(h, 0) + 1
        headers.append(h if seen[h] == 1 else f"{h}__{seen[h]}")
    df = pd.DataFrame(values[1:], columns=headers)
    return df.replace(r"^\s*$", pd.NA, regex=True)


# ---------------------------------------------------------------- HELPERS --
def to_date(s: pd.Series) -> pd.Series:
    """Parse ISO (2026-10-12) first, then day-first (12/10/2026)."""
    s = s.astype("string")
    out = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    rest = out.isna() & s.notna()
    if rest.any():
        out[rest] = pd.to_datetime(s[rest], dayfirst=True, errors="coerce")
    return out


def screening_no(x):
    m = re.search(r"(\d+)\s*$", str(x))
    return int(m.group(1)) if m else None


def fmt(d):
    return "" if pd.isna(d) else pd.Timestamp(d).strftime("%Y-%m-%d")


def col(df, name):
    return df[name] if name in df.columns else pd.Series(pd.NA, index=df.index)


# -------------------------------------------------------------- SELECTION --
def select_visit(df: pd.DataFrame, n: int) -> pd.DataFrame:
    cfg = VISITS[n]
    d = df.copy()
    d["_no"] = d["Screening ID"].map(screening_no)
    d["_anchor"] = to_date(col(d, "Date of Recruitment")).fillna(to_date(col(d, "Date of Collection")))
    d["_done"] = to_date(col(d, cfg["date"]))
    d["_notif"] = to_date(col(d, cfg["notif"]))
    d["_a1"] = to_date(col(d, cfg["a1"]))
    d["_a2"] = to_date(col(d, cfg["a2"]))

    if n == 1:
        d = d[d["_anchor"].notna()]
        if START_AFTER is not None:
            d = d[d["_no"] > START_AFTER]
        fill = d["_notif"].isna()
        d.loc[fill, "_notif"] = d.loc[fill, "_anchor"] + pd.Timedelta(days=V1_NOTIF_DAYS)
        fill = d["_a1"].isna()
        d.loc[fill, "_a1"] = d.loc[fill, "_anchor"] + pd.Timedelta(days=V1_ARAVIND1_DAYS)
        fill = d["_a2"].isna()
        d.loc[fill, "_a2"] = d.loc[fill, "_anchor"] + pd.Timedelta(days=V1_ARAVIND2_DAYS)
    else:
        d = d[to_date(col(d, cfg["prev"])).reindex(d.index).notna()]   # previous visit done = eligible

    d = d[d["_done"].isna()]                                   # has NOT come for this visit
    d = d[d["_notif"].notna() & (d["_notif"].dt.date <= DUE_CUTOFF)]
    drop = col(d, "Decision").astype("string").str.contains(EXCLUDE_DECISION, case=False, na=False)
    d = d[~drop]
    return d.sort_values(["_notif", "_no"]).reset_index(drop=True)


# -------------------------------------------------------------------- PDF --
HEAD = ["Screening ID", "Recruitment ID", "Date of Collection/ Recruitment", "Result",
        "Name/Parent Name/Age/Location", "Phone Numbers", "Incharge", "Notification Date",
        "Aravind Available date1", "Aravind Available date2"]
COL_W = [52, 58, 62, 52, 242, 78, 62, 58, 58, 58]

BULLETS = ["For Call list \u2013 Kindly tick the confirmed Aravind date.",
           "For Visit list \u2013 Call parents one day before confirmed visit.",
           "Note comments against child record.",
           "Update WhatsApp IORV group daily."]


def g(row, name):
    v = row.get(name, pd.NA)
    return "" if pd.isna(v) else str(v).strip()


def build_rows(d, st):
    rows = [[Paragraph(f"<b>{h}</b>", st) for h in HEAD]]
    for _, r in d.iterrows():
        who = f"{g(r,'Name')} ({g(r,'Parents name')}) / {g(r,'Age')} / {g(r,'Location')}"
        phones = " /<br/>".join(escape(p) for p in (g(r, "Phone no.1"), g(r, "Phone no.2")) if p)
        result = g(r, "Result") or g(r, "Result Type")
        cells = [g(r, "Screening ID"), g(r, "Recruitment ID"), fmt(r["_anchor"]), result,
                 None, None, g(r, "Incharge"), fmt(r["_notif"]), fmt(r["_a1"]), fmt(r["_a2"])]
        out = []
        for i, c in enumerate(cells):
            if i == 4:
                out.append(Paragraph(escape(who), st))
            elif i == 5:
                out.append(Paragraph(phones, st))
            else:
                out.append(Paragraph(escape(c), st))
        rows.append(out)
    return rows


def make_pdf(d: pd.DataFrame, n: int, path: str):
    title = f"CEIRR Visit {n} List \u2013 due up to {DUE_CUTOFF:%d/%m/%Y}"
    prep = dt.date.today().strftime("%d/%m/%y")
    base = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=base["Normal"], fontSize=7.5, leading=9)
    top_h = 118

    def on_page(c, doc):
        w, h = landscape(A4)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20, h - 28, title)
        c.setFont("Helvetica", 8.5)
        c.drawString(20, h - 44, f"Date of preparation: {prep}")
        c.drawString(300, h - 44, "Nurse Name: ______________________")
        c.drawRightString(w - 20, h - 28, f"Page {doc.page}")
        c.drawString(20, h - 60, "Details of visit:  V1: Screening   V2: Dose 2   V3: Sample   V4: Dose 3   V5: Sample")
        y = h - 73
        for b in BULLETS:
            c.drawString(26, y, "\u2022 " + b)
            y -= 10.5

    doc = BaseDocTemplate(path, pagesize=landscape(A4), leftMargin=20, rightMargin=20,
                          topMargin=top_h, bottomMargin=24, title=title)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=on_page)])

    story = []
    if d.empty:
        story.append(Paragraph("No eligible records found for this list.", base["Normal"]))
    else:
        t = Table(build_rows(d, cell), colWidths=COL_W, repeatRows=1)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story += [t, Spacer(1, 8), Paragraph(f"<b>Total records: {len(d)}</b>", cell)]
    doc.build(story)


# ------------------------------------------------------------------- MAIN --
def main(df=None):
    df = load_sheet() if df is None else df
    print(f"Sheet rows read: {len(df)}")
    os.makedirs(OUT_DIR, exist_ok=True)
    for n in (1, 2, 3):
        d = select_visit(df, n)
        path = os.path.join(OUT_DIR, f"CEIRR visit{n} list.pdf")
        make_pdf(d, n, path)
        print(f"Visit {n}: {len(d)} records -> {path}")
        if n == 1 and d.empty:
            print("  (Visit 1 list is empty - check START_AFTER / Date of Recruitment in the sheet)")


if __name__ == "__main__":
    main()
