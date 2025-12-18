import io
import math
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st


# ---------- HELPER FUNCTIONS ----------

def haversine_distance_m(lat1, lon1, lat2, lon2):
    """
    Great-circle distance in meters between two lat/long points.
    All args should be convertible to float. Returns np.nan if anything is missing.
    """
    if any(pd.isna(v) for v in [lat1, lon1, lat2, lon2]):
        return np.nan

    lat1 = float(lat1)
    lon1 = float(lon1)
    lat2 = float(lat2)
    lon2 = float(lon2)

    # degrees -> radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    # Haversine
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    R = 6371000  # Earth radius (m)
    return R * c


def load_site_coordinates(site_file) -> dict:
    """
    Load a Site_Coordinates file and return a dict:
        { "Site Name": (lat, lon), ... }

    Accepts .xlsx, .xls, .csv.
    Tolerates:
      - header in first or second row
      - minor variations in column names, e.g.
        'Site_Name', 'Site Name', 'SITE NAME'
        'Lat', 'Latitude (deg)', etc.
    """
    # 1) Read file: try Excel vs CSV
    if site_file.name.lower().endswith((".xlsx", ".xls")):
        tried = []
        for header_row in [0, 1]:
            try:
                df_try = pd.read_excel(site_file, sheet_name=0, header=header_row)
                tried.append(df_try)
            except Exception:
                continue
        if not tried:
            raise ValueError("Could not read Site_Coordinates Excel file.")
        sites_df = tried[0]  # first successful read
    else:
        sites_df = pd.read_csv(site_file)

    # 2) Normalize column names (strip whitespace)
    sites_df.columns = [str(c).strip() for c in sites_df.columns]
    cols = list(sites_df.columns)

    # Helper to find a column by keyword(s) in its name
    def find_col(keywords):
        # keywords: list of substrings that must all be present in lowercased col name
        for c in cols:
            low = c.lower()
            if all(k in low for k in keywords):
                return c
        return None

    # 3) Try to identify the three needed columns
    site_col = find_col(["site", "name"]) or find_col(["site"])
    lat_col = find_col(["lat"])          # matches Latitude, Lat, etc.
    lon_col = find_col(["lon"])          # matches Longitude, Long, etc.

    missing = []
    if site_col is None:
        missing.append("Site_Name")
    if lat_col is None:
        missing.append("Latitude")
    if lon_col is None:
        missing.append("Longitude")

    if missing:
        raise ValueError(
            "Site_Coordinates file missing columns (case-insensitive, flexible names): "
            + ", ".join(missing)
            + "\n\nDetected columns: "
            + ", ".join(cols)
        )

    # 4) Drop rows without a site name
    sites_df = sites_df.dropna(subset=[site_col]).copy()

    # 5) Build dict
    site_coords = {}
    for _, row in sites_df.iterrows():
        name = str(row[site_col]).strip()
        lat = pd.to_numeric(row[lat_col], errors="coerce")
        lon = pd.to_numeric(row[lon_col], errors="coerce")
        if pd.isna(lat) or pd.isna(lon):
            continue
        site_coords[name] = (float(lat), float(lon))

    if not site_coords:
        raise ValueError(
            "No valid site rows found in Site_Coordinates file.\n"
            "Make sure Latitude/Longitude cells are numeric."
        )

    return site_coords


def clean_qualtrics_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Take the raw Qualtrics export and return a cleaned dataframe with:
      Student_ID, Site_Name, Recorded_Date, Student_Latitude, Student_Longitude, Logged_Hours
    """
    df = raw_df.copy()

    # Drop the "question text" row: LocationLatitude == "Location Latitude"
    if "LocationLatitude" in df.columns:
        df = df[df["LocationLatitude"] != "Location Latitude"].copy()

    required_cols = ["RecordedDate", "LocationLatitude", "LocationLongitude", "Q2.1", "Q4", "Q5"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Qualtrics file missing expected columns: {', '.join(missing)}")

    # Filter to consent = 1 if Q2 exists
    if "Q2" in df.columns:
        df = df[df["Q2"] == 1]

    clean = pd.DataFrame()
    clean["Student_ID"] = df["Q2.1"].astype(str).str.strip()
    clean["Site_Name"] = df["Q4"].astype(str).str.strip()

    clean["Recorded_Date"] = pd.to_datetime(df["RecordedDate"], errors="coerce")
    clean["Student_Latitude"] = pd.to_numeric(df["LocationLatitude"], errors="coerce")
    clean["Student_Longitude"] = pd.to_numeric(df["LocationLongitude"], errors="coerce")
    clean["Logged_Hours"] = pd.to_numeric(df["Q5"], errors="coerce")

    return clean


def add_geofence_and_verification(clean_log: pd.DataFrame, site_coords: dict) -> pd.DataFrame:
    """
    Add Distance_From_Site_m, Verification_Status, Verified_Hours to the cleaned log,
    using a site_coords dict: {Site_Name: (lat, lon), ...}
    """
    log = clean_log.copy()

    def compute_distance(row):
        site = row["Site_Name"]
        lat_s = row["Student_Latitude"]
        lon_s = row["Student_Longitude"]

        if site not in site_coords:
            return np.nan

        lat_site, lon_site = site_coords[site]
        return haversine_distance_m(lat_s, lon_s, lat_site, lon_site)

    log["Distance_From_Site_m"] = log.apply(compute_distance, axis=1)

    def status_from_distance(d):
        if pd.isna(d):
            return "No Location/No Site"
        if d <= 100:
            return "Verified"
        if d <= 300:
            return "Review"
        return "Out of Range"

    log["Verification_Status"] = log["Distance_From_Site_m"].apply(status_from_distance)

    log["Verified_Hours"] = np.where(
        log["Verification_Status"] == "Verified",
        log["Logged_Hours"].fillna(0),
        0.0,
    )

    return log


def build_student_summary(log: pd.DataFrame) -> pd.DataFrame:
    """Summary: total verified hours by student."""
    if log.empty:
        return pd.DataFrame(
            columns=["Student_ID", "Total_Verified_Hours", "Verified_Visits", "Last_Recorded_Date"]
        )

    summary = (
        log.groupby("Student_ID", dropna=False)
           .agg(
               Total_Verified_Hours=("Verified_Hours", "sum"),
               Verified_Visits=("Verification_Status", lambda x: (x == "Verified").sum()),
               Last_Recorded_Date=("Recorded_Date", "max"),
           )
           .reset_index()
    )
    return summary.sort_values("Student_ID")


def build_site_summary(log: pd.DataFrame) -> pd.DataFrame:
    """
    Extended site summary:
      - Total verified hours
      - Verified visits
      - Unique students
      - Average hours per visit (Verified)
    """
    if log.empty:
        return pd.DataFrame(
            columns=[
                "Site_Name",
                "Total_Verified_Hours",
                "Verified_Visits",
                "Unique_Students",
                "Avg_Hours_Per_Visit",
            ]
        )

    base = (
        log.groupby("Site_Name", dropna=False)
           .agg(
               Total_Verified_Hours=("Verified_Hours", "sum"),
               Verified_Visits=("Verification_Status", lambda x: (x == "Verified").sum()),
               Unique_Students=("Student_ID", pd.Series.nunique),
           )
           .reset_index()
    )

    # Avoid divide-by-zero
    base["Avg_Hours_Per_Visit"] = np.where(
        base["Verified_Visits"] > 0,
        base["Total_Verified_Hours"] / base["Verified_Visits"],
        0.0,
    )

    return base.sort_values("Site_Name")


def make_output_workbook(log: pd.DataFrame,
                         student_summary: pd.DataFrame,
                         site_summary: pd.DataFrame) -> bytes:
    """
    Return an Excel file (bytes) with three sheets:
      - Practicum_Log
      - Student_Summary
      - Site_Summary
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        log.to_excel(writer, index=False, sheet_name="Practicum_Log")
        student_summary.to_excel(writer, index=False, sheet_name="Student_Summary")
        site_summary.to_excel(writer, index=False, sheet_name="Site_Summary")
    return output.getvalue()


# ---------- STREAMLIT APP ----------

st.set_page_config(page_title="Practicum Geofence Verifier", layout="wide")

st.title("Practicum Attendance Geofence Verifier")

st.markdown(
    """
1. Upload a **Site_Coordinates** file (Excel/CSV) with columns (any case/spaces):  
   - `Site_Name` or `Site Name`  
   - `Latitude`  
   - `Longitude`  

2. Upload the **Qualtrics attendance export** for a practicum.  

3. Download an Excel file with:  
   - Full practicum log + verification  
   - **Student summary** (total verified hours per student)  
   - **Site summary** (total verified hours per site, visits, unique students, avg hours/visit)
"""
)

col_sites, col_data = st.columns(2)

with col_sites:
    site_file = st.file_uploader(
        "Upload Site_Coordinates file (Excel or CSV)",
        type=["xlsx", "xls", "csv"],
        key="sites",
    )

with col_data:
    qualtrics_file = st.file_uploader(
        "Upload Qualtrics attendance export (Excel or CSV)",
        type=["xlsx", "xls", "csv"],
        key="qualtrics",
    )

if site_file is not None and qualtrics_file is not None:
    try:
        # Load site coordinates (robust)
        site_coords = load_site_coordinates(site_file)

        st.subheader("Loaded Site Coordinates")
        st.write(f"Sites found: {len(site_coords)}")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Site_Name": name, "Latitude": lat, "Longitude": lon}
                    for name, (lat, lon) in site_coords.items()
                ]
            )
        )

        # Read Qualtrics data
        if qualtrics_file.name.lower().endswith((".xlsx", ".xls")):
            raw_df = pd.read_excel(qualtrics_file, sheet_name=0)
        else:
            raw_df = pd.read_csv(qualtrics_file)

        st.subheader("Raw Qualtrics Data (first 10 rows)")
        st.dataframe(raw_df.head(10))

        # Clean log
        clean_log = clean_qualtrics_df(raw_df)
        st.subheader("Cleaned Practicum Log (before geofence)")
        st.dataframe(clean_log.head(20))

        # Geofence + verification
        verified_log = add_geofence_and_verification(clean_log, site_coords)
        st.subheader("Verified Practicum Log (sample rows)")
        st.dataframe(verified_log.head(50))

        # Summaries
        student_summary = build_student_summary(verified_log)
        site_summary = build_site_summary(verified_log)

        st.subheader("Summary: Verified Hours by Student")
        st.dataframe(student_summary)

        # ---------- NEW: VISUALIZATION OF VERIFIED HOURS BY STUDENT ----------
        if not student_summary.empty:
            st.markdown("**Bar Chart: Total Verified Hours per Student**")

            # Optionally limit to top N students for readability
            top_n = st.slider(
                "Maximum number of students to display (by verified hours)",
                min_value=5,
                max_value=min(50, len(student_summary)),
                value=min(20, len(student_summary)),
            )

            # Sort by hours descending and select top_n
            student_chart_df = (
                student_summary
                .sort_values("Total_Verified_Hours", ascending=False)
                .head(top_n)
                .set_index("Student_ID")[["Total_Verified_Hours"]]
            )

            st.bar_chart(student_chart_df)

        st.subheader("Summary: Verified Hours by Site")
        st.dataframe(site_summary)

        # ---------- NEW: STUDENTS WITH 'REVIEW' ITEMS ----------
        st.subheader("Students with Entries Flagged for Review")

        if not verified_log.empty:
            review_summary = (
                verified_log
                .groupby("Student_ID", dropna=False)
                .agg(
                    Review_Count=("Verification_Status", lambda x: (x == "Review").sum()),
                    Total_Entries=("Verification_Status", "size"),
                )
                .reset_index()
            )

            review_summary = review_summary[review_summary["Review_Count"] > 0]

            if review_summary.empty:
                st.success("No students currently have entries flagged for Review. 🎉")
            else:
                # Table
                st.dataframe(review_summary.sort_values("Review_Count", ascending=False))

                # Bar chart of Review_Count
                st.markdown("**Bar Chart: Count of 'Review' Entries per Student**")
                review_chart_df = (
                    review_summary
                    .sort_values("Review_Count", ascending=False)
                    .set_index("Student_ID")[["Review_Count"]]
                )
                st.bar_chart(review_chart_df)
        else:
            st.info("No verified log data available to compute review flags.")

        # Export
        excel_bytes = make_output_workbook(verified_log, student_summary, site_summary)

        st.download_button(
            label="📥 Download Verified Excel (Log + Student + Site summaries)",
            data=excel_bytes,
            file_name=f"Practicum_Verified_{datetime.now().date()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as e:
        st.error(f"Something went wrong while processing the file:\n\n{e}")

elif site_file is None and qualtrics_file is None:
    st.info("Upload a **Site_Coordinates** file and a **Qualtrics export** to get started.")
elif site_file is None:
    st.info("Please upload a **Site_Coordinates** file.")
else:
    st.info("Please upload a **Qualtrics attendance export** file.")
