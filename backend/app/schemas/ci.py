
from typing import List, Optional, Any
from datetime import datetime
from pydantic import BaseModel
from app.models.ci import PRReview

class PRReviewRead(BaseModel):
    id: str
    project_id: str
    pr_number: int
    commit_sha: Optional[str]
    event_type: str
    summary: Optional[str]
    full_report: Optional[str]
    context_used: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class CIProjectRead(BaseModel):
    id: str
    name: str
    description: Optional[str]
    repository_url: Optional[str]
    latest_pr_activity: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True
