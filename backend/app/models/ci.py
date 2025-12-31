
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class PRReview(Base):
    """
    Stores the history of PR reviews and Bot interactions.
    This serves as the 'memory' for the CI agent.
    """
    __tablename__ = "pr_reviews"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    
    # PR Identification
    pr_number = Column(Integer, nullable=False)
    commit_sha = Column(String, nullable=True) # The specific commit being reviewed
    
    # Interaction Type
    event_type = Column(String, nullable=False) # 'opened', 'synchronize', 'comment'
    
    # Content
    summary = Column(Text, nullable=True) # Short summary (Markdown)
    full_report = Column(Text, nullable=True) # Detailed report or JSON data
    
    # RAG Context (Debug/Transparency)
    # Stores a JSON string list of file paths/chunk IDs used to generate this response
    context_used = Column(Text, default="[]") 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project = relationship("Project", backref="pr_reviews")
    
    def __repr__(self):
        return f"<PRReview pr={self.pr_number} event={self.event_type}>"
