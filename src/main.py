import asyncio
import argparse
import os
import httpx
import logging
from datetime import datetime, timezone, timedelta
import json

from dotenv import load_dotenv

# Load env variables from .env if present
load_dotenv()

from src.storage.db import DB
from src.entity.resolver import EntityResolver
from src.models.schemas import Startup, Product, ResearchPaper, Job, News
from src.utils.hashing import hash_content
from src.llm.orchestrator import extract_with_fallback
from src.scrapers.github_stars import get_stars_cached
from src.scrapers.startups import fetch_yc_startups, fetch_ai_products_list
from src.scrapers.news import fetch_rss_news
from src.scrapers.jobs import extract_job_rule_based, SOURCE_CONFIGS
from src.exporters.sheets import export_to_sheets, check_sheets_auth

logger = logging.getLogger("GraphOne-Pipeline-Runner")

async def process_record(url, raw_html, db, resolver, schema, extractor_fn):
    content_hash = hash_content(raw_html)
    if db.is_seen(url, content_hash):
        logger.info(f"Skipping already seen record: {url}")
        return None, "DUPLICATE"

    # Run extractor function (returns parsed dict and extraction_method string)
    from src.llm.orchestrator import ExtractionFailedError

    try:
        parsed, method_used = await extractor_fn(raw_html, db)
        if not parsed:
            db.log_failed_extraction(url, schema.__name__, method_used, raw_html, "Extractor returned None or parsing failed", "none")
            return None, "EXTRACTION_FAILED"
    except ExtractionFailedError as e:
        logger.warning(f"Extraction failed for {url}: {e}")
        db.log_failed_extraction(url, schema.__name__, "LLM", raw_html, str(e), getattr(e, "attempted_provider", "none"))
        return None, "EXTRACTION_FAILED"
    except Exception as e:
        logger.warning(f"Unexpected extraction error for {url}: {e}")
        db.log_failed_extraction(url, schema.__name__, "UNKNOWN", raw_html, str(e), "none")
        return None, "EXTRACTION_FAILED"
        
    db.save_raw_capture(url, raw_html, method_used)

    # Resolve startup/company name
    content_dict = parsed.get("content", parsed)
    name_field = content_dict.get("entityName") or content_dict.get("company") or content_dict.get("startupName")
    if name_field:
        canonical, method, confidence = resolver.resolve(name_field)
        db.log_entity_mapping(name_field, canonical, method, confidence)
        
        # Update name field in content with canonical name
        if "entityName" in content_dict:
            parsed["content"]["entityName"] = canonical or name_field
        elif "company" in content_dict:
            parsed["content"]["company"] = canonical or name_field
        elif "startupName" in content_dict:
            parsed["content"]["startupName"] = canonical or name_field

    # Map to schema validation
    try:
        # Wrap parsed dict in schema format if not already wrapped
        if "content" not in parsed:
            # Determine vertical specific wrapper
            if schema == ResearchPaper:
                parsed_wrapped = {
                    "schemaVersion": "1.0",
                    "recordType": "RESEARCH_PAPER",
                    "content": parsed
                }
            elif schema == Job:
                parsed_wrapped = {
                    "schemaVersion": "1.0",
                    "recordType": "JOB",
                    "content": parsed
                }
            else:
                parsed_wrapped = parsed
        else:
            parsed_wrapped = parsed
            
        # Ensure source is injected if missing
        if "source" not in parsed_wrapped:
            source_name = "Unknown"
            if schema == ResearchPaper:
                source_name = "ArXiv" if "arxiv.org" in url else ("Hugging Face" if "huggingface" in url else "Research API")
            elif schema == Job:
                source_name = "Remotive" if "remotive" in url else ("RemoteOK" if "remoteok" in url else ("Hacker News" if "ycombinator" in url else "Arbeitnow"))
            
            parsed_wrapped["source"] = {"name": source_name, "url": url}
            
        # Ensure method and confidence are correctly assigned before Pydantic validation
        if "extraction_method" not in parsed_wrapped:
            parsed_wrapped["extraction_method"] = method_used
        if "confidence" not in parsed_wrapped:
            parsed_wrapped["confidence"] = 1.0 if method_used == "RULE" else 0.85
            
        record = schema.model_validate(parsed_wrapped)
        
        # Throttling to respect free tier LLM rate limits
        if method_used == "LLM":
            await asyncio.sleep(5.0)
            
        db.mark_seen(url, content_hash)
        return record, "SUCCESS"
    except Exception as e:
        logger.error(f"Pydantic Validation failed for {schema.__name__}: {str(e)}. Parsed data: {parsed}")
        db.log_failed_extraction(url, schema.__name__, method_used, raw_html, f"Validation Failed: {str(e)}", "none")
        return None, "VALIDATION_FAILED"

# Extractor functions per vertical
async def extract_startup_extractor(raw_json_str, db):
    # Rule-first json mapping
    try:
        c = json.loads(raw_json_str)
        name = c.get("name", "")
        slug = c.get("slug", "")
        yc_url = f"https://www.ycombinator.com/companies/{slug}" if slug else "https://www.ycombinator.com/companies"
        
        team_size = c.get("team_size") or c.get("employee_count") or c.get("size")
        try:
            emp_count = int(team_size) if team_size else None
        except ValueError:
            emp_count = None
            
        parsed = {
            "schemaVersion": "1.0",
            "recordType": "STARTUP",
            "source": {"name": "Y Combinator", "url": yc_url},
            "content": {
                "entityName": name,
                "employeeCount": emp_count
            },
            "collectedAt": datetime.utcnow().isoformat() + "Z"
        }
        return parsed, "RULE"
    except Exception as e:
        logger.error(f"Error extracting startup via rule: {str(e)}")
        return None, "RULE"

async def extract_product_extractor(raw_json_str, db):
    try:
        from urllib.parse import urlparse
        p = json.loads(raw_json_str)
        
        name = p.get("name", "")
        if not name and p.get("handle"):
            name = p.get("handle").replace("-", " ").title()
            
        url = p.get("url") or p.get("website") or "https://github.com/lakey009/AI-Tools-List"
        
        fallback_company = "Unknown"
        if url and "github.com" not in url:
            try:
                domain = urlparse(url).netloc
                fallback_company = domain.replace("www.", "").split(".")[0].title() or "Unknown"
            except:
                pass
        
        # Rule-based fallback instead of LLM
        parsed = {
            "schemaVersion": "1.0",
            "recordType": "PRODUCT",
            "source": {"name": "AI-Tools-List", "url": url},
            "content": {
                "productName": name,
                "startupName": fallback_company,
                "pricingModel": "FREEMIUM",
                "description": p.get('description', '')
            },
            "collectedAt": datetime.utcnow().isoformat() + "Z",
            "confidence": 1.0,
            "extraction_method": "RULE"
        }
        
        return parsed, "RULE"
    except Exception as e:
        logger.error(f"Product extraction failed: {str(e)}")
        return None, "RULE"

async def extract_paper_extractor(raw_json_str, db):
    try:
        p = json.loads(raw_json_str)
        title = p.get("title", "")
        authors = p.get("authors", [])
        paper_url = p.get("paper_url") or p.get("url_pdf") or p.get("url_abs", "")
        github_url = p.get("github_url", "")
        stars = p.get("github_stars", 0)
        published_date = p.get("published_date") or datetime.utcnow().isoformat()
        abstract = p.get("abstract", "")
        
        parsed = {
            "title": title,
            "authors": authors,
            "paper_url": paper_url,
            "github_url": github_url,
            "github_stars": stars,
            "published_date": published_date,
            "research_domain": "Other" # Default
        }
        
        method = "RULE"
        if abstract:
            from src.llm.orchestrator import extract_with_fallback
            from src.models.schemas import ResearchDomainClassification
            prompt = f"Classify this research paper abstract into the correct domain.\n\nTitle: {title}\nAbstract: {abstract}"
            try:
                validated = await extract_with_fallback(prompt, ResearchDomainClassification, db)
                parsed["research_domain"] = validated.research_domain.value
                method = "LLM" # We used LLM for enrichment
            except Exception as e:
                logger.warning(f"Failed to classify research domain for {paper_url}: {e}")
                
        return parsed, method
    except Exception as e:
        logger.error(f"Error extracting paper via rule: {str(e)}")
        return None, "RULE"

async def extract_job_extractor(raw_html, db):
    # Rule first
    try:
        import json
        from datetime import datetime
        j = json.loads(raw_html)
        title = j.get("title") or j.get("position") or j.get("name")
        company = j.get("company_name") or j.get("company")
        if title and company:
            is_remote = "remote" in str(j).lower()
            role_family = "Engineering"
            title_lower = str(title).lower()
            if "product" in title_lower: role_family = "Product Management"
            elif "design" in title_lower: role_family = "Design"
            elif "sales" in title_lower or "growth" in title_lower: role_family = "Sales/Growth"
            elif "data" in title_lower: role_family = "Data Science/Analytics"
            
            parsed = {
                "schemaVersion": "1.0",
                "recordType": "JOB",
                "content": {
                    "title": title,
                    "company": company,
                    "date": datetime.utcnow().isoformat(),
                    "is_remote": is_remote,
                    "role_family": role_family
                },
                "confidence": 1.0,
                "extraction_method": "RULE"
            }
            return parsed, "RULE"
    except Exception:
        pass
        
    # Search HTML configs if JSON failed
    for source_name, config in SOURCE_CONFIGS.items():
        parsed = extract_job_rule_based(raw_html, config)
        if parsed:
            parsed_job = {
                "schemaVersion": "1.0",
                "recordType": "JOB",
                "content": {
                    "title": parsed.get("title", ""),
                    "company": parsed.get("company", ""),
                    "date": parsed.get("date", datetime.utcnow().isoformat()),
                    "is_remote": parsed.get("is_remote", False),
                    "role_family": "Unknown"
                },
                "confidence": 1.0,
                "extraction_method": "RULE"
            }
            return parsed_job, "RULE"
            
    # LLM fallback
    logger.info("Rules failed for Job. Falling back to LLM...")
    prompt = (
        "Analyze the following job post HTML and extract these details in JSON: "
        "{\n"
        "  \"title\": \"Job title\",\n"
        "  \"company\": \"Company name\",\n"
        "  \"date\": \"ISO-8601 publication date\",\n"
        "  \"is_remote\": true/false,\n"
        "  \"role_family\": \"Engineering/Design/Product Management/Data Science/Analytics/Sales/Growth/Other\"\n"
        "}\n"
        "Return valid JSON only matching this format."
    )
    try:
        validated = await extract_with_fallback(prompt + "\n\nHTML:\n" + raw_html[:4000], Job, db)
        return validated.model_dump(), "LLM"
    except Exception as e:
        logger.error(f"LLM job extraction failed: {str(e)}")
        return None, "LLM"

async def extract_news_extractor(raw_json_str, db):
    try:
        n = json.loads(raw_json_str)
        parsed = {
            "schemaVersion": "1.0",
            "recordType": "NEWS",
            "source": {"name": n.get("source", "RSS Feed"), "url": n.get("url", "")},
            "content": {
                "title": n.get("title", ""),
                "url": n.get("url", ""),
                "published_date": n.get("published_date") or datetime.utcnow().isoformat(),
                "full_text": n.get("summary", "") or n.get("title", "")
            },
            "collectedAt": datetime.utcnow().isoformat() + "Z"
        }
        return parsed, "RULE"
    except Exception:
        return None, "RULE"

# Sync DB wrapper
import uuid

async def main():
    parser = argparse.ArgumentParser(description="GraphOne Ingestion Orchestrator")
    parser.add_argument("--vertical", type=str, default="all", 
                        choices=["all", "startups", "products", "research_papers", "jobs", "news"],
                        help="Ingestion vertical to run")
    parser.add_argument("--limit", type=int, default=50, help="Ingestion limit per vertical")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    db = DB()
    run_id = str(uuid.uuid4())
    db.start_run(run_id)
    run_stats = {"records": 0, "duplicates": 0, "stale_dropped": 0}
    
    # 50 Seed startups list
    from src.mock_db import CANONICAL_STARTUPS
    resolver = EntityResolver(CANONICAL_STARTUPS)
    
    sheet_id = os.getenv("SHEET_ID")
    creds_path = os.getenv("GOOGLE_SHEETS_CREDS_PATH", "./creds/service_account.json")
    
    # Early Auth Check
    check_sheets_auth(sheet_id, creds_path)
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Startups
        if args.vertical in ["all", "startups"]:
            logger.info("Executing YC Startups Ingestion...")
            raw_startups = await fetch_yc_startups(client, limit=args.limit)
            for item in raw_startups:
                payload_str = json.dumps(item)
                url = f"https://www.ycombinator.com/companies/{item.get('slug', 'unknown')}"
                record, status = await process_record(url, payload_str, db, resolver, Startup, extract_startup_extractor)
                if status == "DUPLICATE":
                    run_stats["duplicates"] += 1
                elif status == "SUCCESS" and record:
                    db.upsert_record("startups", url, record.model_dump(), record.collectedAt.isoformat())
                    run_stats["records"] += 1
            logger.info(f"Ingested {run_stats['records']} startups.")

        # Products
        if args.vertical in ["all", "products"]:
            logger.info("Executing AI Products Ingestion...")
            raw_products = await fetch_ai_products_list(client, limit=args.limit)
            for item in raw_products:
                payload_str = json.dumps(item)
                url = item.get("url") or item.get("website") or f"https://github.com/lakey009/AI-Tools-List#{item.get('name')}"
                record, status = await process_record(url, payload_str, db, resolver, Product, extract_product_extractor)
                if status == "DUPLICATE":
                    run_stats["duplicates"] += 1
                elif status == "SUCCESS" and record:
                    db.upsert_record("products", url, record.model_dump(), record.collectedAt.isoformat())
                    run_stats["records"] += 1
            logger.info(f"Ingested {run_stats['records']} products.")

        # Research Papers
        if args.vertical in ["all", "research_papers"]:
            logger.info("Executing Research Papers Ingestion (Hugging Face API)...")
            hf_url = "https://huggingface.co/api/daily_papers"
            github_token = os.getenv("GITHUB_TOKEN")
            
            papers_count = 0
            days_back = 0
            
            while papers_count < args.limit and days_back < 30:
                target_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
                url = f"{hf_url}?date={target_date}"
                logger.info(f"Fetching HF daily papers for {target_date}...")
                
                try:
                    resp = await client.get(url, timeout=20)
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data:
                            paper_data = item.get("paper") or item
                            arxiv_id = paper_data.get("id", "")
                            github_repo = paper_data.get("githubRepo")
                            
                            stars = 0
                            if github_repo and "github.com/" in github_repo:
                                repo_path = github_repo.split("github.com/")[-1].strip().rstrip("/")
                                stars = await get_stars_cached(repo_path, client, db, github_token) or 0
                            
                            authors = []
                            for auth in paper_data.get("authors", []):
                                if isinstance(auth, dict) and "name" in auth:
                                    authors.append(auth["name"])
                                elif isinstance(auth, str):
                                    authors.append(auth)
                                    
                            paper_payload = {
                                "title": paper_data.get("title", ""),
                                "authors": authors,
                                "paper_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else paper_data.get("url", ""),
                                "github_url": github_repo or "",
                                "github_stars": stars,
                                "published_date": paper_data.get("publishedAt") or datetime.utcnow().isoformat(),
                                "abstract": paper_data.get("summary", "") or paper_data.get("abstract", "")
                            }
                            
                            paper_url = paper_payload["paper_url"]
                            record, status = await process_record(paper_url, json.dumps(paper_payload), db, resolver, ResearchPaper, extract_paper_extractor)
                            if status == "DUPLICATE":
                                run_stats["duplicates"] += 1
                            elif status == "SUCCESS" and record:
                                db.upsert_record("research_papers", paper_url, record.model_dump(), datetime.utcnow().isoformat())
                                run_stats["records"] += 1
                                papers_count += 1
                                if papers_count >= args.limit:
                                    break
                except Exception as e:
                    logger.error(f"Error fetching papers for {target_date}: {str(e)}")
                    
                days_back += 1
                await asyncio.sleep(0.5)
            logger.info(f"Ingested {run_stats['records']} papers.")

        # News
        if args.vertical in ["all", "news"]:
            logger.info("Executing News Ingestion (RSS)...")
            from src.utils.date_utils import normalize_date, is_fresh
            feeds = [
                # Tier 1
                "https://nvidianews.nvidia.com/rss.xml",
                "https://venturebeat.com/ai/feed/",
                "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
                "https://techcrunch.com/category/artificial-intelligence/feed/",
                "https://huggingface.co/blog/feed.xml",
                # Tier 2
                "https://openai.com/news/rss.xml",
                "https://www.anthropic.com/news/rss.xml",
                "https://deepmind.google/blog/rss.xml",
                "https://ai.meta.com/blog/rss/",
                # Tier 3 (High Volume)
                "https://hnrss.org/frontpage",
                "https://hnrss.org/newest?q=AI",
                "https://www.reddit.com/r/artificial/.rss",
                "https://www.reddit.com/r/MachineLearning/.rss",
                # Existing Working Feeds
                "https://thedecoder.com/feed/",
                "http://export.arxiv.org/rss/cs.AI",
                "https://blogs.nvidia.com/feed/"
            ]
            for feed in feeds:
                try:
                    for entry in fetch_rss_news(feed):
                        published = normalize_date(entry.get("published_str"))
                        if published and not is_fresh(published):
                            run_stats["stale_dropped"] += 1
                            age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
                            title = entry.get('title', entry.get('url', ''))
                            logger.info(f"Rejected: {title} | Published={published} | Age={age_hours:.1f}h")
                            continue
                            
                        word_count = len(entry["full_text"].split()) if entry["full_text"] else 0
                        
                        payload = {
                            "title": entry["title"],
                            "url": entry["url"],
                            "published_date": published.isoformat() if published else datetime.utcnow().isoformat(),
                            "full_text": entry["full_text"],
                            "word_count": word_count,
                            "source": "RSS Feed"
                        }
                        
                        payload["summary"] = entry["full_text"]
                        record, status = await process_record(entry["url"], json.dumps(payload), db, resolver, News, extract_news_extractor)
                        if status == "DUPLICATE":
                            run_stats["duplicates"] += 1
                        elif status == "SUCCESS" and record:
                            db.upsert_record("news", entry["url"], record.model_dump() if hasattr(record, 'model_dump') else record, record.collectedAt.isoformat() if hasattr(record, 'collectedAt') else datetime.utcnow().isoformat())
                            run_stats["records"] += 1
                except Exception as e:
                    logger.error(f"Failed to fetch {feed}: {e}")
            logger.info(f"Ingested {run_stats['records']} fresh news articles.")

        # Jobs
        if args.vertical in ["all", "jobs"]:
            logger.info("Executing Jobs Ingestion (APIs)...")
            count = 0
            
            # Fetch from Remotive API
            try:
                logger.info("Fetching jobs from Remotive API...")
                resp = await client.get("https://remotive.com/api/remote-jobs?limit=20", headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    jobs = resp.json().get("jobs", [])
                    for job in jobs[:args.limit]:
                        published = normalize_date(job.get("publication_date"))
                        if published and not is_fresh(published):
                            run_stats["stale_dropped"] += 1
                            age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
                            title = job.get('title', job.get('url', ''))
                            logger.info(f"Rejected: {title} | Published={published} | Age={age_hours:.1f}h")
                            continue
                        record, status = await process_record(job["url"], json.dumps(job), db, resolver, Job, extract_job_extractor)
                        if status == "SUCCESS" and record:
                            db.upsert_record("jobs", job["url"], record.model_dump() if hasattr(record, 'model_dump') else record, datetime.utcnow().isoformat())
                            count += 1
            except Exception as e:
                logger.error(f"Remotive API failed: {e}")
                
            # Fetch from RemoteOK API
            try:
                logger.info("Fetching jobs from RemoteOK API...")
                resp = await client.get("https://remoteok.com/api", headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    jobs = resp.json()
                    for job in jobs[1:args.limit+1]:  # First item is legal info
                        url = job.get("url")
                        published = normalize_date(job.get("date"))
                        if published and not is_fresh(published):
                            run_stats["stale_dropped"] += 1
                            age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
                            title = job.get('title', job.get('url', ''))
                            logger.info(f"Rejected: {title} | Published={published} | Age={age_hours:.1f}h")
                            continue
                        if url:
                            record, status = await process_record(url, json.dumps(job), db, resolver, Job, extract_job_extractor)
                            if status == "SUCCESS" and record:
                                db.upsert_record("jobs", url, record.model_dump() if hasattr(record, 'model_dump') else record, datetime.utcnow().isoformat())
                                count += 1
            except Exception as e:
                logger.error(f"RemoteOK API failed: {e}")
                
            # Fetch from Hacker News Jobs API
            try:
                logger.info("Fetching jobs from Hacker News API...")
                resp = await client.get("https://hacker-news.firebaseio.com/v0/jobstories.json")
                if resp.status_code == 200:
                    ids = resp.json()
                    for job_id in ids[:args.limit]:
                        j_resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{job_id}.json")
                        if j_resp.status_code == 200:
                            job = j_resp.json()
                            published = normalize_date(str(job.get("time")))
                            if published and not is_fresh(published):
                              run_stats["stale_dropped"] += 1
                              age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
                              title = job.get('title', job.get('url', ''))
                              logger.info(f"Rejected: {title} | Published={published} | Age={age_hours:.1f}h")
                              continue
                            url = job.get("url") or f"https://news.ycombinator.com/item?id={job_id}"
                            record, status = await process_record(url, json.dumps(job), db, resolver, Job, extract_job_extractor)
                            if status == "SUCCESS" and record:
                                db.upsert_record("jobs", url, record.model_dump() if hasattr(record, 'model_dump') else record, datetime.utcnow().isoformat())
                                count += 1
            except Exception as e:
                logger.error(f"Hacker News API failed: {e}")

            # Fetch from Arbeitnow API
            try:
                logger.info("Fetching jobs from Arbeitnow API...")
                resp = await client.get("https://arbeitnow.com/api/job-board-api", headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    jobs = resp.json().get("data", [])
                    for job in jobs[:args.limit]:
                        url = job.get("url")
                        published = normalize_date(str(job.get("created_at")))
                        if published and not is_fresh(published):
                            run_stats["stale_dropped"] += 1
                            age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
                            title = job.get('title', job.get('url', ''))
                            logger.info(f"Rejected: {title} | Published={published} | Age={age_hours:.1f}h")
                            continue
                        if url:
                            record, status = await process_record(url, json.dumps(job), db, resolver, Job, extract_job_extractor)
                            if status == "SUCCESS" and record:
                                db.upsert_record("jobs", url, record.model_dump() if hasattr(record, 'model_dump') else record, datetime.utcnow().isoformat())
                                count += 1
            except Exception as e:
                logger.error(f"Arbeitnow API failed: {e}")

            # Fetch from TheMuse API
            try:
                logger.info("Fetching jobs from TheMuse API...")
                resp = await client.get("https://www.themuse.com/api/public/jobs?page=1", headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    jobs = resp.json().get("results", [])
                    for job in jobs[:args.limit]:
                        published = normalize_date(job.get("publication_date"))
                        if published and not is_fresh(published):
                            run_stats["stale_dropped"] += 1
                            age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
                            title = job.get('title', job.get('url', ''))
                            logger.info(f"Rejected: {title} | Published={published} | Age={age_hours:.1f}h")
                            continue
                        url = job.get("refs", {}).get("landing_page") or f"https://www.themuse.com/jobs/{job.get('id')}"
                        record, status = await process_record(url, json.dumps(job), db, resolver, Job, extract_job_extractor)
                        if status == "SUCCESS" and record:
                            db.upsert_record("jobs", url, record.model_dump() if hasattr(record, 'model_dump') else record, datetime.utcnow().isoformat())
                            count += 1
            except Exception as e:
                logger.error(f"TheMuse API failed: {e}")

            logger.info(f"Ingested {count} fresh job listings.")

    # Export
    logger.info("Exporting records to Google Sheets / Local CSVs...")
    export_to_sheets(db, sheet_id, creds_path)
    
    # End run tracking
    run_start_time = db.conn.execute("SELECT started_at FROM pipeline_runs WHERE run_id=?", (run_id,)).fetchone()[0]
    fallbacks = db.conn.execute("SELECT COUNT(*) FROM llm_events WHERE event_type='FALLBACK' AND ts > ?", (run_start_time,)).fetchone()[0]
    db.end_run(run_id, run_stats["records"], run_stats["duplicates"], fallbacks, run_stats["stale_dropped"])
    logger.info(f"Ingestion run {run_id} completed successfully!")



if __name__ == "__main__":
    asyncio.run(main())
