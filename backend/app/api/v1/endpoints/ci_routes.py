
from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.api import deps
from app.db.session import get_db
from app.models.project import Project
from app.models.ci import PRReview
from app.schemas.ci import CIProjectRead, PRReviewRead

router = APIRouter()

@router.get("/projects", response_model=List[CIProjectRead])
async def read_ci_projects(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve all CI-managed projects.
    """
    query = select(Project).where(Project.is_ci_managed == True)
    query = query.order_by(desc(Project.latest_pr_activity)).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/projects/{project_id}/reviews", response_model=List[PRReviewRead])
async def read_project_reviews(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
) -> Any:
    """
    Retrieve PR reviews for a specific project.
    """
    query = select(PRReview).where(PRReview.project_id == project_id)
    query = query.order_by(desc(PRReview.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@router.delete("/projects/{project_id}")
async def delete_ci_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Delete a CI project and its reviews.
    """
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if not project.is_ci_managed:
        raise HTTPException(status_code=400, detail="Cannot delete non-CI managed project via this API")
        
    await db.delete(project)
    await db.commit()
    return {"status": "success"}
