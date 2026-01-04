from fastapi import APIRouter, Header, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
import hmac
import hashlib
import logging
import json

from app.api.deps import get_db
from app.db.session import AsyncSessionLocal
from app.core.config import settings
from app.services.ci_service import CIService

router = APIRouter()
logger = logging.getLogger(__name__)

async def process_gitea_event(event_type: str, payload: dict):
    """
    Background task to process Gitea events without blocking the webhook response.
    """
    async with AsyncSessionLocal() as db:
        try:
            ci_service = CIService(db)
            if event_type == "pull_request":
                action = payload.get("action")
                if action in ["opened", "synchronized", "reopened"]:
                    logger.info(f"Starting background PR processing for action: {action}")
                    await ci_service.handle_pr_event(payload)
                else:
                    logger.info(f"Ignoring PR Action in background: {action}")
            elif event_type == "issue_comment":
                logger.info(f"Starting background comment processing")
                await ci_service.handle_comment_event(payload)
        except Exception as e:
            logger.error(f"Background Webhook Processing Error: {e}", exc_info=True)

@router.get("/health")
async def webhook_health():
    return {"status": "ok", "module": "webhooks"}

@router.post("/gitea")
async def handle_gitea_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_gitea_signature: str = Header(None),
    x_gitea_event: str = Header(None),
):
    """
    Handle incoming Gitea webhook events with background processing to prevent timeouts.
    """
    # 1. Capture Raw Body for Signature Verification
    payload_bytes = await request.body()
    
    # 2. Verify Signature
    if settings.GITEA_WEBHOOK_SECRET:
        if not x_gitea_signature:
            logger.warning("Missing Gitea Signature")
            raise HTTPException(status_code=401, detail="Missing Signature")
        
        computed_signature = hmac.new(
            key=settings.GITEA_WEBHOOK_SECRET.encode(),
            msg=payload_bytes,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(computed_signature, x_gitea_signature):
            logger.warning(f"Invalid Gitea Signature. Expected: {computed_signature}, Got: {x_gitea_signature}")
            raise HTTPException(status_code=401, detail="Invalid Signature")

    # 3. Parse Payload
    try:
        payload = json.loads(payload_bytes.decode())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 4. Enqueue Background Task
    logger.info(f"Enqueuing Gitea Event for background processing: {x_gitea_event}")
    background_tasks.add_task(process_gitea_event, x_gitea_event, payload)
    
    # 5. Return Success Immediately
    return {"status": "accepted", "event": x_gitea_event, "message": "Task enqueued"}
