"""
用户配置API端点
"""

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import json

from app.api import deps
from app.db.session import get_db
from app.models.user_config import UserConfig
from app.models.user import User
from app.core.config import settings
from app.core.encryption import encrypt_sensitive_data, decrypt_sensitive_data

router = APIRouter()

# 需要加密的敏感字段列表 (LLM 已锁定至 .env，此处仅保留其他配置)
SENSITIVE_LLM_FIELDS = [
    'llmApiKey', 'geminiApiKey', 'openaiApiKey', 'claudeApiKey', 
    'qwenApiKey', 'deepseekApiKey', 'zhipuApiKey', 'moonshotApiKey',
    'baiduApiKey', 'minimaxApiKey', 'doubaoApiKey'
]
SENSITIVE_OTHER_FIELDS = ['githubToken', 'gitlabToken']


def mask_api_key(key: Optional[str]) -> str:
    """部分遮盖API Key，显示前3位和后4位"""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}***{key[-4:]}"


def encrypt_config(config: dict, sensitive_fields: list) -> dict:
    """加密配置中的敏感字段"""
    encrypted = config.copy()
    for field in sensitive_fields:
        if field in encrypted and encrypted[field]:
            encrypted[field] = encrypt_sensitive_data(encrypted[field])
    return encrypted


def decrypt_config(config: dict, sensitive_fields: list) -> dict:
    """解密配置中的敏感字段"""
    decrypted = config.copy()
    for field in sensitive_fields:
        if field in decrypted and decrypted[field]:
            decrypted[field] = decrypt_sensitive_data(decrypted[field])
    return decrypted


class LLMConfigSchema(BaseModel):
    """LLM配置Schema"""
    llmProvider: Optional[str] = None
    llmApiKey: Optional[str] = None
    llmModel: Optional[str] = None
    llmBaseUrl: Optional[str] = None
    llmTimeout: Optional[int] = None
    llmTemperature: Optional[float] = None
    llmMaxTokens: Optional[int] = None
    llmCustomHeaders: Optional[str] = None
    
    # 平台专用配置
    geminiApiKey: Optional[str] = None
    openaiApiKey: Optional[str] = None
    claudeApiKey: Optional[str] = None
    qwenApiKey: Optional[str] = None
    deepseekApiKey: Optional[str] = None
    zhipuApiKey: Optional[str] = None
    moonshotApiKey: Optional[str] = None
    baiduApiKey: Optional[str] = None
    minimaxApiKey: Optional[str] = None
    doubaoApiKey: Optional[str] = None
    ollamaBaseUrl: Optional[str] = None


class OtherConfigSchema(BaseModel):
    """其他配置Schema"""
    githubToken: Optional[str] = None
    gitlabToken: Optional[str] = None
    maxAnalyzeFiles: Optional[int] = None
    llmConcurrency: Optional[int] = None
    llmGapMs: Optional[int] = None
    outputLanguage: Optional[str] = None


class UserConfigRequest(BaseModel):
    """用户配置请求"""
    llmConfig: Optional[LLMConfigSchema] = None
    otherConfig: Optional[OtherConfigSchema] = None


class UserConfigResponse(BaseModel):
    """用户配置响应"""
    id: str
    user_id: str
    llmConfig: dict
    otherConfig: dict
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


def get_default_config() -> dict:
    """获取系统默认配置"""
    return {
        "llmConfig": {
            "llmProvider": settings.LLM_PROVIDER,
            "llmApiKey": mask_api_key(settings.LLM_API_KEY),
            "llmModel": settings.LLM_MODEL or "",
            "llmBaseUrl": settings.LLM_BASE_URL or "",
            "llmTimeout": settings.LLM_TIMEOUT * 1000,  # 转换为毫秒
            "llmTemperature": settings.LLM_TEMPERATURE,
            "llmMaxTokens": settings.LLM_MAX_TOKENS,
            "llmCustomHeaders": "",
            "geminiApiKey": mask_api_key(settings.GEMINI_API_KEY),
            "openaiApiKey": mask_api_key(settings.OPENAI_API_KEY),
            "claudeApiKey": mask_api_key(settings.CLAUDE_API_KEY),
            "qwenApiKey": mask_api_key(settings.QWEN_API_KEY),
            "deepseekApiKey": mask_api_key(settings.DEEPSEEK_API_KEY),
            "zhipuApiKey": mask_api_key(settings.ZHIPU_API_KEY),
            "moonshotApiKey": mask_api_key(settings.MOONSHOT_API_KEY),
            "baiduApiKey": mask_api_key(settings.BAIDU_API_KEY),
            "minimaxApiKey": mask_api_key(settings.MINIMAX_API_KEY),
            "doubaoApiKey": mask_api_key(settings.DOUBAO_API_KEY),
            "ollamaBaseUrl": settings.OLLAMA_BASE_URL or "http://localhost:11434/v1",
        },
        "otherConfig": {
            "githubToken": settings.GITHUB_TOKEN or "",
            "gitlabToken": settings.GITLAB_TOKEN or "",
            "maxAnalyzeFiles": settings.MAX_ANALYZE_FILES,
            "llmConcurrency": settings.LLM_CONCURRENCY,
            "llmGapMs": settings.LLM_GAP_MS,
            "outputLanguage": settings.OUTPUT_LANGUAGE,
        }
    }


@router.get("/defaults")
async def get_default_config_endpoint() -> Any:
    """获取系统默认配置（无需认证）"""
    return get_default_config()


@router.get("/me", response_model=UserConfigResponse)
async def get_my_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """获取当前用户的配置（合并用户配置和系统默认配置）"""
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    
    # 获取系统默认配置
    default_config = get_default_config()
    
    if not config:
        print(f"[Config] 用户 {current_user.id} 没有保存的配置，返回默认配置")
        # 返回系统默认配置
        return UserConfigResponse(
            id="",
            user_id=current_user.id,
            llmConfig=default_config["llmConfig"],
            otherConfig=default_config["otherConfig"],
            created_at="",
        )
    
    # 合并用户配置和默认配置（用户配置优先）
    user_llm_config = json.loads(config.llm_config) if config.llm_config else {}
    user_other_config = json.loads(config.other_config) if config.other_config else {}
    
    # 解密敏感字段
    user_llm_config = decrypt_config(user_llm_config, SENSITIVE_LLM_FIELDS)
    user_other_config = decrypt_config(user_other_config, SENSITIVE_OTHER_FIELDS)
    
    print(f"[Config] 用户 {current_user.id} 的保存配置:")
    print(f"  - llmProvider: {user_llm_config.get('llmProvider')}")
    print(f"  - llmApiKey: {'***' + user_llm_config.get('llmApiKey', '')[-4:] if user_llm_config.get('llmApiKey') else '(空)'}")
    print(f"  - llmModel: {user_llm_config.get('llmModel')}")
    
    # LLM配置始终来自系统默认（.env），不再允许用户覆盖
    merged_llm_config = default_config["llmConfig"]
    merged_other_config = {**default_config["otherConfig"], **user_other_config}
    
    return UserConfigResponse(
        id=config.id,
        user_id=config.user_id,
        llmConfig=merged_llm_config,
        otherConfig=merged_other_config,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.put("/me", response_model=UserConfigResponse)
async def update_my_config(
    config_in: UserConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """更新当前用户的配置"""
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    
    # 准备要保存的配置数据（加密敏感字段）
    llm_data = config_in.llmConfig.dict(exclude_none=True) if config_in.llmConfig else {}
    other_data = config_in.otherConfig.dict(exclude_none=True) if config_in.otherConfig else {}
    
    # 加密敏感字段
    llm_data_encrypted = encrypt_config(llm_data, SENSITIVE_LLM_FIELDS)
    other_data_encrypted = encrypt_config(other_data, SENSITIVE_OTHER_FIELDS)
    
    if not config:
        # 创建新配置
        config = UserConfig(
            user_id=current_user.id,
            llm_config=json.dumps(llm_data_encrypted),
            other_config=json.dumps(other_data_encrypted),
        )
        db.add(config)
    else:
        # 更新现有配置
        if config_in.llmConfig:
            existing_llm = json.loads(config.llm_config) if config.llm_config else {}
            # 先解密现有数据，再合并新数据，最后加密
            existing_llm = decrypt_config(existing_llm, SENSITIVE_LLM_FIELDS)
            existing_llm.update(llm_data)  # 使用未加密的新数据合并
            config.llm_config = json.dumps(encrypt_config(existing_llm, SENSITIVE_LLM_FIELDS))
        
        if config_in.otherConfig:
            existing_other = json.loads(config.other_config) if config.other_config else {}
            # 先解密现有数据，再合并新数据，最后加密
            existing_other = decrypt_config(existing_other, SENSITIVE_OTHER_FIELDS)
            existing_other.update(other_data)  # 使用未加密的新数据合并
            config.other_config = json.dumps(encrypt_config(existing_other, SENSITIVE_OTHER_FIELDS))
    
    await db.commit()
    await db.refresh(config)
    
    # 获取系统默认配置并合并（与 get_my_config 保持一致）
    default_config = get_default_config()
    user_llm_config = json.loads(config.llm_config) if config.llm_config else {}
    user_other_config = json.loads(config.other_config) if config.other_config else {}
    
    # 解密后返回给前端
    user_llm_config = decrypt_config(user_llm_config, SENSITIVE_LLM_FIELDS)
    user_other_config = decrypt_config(user_other_config, SENSITIVE_OTHER_FIELDS)
    
    # LLM配置始终来自系统默认（.env），不再允许用户覆盖
    merged_llm_config = default_config["llmConfig"]
    merged_other_config = {**default_config["otherConfig"], **user_other_config}
    
    return UserConfigResponse(
        id=config.id,
        user_id=config.user_id,
        llmConfig=merged_llm_config,
        otherConfig=merged_other_config,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.delete("/me")
async def delete_my_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """删除当前用户的配置（恢复为默认）"""
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    
    if config:
        await db.delete(config)
        await db.commit()
    
    return {"message": "配置已删除"}


class LLMTestRequest(BaseModel):
    """LLM测试请求"""
    provider: str
    apiKey: str
    model: Optional[str] = None
    baseUrl: Optional[str] = None


class LLMTestResponse(BaseModel):
    """LLM测试响应"""
    success: bool
    message: str
    model: Optional[str] = None
    response: Optional[str] = None
    # 调试信息
    debug: Optional[dict] = None


@router.post("/test-llm", response_model=LLMTestResponse)
async def test_llm_connection(
    request: LLMTestRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """测试当前系统 LLM 配置是否正常"""
    from app.services.llm.service import LLMService
    import time
    import traceback

    start_time = time.time()
    
    try:
        # LLMService 已经重构为锁定读取 .env 配置
        llm_service = LLMService()
        
        # 记录测试信息
        print(f"🔍 测试 LLM 连接: Provider={llm_service.config.provider}, Model={llm_service.config.model}")
        
        # 简单测试：获取分析结果
        test_code = "print('hello world')"
        result = await llm_service.analyze_code(test_code, "python")
        
        duration = round(time.time() - start_time, 2)
        
        return LLMTestResponse(
            success=True,
            message=f"连接成功！耗时: {duration}s",
            model=llm_service.config.model,
            response="分析测试完成",
            debug={
                "provider": llm_service.config.provider.value,
                "model": llm_service.config.model,
                "duration_s": duration,
                "issues_found": len(result.get("issues", []))
            }
        )
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        error_msg = str(e)
        print(f"❌ LLM 测试失败: {error_msg}")
        return LLMTestResponse(
            success=False,
            message=f"连接失败: {error_msg}",
            debug={
                "error": error_msg,
                "traceback": traceback.format_exc(),
                "duration_s": duration
            }
        )


@router.get("/llm-providers")
async def get_llm_providers() -> Any:
    """获取支持的LLM提供商列表"""
    from app.services.llm.factory import LLMFactory
    from app.services.llm.types import LLMProvider, DEFAULT_BASE_URLS
    
    providers = []
    for provider in LLMFactory.get_supported_providers():
        providers.append({
            "id": provider.value,
            "name": provider.value.upper(),
            "defaultModel": LLMFactory.get_default_model(provider),
            "models": LLMFactory.get_available_models(provider),
            "defaultBaseUrl": DEFAULT_BASE_URLS.get(provider, ""),
        })
    
    return {"providers": providers}

