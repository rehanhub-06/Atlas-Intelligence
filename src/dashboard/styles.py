import streamlit as st

def inject_custom_css():
    st.markdown("""
        <style>
        /* Import Inter Font */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        /* Apply font globally */
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }
        
        /* Subtle styling for metric cards */
        div[data-testid="stMetric"] {
            background-color: #1A1C23;
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        
        /* Ensure headers look clean */
        h1, h2, h3 {
            font-weight: 600 !important;
            letter-spacing: -0.02em !important;
        }
        </style>
    """, unsafe_allow_html=True)
