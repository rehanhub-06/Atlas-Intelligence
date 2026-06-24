from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from enum import Enum

class ResearchDomain(str, Enum):
    LLM = "LLM"
    COMPUTER_VISION = "Computer Vision"
    ROBOTICS = "Robotics"
    RAG = "RAG"
    AGENTS = "Agents"
    OTHER = "Other"

class ResearchDomainClassification(BaseModel):
    research_domain: ResearchDomain

class Source(BaseModel):
    name: str
    url: str # Use str instead of HttpUrl to avoid strict serialization/validation issues with custom protocols or local URLs in some environments

class StartupContent(BaseModel):
    entityName: str
    employeeCount: Optional[int] = None

class Startup(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    recordType: Literal["STARTUP"] = "STARTUP"
    source: Source
    content: StartupContent
    collectedAt: datetime
    confidence: float = 0.85
    extraction_method: Literal["LLM", "RULE"] = "LLM"

class ProductContent(BaseModel):
    productName: str # Restoring productName as we need to track the name of the product
    startupName: str
    pricingModel: Literal["FREE", "FREEMIUM", "PAID", "ENTERPRISE"]
    description: Optional[str] = ""

class Product(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    recordType: Literal["PRODUCT"] = "PRODUCT"
    source: Source
    content: ProductContent
    collectedAt: datetime
    confidence: float = 0.85
    extraction_method: Literal["LLM", "RULE"] = "LLM"

class PaperContent(BaseModel):
    title: str
    authors: list[str]
    paper_url: str
    github_url: Optional[str] = None
    github_stars: Optional[int] = None
    published_date: datetime
    research_domain: Optional[str] = None

class ResearchPaper(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    recordType: Literal["RESEARCH_PAPER"] = "RESEARCH_PAPER"
    content: PaperContent
    confidence: float = 0.85
    extraction_method: Literal["LLM", "RULE"] = "LLM"

class JobContent(BaseModel):
    title: str # Restoring job title
    company: str
    date: datetime
    is_remote: bool
    role_family: str

class Job(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    recordType: Literal["JOB"] = "JOB"
    content: JobContent
    confidence: float = 0.85
    extraction_method: Literal["LLM", "RULE"] = "LLM"

class NewsContent(BaseModel):
    title: str
    url: str
    published_date: datetime
    full_text: str
    word_count: Optional[int] = None

class News(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    recordType: Literal["NEWS"] = "NEWS"
    source: Source
    content: NewsContent
    collectedAt: datetime
    confidence: float = 0.85
    extraction_method: Literal["LLM", "RULE"] = "LLM"
