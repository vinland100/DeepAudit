
"""
CI Service
Handles Gitea webhook events, manages RAG indexing for CI projects, and performs automated code reviews.
"""

import os
import shutil
import logging
import subprocess
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import asyncio
import httpx

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.models.project import Project
from app.models.ci import PRReview
from app.core.ci_prompts import (
    build_pr_review_prompt, 
    build_chat_prompt, 
    PR_SYNC_TASK
)
from app.services.rag.indexer import CodeIndexer, IndexUpdateMode
from app.services.rag.retriever import CodeRetriever
from app.services.llm.service import LLMService

logger = logging.getLogger(__name__)

# Base directory for storing CI clones
CI_WORKSPACE_DIR = Path("data/ci_workspace")
CI_VECTOR_DB_DIR = Path("data/ci_vectordb")

class CIService:
    
    def __init__(self, db: AsyncSession):
        self.db = db
        # Ensure workspaces exist
        CI_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        CI_VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
        
        self.llm_service = LLMService() # Use default config

    async def handle_pr_event(self, payload: Dict[str, Any]):
        """
        Handle Pull Request events (opened, synchronized)
        """
        action = payload.get("action")
        pr = payload.get("pull_request")
        repo = payload.get("repository")
        
        if not pr or not repo:
            return

        repo_url = repo.get("clone_url")
        pr_number = pr.get("number")
        branch = pr.get("head", {}).get("ref")
        commit_sha = pr.get("head", {}).get("sha")
        base_branch = pr.get("base", {}).get("ref")
        
        logger.info(f"🚀 Handling PR Event: {repo.get('full_name')} #{pr_number} ({action})")

        # 1. Get or Create Project
        try:
            project = await self._get_or_create_project(repo, pr)
        except Exception as e:
            logger.error(f"Error creating project: {e}")
            return

        # 2. Clone/Update Repo & Indexing (RAG)
        try:
            repo_path = await self._prepare_repository(project, repo_url, branch, settings.GITEA_BOT_TOKEN)
        except Exception as e:
            logger.error(f"Git operation failed: {e}")
            # If clone fails, we can't proceed with RAG, but we shouldn't crash
            return
        
        try:
            # 3. Incremental Indexing
            indexer = CodeIndexer(
                collection_name=f"ci_{project.id}", 
                persist_directory=str(CI_VECTOR_DB_DIR / project.id)
            )
            # Iterate over the generator to execute indexing
            async for progress in indexer.smart_index_directory(
                directory=repo_path, 
                update_mode=IndexUpdateMode.INCREMENTAL
            ):
                if progress.processed_files % 10 == 0:
                    logger.info(f"Indexing progress: {progress.processed_files}/{progress.total_files}")
    
            # 4. Analyze Diff & Retrieve Context
            diff_text = await self._get_pr_diff(repo, pr_number)
            if not diff_text:
                logger.warning("Empty diff or failed to fetch diff. Skipping review.")
                return

            # Retrieve context relevant to the diff
            retriever = CodeRetriever(
                collection_name=f"ci_{project.id}",
                persist_directory=str(CI_VECTOR_DB_DIR / project.id)
            )
            
            context_results = await retriever.retrieve(diff_text[:1000], top_k=5)
            repo_context = "\n".join([r.to_context_string() for r in context_results])
            
            # 5. Generate Review
            history = "" 
            
            if action == "synchronize":
                 prompt = build_pr_review_prompt(diff_text, repo_context, history)
                 prompt += f"\n\nNOTE: {PR_SYNC_TASK}"
            else:
                 prompt = build_pr_review_prompt(diff_text, repo_context, history)
                 
            # Call LLM
            response = await self.llm_service.chat_completion_raw(
                messages=[{"role": "user", "content": prompt}], 
                temperature=0.2
            )
            
            review_body = response["content"]
            
            # 6. Post Comment
            await self._post_gitea_comment(repo, pr_number, review_body)
            
            # 7. Save Record
            review_record = PRReview(
                project_id=project.id,
                pr_number=pr_number,
                commit_sha=commit_sha,
                event_type=action,
                summary=review_body[:200] + "...",
                full_report=review_body,
                context_used=json.dumps([r.file_path for r in context_results])
            )
            self.db.add(review_record)
            
            # Update project activity
            project.latest_pr_activity = datetime.utcnow()
            await self.db.commit()

        except Exception as e:
            logger.error(f"Error processing PR event: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Don't raise, just log, so webhook returns 200
            return


    async def handle_comment_event(self, payload: Dict[str, Any]):
        """
        Handle Issue Comment events (chat)
        """
        action = payload.get("action")
        issue = payload.get("issue")
        comment = payload.get("comment")
        repo = payload.get("repository")
        
        if action != "created" or not issue or not comment:
            return
            
        # Check if it's a PR
        if "pull_request" not in issue:
            return
            
        body = comment.get("body", "")
        if "@ai-bot" not in body:
            return
            
        logger.info(f"💬 Handling Chat Event: {repo.get('full_name')} #{issue.get('number')}")
        
        # 1. Get Project (or Create if discovered via Chat first)
        # We need a dummy PR object if we are creating project from chat, or we just fetch by repo
        # Since _get_or_create_project needs PR info to determine branch/owner, we might need a distinct method
        # or simplified flow.
        project = await self._get_project_by_repo(repo.get("clone_url"))
        
        if not project:
            # If project doesn't exist, we try to create it using available repo info
            # We construct a minimal "pseudo-PR" dict if needed, or better:
            # We assume if we are chatting on a PR, we can get PR details via API later
            # For now, let's just Try to Find Project. If not found, we CANNOT proceed easily without syncing.
            # But user wants "Auto Discovery".
            # Let's try to create it.
            try:
                # Mock a PR object for creation purposes (minimal fields)
                mock_pr = {
                    "number": issue.get("number"),
                    "head": {"ref": repo.get("default_branch", "main"), "sha": "HEAD"}, # Fallback
                    "base": {"ref": repo.get("default_branch", "main")}
                }
                project = await self._get_or_create_project(repo, mock_pr)
            except Exception as e:
                logger.error(f"Failed to auto-create project from chat: {e}")
                return

        if not project:
            logger.warning("Project could not be determined for chat event")
            return

        # 2. Retrieve Context (RAG)
        retriever = CodeRetriever(
            collection_name=f"ci_{project.id}",
            persist_directory=str(CI_VECTOR_DB_DIR / project.id)
        )
        # Use the user comment as query
        query = body.replace("@ai-bot", "").strip()
        context_results = await retriever.retrieve(query, top_k=5)
        repo_context = "\n".join([r.to_context_string() for r in context_results])
        
        # 3. Build Prompt
        # Fetch conversation history (simplified: just current comment)
        history = f"User: {query}"
        prompt = build_chat_prompt(query, repo_context, history)
        
        # 4. Generate Answer
        response = await self.llm_service.chat_completion_raw(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        
        answer = response["content"]
        
        # 5. Reply
        # Append context info footer
        footer = "\n\n---\n*Context used: " + ", ".join([f"`{r.file_path}`" for r in context_results]) + "*"
        await self._post_gitea_comment(repo, issue.get("number"), answer + footer)
        
        # 6. Record (Optional, maybe just log)
        review_record = PRReview(
            project_id=project.id,
            pr_number=issue.get("number"),
            event_type="comment",
            summary=f"Q: {query[:50]}...",
            full_report=answer,
            context_used=json.dumps([r.file_path for r in context_results])
        )
        self.db.add(review_record)
        await self.db.commit()


    async def _get_or_create_project(self, repo: Dict, pr: Dict) -> Project:
        repo_url = repo.get("clone_url")
        # Check if exists
        stmt = select(Project).where(Project.repository_url == repo_url)
        result = await self.db.execute(stmt)
        project = result.scalars().first()
        
        if not project:
            # Create new
            # Find a valid user to assign as owner (required field)
            from app.models.user import User
            user_stmt = select(User).limit(1)
            user_res = await self.db.execute(user_stmt)
            default_user = user_res.scalars().first()
            
            owner_id = default_user.id if default_user else "system_fallback_user"
            
            project = Project(
                name=repo.get("name"),
                description=repo.get("description"),
                source_type="repository",
                repository_url=repo_url,
                repository_type="gitea",
                default_branch=repo.get("default_branch", "main"),
                owner_id=owner_id, 
                is_ci_managed=True
            )
            
            try:
                self.db.add(project)
                await self.db.commit()
                await self.db.refresh(project)
                logger.info(f"🆕 Created CI Project: {project.name}")
            except Exception as e:
                logger.error(f"Failed to create project: {e}")
                # Try rollback possibly?
                await self.db.rollback()
                raise e
            
        return project

    async def _get_project_by_repo(self, repo_url: str) -> Optional[Project]:
        stmt = select(Project).where(Project.repository_url == repo_url)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _prepare_repository(self, project: Project, repo_url: str, branch: str, token: str) -> str:
        """
        Clones or Updates the repository locally.
        """
        target_dir = CI_WORKSPACE_DIR / project.id
        
        # Inject Token into URL for auth
        # Format: http://token@host/repo.git
        if "://" in repo_url:
            protocol, rest = repo_url.split("://", 1)
            auth_url = f"{protocol}://{token}@{rest}"
        else:
            auth_url = repo_url # Fallback
            
        if target_dir.exists():
            # Update
            logger.info(f"🔄 Updating repo at {target_dir}")
            try:
                # git fetch --all
                subprocess.run(["git", "fetch", "--all"], cwd=target_dir, check=True)
                # git checkout branch
                subprocess.run(["git", "checkout", branch], cwd=target_dir, check=True)
                # git reset --hard origin/branch
                subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=target_dir, check=True)
            except Exception as e:
                logger.error(f"Git update failed: {e}. Re-cloning...")
                shutil.rmtree(target_dir) # Nuke and retry
                return await self._prepare_repository(project, repo_url, branch, token)
        else:
            # Clone
            logger.info(f"📥 Cloning repo to {target_dir}")
            try:
                subprocess.run(["git", "clone", "-b", branch, auth_url, str(target_dir)], check=True)
            except Exception as e:
                logger.error(f"Git clone failed: {e}")
                raise e
                
        return str(target_dir)

    async def _get_pr_diff(self, repo: Dict, pr_number: int) -> str:
        """
        Fetch the PR diff from Gitea API
        """
        api_url = f"{settings.GITEA_HOST_URL}/api/v1/repos/{repo['owner']['login']}/{repo['name']}/pulls/{pr_number}.diff"
        headers = {"Authorization": f"token {settings.GITEA_BOT_TOKEN}"}
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(api_url, headers=headers)
                if resp.status_code == 200:
                    return resp.text
                else:
                    logger.error(f"Failed to fetch diff: {resp.status_code} - {resp.text[:200]}")
                    return ""
        except Exception as e:
            logger.error(f"Failed to fetch PR diff: {e}")
            return ""

    async def _post_gitea_comment(self, repo: Dict, issue_number: int, body: str):
        if not settings.GITEA_HOST_URL or not settings.GITEA_BOT_TOKEN:
            logger.error("GITEA_HOST_URL or GITEA_BOT_TOKEN not configured")
            return
            
        api_url = f"{settings.GITEA_HOST_URL}/api/v1/repos/{repo['owner']['login']}/{repo['name']}/issues/{issue_number}/comments"
        
        headers = {
            "Authorization": f"token {settings.GITEA_BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                 resp = await client.post(api_url, headers=headers, json={"body": body})
                 if resp.status_code >= 400:
                     logger.error(f"Gitea API Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Failed to post Gitea comment: {e}")
