"""Cambodia Road Crash Portal. Run: streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="Cambodia Road Crash Portal", page_icon="🛵", layout="wide")

pages = [
    st.Page("pages/1_overview.py", title="Overview: map and time", icon="🗺️", default=True),
    st.Page("pages/4_findings.py", title="Findings", icon="📌"),
    st.Page("pages/2_upload.py", title="Upload data", icon="📤"),
    st.Page("pages/3_data_quality.py", title="Data quality", icon="🧪"),
    st.Page("pages/5_methods.py", title="Methods and ethics", icon="📚"),
]
st.navigation(pages).run()
