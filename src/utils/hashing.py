import hashlib

def hash_content(text: str) -> str:
    """
    Generate a SHA-256 hash for content-addressable storage.
    We strictly use SHA-256 over MD5 to avoid collision vulnerabilities 
    and to adhere to modern production-grade engineering standards.
    """
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
