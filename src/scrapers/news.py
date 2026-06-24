import feedparser
import requests
import trafilatura
import logging

logger = logging.getLogger("News-Scraper")

def fetch_rss_news(feed_url):
    logger.info(f"Parsing feed: {feed_url}")
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            published_str = entry.get("published") or entry.get("updated") or entry.get("pubDate")
            
            from src.utils.date_utils import normalize_date, is_fresh
            published = normalize_date(published_str)
            if published and not is_fresh(published):
                yield {
                    "title": entry.title,
                    "url": entry.link,
                    "published_str": published_str,
                    "full_text": ""
                }
                continue
                
            url = entry.link
            full_text = ""
            try:
                html = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}).text
                extracted = trafilatura.extract(html)
                if extracted:
                    full_text = extracted
            except Exception as e:
                logger.warning(f"Trafilatura failed to extract full text for {url}: {e}")

            if not full_text:
                full_text = entry.get("summary", "")
                
            yield {
                "title": entry.title,
                "url": url,
                "published_str": published_str,
                "full_text": full_text
            }
    except Exception as e:
        logger.error(f"Failed parsing RSS feed {feed_url}: {str(e)}")
