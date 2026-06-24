import streamlit as st
import sqlite3
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from styles import inject_custom_css

st.set_page_config(page_title="Freshness Audits", layout="wide")
inject_custom_css()

@st.cache_resource
def get_conn():
    db_path = "data/pipeline.db"
    if not os.path.exists(db_path) and os.path.exists("../../../data/pipeline.db"):
        db_path = "../../../data/pipeline.db"
    elif not os.path.exists(db_path) and os.path.exists("../../data/pipeline.db"):
        db_path = "../../data/pipeline.db"
    elif not os.path.exists(db_path) and os.path.exists("../data/pipeline.db"):
        db_path = "../data/pipeline.db"
    return sqlite3.connect(db_path, check_same_thread=False)

conn = get_conn()

st.header(" Freshness Check")
st.markdown("Verifying news articles and job listings ingested within the sliding **24-hour freshness window**.")

st.markdown("### Freshness KPIs")

try:
    total_news = pd.read_sql("SELECT COUNT(*) as n FROM news", conn)["n"].iloc[0]
except Exception:
    total_news = 0

try:
    total_jobs = pd.read_sql("SELECT COUNT(*) as n FROM jobs", conn)["n"].iloc[0]
except Exception:
    total_jobs = 0

try:
    stale_dropped = pd.read_sql("SELECT SUM(stale_dropped) as n FROM pipeline_runs", conn)["n"].iloc[0]
    stale_dropped = int(stale_dropped) if pd.notna(stale_dropped) else 0
except Exception:
    stale_dropped = 0

total_fresh = total_news + total_jobs
compliance_rate = (total_fresh / (total_fresh + stale_dropped)) * 100 if (total_fresh + stale_dropped) > 0 else 100.0

k1, k2, k3 = st.columns(3)
k1.metric("Fresh Records (<24h)", f"{total_fresh:,}")
k2.metric("Dropped (>24h)", f"{stale_dropped:,}")
k3.metric("Freshness Compliance", f"{compliance_rate:.1f}%")

st.markdown("---")

cols = st.columns(2)
for i, table in enumerate(["news", "jobs"]):
    with cols[i]:
        st.subheader(f"Data Source: {table.capitalize()}")
        try:
            df = pd.read_sql(f"SELECT payload, collectedAt FROM {table} ORDER BY collectedAt DESC LIMIT 100", conn)
            if not df.empty:
                total_count = total_news if table == 'news' else total_jobs
                st.metric(label=f"Total tracked {table}", value=f"{total_count:,}")
                st.dataframe(df.head(50), use_container_width=True)
                st.caption("Verify published dates within the JSON payload.")
            else:
                st.info(f"No records found in '{table}'.")
        except Exception as e:
            st.warning(f"Failed to query '{table}': {str(e)}")
