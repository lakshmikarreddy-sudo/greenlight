"""Research domain models supporting the Parallel Search API integration."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ResearchConfidence(str, Enum):
    """Confidence level of research findings."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ResearchQuery(BaseModel):
    """An individual search query formulated for external research."""
    query_text: str = Field(..., description="High-precision search query string")
    priority: int = Field(default=1, description="Priority ranking for query execution (1 = highest)")


class ResearchTask(BaseModel):
    """A research task formulated by the agent to investigate an external dependency."""
    task_id: Optional[str] = Field(default=None, description="Optional unique identifier for the task")
    objective: str = Field(..., description="Core investigative objective, e.g. 'Verify FAA drone permit regulations for NYC'")
    search_queries: List[str] = Field(..., description="List of targeted queries for the Parallel Search API")
    category: Optional[str] = Field(default=None, description="Logistical domain category")
    dependency_element: Optional[str] = Field(default=None, description="Associated screenplay dependency element")


class SearchSource(BaseModel):
    """A source retrieved from external research containing authoritative evidence."""
    title: str = Field(..., description="Title of the source webpage or document")
    url: str = Field(..., description="Direct hyperlink to the source")
    publish_date: Optional[str] = Field(default=None, description="Publication or revision date if available")
    excerpts: List[str] = Field(default_factory=list, description="Dense, LLM-optimized excerpts extracted from source")
    relevance_score: Optional[float] = Field(default=None, description="Optional numerical relevance score (0.0 to 1.0)")


class ResearchResult(BaseModel):
    """Aggregated result of an external research inquiry."""
    search_id: Optional[str] = Field(default=None, description="Parallel Search API search_id if available")
    objective: str = Field(..., description="The objective that guided this research")
    sources: List[SearchSource] = Field(default_factory=list, description="List of cited source items")
    key_findings: List[str] = Field(default_factory=list, description="Extracted factual takeaways")
    confidence: ResearchConfidence = Field(default=ResearchConfidence.HIGH, description="Confidence in findings")
    is_mock: bool = Field(default=False, description="True if generated from local fixture rather than live network")
    error: Optional[str] = Field(default=None, description="Error message if research call encountered issues")


class ParallelResultItem(BaseModel):
    """Schema matching a single result item from the Parallel Search API."""
    url: str = Field(..., description="Source URL")
    title: str = Field(..., description="Webpage title")
    publish_date: Optional[str] = Field(default=None, description="Publish date string")
    excerpts: List[str] = Field(default_factory=list, description="LLM-optimized passage excerpts")


class ParallelSearchResponse(BaseModel):
    """Schema directly matching the Parallel Search API response payload."""
    search_id: Optional[str] = Field(default=None, description="Unique search operation identifier")
    results: List[ParallelResultItem] = Field(default_factory=list, description="List of retrieved results")
    session_id: Optional[str] = Field(default=None, description="Parallel session identifier")
    warnings: Optional[List[str]] = Field(default=None, description="Non-fatal warnings if present")
