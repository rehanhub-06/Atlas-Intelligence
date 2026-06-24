import sqlite3
import json
import os
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_content (
    source_url TEXT UNIQUE,
    content_hash TEXT,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP
);
CREATE TABLE IF NOT EXISTS entity_mapping_log (
    raw_name TEXT, 
    canonical_name TEXT, 
    method TEXT,
    confidence REAL, 
    resolved_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS github_star_cache (
    repo_full_name TEXT UNIQUE, 
    stars INTEGER, 
    fetched_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS llm_events (
    tier TEXT, 
    event_type TEXT, 
    schema_name TEXT, 
    ts TIMESTAMP
);
CREATE TABLE IF NOT EXISTS raw_captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT, 
    fetched_at TIMESTAMP, 
    raw_payload TEXT, 
    extraction_method TEXT
);
CREATE TABLE IF NOT EXISTS startups (
    source_url TEXT UNIQUE, 
    payload TEXT, 
    collectedAt TIMESTAMP
);
CREATE TABLE IF NOT EXISTS products (
    source_url TEXT UNIQUE, 
    payload TEXT, 
    collectedAt TIMESTAMP
);
CREATE TABLE IF NOT EXISTS research_papers (
    source_url TEXT UNIQUE, 
    payload TEXT, 
    collectedAt TIMESTAMP
);
CREATE TABLE IF NOT EXISTS jobs (
    source_url TEXT UNIQUE, 
    payload TEXT, 
    collectedAt TIMESTAMP
);
CREATE TABLE IF NOT EXISTS news (
    source_url TEXT UNIQUE, 
    payload TEXT, 
    collectedAt TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    records_processed INTEGER,
    duplicates_skipped INTEGER,
    fallback_count INTEGER,
    stale_dropped INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS failed_extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT,
    record_type TEXT,
    failure_stage TEXT,
    raw_html TEXT,
    error_message TEXT,
    attempted_provider TEXT,
    timestamp TIMESTAMP
);
"""

class DB:
    def __init__(self, path="data/pipeline.db"):
        # Make sure data/ folder exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def is_seen(self, url, content_hash):
        row = self.conn.execute(
            "SELECT content_hash FROM seen_content WHERE source_url=?", (url,)
        ).fetchone()
        return row is not None and row[0] == content_hash

    def mark_seen(self, url, content_hash):
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT INTO seen_content (source_url, content_hash, first_seen, last_seen)
            VALUES (?,?,?,?)
            ON CONFLICT(source_url) DO UPDATE SET content_hash=?, last_seen=?
        """, (url, content_hash, now, now, content_hash, now))
        self.conn.commit()

    def upsert_record(self, table, source_url, payload: dict, collected_at):
        self.conn.execute(f"""
            INSERT INTO {table} (source_url, payload, collectedAt) VALUES (?,?,?)
            ON CONFLICT(source_url) DO UPDATE SET payload=?, collectedAt=?
        """, (source_url, json.dumps(payload, default=str), collected_at,
              json.dumps(payload, default=str), collected_at))
        self.conn.commit()

    def log_entity_mapping(self, raw_name, canonical_name, method, confidence):
        self.conn.execute("""
            INSERT INTO entity_mapping_log (raw_name, canonical_name, method, confidence, resolved_at)
            VALUES (?,?,?,?,?)
        """, (raw_name, canonical_name, method, confidence, datetime.utcnow().isoformat()))
        self.conn.commit()

    def log_llm_event(self, tier, event_type, schema_name):
        self.conn.execute(
            "INSERT INTO llm_events (tier, event_type, schema_name, ts) VALUES (?,?,?,?)",
            (tier, event_type, schema_name, datetime.utcnow().isoformat())
        )
        self.conn.commit()

    def save_raw_capture(self, source_url, raw_payload, method):
        self.conn.execute("""
            INSERT INTO raw_captures (source_url, fetched_at, raw_payload, extraction_method)
            VALUES (?,?,?,?)
        """, (source_url, datetime.utcnow().isoformat(), raw_payload, method))
        self.conn.commit()

    def start_run(self, run_id):
        self.conn.execute("""
            INSERT INTO pipeline_runs (run_id, started_at)
            VALUES (?, ?)
        """, (run_id, datetime.utcnow().isoformat()))
        self.conn.commit()
        
    def log_failed_extraction(self, source_url, record_type, failure_stage, raw_html, error_message, attempted_provider):
        self.conn.execute("""
            INSERT INTO failed_extractions (source_url, record_type, failure_stage, raw_html, error_message, attempted_provider, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (source_url, record_type, failure_stage, raw_html, error_message, attempted_provider, datetime.utcnow().isoformat()))
        self.conn.commit()
        
    def end_run(self, run_id, records, duplicates, fallbacks, stale_dropped=0):
        self.conn.execute("""
            UPDATE pipeline_runs 
            SET ended_at = ?, records_processed = ?, duplicates_skipped = ?, fallback_count = ?, stale_dropped = ?
            WHERE run_id = ?
        """, (datetime.utcnow().isoformat(), records, duplicates, fallbacks, stale_dropped, run_id))
        self.conn.commit()

    def get_github_cache(self, repo, max_age_hours=24):
        row = self.conn.execute(
            "SELECT stars, fetched_at FROM github_star_cache WHERE repo_full_name=?", (repo,)
        ).fetchone()
        if row:
            try:
                fetched_at = datetime.fromisoformat(row[1])
                if (datetime.utcnow() - fetched_at).total_seconds() < max_age_hours * 3600:
                    return row[0]
            except Exception:
                pass
        return None

    def set_github_cache(self, repo, stars):
        now = datetime.utcnow().isoformat()
        self.conn.execute("""
            INSERT INTO github_star_cache (repo_full_name, stars, fetched_at) VALUES (?,?,?)
            ON CONFLICT(repo_full_name) DO UPDATE SET stars=?, fetched_at=?
        """, (repo, stars, now, stars, now))
        self.conn.commit()
