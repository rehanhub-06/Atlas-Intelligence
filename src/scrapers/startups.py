import asyncio
import httpx
import logging
from src.utils.retry import with_retry

logger = logging.getLogger("Startups-Scraper")
sem = asyncio.Semaphore(5)

@with_retry(max_attempts=3, base_delay=2.0)
async def fetch_endpoint(client: httpx.AsyncClient, url: str) -> dict:
    async with sem:
        resp = await client.get(url, timeout=20.0)
        resp.raise_for_status()
        return resp.json()

async def fetch_yc_startups(client: httpx.AsyncClient, limit: int = 1000) -> list[dict]:
    url = "https://yc-oss.github.io/api/companies/all.json"
    logger.info(f"Fetching YC startups from: {url}")
    try:
        companies = await fetch_endpoint(client, url)
        # If companies is a list (which is expected)
        if isinstance(companies, list):
            logger.info(f"Loaded {len(companies)} raw startups from YC OSS registry.")
            return companies[:limit]
        return []
    except Exception as e:
        logger.error(f"Error fetching YC startups: {str(e)}")
        return []

async def fetch_ai_products_list(client: httpx.AsyncClient, limit: int = 1000) -> list[dict]:
    url = "https://raw.githubusercontent.com/lakey009/AI-Tools-List/main/AIToolsList.json"
    logger.info(f"Fetching AI products from: {url}")
    try:
        products = await fetch_endpoint(client, url)
        if isinstance(products, list):
            logger.info(f"Loaded {len(products)} raw products from AI-Tools-List registry.")
            return products[:limit]
        return []
    except Exception as e:
        logger.error(f"Error fetching AI products registry: {str(e)}")
        return []
