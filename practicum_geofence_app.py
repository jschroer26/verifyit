import io
import math
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

# ---------- CONFIG: SITE COORDINATES (same list you gave me) ----------
SITE_COORDS = {
    "Laramie High School": (41.3021, -105.5485),
    "Laramie Middle School": (41.3256, -105.5721),
    "Whiting High School": (41.3106, -105.5686),
    "Centennial Elementary": (41.2982, -106.1364),
    "Harmony Elementary": (41.1714, -105.8814),
    "Indian Paintbrush": (41.3340, -105.5631),
    "Linford Elementary": (41.3115, -105.6300),
    "Rock River School": (41.7431, -105.9754),
    "Slade Elementary": (41.3204, -105.5866),
    "Spring Creek Elementary": (41.3060, -105.5860),
    "Laramie Montessori Charter": (41.3102, -105.5947),
    "Snowy Range Academy": (41.3155, -105.5458),
}

# ---------- HELPER FUNCTIONS ----------

def haversine_distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters between two lat/long points."""
    # If anything is missing, return NaN
    if any(pd.isna(v) for v in [lat1, lon1, lat2, lon2]):
        return np.nan

    # Convert to float explicitly
    lat1 = float(lat1)
    lon1 = float(lon1)
    lat2 = float(lat2)
    lon2 = float(lon2)

    # Convert degrees -> radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    # Haversine
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    R = 6371000  # Earth radius in meters
    return R * c


def clean_qualtrics_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Take the raw Qualtrics export and return a cleaned dataframe with:
    Student_ID, Site_Name, Recorded_Date, Student_Latitude, Student_Longitude, Logged_Hours
    """

    df = raw_df.copy()

    # Drop the "question text" row: LocationLatitude == "Location Latitude"
    if "LocationLatitude" in df.columns:
        df = df[df["LocationLatitude"] != "Location Latitude"].copy()

    # Basic column existence checks
    required_cols = ["RecordedDate", "LocationLatitude", "LocationLongitude", "Q2.1", "Q4", "Q5"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {', '.join(missing)}")

    # Consent filter (if Q2 exists and coded as 1)
    if "Q2" in df.columns:
        df = df[df["Q2"] == 1]

    # Build clean log
    clean = pd.DataFrame()
    clean["Student_ID"] = df["Q2.1"].astype(str).str.strip()
    clean["Site_Name"] = df["Q4"].astype(str).str.strip()

    # Recorded date as datetime
    clean["Recorded_Date"] = pd.to_datetime(df["RecordedDate"], errors="coerce")

    # Lat/Long as numeric
    clean["Student_Latitude"] = pd.to_numeric(df["LocationLatitude"], errors="coerce")
    clean["Student_Longitude"] = pd.to_numeric(df["LocationLongitude"], errors="coerce")

    # Logged hours as float (students enter decimal hours)
    clean["Logged_Hours"] = pd.to_numeric(df["Q5"], errors="coerce")

    return clean


def add_geofence_and_verification(clean_log: pd.DataFrame) -> pd.DataFrame:
    """Add Distance_From_Site_m, Verification_Status, Verified_Hours to the cleaned log."""

    log = clean_log.copy()

    # Compute distance
    distances = []
    for _, row in log.iterrows():
        site = row["Site_Name"]
        lat_s = row["Student_Latitude"]
        lon_s = row["Student_Longitude"]

        if site not in SITE_COORDS:
            distances.append(np.nan)
            continue

        lat_site, lon_site = SITE_COORDS[site]
        d_m = haversine_distance_m(lat_s, lon_s, lat_site, lon_site)
        distances.append(d_m)

    log["Distance_From_Site_m"] = distances

    # Verification rules
    def status_from_distance(d):
        if pd.isna(d):
            return "No Location/No Site"
        if d <= 100:
            return "Verified"
        if d <= 300:
            return "Review"
        return "Out of Range"

    log["Verification_Status"] = log["Distance_From_Site_m"].apply(status_from_distance)

    # Verified hours: only count hours when Verified
    log["Verified_Hours"] = np.where(
        log["Verification_Status"] == "Verified",
        log["Logged_Hours"].fillna(0),
        0.0
    )

    return log


def build_overviews(log: pd.DataFrame):
    """
    Build two summaries:
      1) By student
      2) By site (school)
    """
    if log.empty:
        empty_student = pd.DataFrame(
            columns=["Student_ID", "Total_Verified_Hours", "Verified_Visits", "Last_Recorded_Date"]
        )
        empty_site = pd.DataFrame(
            columns=["Site_Name", "Total_Verified_Hours", "Unique_Students", "Verified_Visits"]
        )
        return empty_student, empty_site

    # --- Summary by student ---
    summary_students = (
        log
        .groupby("Student_ID", dropna=False)
        .agg(
            Total_Verified_Hours=("Verified_Hours", "sum"),
            Verified_Visits=("Verification_Status", lambda x: (x == "Verified").sum()),
            Last_Recorded_Date=("Recorded_Date", "max"),
        )
        .reset_index()
        .sort_values("Student_ID")
    )

    # --- Summary by site (school) ---
    summary_sites = (
        log
        .groupby("Site_Name", dropna=False)
        .agg(
            Total_Verified_Hours=("Verified_Hours", "sum"),
            Unique_Students=("Student_ID", "nunique"),
            Verified_Visits=("Verification_Status", lambda x: (x == "Verified").sum()),
        )
        .reset_index()
        .sort_values("Total_Verified_Hours", ascending=False)
    )

    return summary_students, summary_sites


def make_output_workbook(log: pd.DataFrame,
                         summary_students: pd.DataFrame,
                         summary_sites: pd.DataFrame) -> bytes:
    """Return an Excel file (bytes) with Practicum_Log + two summary sheets."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        log.to_excel(writer, index=False, sheet_name="Practicum_Log")
        summary_students.to_excel(writer, index=False, sheet_name="Summary_By_Student")
        summary_sites.to_excel(writer, index=False, sheet_name="Summary_By_Site")
    return output.getvalue()


# ---------- STREAMLIT APP ----------

st.set_page_config(page_title="Practicum Geofence Verifier", layout="wide")

st.title("Practicum Attendance Geofence Verifier")
st.write(
    "Upload the **Qualtrics attendance export** for a practicum. "
    "This app will compute distance to the school, verify hours, and produce summaries by student and by site."
)

uploaded_file = st.file_uploader("Upload Qualtrics Excel or CSV file", type=["xlsx", "xls", "csv"])

if uploaded_file is not None:
    try:
        # Read file
        if uploaded_file.name.lower().endswith((".xlsx", ".xls")):
            raw_df = pd.read_excel(uploaded_file, sheet_name=0)
        else:
            raw_df = pd.read_csv(uploaded_file)

        st.subheader("Raw Data (first 10 rows)")
        st.dataframe(raw_df.head(10))

        # Clean + transform
        clean_log = clean_qualtrics_df(raw_df)

        st.subheader("Cleaned Log (before geofence)")
        st.dataframe(clean_log.head(20))

        # Add geofence verification
        verified_log = add_geofence_and_verification(clean_log)

        st.subheader("Verified Practicum Log")
        st.dataframe(verified_log.head(50))

        # Summaries
        summary_students, summary_sites = build_overviews(verified_log)

        st.subheader("Summary: Verified Hours by Student")
        st.dataframe(summary_students)

        st.subheader("Summary: Verified Hours by Site (School)")
        st.dataframe(summary_sites)

        # Build downloadable workbook
        excel_bytes = make_output_workbook(verified_log, summary_students, summary_sites)

        st.download_button(
            label="📥 Download Verified Excel (Log + Summaries)",
            data=excel_bytes,
            file_name=f"Practicum_Verified_{datetime.now().date()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.error(f"Something went wrong while processing the file:\n\n{e}")

else:
    st.info("Upload a Qualtrics export (.xlsx or .csv) to get started.")
