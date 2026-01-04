
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
    build_pr_sync_prompt,
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

        # 2. Sync Repository and Index
        repo_path = await self._ensure_indexed(project, repo_url, branch, pr_number=pr_number)
        if not repo_path:
            return
        
        try:
            # 4. Analyze Diff & Retrieve Context
            diff_text = await self._get_pr_diff(repo, pr_number)
            if not diff_text:
                logger.warning("Empty diff or failed to fetch diff. Skipping review.")
                return

            # Determine sync diff if needed
            sync_diff = ""
            history = ""
            if action == "synchronized":
                 # 增量同步模式：获取全部对话历史
                 history = await self._get_conversation_history(repo, pr_number)
                 
                 # 获取本次同步的具体差异 (commit diff)
                 before_sha = payload.get("before")
                 after_sha = payload.get("after") or commit_sha
                 
                 if not before_sha:
                     logger.info(f"🔍 Webhook payload missing 'before' SHA, searching database for previous sync head...")
                     before_sha = await self._get_previous_review_sha(project.id, pr_number)
                 
                 if not before_sha or not await self._is_sha_valid(repo_path, str(before_sha)):
                     logger.warning(f"⚠️ Baseline SHA {before_sha} is missing or invalid. Falling back to {after_sha}^")
                     before_sha = f"{after_sha}^"
                 
                 if before_sha and after_sha and before_sha != after_sha:
                     logger.info(f"📂 Fetching sync diff: {before_sha} -> {after_sha}")
                     sync_diff = await self._get_commit_diff(repo_path, str(before_sha), str(after_sha))
                 
                 if not sync_diff or (hasattr(sync_diff, "strip") and sync_diff.strip() == ""):
                      if str(before_sha) == str(after_sha):
                           sync_diff = "(推送的 HEAD 与上次评审点相同，无新增差异)"
                      else:
                           sync_diff = "(本次同步虽有 SHA 变动，但代码内容与上次评审点完全一致。)"

            # Retrieve context relevant to the diff
            retriever = CodeRetriever(
                collection_name=f"ci_{project.id}",
                persist_directory=str(CI_VECTOR_DB_DIR / project.id)
            )
            
            # 优先使用 sync_diff 作为检索关键词，若为空（如初次 PR）则使用全量 diff
            # 增加检索字符长度到 2000 以获得更多上下文
            rag_query = sync_diff if sync_diff and "---" in sync_diff else diff_text
            context_results = await retriever.retrieve(rag_query[:2000], top_k=5)
            repo_context = "\n".join([r.to_context_string() for r in context_results])
            
            # 5. 生成评审
            if action == "synchronized":
                 prompt = build_pr_sync_prompt(sync_diff, repo_context, history)
            else:
                 prompt = build_pr_review_prompt(diff_text, repo_context, history)
                 
            # Call LLM
            response = await self.llm_service.chat_completion_raw(
                messages=[{"role": "user", "content": prompt}], 
                temperature=0.2
            )
            
            review_body = response["content"]
            
            # 6. Post Comment
            # 附加上下文信息页脚
            footer_parts = [f"`{r.file_path}`" for r in context_results]
            footer = "\n\n---\n*本次评审参考了以下文件: " + (", ".join(footer_parts) if footer_parts else "无（使用了模型通用知识）") + "*"
            await self._post_gitea_comment(repo, pr_number, review_body + footer)
            
            if action == "synchronized":
                logger.info(f"✅ Successfully posted PR Sync (Incremental) review for PR #{pr_number}")
            else:
                logger.info(f"✅ Successfully posted PR Review (Initial) for PR #{pr_number}")
            
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
        # 1. Get Project (or Create if discovered via Chat first)
        repo_url = repo.get("clone_url")
        project = await self._get_project_by_repo(repo_url)
        
        if not project:
            try:
                # Mock a PR object for creation
                mock_pr = {
                    "number": issue.get("number"),
                    "head": {"ref": repo.get("default_branch", "main"), "sha": "HEAD"},
                    "base": {"ref": repo.get("default_branch", "main")}
                }
                project = await self._get_or_create_project(repo, mock_pr)
            except Exception as e:
                logger.error(f"Failed to auto-create project from chat: {e}")
                return

        if not project:
            logger.warning("Project could not be determined for chat event")
            return

        # 2. Ensure Indexed (Important for first-time chat or if project auto-created)
        branch = repo.get("default_branch", "main")
        repo_path = await self._ensure_indexed(project, repo_url, branch, pr_number=issue.get("number"))
        if not repo_path:
            logger.error("Failed to sync/index repository for chat")
            return

        # 3. Retrieve Context (RAG)
        retriever = CodeRetriever(
            collection_name=f"ci_{project.id}",
            persist_directory=str(CI_VECTOR_DB_DIR / project.id)
        )
        # Use the user comment as query
        query = body.replace("@ai-bot", "").strip()
        
        # Handle empty query
        if not query:
            msg = "你好！我是 DeepAudit AI 助手。你可以问我关于此 PR 或项目代码的任何安全及逻辑问题。例如：\n- '这段代码有 SQL 注入风险吗？'\n- '这个 PR 修改了哪些核心组件？'\n\n请提供具体问题以便我通过代码上下文为你解答。"
            await self._post_gitea_comment(repo, issue.get("number"), msg)
            return

        try:
            context_results = await retriever.retrieve(query, top_k=5)
        except Exception as e:
            err_msg = str(e).lower()
            # Dimension mismatch, 404 (model not found), or 401 (auth issue usually model related)
            # indicator of need for re-index with current settings
            should_rebuild = any(x in err_msg for x in ["dimension", "404", "401", "400", "invalid_model"])
            
            if should_rebuild:
                logger.warning(f"Embedding/RAG error for project {project.id}: {e}. Triggering full rebuild...")
                # Rebuild using current correct configuration
                await self._ensure_indexed(project, repo, branch, force_rebuild=True)
                # Retry retrieval
                try:
                    context_results = await retriever.retrieve(query, top_k=5)
                except Exception as retry_e:
                    logger.error(f"Retry retrieval failed: {retry_e}")
                    context_results = []
            else:
                logger.error(f"Retrieval error (no rebuild): {e}")
                context_results = []

        repo_context = "\n".join([r.to_context_string() for r in context_results])
        
        # 4. 获取 PR 差异作为上下文
        diff_text = await self._get_pr_diff(repo, issue.get("number"))

        # 5. 构建提示词
        # 获取全部 PR 对话历史作为上下文
        history = await self._get_conversation_history(repo, issue.get("number"))
        prompt = build_chat_prompt(query, repo_context, history, diff=diff_text)
        
        # 6. 生成回答
        response = await self.llm_service.chat_completion_raw(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        
        answer = response["content"]
        
        # 7. 回复
        # 附加上下文信息页脚
        footer_parts = [f"`{r.file_path}`" for r in context_results]
        footer = "\n\n---\n*本次回答参考了以下文件: " + (", ".join(footer_parts) if footer_parts else "无（使用了模型通用知识）") + "*"
        await self._post_gitea_comment(repo, issue.get("number"), answer + footer)
        logger.info(f"✅ Successfully posted @ai-bot Chat response for PR #{issue.get('number')}")
        
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

    async def _ensure_indexed(self, project: Project, repo_url: str, branch: str, pr_number: Optional[int] = None, force_rebuild: bool = False) -> Optional[str]:
        """
        Syncs the repository and ensures it is indexed.
        Returns the local path if successful.
        """
        # 1. Prepare Repository (Clone/Pull)
        repo_path = await self._prepare_repository(project, repo_url, branch, settings.GITEA_BOT_TOKEN, pr_number=pr_number)
        
        if not repo_path:
            logger.error(f"Failed to prepare repository for project {project.id}")
            return None
        
        try:
            # 2. Incremental or Full Indexing
            indexer = CodeIndexer(
                collection_name=f"ci_{project.id}", 
                persist_directory=str(CI_VECTOR_DB_DIR / project.id)
            )
            
            update_mode = IndexUpdateMode.FULL if force_rebuild else IndexUpdateMode.INCREMENTAL
            
            # Iterate over the generator to execute indexing
            async for progress in indexer.smart_index_directory(
                directory=repo_path, 
                update_mode=update_mode
            ):
                # Log progress occasionally
                if progress.total_files > 0 and progress.processed_files % 20 == 0:
                    logger.info(f"[{project.name}] Indexing: {progress.processed_files}/{progress.total_files}")
            
            logger.info(f"✅ Project {project.name} indexing complete.")
            return repo_path
        except Exception as e:
            err_msg = str(e)
            # Detect dimension mismatch or specific embedding API errors that might require a rebuild
            should_rebuild = any(x in err_msg.lower() for x in ["dimension", "404", "401", "400", "invalid_model"])
            
            if not force_rebuild and should_rebuild:
                logger.warning(f"⚠️ Indexing error for project {project.id}: {e}. Triggering automatic full rebuild...")
                return await self._ensure_indexed(project, repo_url, branch, pr_number=pr_number, force_rebuild=True)
                
            logger.error(f"Indexing error for project {project.id}: {e}")
            return None # Fail properly

    async def _get_project_by_repo(self, repo_url: str) -> Optional[Project]:
        stmt = select(Project).where(Project.repository_url == repo_url)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def _prepare_repository(self, project: Project, repo_url: str, branch: str, token: str, pr_number: Optional[int] = None) -> str:
        """
        Clones or Updates the repository locally.
        """
        target_dir = CI_WORKSPACE_DIR / project.id
        
        # 1. Rewrite URL to use configured Host if necessary
        # Gitea might send 'localhost:3000' in payload, but we need settings.GITEA_HOST_URL
        if settings.GITEA_HOST_URL and "://" in repo_url:
            from urllib.parse import urlparse, urlunparse
            payload_url = urlparse(repo_url)
            config_url = urlparse(settings.GITEA_HOST_URL)
            # Use host (and port) from config, keep path from payload
            repo_url = urlunparse((
                config_url.scheme or payload_url.scheme,
                config_url.netloc,
                payload_url.path,
                payload_url.params,
                payload_url.query,
                payload_url.fragment
            ))
            logger.info(f"🔗 Rewrote Clone URL: {repo_url}")

        # 2. Inject Token into URL for auth
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
                
                if pr_number:
                    # Fetch PR ref specifically from base repo: refs/pull/ID/head
                    logger.info(f"📥 Fetching PR ref: refs/pull/{pr_number}/head")
                    subprocess.run(["git", "fetch", "origin", f"refs/pull/{pr_number}/head"], cwd=target_dir, check=True)
                    subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=target_dir, check=True)
                else:
                    # git checkout branch
                    subprocess.run(["git", "checkout", branch], cwd=target_dir, check=True)
                    # git reset --hard origin/branch
                    subprocess.run(["git", "reset", "--hard", f"origin/{branch}"], cwd=target_dir, check=True)
            except Exception as e:
                logger.error(f"Git update failed: {e}. Re-cloning...")
                shutil.rmtree(target_dir) # Nuke and retry
                return await self._prepare_repository(project, repo_url, branch, token, pr_number=pr_number)
        else:
            # Clone
            logger.info(f"📥 Cloning repo to {target_dir}")
            try:
                # Clone without -b first, then fetch and checkout
                subprocess.run(["git", "clone", auth_url, str(target_dir)], check=True)
                
                if pr_number:
                    logger.info(f"📥 Fetching PR ref: refs/pull/{pr_number}/head")
                    subprocess.run(["git", "fetch", "origin", f"refs/pull/{pr_number}/head"], cwd=target_dir, check=True)
                    subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=target_dir, check=True)
                else:
                    subprocess.run(["git", "checkout", branch], cwd=target_dir, check=True)
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
                elif resp.status_code == 403:
                    logger.error(f"❌ Failed to fetch diff: 403 Forbidden. This usually means the GITEA_BOT_TOKEN lacks 'read:repository' scope. Response: {resp.text[:200]}")
                    return ""
                else:
                    logger.error(f"Failed to fetch diff: {resp.status_code} - {resp.text[:200]}")
                    return ""
        except Exception as e:
            logger.error(f"Failed to fetch PR diff: {e}")
            return ""

    async def _get_commit_diff(self, repo_path: str, before: str, after: str) -> str:
        """
        Fetch the diff between two commits using local git command.
        The repository must be already cloned and fetched.
        """
        try:
            # git diff before..after
            cmd = ["git", "diff", f"{before}..{after}"]
            logger.info(f"🛠️ Executing: {' '.join(cmd)} in {repo_path}")
            
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            diff_out = result.stdout
            logger.info(f"📊 Git diff result size: {len(diff_out)} bytes")
            return diff_out
        except subprocess.CalledProcessError as e:
            logger.error(f"Git diff failed: {e.stderr}")
            return ""
        except Exception as e:
            logger.error(f"Failed to fetch commit diff via git: {e}")
            return ""

    async def _is_sha_valid(self, repo_path: str, sha: str) -> bool:
        """
        Check if a given SHA exists in the local repository.
        """
        try:
            subprocess.run(
                ["git", "rev-parse", "--verify", sha],
                cwd=repo_path,
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
        except Exception as e:
            logger.error(f"Error validating SHA {sha}: {e}")
            return False

    async def _get_previous_review_sha(self, project_id: str, pr_number: int) -> Optional[str]:
        """
        Find the commit SHA of the most recent review for this PR.
        This allows us to calculate the 'incremental' diff for a sync event.
        """
        try:
            result = await self.db.execute(
                select(PRReview.commit_sha)
                .where(PRReview.project_id == project_id)
                .where(PRReview.pr_number == pr_number)
                .order_by(PRReview.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error fetching previous review SHA: {e}")
            return None

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

    async def _get_conversation_history(self, repo: Dict, issue_number: int) -> str:
        """
        Fetch the conversation history (comments) from Gitea API
        """
        if not settings.GITEA_HOST_URL or not settings.GITEA_BOT_TOKEN:
            return "无"
            
        api_url = f"{settings.GITEA_HOST_URL}/api/v1/repos/{repo['owner']['login']}/{repo['name']}/issues/{issue_number}/comments"
        headers = {"Authorization": f"token {settings.GITEA_BOT_TOKEN}"}
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(api_url, headers=headers)
                if resp.status_code == 200:
                    comments = resp.json()
                    history_parts = []
                    for c in comments:
                        user = c.get("user", {}).get("username") or c.get("user", {}).get("login") or "未知用户"
                        body = c.get("body", "")
                        history_parts.append(f"{user}: {body}")
                    
                    return "\n".join(history_parts) if history_parts else "无"
                else:
                    logger.error(f"Failed to fetch conversation history: {resp.status_code} - {resp.text[:200]}")
                    return "无"
        except Exception as e:
            logger.error(f"Failed to fetch PR conversation history: {e}")
            return "无"
