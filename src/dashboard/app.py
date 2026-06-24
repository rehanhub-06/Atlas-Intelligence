import sys
import os
import streamlit as st
import sqlite3
import pandas as pd

# Ensure the dashboard directory is in path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from queries import vertical_counts, failed_extractions_count
from styles import inject_custom_css

st.set_page_config(page_title="Atlas Intelligence", layout="wide", initial_sidebar_state="expanded")
inject_custom_css()

@st.cache_resource
def get_conn():
    db_path = "data/pipeline.db"
    if not os.path.exists(db_path) and os.path.exists("../../data/pipeline.db"):
        db_path = "../../data/pipeline.db"
    elif not os.path.exists(db_path) and os.path.exists("../data/pipeline.db"):
        db_path = "../data/pipeline.db"
    return sqlite3.connect(db_path, check_same_thread=False)

conn = get_conn()
st.title(" Atlas Intelligence Platform")
st.markdown("---")

# Fetch latest run stats
try:
    latest_run = pd.read_sql("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1", conn)
except Exception:
    latest_run = pd.DataFrame()

if not latest_run.empty:
    run = latest_run.iloc[0]
    st.subheader(" Latest Pipeline Run")
    rc1, rc2, rc3, rc4 = st.columns(4)
    
    # Handle NULL values if the run is still currently in progress
    records = int(run['records_processed']) if pd.notna(run.get('records_processed')) else 0
    dupes = int(run['duplicates_skipped']) if pd.notna(run.get('duplicates_skipped')) else 0
    fallbacks_count = int(run['fallback_count']) if pd.notna(run.get('fallback_count')) else 0
    
    rc1.metric("Run ID", str(run["run_id"])[:8])
    rc2.metric("Records Processed", f"{records:,}")
    rc3.metric("Duplicates Skipped", f"{dupes:,}")
    rc4.metric("LLM Fallbacks Triggered", f"{fallbacks_count:,}")
    st.markdown("---")

st.subheader("Global Ingestion Metrics")
df = vertical_counts(conn)

if not df.empty:
    cols = st.columns(len(df))
    for col, (_, row) in zip(cols, df.iterrows()):
        name = str(row["rt"]).replace("_", " ").title()
        col.metric(label=name, value=f"{int(row['n']):,}")
else:
    st.info("No data ingested yet. Run the pipeline to populate metrics.")

st.markdown("---")

st.markdown("###  Pipeline Health & Cost Savings")
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Operations Health")
    total_records = int(df["n"].sum()) if not df.empty else 0
    try:
        failed_count = failed_extractions_count(conn)
    except Exception:
        failed_count = 0
        
    success_rate = ((total_records) / (total_records + failed_count)) * 100 if (total_records + failed_count) > 0 else 100.0
    
    hc1, hc2 = st.columns(2)
    hc1.metric("Success Rate", f"{success_rate:.2f}%")
    hc2.metric("Failed Extractions", failed_count)
    
with col2:
    st.markdown("#### Engineering Efficiency")
    try:
        total_dupes = conn.execute("SELECT SUM(duplicates_skipped) FROM pipeline_runs").fetchone()[0] or 0
    except Exception:
        total_dupes = 0
    
    # Assume 10 cents per 1k records for Gemini Flash for complex extractions
    cost_per_record = 0.0001 
    saved = total_dupes * cost_per_record
    
    ec1, ec2 = st.columns(2)
    ec1.metric("Duplicate Extractions Avoided", f"{int(total_dupes):,}")
    ec2.metric("Estimated Cost Saved", f"${saved:.2f}", help="Assuming Gemini 1.5 Flash pricing at $0.0001 per extraction.")

st.markdown("---")
st.info(" Use the sidebar to navigate to **Overview (Data)**, **Entity Resolution**, **Freshness**, **LLM Telemetry**, and **Traceability**.")
st.caption("Atlas Intelligence Internal Operations Dashboard © 2026")
