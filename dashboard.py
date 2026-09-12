import streamlit as st
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------
# Configuration
# ---------------------------------------------------

st.set_page_config(
    page_title="CEIRR Tracker Dashboard",
    page_icon="📊",
    layout="wide"
)

BASE_DIR = Path(__file__).parent

# Google Sheet destination ID extracted from your URLs
# URL: https://docs.google.com/spreadsheets/d/1uEaBqs8DoSF4X88ERq6KfXo54Abj7qtft_0lx1dxaxU/edit?usp=sharing
SPREADSHEET_ID = "1z3ey_vJrTNtbLAPlzRXYWEJFRY4_-89nvJLwmSBXRfs"
DOWNLOAD_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx"


# ---------------------------------------------------
# Function to run python scripts
# ---------------------------------------------------

def run_script(script_name):

    script_path = BASE_DIR / script_name

    if not script_path.exists():
        st.error(f"{script_name} not found.")
        return

    with st.spinner(f"Running {script_name}..."):

        process = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

    if process.returncode == 0:
        st.success(f"{script_name} completed successfully.")

        if process.stdout.strip():
            st.text_area(
                "Output",
                process.stdout,
                height=250
            )

    else:
        st.error(f"{script_name} failed.")

        st.text_area(
            "Error",
            process.stderr,
            height=300
        )


# ---------------------------------------------------
# Title
# ---------------------------------------------------

st.title("CEIRR Tracker Dashboard")

st.markdown("---")

st.write("### Weekly Processing")

col1, col2, col3 = st.columns(3)

# ---------------------------------------------------
# Button 1
# ---------------------------------------------------

with col1:

    st.subheader("SurveyCTO")

    if st.button(
        "Update Lab sheet Data",
        use_container_width=True
    ):
        run_script("lab_update.py")


# ---------------------------------------------------
# Button 2 (With Download Option)
# ---------------------------------------------------

with col2:

    st.subheader("Tracker")

    if st.button(
        "Update Google Tracker",
        use_container_width=True
    ):
        run_script("02G_tracker.py")
        
    st.write("") # Tiny spacer

    # Direct export link to download the Google Sheet as an Excel file (.xlsx)
    st.link_button(
        "📥 Download Tracker (Excel)",
        DOWNLOAD_URL,
        use_container_width=True
    )


# ---------------------------------------------------
# Button 3
# ---------------------------------------------------

with col3:

    st.subheader("PDF(Sat 9 AM Send Mail to All)")

    if st.button(
        "Generate PDF",
        use_container_width=True
    ):
        run_script("03pdf.py")


st.markdown("---")

# ---------------------------------------------------
# Complete Process
# ---------------------------------------------------

st.subheader("Complete Weekly Process (Sat 9 AM Mail Send to All)")

if st.button(
    "Run Complete Process",
    use_container_width=True
):

    scripts = [
        "lab_update.py",
        "02G_tracker.py",
        "03pdf.py"
    ]

    progress = st.progress(0)

    status = st.empty()

    for i, script in enumerate(scripts):

        status.info(f"Running {script}...")

        process = subprocess.run(
            [sys.executable, str(BASE_DIR / script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if process.returncode != 0:

            status.error(f"{script} failed.")

            st.text_area(
                f"Error in {script}",
                process.stderr,
                height=300
            )

            break

        progress.progress((i + 1) / len(scripts))

    else:

        status.success(" Complete Weekly Process Finished Successfully")
