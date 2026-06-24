import pandas as pd

import logging
logger = logging.getLogger(__name__)

def vertical_counts(conn):
    try:
        df = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)
        all_tables = df['name'].tolist()
        
        # Discover actual data verticals by inspecting schema for required columns
        data_tables = []
        for t in all_tables:
            cols = pd.read_sql(f"PRAGMA table_info({t})", conn)['name'].tolist()
            if 'payload' in cols and 'collectedAt' in cols:
                data_tables.append(t)
                
        data_tables = sorted(data_tables)
        
        if not data_tables:
            return pd.DataFrame()
            
        queries = []
        for t in data_tables:
            queries.append(f"SELECT '{t.upper()}' rt, COUNT(*) n FROM {t}")
            
        query = "\nUNION ALL ".join(queries)
        return pd.read_sql(query, conn)
    except Exception as e:
        logger.warning(f"Failed to calculate vertical counts: {e}")
        return pd.DataFrame()

def resolution_breakdown(conn):
    try:
        return pd.read_sql("SELECT method, COUNT(*) n FROM entity_mapping_log GROUP BY method", conn)
    except Exception:
        return pd.DataFrame(columns=["method", "n"])

def unresolved_entities(conn):
    try:
        return pd.read_sql("""
            SELECT raw_name, COUNT(*) freq FROM entity_mapping_log
            WHERE method='UNRESOLVED' GROUP BY raw_name ORDER BY freq DESC LIMIT 50
        """, conn)
    except Exception:
        return pd.DataFrame(columns=["raw_name", "freq"])

def llm_tier_usage(conn):
    try:
        df = pd.read_sql(
            "SELECT tier, COUNT(*) n FROM llm_events WHERE event_type='SUCCESS' GROUP BY tier", conn
        )
        # Ensure all providers exist in the dataframe
        providers = ["Gemini", "Groq"]
        existing = df['tier'].tolist() if not df.empty else []
        missing = [{"tier": p, "n": 0} for p in providers if p not in existing]
        if missing:
            df = pd.concat([df, pd.DataFrame(missing)], ignore_index=True) if not df.empty else pd.DataFrame(missing)
        return df
    except Exception:
        return pd.DataFrame([{"tier": "Gemini", "n": 0}, {"tier": "Groq", "n": 0}])

def llm_event_breakdown(conn):
    try:
        df = pd.read_sql("SELECT event_type, COUNT(*) n FROM llm_events GROUP BY event_type", conn)
        # Ensure base event types exist
        events = ["SUCCESS", "VALIDATION_RETRY", "FALLBACK"]
        existing = df['event_type'].tolist() if not df.empty else []
        missing = [{"event_type": e, "n": 0} for e in events if e not in existing]
        if missing:
            df = pd.concat([df, pd.DataFrame(missing)], ignore_index=True) if not df.empty else pd.DataFrame(missing)
        return df
    except Exception:
        return pd.DataFrame([{"event_type": "SUCCESS", "n": 0}, {"event_type": "VALIDATION_RETRY", "n": 0}, {"event_type": "FALLBACK", "n": 0}])

def failed_extractions_count(conn):
    try:
        res = pd.read_sql("SELECT COUNT(*) as cnt FROM failed_extractions", conn)
        return int(res["cnt"].iloc[0])
    except Exception:
        return 0

def failed_extractions_data(conn):
    try:
        return pd.read_sql("SELECT source_url, record_type, failure_stage, attempted_provider, error_message, timestamp FROM failed_extractions ORDER BY timestamp DESC LIMIT 100", conn)
    except Exception:
        return pd.DataFrame(columns=["source_url", "record_type", "failure_stage", "attempted_provider", "error_message", "timestamp"])
