import gspread
import pandas as pd
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger("Sheets-Exporter")

TABLES = ["startups", "products", "research_papers", "jobs", "news", "pipeline_runs"]
TAB_NAMES = {
    "startups": "Startups", 
    "products": "Products", 
    "research_papers": "Research Papers",
    "jobs": "Jobs", 
    "news": "News",
    "pipeline_runs": "Pipeline Runs"
}

def check_sheets_auth(sheet_id, creds_path) -> bool:
    if not sheet_id or not creds_path:
        logger.warning("SHEET_ID or GOOGLE_SHEETS_CREDS_PATH not defined. Sheets export will be skipped.")
        return False
    if not os.path.exists(creds_path):
        logger.warning(f"Google sheets credentials file not found at '{creds_path}'. Sheets export will be skipped.")
        return False
    try:
        gc = gspread.service_account(filename=creds_path)
        gc.open_by_key(sheet_id)
        return True
    except Exception as e:
        logger.error(f"Google Sheets Authentication check failed: {str(e)}")
        return False

def flatten_and_format_df(table_name, df):
    """
    Flattens the JSON payload, drops internal columns, and reorders them professionally.
    """
    if df.empty:
        return df, {}

    flattened = []
    source_counts = {}

    for _, row in df.iterrows():
        # Pipeline runs don't have a payload to flatten
        if table_name == "pipeline_runs":
            return df[
                ['run_id', 'records_processed', 'fallback_count', 'duplicates_skipped', 'started_at', 'ended_at']
            ].rename(columns={
                'run_id': 'Run ID',
                'records_processed': 'Records',
                'fallback_count': 'Fallbacks',
                'duplicates_skipped': 'Duplicates',
                'started_at': 'Started At',
                'ended_at': 'Completed At'
            }), {}

        flat_row = {"Collected At": row.get("collectedAt", "")}
        payload = {}
        if "payload" in row and pd.notna(row["payload"]):
            try:
                payload = json.loads(row["payload"])
            except Exception:
                pass
        
        # Track Source Coverage
        source_name = "Unknown"
        if "source" in payload and isinstance(payload["source"], dict):
            source_name = payload["source"].get("name", "Unknown")
        elif "source_name" in payload:
            source_name = payload["source_name"]
        
        source_counts[source_name] = source_counts.get(source_name, 0) + 1

        flat_row["Source"] = source_name
        flat_row["Confidence"] = payload.get("confidence", "")
        flat_row["Method"] = payload.get("extraction_method", "UNKNOWN")

        # Map business fields based on table
        content = payload.get("content", {})
        if table_name == "startups":
            flat_row["Company"] = content.get("entityName", content.get("startupName", ""))
            flat_row["Employees"] = content.get("employeeCount", "")
            flat_row["Funding"] = content.get("fundingStage", "")
        elif table_name == "products":
            flat_row["Product"] = content.get("productName", "")
            flat_row["Company"] = content.get("startupName", "")
            flat_row["Pricing"] = content.get("pricingModel", "")
        elif table_name == "research_papers":
            flat_row["Title"] = content.get("title", "")
            flat_row["Authors"] = content.get("authors", "")
            flat_row["Domain"] = content.get("research_domain", "")
        elif table_name == "jobs":
            flat_row["Role"] = content.get("jobTitle", "")
            flat_row["Company"] = content.get("company", "")
            flat_row["Location"] = content.get("location", "")
        elif table_name == "news":
            flat_row["Headline"] = content.get("headline", "")
            flat_row["Sentiment"] = content.get("sentiment", "")
            flat_row["Entities"] = ", ".join(content.get("entities_mentioned", []))

        # Add all other content keys that weren't explicitly mapped
        for k, v in content.items():
            if isinstance(v, (dict, list)):
                v = str(v)
            # Find a dynamic name if it's not already in flat_row
            name = k.replace("_", " ").title()
            # Only add if we didn't map it to a primary business field
            if not any(x.lower() == name.lower() for x in flat_row.keys()) and k not in ['entityName', 'startupName', 'productName', 'jobTitle', 'company', 'location', 'headline', 'sentiment', 'entities_mentioned']:
                flat_row[name] = v
        
        flat_row["URL"] = payload.get("url", payload.get("paper_url", payload.get("source_url", row.get("source_url", ""))))

        flattened.append(flat_row)

    flat_df = pd.DataFrame(flattened)
    
    # Reorder columns to put business fields first
    primary_cols = ["Company", "Product", "Title", "Headline", "Role", "Source", "Confidence", "Method", "Collected At"]
    ordered_cols = [c for c in primary_cols if c in flat_df.columns]
    ordered_cols += [c for c in flat_df.columns if c not in ordered_cols]

    return flat_df[ordered_cols], source_counts

def apply_worksheet_formatting(sh, ws, df_str):
    # Format header row
    try:
        ws.format("A1:Z1", {
            "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
            "textFormat": {"bold": True, "fontSize": 10}
        })
        ws.freeze(rows=1)
        ws.set_basic_filter()
    except Exception as e:
        logger.warning(f"Failed to apply basic formatting to {ws.title}: {e}")

    # Conditional Formatting for Confidence
    if "Confidence" in df_str.columns:
        col_idx = df_str.columns.get_loc("Confidence")
        
        requests = [
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1}],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "0.9"}]},
                            "format": {"backgroundColor": {"red": 0.85, "green": 0.96, "blue": 0.85}} # Green
                        }
                    },
                    "index": 0
                }
            },
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1}],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_BETWEEN", "values": [{"userEnteredValue": "0.75"}, {"userEnteredValue": "0.899"}]},
                            "format": {"backgroundColor": {"red": 1.0, "green": 0.96, "blue": 0.85}} # Yellow
                        }
                    },
                    "index": 1
                }
            },
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1}],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0.75"}]},
                            "format": {"backgroundColor": {"red": 0.98, "green": 0.85, "blue": 0.85}} # Red
                        }
                    },
                    "index": 2
                }
            }
        ]
        try:
            # Just try to execute the add requests
            sh.batch_update({"requests": requests})
        except Exception as e:
            logger.warning(f"Failed to apply conditional formatting to {ws.title}: {e}")


def export_to_sheets(db, sheet_id, creds_path):
    os.makedirs("data/exports", exist_ok=True)
    logger.info("Exporting SQLite tables to local CSV directory 'data/exports/'...")
    for table in TABLES:
        try:
            df = pd.read_sql(f"SELECT * FROM {table}", db.conn)
            df.to_csv(f"data/exports/{table}.csv", index=False, encoding="utf-8")
        except Exception:
            pass
            
    try:
        mapping_df = pd.read_sql("SELECT * FROM entity_mapping_log", db.conn)
        mapping_df.to_csv("data/exports/entity_mapping_log.csv", index=False, encoding="utf-8")
    except Exception:
        pass

    if not check_sheets_auth(sheet_id, creds_path):
        return

    logger.info(f"Uploading data to Google Sheet ID: {sheet_id}...")
    try:
        gc = gspread.service_account(filename=creds_path)
        sh = gc.open_by_key(sheet_id)

        # Build Source Coverage Data
        global_sources = {}
        total_records = 0
        
        # Ensure README is at the front
        try:
            readme_ws = sh.worksheet("README")
        except gspread.WorksheetNotFound:
            readme_ws = sh.add_worksheet(title="README", rows="20", cols="5")
        
        # Ensure Source Coverage is second
        try:
            source_ws = sh.worksheet("Source Coverage")
        except gspread.WorksheetNotFound:
            source_ws = sh.add_worksheet(title="Source Coverage", rows="100", cols="2")

        # Process standard tables
        for table in TABLES:
            df = pd.read_sql(f"SELECT * FROM {table}", db.conn)
            if table != "pipeline_runs":
                total_records += len(df)
            
            # Flatten and reorder
            if table != "pipeline_runs":
                flat_df, source_counts = flatten_and_format_df(table, df)
                for src, cnt in source_counts.items():
                    global_sources[src] = global_sources.get(src, 0) + cnt
            else:
                flat_df, _ = flatten_and_format_df(table, df)

            df_str = flat_df.fillna("").astype(str)
            df_str = df_str.map(lambda x: x[:49000] + '... [TRUNCATED]' if isinstance(x, str) and len(x) > 49000 else x)
            
            try:
                ws = sh.worksheet(TAB_NAMES[table])
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(title=TAB_NAMES[table], rows="100", cols="20")
                
            ws.clear()
            if not df_str.empty:
                ws.update([df_str.columns.tolist()] + df_str.values.tolist())
            apply_worksheet_formatting(sh, ws, df_str)
            logger.info(f"Uploaded {table} data to sheet tab: {TAB_NAMES[table]}")

        # Process Entity Resolution
        try:
            ws = sh.worksheet("Entity Resolution")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title="Entity Resolution", rows="100", cols="20")
            
        ws.clear()
        mapping_df_str = mapping_df.fillna("").astype(str)
        mapping_df_str = mapping_df_str.map(lambda x: x[:49000] + '... [TRUNCATED]' if isinstance(x, str) and len(x) > 49000 else x)
        if not mapping_df_str.empty:
            ws.update([mapping_df_str.columns.tolist()] + mapping_df_str.values.tolist())
        apply_worksheet_formatting(sh, ws, mapping_df_str)
        logger.info("Uploaded Entity Resolution to Google Sheets.")

        # Update Source Coverage Tab
        source_ws.clear()
        source_data = [["Source", "Records"]] + [[k, v] for k, v in sorted(global_sources.items(), key=lambda item: item[1], reverse=True)]
        source_ws.update(source_data)
        apply_worksheet_formatting(sh, source_ws, pd.DataFrame(columns=["Source", "Records"]))

        # Update README Tab
        readme_ws.clear()
        readme_data = [
            ["Atlas Intelligence Data Export", ""],
            ["", ""],
            ["Total Records Tracked", str(total_records)],
            ["Unique Sources", str(len(global_sources))],
            ["Last Updated", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")],
            ["", ""],
            ["Key Features", ""],
            ["• Multi-source ingestion", ""],
            ["• Freshness validation", ""],
            ["• Entity resolution", ""],
            ["• LLM enrichment", ""],
            ["• Traceability", ""],
            ["• DLQ architecture", ""]
        ]
        readme_ws.update(readme_data)
        try:
            readme_ws.format("A1", {"textFormat": {"bold": True, "fontSize": 14}})
            readme_ws.format("A3:A5", {"textFormat": {"bold": True}})
            readme_ws.format("A7", {"textFormat": {"bold": True, "fontSize": 12}})
        except Exception:
            pass

        # Ensure README is the first tab via batch update
        try:
            requests = [
                {"updateSheetProperties": {"properties": {"sheetId": readme_ws.id, "index": 0}, "fields": "index"}},
                {"updateSheetProperties": {"properties": {"sheetId": source_ws.id, "index": 1}, "fields": "index"}}
            ]
            sh.batch_update({"requests": requests})
        except Exception as e:
            logger.warning(f"Could not reorder sheets: {e}")

        logger.info("Google Sheets completely updated!")
        
    except Exception as e:
        logger.error(f"Google Sheets upload failed: {str(e)}")
