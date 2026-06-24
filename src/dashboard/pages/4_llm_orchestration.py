import streamlit as st
import sqlite3
import plotly.express as px
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from queries import llm_tier_usage, llm_event_breakdown
from styles import inject_custom_css

st.set_page_config(page_title="LLM Telemetry", layout="wide")
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

st.header(" LLM Orchestration & Telemetry")
st.markdown("Deep dive into the extraction engine's fallback executions, rate limits, and model utilization.")

st.markdown("---")
st.subheader(" Ingestion Event Telemetry")
st.markdown("Audits of validation retries, fallback activations, context window overflows, and rate-limit hits.")

events = llm_event_breakdown(conn)
if not events.empty:
    # Ensure SUCCESS, VALIDATION_RETRY, FALLBACK are shown prominently
    main_events = events[events['event_type'].isin(['SUCCESS', 'VALIDATION_RETRY', 'FALLBACK'])]
    other_events = events[~events['event_type'].isin(['SUCCESS', 'VALIDATION_RETRY', 'FALLBACK'])]
    
    cols = st.columns(3)
    for i, (_, row) in enumerate(main_events.iterrows()):
        evt = str(row['event_type']).replace("_", " ").title()
        if 'Success' in evt:
            evt = "LLM Success"
        cols[i].metric(label=evt, value=f"{int(row['n']):,}")
        
    if not other_events.empty:
        st.markdown("#### Other Errors")
        err_cols = st.columns(len(other_events) if len(other_events) <= 5 else 5)
        for i, (_, row) in enumerate(other_events.iterrows()):
            evt = str(row['event_type']).replace("_", " ").title()
            err_cols[i % len(err_cols)].metric(label=evt, value=f"{int(row['n']):,}")

st.markdown("---")
usage = llm_tier_usage(conn)
if not usage.empty:
    st.subheader("Provider Utilization")
    fig1 = px.bar(
        usage,
        x='n',
        y='tier',
        color='tier',
        orientation='h',
        text='n',
        color_discrete_map={'Gemini': '#6366F1', 'Groq': '#22C55E'}
    )
    fig1.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)', 
        font_color='#FAFAFA', 
        showlegend=False,
        xaxis_title="Successful Extractions",
        yaxis_title=""
    )
    st.plotly_chart(fig1, use_container_width=True)
else:
    st.info("No successful LLM calls logged yet.")
