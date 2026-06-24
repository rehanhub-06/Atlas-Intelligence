import logging
import numpy as np

# Try to import rapidfuzz and sentence-transformers
try:
    from rapidfuzz import fuzz
except ImportError:
    # Minimal fallback sequence matcher if rapidfuzz is missing
    import difflib
    class MockFuzz:
        @staticmethod
        def ratio(s1, s2):
            return int(difflib.SequenceMatcher(None, s1, s2).ratio() * 100)
    fuzz = MockFuzz()

logger = logging.getLogger("Entity-Resolver")

# Global lazy-loaded model to avoid overhead at import time
_model = None

def get_embedding_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # Suppress logs from transformers during loading
            import os
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            logger.info("Loading sentence-transformers model 'all-MiniLM-L6-v2'...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load sentence-transformers: {str(e)}. Embedding similarity will be disabled.")
            _model = False
    return _model

class EntityResolver:
    def __init__(self, canonical_list: list[str]):
        self.canonical_list = canonical_list
        self.canonical_norm = [self._normalize(c) for c in canonical_list]
        
        # Load embedding model
        model = get_embedding_model()
        if model:
            try:
                self.embeddings = model.encode(canonical_list)
            except Exception as e:
                logger.error(f"Error encoding canonical list: {str(e)}")
                self.embeddings = None
        else:
            self.embeddings = None

    def _normalize(self, name: str) -> str:
        name = name.lower().strip()
        # Clean standard suffixes
        for suffix in [", inc.", " inc.", ", llc", " llc", ", ltd", " ltd", " co.", " corp.", " corporation"]:
            name = name.replace(suffix, "")
        return name.strip()

    def resolve(self, raw_name: str) -> tuple[str | None, str, float]:
        if not raw_name:
            return None, "UNRESOLVED", 0.0
            
        norm = self._normalize(raw_name)

        # Tier 1: exact match
        if norm in self.canonical_norm:
            idx = self.canonical_norm.index(norm)
            return self.canonical_list[idx], "EXACT", 1.0

        # Tier 2: fuzzy match
        best_score, best_idx = 0, -1
        for i, c in enumerate(self.canonical_norm):
            score = fuzz.ratio(norm, c)
            if score > best_score:
                best_score, best_idx = score, i
                
        if best_score >= 85:
            return self.canonical_list[best_idx], "FUZZY", best_score / 100.0

        # Tier 3: embedding similarity (only reached if fuzzy fails)
        model = get_embedding_model()
        if model and self.embeddings is not None:
            try:
                vec = model.encode([raw_name])[0]
                # Cosine similarity
                sims = self.embeddings @ vec / (
                    np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(vec)
                )
                best_emb_idx = sims.argmax()
                if sims[best_emb_idx] >= 0.75:
                    return self.canonical_list[best_emb_idx], "EMBEDDING", float(sims[best_emb_idx])
            except Exception as e:
                logger.error(f"Error during embedding resolution: {str(e)}")

        return None, "UNRESOLVED", 0.0
