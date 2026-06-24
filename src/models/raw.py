from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class RawCapture(BaseModel):
    source_url: str
    fetched_at: datetime
    raw_payload: str
    extraction_method: Literal["RULE", "LLM"]
