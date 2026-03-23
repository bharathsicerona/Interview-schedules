import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Interview Dashboard", layout="wide")

st.title("🎯 Interview Tracking Dashboard")

CSV_FILE = "interviews.csv"
REQUIRED_COLUMNS = {"when_local", "status", "from", "subject"}

if not os.path.exists(CSV_FILE):
    st.warning(f"No data found! Please run your script first:\n`python gmail_interviews.py --days 30 --csv {CSV_FILE}`")
else:
    try:
        df = pd.read_csv(CSV_FILE)
    except Exception as exc:
        st.error(f"Could not read `{CSV_FILE}`: {exc}")
        st.stop()

    missing_columns = REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        st.error(
            "The CSV is missing required columns: "
            + ", ".join(sorted(missing_columns))
            + ". Re-run the export script to regenerate it."
        )
        st.stop()

    if df.empty:
        st.info("The CSV exists, but it does not contain any interview rows yet.")
        st.stop()

    df["when_local_dt"] = pd.to_datetime(df["when_local"], errors="coerce")
    if "event_when_local" in df.columns:
        df["event_when_local_dt"] = pd.to_datetime(df["event_when_local"], errors="coerce")
    else:
        df["event_when_local_dt"] = pd.NaT

    total_interviews = len(df)
    attended = len(df[df["status"] == "Attended"])
    cancelled = len(df[df["status"] == "Cancelled"])
    scheduled = len(df[df["status"] == "Scheduled"])

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Interviews", total_interviews)
    with col2:
        st.metric("Attended ✅", attended)
    with col3:
        st.metric("Cancelled ❌", cancelled)
    with col4:
        st.metric("Scheduled ⏳", scheduled)

    st.divider()

    status_options = ["Scheduled", "Attended", "Cancelled"]
    status_filter = st.multiselect(
        "Filter by Status",
        options=status_options,
        default=status_options,
    )

    filtered_df = df[df["status"].isin(status_filter)].copy()
    filtered_df = filtered_df.sort_values(by=["event_when_local_dt", "when_local_dt"], ascending=[False, False])

    if filtered_df.empty:
        st.info("No interviews match the current filter.")
    else:
        st.subheader("Interview Details")
        display_columns = ["when_local", "status", "from", "subject"]
        if "event_when_local" in filtered_df.columns:
            display_columns.insert(1, "event_when_local")
        st.dataframe(filtered_df[display_columns], use_container_width=True)
