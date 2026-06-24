import streamlit as st
import sqlite3
import pandas as pd
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from queries import failed_extractions_data
from styles import inject_custom_css

st.set_page_config(page_title="Data Traceability", layout="wide")
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

st.header(" Source-to-Output Traceability")
st.markdown("Audit the complete lifecycle of a record from its raw HTML/JSON origin to the final extracted payload.")

# Fetch recent records for preloaded examples
try:
    recent_urls = pd.read_sql("SELECT source_url FROM raw_captures ORDER BY captured_at DESC LIMIT 50", conn)["source_url"].tolist()
except Exception:
    recent_urls = []

selected_url = st.selectbox(
    "Select a recent record to Audit (or type a custom URL):",
    options=[""] + recent_urls if recent_urls else [""],
    index=0,
    help="Select an ingested URL to trace its pipeline execution."
)

lookup_manual = st.text_input("Or enter a specific Source URL manually:", placeholder="https://...")

lookup = lookup_manual if lookup_manual else selected_url

if lookup:
    st.markdown("---")
    
    # 1. Fetch Raw Capture
    raw_df = pd.read_sql("SELECT * FROM raw_captures WHERE source_url=?", conn, params=(lookup,))
    if raw_df.empty:
        st.error(" No raw capture found for this URL in the `raw_captures` ledger.")
    else:
        source_url = raw_df.iloc[0]['source_url']
        st.success(" Found in `raw_captures` ledger")
        
        # 2. Try to find the final payload in vertical tables
        tables = ["startups", "products", "research_papers", "jobs", "news"]
        final_payload = None
        found_table = None
        
        for table in tables:
            try:
                res = pd.read_sql(f"SELECT * FROM {table} WHERE source_url=?", conn, params=(source_url,))
                if not res.empty:
                    final_payload = res.iloc[0]['payload']
                    found_table = table
                    break
            except Exception:
                pass
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("1. Raw Scraped Content")
            st.caption("The exact HTML/JSON/XML payload retrieved before any LLM processing.")
            raw_content = raw_df.iloc[0]['raw_payload']
            try:
                # Pretty print if it's JSON (e.g. HN API)
                parsed_raw = json.loads(raw_content)
                st.json(parsed_raw)
            except Exception:
                st.text_area("Raw Text/HTML", value=raw_content, height=500, disabled=True)
                
        with col2:
            st.subheader("2. Final Structured Payload")
            if final_payload:
                st.caption(f"Successfully extracted and validated. Stored in `{found_table}` table.")
                try:
                    parsed_final = json.loads(final_payload)
                    st.json(parsed_final)
                except Exception:
                    st.text_area("Final Output", value=final_payload, height=500, disabled=True)
            else:
                st.warning("️ Raw capture exists, but could not find a final structured payload. It may have failed Pydantic validation or LLM extraction.")

st.markdown("---")
st.header(" Dead Letter Queue (Failed Extractions)")
st.markdown("Records that failed extraction are quarantined here to protect downstream dataset integrity.")

dlq_df = failed_extractions_data(conn)
if not dlq_df.empty:
    st.dataframe(dlq_df, use_container_width=True, hide_index=True)
else:
    st.success("No failed extractions in the Dead Letter Queue. All records successfully parsed!")
