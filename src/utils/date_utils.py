import dateparser
from datetime import datetime, timezone, timedelta

def normalize_date(date_string):
    """
    Parses a string (including relative times like "2 hours ago") 
    into a UTC timezone-aware datetime object.
    """
    if not date_string:
        return None
    
    dt = dateparser.parse(
        date_string,
        settings={
            "RETURN_AS_TIMEZONE_AWARE": True
        }
    )
    if dt:
        return dt.astimezone(timezone.utc)
    return None

def is_fresh(published_date):
    """
    Returns True if the published_date is within the last 24 hours.
    Expects a timezone-aware UTC datetime.
    """
    if not published_date:
        return False
    return (datetime.now(timezone.utc) - published_date) <= timedelta(hours=24)
