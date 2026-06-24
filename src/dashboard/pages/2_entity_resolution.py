import streamlit as st
import sqlite3
import plotly.express as px
import sys
import os

# Set path to parent folder for queries imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from queries import resolution_breakdown, unresolved_entities
from styles import inject_custom_css

st.set_page_config(page_title="Entity Resolution", layout="wide")
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

st.header(" Entity Resolution Logs")
st.markdown("Audits of exact, fuzzy, and embedding matches against our seed startup database.")

st.info(" **Note on Coverage**: The YC startup corpus intentionally contains hundreds of entities outside our 50-company AI seed list. A high 'Unresolved' count is expected and proves the resolution engine avoids hallucinating matches for unknown companies.")

breakdown = resolution_breakdown(conn)
if not breakdown.empty:
    st.subheader("Resolution Methodology Distribution")
    
    # Calculate coverage metrics
    total_entities = breakdown['n'].sum()
    unresolved_count = breakdown[breakdown['method'] == 'UNRESOLVED']['n'].sum() if 'UNRESOLVED' in breakdown['method'].values else 0
    resolved_count = total_entities - unresolved_count
    coverage_rate = (resolved_count / total_entities * 100) if total_entities > 0 else 0
    
    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("Total Extracted Entities", f"{total_entities:,}")
    rc2.metric("Successfully Resolved", f"{resolved_count:,}")
    rc3.metric("Coverage Rate", f"{coverage_rate:.1f}%")
    
    fig = px.pie(
        breakdown, 
        values='n', 
        names='method', 
        hole=0.4,
        color_discrete_sequence=['#6366F1', '#22C55E', '#F59E0B', '#EF4444']
    )
    fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='#FAFAFA')
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No resolution mappings logged yet.")

st.markdown("---")
st.subheader(" Unresolved Entity Log")
st.markdown("Messy names that could not be resolved to any canonical seed startup (candidates to add to the mock db).")

unresolved = unresolved_entities(conn)
if not unresolved.empty:
    st.dataframe(unresolved, use_container_width=True)
else:
    st.success("All raw entities resolved successfully to our canonical startup list!")
