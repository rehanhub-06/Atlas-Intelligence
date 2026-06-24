import json
import os
import litellm
import logging
from pydantic import BaseModel, ValidationError
from tenacity import retry, wait_exponential_jitter, stop_after_attempt, retry_if_exception_type
from src.llm.chunking import chunk_text
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("LLM-Orchestrator")

CHAIN = [
    {"model": "gemini/gemini-2.5-flash", "key_name": "GEMINI_API_KEY"},
    {"model": "groq/llama-3.1-8b-instant", "key_name": "GROQ_API_KEY"},
    {"model": "groq/llama-3.3-70b-versatile", "key_name": "GROQ_API_KEY"}
]

gemini_disabled_until = None

class ExtractionFailedError(Exception):
    def __init__(self, message, attempted_provider="none"):
        super().__init__(message)
        self.attempted_provider = attempted_provider

async def extract_with_fallback(prompt, schema: type[BaseModel], db, max_validation_retries=2):
    global gemini_disabled_until
    
    has_api_keys = any(os.getenv(tier["key_name"]) for tier in CHAIN)
    attempted_provider = "none"
    
    if not has_api_keys:
        db.log_llm_event("none", "NO_KEYS", schema.__name__)
        raise ExtractionFailedError(f"No API keys configured for schema {schema.__name__}", attempted_provider="none")

    # Ensure the prompt explicitly asks for JSON to satisfy Groq/LiteLLM constraints
    if "json" not in prompt.lower():
        prompt += "\n\nIMPORTANT: Return ONLY a valid JSON object."

    for idx, tier in enumerate(CHAIN):
        if "gemini" in tier["model"] and gemini_disabled_until and datetime.now() < gemini_disabled_until:
            continue
            
        # Check if the API key for this model is configured
        api_key = os.getenv(tier["key_name"])
        if not api_key:
            continue
            
        attempted_provider = tier["model"].split("/")[0] if "/" in tier["model"] else tier["model"]
        
        if idx > 0:
            db.log_llm_event(tier["model"], "FALLBACK", schema.__name__)
            
        prompt_for_tier = prompt
        for attempt in range(max_validation_retries + 1):
            try:
                @retry(
                    wait=wait_exponential_jitter(initial=2, max=65), 
                    stop=stop_after_attempt(2), 
                    retry=retry_if_exception_type(litellm.RateLimitError),
                    reraise=True
                )
                async def _call_api():
                    return await litellm.acompletion(
                        model=tier["model"],
                        messages=[{"role": "user", "content": prompt_for_tier}],
                        response_format={"type": "json_object"},
                        timeout=30,
                        api_key=api_key
                    )
                
                resp = await _call_api()
                raw_text = resp.choices[0].message.content.strip()
                
                # Strip markdown json blocks if present
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()
                
                try:
                    raw = json.loads(raw_text)
                except json.JSONDecodeError as je:
                    logger.error(f"JSON decode failed for {tier['model']}: {je}. Raw output: {raw_text}")
                    raise je
                
                # Check for standard wrapped formats (sometimes LLM wraps content in a root key)
                if "content" not in raw and "entityName" in raw:
                    # Unwrapped Startup Content
                    raw = {
                        "schemaVersion": "1.0",
                        "recordType": "STARTUP",
                        "source": {"name": "YC", "url": "https://www.ycombinator.com"},
                        "content": raw,
                        "collectedAt": "2026-06-23T12:00:00Z"
                    }
                
                validated = schema.model_validate(raw)
                
                # Dynamic Confidence Logic
                if hasattr(validated, "confidence"):
                    if idx == 0:
                        validated.confidence = 0.85
                    else:
                        validated.confidence = 0.75
                if hasattr(validated, "extraction_method"):
                    validated.extraction_method = "LLM"
                
                db.log_llm_event(tier["model"], "SUCCESS", schema.__name__)
                return validated
            except litellm.RateLimitError:
                db.log_llm_event(tier["model"], "RATE_LIMIT", schema.__name__)
                if "gemini" in tier["model"]:
                    gemini_disabled_until = datetime.now() + timedelta(minutes=30)
                break
            except litellm.ContextWindowExceededError:
                db.log_llm_event(tier["model"], "CONTEXT_OVERFLOW", schema.__name__)
                prompt_for_tier = chunk_text(prompt_for_tier)
            except ValidationError as e:
                db.log_llm_event(tier["model"], "VALIDATION_RETRY", schema.__name__)
                prompt_for_tier = prompt + f"\n\nFix this validation error, return valid JSON matching the schema only: {e}"
            except Exception as e:
                logger.error(f"LLM Orchestrator exception on tier {tier['model']}: {type(e).__name__} - {str(e)}")
                db.log_llm_event(tier["model"], f"ERROR_{type(e).__name__}", schema.__name__)
                if "gemini" in tier["model"] and ("429" in str(e) or "resource" in str(e).lower() or "timeout" in str(e).lower()):
                    gemini_disabled_until = datetime.now() + timedelta(minutes=30)
                break
                
    # If all LLMs fail, raise DLQ error
    logger.warning("All LLM tiers failed. Raising ExtractionFailedError.")
    db.log_llm_event("all_tiers_failed", "FAILED", schema.__name__)
    raise ExtractionFailedError(f"Extraction failed for schema {schema.__name__} after exhausting all tiers.", attempted_provider=attempted_provider)
