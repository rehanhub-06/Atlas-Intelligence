import streamlit as st
import sqlite3
import pandas as pd
import sys
import os
import logging

logger = logging.getLogger(__name__)

# Set path to parent folder for queries imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from styles import inject_custom_css

st.set_page_config(page_title="Data Overview", layout="wide")
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

st.header(" Vertical Data Browser")
st.markdown("Browse raw structured data ingested into SQLite database across all verticals.")

st.markdown("###  Source Coverage")

def get_data_tables(c):
    try:
        df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", c)
        all_tables = df['name'].tolist()
        
        # Discover actual data verticals by inspecting schema for required columns
        data_tables = []
        for t in all_tables:
            cols = pd.read_sql(f"PRAGMA table_info({t})", c)['name'].tolist()
            if 'payload' in cols and 'collectedAt' in cols:
                data_tables.append(t)
                
        return sorted(data_tables)
    except Exception as e:
        logger.warning(f"Failed to fetch tables: {e}")
        return []

def get_source_coverage(c, tables):
    sources = {}
    
    for table in tables:
        try:
            query = f"""
            SELECT 
                COALESCE(
                    json_extract(payload, '$.source.name'),
                    json_extract(payload, '$.source'),
                    json_extract(payload, '$.source_name')
                ) as source_name, 
                COUNT(*) as cnt 
            FROM {table} 
            GROUP BY source_name
            """
            df = pd.read_sql(query, c)
            for _, row in df.iterrows():
                if pd.notna(row['source_name']):
                    name = row['source_name']
                    if name in sources:
                        sources[name] += row['cnt']
                    else:
                        sources[name] = row['cnt']
        except Exception as e:
            logger.warning(f"Failed source coverage query for {table}: {e}")
            
    return sources

data_tables = get_data_tables(conn)
sources = get_source_coverage(conn, data_tables)
if sources:
    cols = st.columns(len(sources))
    for col, (name, count) in zip(cols, sources.items()):
        col.metric(label=name, value=f"{int(count):,}")
else:
    st.info("Run the pipeline to populate source coverage.")
    
st.markdown("---")

if not data_tables:
    st.info("No data tables found. Run the pipeline to populate data.")
else:
    tabs = st.tabs([t.replace("_", " ").title() for t in data_tables])
    
    for i, table in enumerate(data_tables):
        with tabs[i]:
            st.subheader(f"Latest {table.replace('_', ' ').title()}")
            try:
                df = pd.read_sql(f"SELECT * FROM {table} ORDER BY collectedAt DESC LIMIT 500", conn)
                if not df.empty:
                    import json
                    # Flatten the JSON payload
                    flattened = []
                    for _, row in df.iterrows():
                        flat_row = {"source_url": row["source_url"], "collectedAt": row["collectedAt"]}
                        if "payload" in row and pd.notna(row["payload"]):
                            try:
                                payload = json.loads(row["payload"])
                                # Add top level keys
                                for k, v in payload.items():
                                    if not isinstance(v, (dict, list)):
                                        flat_row[k] = v
                            except Exception:
                                pass
                        # Include the raw payload for the expander if needed
                        flat_row["_raw"] = row["payload"]
                        flattened.append(flat_row)
                    
                    flat_df = pd.DataFrame(flattened)
                    
                    # Display flattened dataframe without raw payload
                    display_cols = [c for c in flat_df.columns if c != "_raw"]
                    st.write(f"Showing last {len(df)} records:")
                    st.dataframe(flat_df[display_cols], use_container_width=True)
                    
                    with st.expander("Inspect Raw JSON Payloads"):
                        for _, row in flat_df.head(5).iterrows():
                            st.markdown(f"**URL:** {row['source_url']}")
                            st.json(row['_raw'])
                else:
                    st.info(f"No records found in '{table}'.")
            except Exception as e:
                st.warning(f"Could not load data for '{table}': {str(e)}")

