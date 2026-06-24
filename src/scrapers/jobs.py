import dateparser
from bs4 import BeautifulSoup
from datetime import datetime
import logging

logger = logging.getLogger("Jobs-Scraper")

SOURCE_CONFIGS = {
    "ai_jobs_net": {
        "company_selector": ".company",
        "date_selector": ".pub-date",
        "remote_selector": ".location",
        "title_selector": ".job-title",
    },
    "weworkremotely": {
        "company_selector": ".company",
        "date_selector": ".date",
        "remote_selector": ".region",
        "title_selector": ".title",
    },
    "remoteco": {
        "company_selector": ".co-name",
        "date_selector": ".date-posted",
        "remote_selector": ".location-type",
        "title_selector": ".job-position",
    },
    "huggingface": {
        "company_selector": ".job-company",
        "date_selector": ".job-date",
        "remote_selector": ".job-location",
        "title_selector": ".job-title",
    },
    "yc_jobs": {
        "company_selector": ".company-name",
        "date_selector": ".post-date",
        "remote_selector": ".job-loc",
        "title_selector": ".job-pos",
    }
}

def extract_job_rule_based(html, config):
    soup = BeautifulSoup(html, "html.parser")
    try:
        company_el = soup.select_one(config["company_selector"])
        company = company_el.text.strip() if company_el else None
        
        date_el = soup.select_one(config["date_selector"])
        date_text = date_el.text.strip() if date_el else None
        
        date = None
        if date_text:
            date = dateparser.parse(date_text, settings={"RELATIVE_BASE": datetime.utcnow()})
            
        remote_el = soup.select_one(config.get("remote_selector", ""))
        is_remote = bool(remote_el) and "remote" in remote_el.text.lower()
        
        title_el = soup.select_one(config.get("title_selector", ""))
        title = title_el.text.strip() if title_el else ""
        
        if not (company and date):
            return None
            
        return {
            "company": company,
            "date": date,
            "is_remote": is_remote,
            "title": title
        }
    except AttributeError as e:
        logger.warning(f"Failed parsing HTML with rule config: {str(e)}")
        return None
