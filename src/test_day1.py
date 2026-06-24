import asyncio
import logging
from datetime import datetime
from src.storage.db import DB
from src.scrapers.arxiv import fetch_arxiv_papers
from src.models.schemas import ResearchPaper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Day1-Checkpoint")

async def test_arxiv_spine():
    logger.info("Starting Day 1 Checkpoint Test...")
    db = DB()
    
    # 1. Fetch papers from arXiv
    logger.info("Fetching papers from arXiv API...")
    raw_papers = list(fetch_arxiv_papers(max_results=10))
    logger.info(f"Retrieved {len(raw_papers)} papers from arXiv.")
    
    if len(raw_papers) == 0:
        logger.error("ArXiv returned 0 papers! Testing failed.")
        return
        
    # 2. Map and validate using Pydantic ResearchPaper schema
    validated_count = 0
    for idx, paper in enumerate(raw_papers):
        try:
            # Map values
            pub_date = paper["published_date"]
            if hasattr(pub_date, "isoformat"):
                pub_date_str = pub_date.isoformat()
            else:
                pub_date_str = str(pub_date)
                
            paper_payload = {
                "schemaVersion": "1.0",
                "recordType": "RESEARCH_PAPER",
                "content": {
                    "title": paper["title"],
                    "authors": paper["authors"],
                    "paper_url": paper["paper_url"],
                    "github_url": None,
                    "github_stars": None,
                    "published_date": pub_date_str
                }
            }
            
            # Validate schema
            record = ResearchPaper.model_validate(paper_payload)
            
            # 3. Write to SQLite DB research_papers table
            url = record.content.paper_url
            db.upsert_record("research_papers", url, record.model_dump(), datetime.utcnow().isoformat())
            validated_count += 1
            
            if idx == 0:
                logger.info(f"Sample validated record: {record.model_dump()}")
                
        except Exception as e:
            logger.error(f"Failed to validate/store paper {idx}: {str(e)}")
            
    logger.info(f"Day 1 Checkpoint Complete. Successfully validated and stored {validated_count}/{len(raw_papers)} papers in SQLite.")
    
    # Verify DB contents
    conn = db.conn
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM research_papers")
    row_count = cursor.fetchone()[0]
    logger.info(f"Confirmed row count in 'research_papers' SQLite table: {row_count}")
    
    assert row_count > 0, "No records written to SQLite table!"

if __name__ == "__main__":
    asyncio.run(test_arxiv_spine())
