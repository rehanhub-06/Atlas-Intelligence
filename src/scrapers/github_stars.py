import asyncio
import logging

logger = logging.getLogger("GitHub-Stars")
sem = asyncio.Semaphore(5)

async def get_stars_cached(repo_full_name, client, db, token):
    cached = db.get_github_cache(repo_full_name)
    if cached is not None:
        return cached
        
    async with sem:
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        headers["Accept"] = "application/vnd.github.v3+json"
        headers["User-Agent"] = "GraphOne-Pipeline"
        
        try:
            resp = await client.get(f"https://api.github.com/repos/{repo_full_name}", headers=headers)
            if resp.status_code == 403 or resp.status_code == 429:
                logger.warning(f"GitHub API Rate Limit hit for {repo_full_name}. Skipping to prevent hallucination.")
                db.set_github_cache(repo_full_name, 0)
                return 0
                
            if resp.status_code != 200:
                logger.error(f"Failed to fetch stars for {repo_full_name}: Status {resp.status_code}")
                db.set_github_cache(repo_full_name, 0)
                return 0
                
            stars = resp.json().get("stargazers_count")
            db.set_github_cache(repo_full_name, stars)
            return stars
        except Exception as e:
            logger.error(f"Error fetching stars for {repo_full_name}: {str(e)}")
            return 0
