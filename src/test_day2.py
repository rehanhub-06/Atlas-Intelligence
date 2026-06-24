import asyncio
import logging
from src.storage.db import DB
from src.entity.resolver import EntityResolver
from src.mock_db import CANONICAL_STARTUPS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Day2-Checkpoint")

async def test_resolution_tiers():
    logger.info("Starting Day 2 Checkpoint Test...")
    DB()
    
    # Initialize resolver
    logger.info("Initializing EntityResolver...")
    resolver = EntityResolver(CANONICAL_STARTUPS)
    
    # 1. Exact Match Test
    logger.info("\n--- Tier 1: Exact Match ---")
    canonical, method, confidence = resolver.resolve("OpenAI")
    logger.info(f"Resolved 'OpenAI' -> '{canonical}' (method={method}, conf={confidence})")
    assert canonical == "OpenAI"
    assert method == "EXACT"
    
    # 2. Fuzzy Match Test (Inc. suffix cleaning + ratio)
    logger.info("\n--- Tier 2: Fuzzy Match ---")
    canonical, method, confidence = resolver.resolve("OpenAI, Inc.")
    logger.info(f"Resolved 'OpenAI, Inc.' -> '{canonical}' (method={method}, conf={confidence})")
    assert canonical == "OpenAI"
    assert method == "EXACT" or method == "FUZZY" # If EXACT, it's due to normalization cleaning suffix! Excellent.
    
    # Test a true fuzzy match
    canonical, method, confidence = resolver.resolve("Open AI")
    logger.info(f"Resolved 'Open AI' -> '{canonical}' (method={method}, conf={confidence})")
    assert canonical == "OpenAI"
    assert method == "FUZZY"
    
    # 3. Embedding Match Test (if sentence-transformers is loaded)
    logger.info("\n--- Tier 3: Embedding Match ---")
    canonical, method, confidence = resolver.resolve("stability artificial intelligence")
    logger.info(f"Resolved 'stability artificial intelligence' -> '{canonical}' (method={method}, conf={confidence})")
    if resolver.embeddings is not None:
        assert canonical == "Stability AI"
        assert method == "EMBEDDING"
    else:
        logger.info("Embedding model not loaded. Skipping embedding assert.")

    logger.info("Day 2 Checkpoint Test Complete. Resolution tiers validated.")

if __name__ == "__main__":
    asyncio.run(test_resolution_tiers())
