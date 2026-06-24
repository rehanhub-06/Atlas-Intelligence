# GraphOne (Atlas Intelligence) Pipeline & Telemetry Dashboard

![Dashboard Overview](C:\Users\rehan\.gemini\antigravity\brain\af86af33-8ded-4dbb-8f9f-921739febdc3\media__1782323562546.png)

A robust, production-grade intelligence pipeline that aggregates, enriches, and resolves entities across AI startups, products, research papers, fresh jobs, and news signals. Powered by LiteLLM (Gemini Flash / Llama 3 / DeepSeek) and strict Pydantic contracts, it enforces semantic deduplication and entity resolution at the edge.

---

## 🛠️ Tech Stack

- **Orchestration & Routing**: Python (Asyncio), LiteLLM, Tenacity
- **Data Validation**: Pydantic
- **Web Scraping**: Playwright, BeautifulSoup4, Feedparser
- **Semantic Resolution**: Sentence-Transformers (`all-MiniLM-L6-v2`), RapidFuzz
- **Storage**: SQLite (Prototype) -> PostgreSQL/Neo4j (Production)
- **UI & Telemetry**: Streamlit, Pandas
- **Exporting**: Google Sheets API (`gspread`)

---

## 📸 Platform Showcase

### Vertical Data Browser (Multi-Source Operations)
Monitor real-time ingestion health across all targeted verticals.
![Vertical Data Browser](C:\Users\rehan\.gemini\antigravity\brain\af86af33-8ded-4dbb-8f9f-921739febdc3\media__1782323628012.png)

### Real-Time Signal Ingestion (News & Jobs)
Automatically tracks LLM extraction methods, confidence scores, and raw payloads.
![News Stream](C:\Users\rehan\.gemini\antigravity\brain\af86af33-8ded-4dbb-8f9f-921739febdc3\media__1782323751797.png)

### Semantic Entity Resolution Engine
Resolves messy company names into canonical startup targets using exact, fuzzy, and embedding matches.
![Entity Resolution Logs](C:\Users\rehan\.gemini\antigravity\brain\af86af33-8ded-4dbb-8f9f-921739febdc3\media__1782323786054.png)

### Dead-Letter Queue (DLQ) & Traceability
Safely isolates unresolvable entities without hallucinating, keeping the primary database clean.
![Unresolved Entity Logs](C:\Users\rehan\.gemini\antigravity\brain\af86af33-8ded-4dbb-8f9f-921739febdc3\media__1782323808651.png)

### Freshness SLA & Compliance
Continuously validates that jobs and news remain under a strict 24-hour freshness window.
![Freshness Check](C:\Users\rehan\.gemini\antigravity\brain\af86af33-8ded-4dbb-8f9f-921739febdc3\media__1782324266591.png)

### LLM Orchestration & Telemetry
Deep dive into the extraction engine's fallback executions, rate limit protections, and model utilization efficiency.
![LLM Telemetry](C:\Users\rehan\.gemini\antigravity\brain\af86af33-8ded-4dbb-8f9f-921739febdc3\media__1782324266620.png)

### Source-to-Output Traceability
Audit the complete lifecycle of any record from its raw HTML/JSON origin to the final extracted structured payload.
![Traceability](C:\Users\rehan\.gemini\antigravity\brain\af86af33-8ded-4dbb-8f9f-921739febdc3\media__1782324266624.png)

---

## 🚀 Setup & Installation

### 1. Environment Configuration
Install required Python dependencies:
```bash
pip install httpx aiohttp asyncio playwright beautifulsoup4 dateparser \
            arxiv litellm pydantic rapidfuzz sentence-transformers \
            gspread oauth2client streamlit pandas feedparser python-dotenv
```

Initialize Playwright browser binaries for headless scraping:
```bash
playwright install chromium
```

### 2. Environment Variables
Setup your `.env` configuration (copy `.env.example` if available):
```env
# LLM Providers (LiteLLM Routing)
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
DEEPSEEK_API_KEY=your_deepseek_key

# Optional Enrichments
GITHUB_TOKEN=your_github_token

# Exporters
GOOGLE_SHEETS_CREDS_PATH=./creds/service_account.json
SHEET_ID=your_sheet_id
```

---

## ⚙️ Ingestion Orchestration

Execute the pipeline using the primary orchestrator. Every run is **fully idempotent**; existing records are checked against a local `seen_content` cache to prevent redundant LLM billing and duplicates.

**Ingest all active vertical feeds:**
```bash
python src/main.py --vertical all --limit 1000
```

**Ingest specific vertical streams (startups, products, research_papers, jobs, news):**
```bash
python src/main.py --vertical research_papers --limit 100
python src/main.py --vertical news --limit 50
```

---

## 📊 Streaming Monitoring Dashboard

Review database tables, track entity resolution methodologies, monitor freshness compliance, and view LLM telemetry cost-savings in real-time.

```bash
streamlit run src/dashboard/app.py
```
*Access the dashboard locally via `http://localhost:8501`.*

---

## 📈 Scalability

The current implementation can scale substantially through vertical scaling and asynchronous processing. For large-scale distributed ingestion workloads (500k+ entities), PostgreSQL and distributed worker orchestration are recommended.

However, scaling horizontally (distributing processing across multiple Kubernetes pods) requires hot-swapping the SQLite driver for PostgreSQL (to prevent concurrent lock errors) and detaching the Google Sheets exporter (as massive row counts exceed the API payload limits).

---

## 🏗️ Architecture Overview

The pipeline leverages a multi-tier structure designed for resilience, automated enrichment, and strict traceability.

- **Data Sources:** Y Combinator (Startups), AI Tools List (Products), Hugging Face / ArXiv (Papers), RSS Feeds (News), and Multiple APIs (Jobs).
- **Ingestion & Fallback Engine:** Employs rule-based heuristics first. Upon missing or unstructured data, it triggers a deterministic **LLM Fallback Chain** via LiteLLM to guarantee Pydantic schema alignment.
- **Semantic Resolution:** Leverages `sentence-transformers` (`all-MiniLM-L6-v2`) and `rapidfuzz` to link external entity mentions (e.g., in a news article) to canonical startups within the core database.
- **Exporting Layer:** Syncs the polished SQLite (`pipeline.db`) structured data seamlessly to a designated Google Sheet, presenting professional, dynamically flattened datasets.

For a detailed breakdown of the theoretical distributed scaling, queue management, and vector database structures, please read the full [Architecture Documentation](architecture.md).
