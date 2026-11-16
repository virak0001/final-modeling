"""Findings: one sentence and one number each, with the chart that proves it."""
import pandas as pd
import streamlit as st

from src import ui
from src.findings import compute_findings

st.title("What we found")
st.markdown("Each finding is computed live from the data on this portal (2018-2024, uploads included) and is reproduced "
            "by `notebooks/analysis.ipynb`. A rejected hypothesis would be reported the same way.")


@st.cache_data(show_spinner=False)
def _findings(data: pd.DataFrame):
    return compute_findings(data, ui.census(), ui.worldbank(), ui.official())


for number, finding in enumerate(_findings(ui.crashes(True)), start=1):
    st.markdown(f"#### {number}. {finding.sentence}")
    if finding.hypothesis:
        st.markdown(f"**{finding.hypothesis}.**")
    st.plotly_chart(finding.figure, config={"displayModeBar": False}, key=f"finding_{finding.key}")
    st.caption(f"What it does not prove: {finding.caveat}")
    st.divider()
