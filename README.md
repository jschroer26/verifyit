# verifyit
Practicum Geofencing Verification App
Absolutely — here is a polished, professional `README.md` you can drop straight into GitHub, including project description, usage instructions, screenshots placeholders, structure explanation, and GPL v3 licensing language.

Feel free to adjust branding references to your university or course.

---

# Practicum Attendance Geofence Verifier

*A Streamlit app to verify preservice educator practicum attendance using GPS-based geofencing*

---

## 📌 Overview

Teacher preparation programs face a common challenge:
**How do we verify that preservice teachers are truly completing their observation and practicum hours on-site?**

This web app allows instructors to upload a **Qualtrics practicum attendance export**, and automatically:

* Extract student ID, hours, school placement, and timestamp
* Geographically verify submissions using GPS lat/long geofencing
* Classify logs as `Verified`, `Review`, or `Out of Range`
* Calculate `Verified Hours` by student
* Produce downloadable Excel reports (log + summary)
* Run entirely through a user-friendly Streamlit dashboard

The goal is to remove administrative burden, allow scalable verification, and support accountability with minimal mentor teacher load.

This project is used in **University of Wyoming preservice educator practicums**, but the code is generic enough to be adapted to any teacher-education program.

---

## 🔍 How It Works (High-Level)

1. **Instructor uploads Qualtrics export**
   (`.xlsx`, `.xls`, or `.csv`)

2. The app:

   * Cleans the data
   * Removes the Qualtrics question header row
   * Extracts student name + site + hours
   * Converts student coordinates to floats

3. Using the embedded school coordinate dictionary, the app:

   * Calculates Haversine distance from school site
   * Flags submissions into 4 tiers:
     `Verified`, `Review`, `Out of Range`, `No Location/No Site`

4. Hours are counted only if status = `Verified`

5. Users can:

   * View raw log
   * View cleaned + verified log
   * View summary by student
   * Download finalized Excel workbook

---

## 🗂 Project Structure

```
/streamlit_app.py    → Main application file
/README.md           → Project documentation (this file)
/LICENSE             → GNU GPL v3 license file
/fake_data/          → Optional: sample test data
```

---

## 🚀 Requirements

Python ≥ 3.9
Recommended packages:

```
streamlit
pandas
numpy
openpyxl
```

Install via:

```
pip install -r requirements.txt
```

---

## ▶️ Running Locally

```bash
streamlit run streamlit_app.py
```

Then open:

```
http://localhost:8501
```

---

## 📁 Expected Data Format

Qualtrics export must include at minimum:

* `RecordedDate`
* `LocationLatitude`
* `LocationLongitude`
* `Q2` (consent flag = 1)
* `Q2.1` (student ID or W# reference)
* `Q4` (site name)
* `Q5` (decimal hours logged)

The system automatically removes the first row of question text.

---

## 📍 Geofencing Logic

The app validates student GPS submissions by calculating great-circle distance between:

* Recorded student location
  and
* Official school coordinates (provided in-app)

Rules:

* ≤ 100m → `Verified`
* 101–300m → `Review`
* > 300m → `Out of Range`

These thresholds may be tuned in code.

---

## 📊 Output Report

Downloadable Excel workbook contains:

### Sheet 1: Practicum_Log

* Student
* Date/time
* School site
* Hours reported
* Distance to site
* Verification status
* Verified hours

### Sheet 2: Summary

Aggregates by student:

* Total verified hours
* Count of verified visits
* Most recent recorded submission

---

## 🧪 Testing With Fake Data

Included in development:
`Practicum1_Attendance_FakeData.xlsx` (optional)

This dataset contains multiple students, randomized days, and valid geo locations to test app logic before going live.

---

## 🔒 Privacy Notes

* The app does not permanently store uploaded student data.
* All verification occurs in-memory.
* No user information is transmitted to external services.
* Data download remains local to user.

---

## 🤝 Contributions

Pull requests, feature additions, and bug reports are welcome.
Possible future additions:

* Mentor teacher digital signature workflow
* Student check-in/check-out pairing logic
* Multi-district support
* API-based school coordinate imports
* UI filtering + chart dashboards

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

You are free to:

* Run, study, and modify this software
* Redistribute code under the same license

Full license text can be found in `LICENSE`.

---

## 👨‍🏫 Attribution

Developed to support practicum oversight for university-level teacher preparation programs.

If publishing academic or commercial derivatives, please cite original work.

---

If you want, I can also supply:

✔ `requirements.txt`
✔ a `LICENSE` file already written
✔ GitHub Actions deployment
✔ Screenshot placeholders
✔ Badges for PyPI/Streamlit/GitHub Pages
✔ Documentation site structure

Just say the word.
