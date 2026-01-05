"""
嵌入模型配置 API
独立于 LLM 配置，专门用于 RAG 系统的嵌入模型
使用 UserConfig.other_config 持久化存储
"""

import json
import uuid
from typing import Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api import deps
from app.models.user import User
from app.models.user_config import UserConfig
from app.core.config import settings

router = APIRouter()


# ============ Schemas ============

class EmbeddingProvider(BaseModel):
    """嵌入模型提供商"""
    id: str
    name: str
    description: str
    models: List[str]
    requires_api_key: bool
    default_model: str


class EmbeddingConfig(BaseModel):
    """嵌入模型配置"""
    provider: str = Field(description="提供商: openai, ollama, azure, cohere, huggingface, jina, qwen")
    model: str = Field(description="模型名称")
    api_key: Optional[str] = Field(default=None, description="API Key (如需要)")
    base_url: Optional[str] = Field(default=None, description="自定义 API 端点")
    dimensions: Optional[int] = Field(default=None, description="向量维度 (某些模型支持)")
    batch_size: int = Field(default=100, description="批处理大小")


class EmbeddingConfigResponse(BaseModel):
    """配置响应"""
    provider: str
    model: str
    api_key: Optional[str] = None  # 返回 API Key
    base_url: Optional[str]
    dimensions: int
    batch_size: int


class TestEmbeddingRequest(BaseModel):
    """测试嵌入请求"""
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    test_text: str = "这是一段测试文本，用于验证嵌入模型是否正常工作。"


class TestEmbeddingResponse(BaseModel):
    """测试嵌入响应"""
    success: bool
    message: str
    dimensions: Optional[int] = None
    sample_embedding: Optional[List[float]] = None  # 前 5 个维度
    latency_ms: Optional[int] = None


# ============ 提供商配置 ============

EMBEDDING_PROVIDERS: List[EmbeddingProvider] = [
    EmbeddingProvider(
        id="openai",
        name="OpenAI (兼容 DeepSeek/Moonshot/智谱 等)",
        description="OpenAI 官方或兼容 API，填写自定义端点可接入其他服务商",
        models=[
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-embedding-ada-002",
        ],
        requires_api_key=True,
        default_model="text-embedding-3-small",
    ),
    EmbeddingProvider(
        id="azure",
        name="Azure OpenAI",
        description="Azure 托管的 OpenAI 嵌入模型",
        models=[
            "text-embedding-3-small",
            "text-embedding-3-large",
            "text-embedding-ada-002",
        ],
        requires_api_key=True,
        default_model="text-embedding-3-small",
    ),
    EmbeddingProvider(
        id="ollama",
        name="Ollama (本地)",
        description="本地运行的开源嵌入模型 (使用 /api/embed 端点)",
        models=[
            "nomic-embed-text",
            "mxbai-embed-large",
            "all-minilm",
            "snowflake-arctic-embed",
            "bge-m3",
            "qwen3-embedding",
        ],
        requires_api_key=False,
        default_model="nomic-embed-text",
    ),
    EmbeddingProvider(
        id="cohere",
        name="Cohere",
        description="Cohere Embed v2 API (api.cohere.com/v2)",
        models=[
            "embed-english-v3.0",
            "embed-multilingual-v3.0",
            "embed-english-light-v3.0",
            "embed-multilingual-light-v3.0",
            "embed-v4.0",
        ],
        requires_api_key=True,
        default_model="embed-multilingual-v3.0",
    ),
    EmbeddingProvider(
        id="huggingface",
        name="HuggingFace",
        description="HuggingFace Inference Providers (router.huggingface.co)",
        models=[
            "sentence-transformers/all-MiniLM-L6-v2",
            "sentence-transformers/all-mpnet-base-v2",
            "BAAI/bge-large-zh-v1.5",
            "BAAI/bge-m3",
        ],
        requires_api_key=True,
        default_model="BAAI/bge-m3",
    ),
    EmbeddingProvider(
        id="jina",
        name="Jina AI",
        description="Jina AI 嵌入模型，代码嵌入效果好",
        models=[
            "jina-embeddings-v2-base-code",
            "jina-embeddings-v2-base-en",
            "jina-embeddings-v2-base-zh",
        ],
        requires_api_key=True,
        default_model="jina-embeddings-v2-base-code",
    ),
    EmbeddingProvider(
        id="qwen",
        name="Qwen (DashScope)",
        description="阿里云 DashScope Qwen 嵌入模型，兼容 OpenAI embeddings 接口",
        models=[
            "text-embedding-v4",
            "text-embedding-v3",
            "text-embedding-v2",
        ],
        requires_api_key=True,
        default_model="text-embedding-v4",
    ),
]


# ============ 数据库持久化存储 (异步) ============

EMBEDDING_CONFIG_KEY = "embedding_config"


def mask_api_key(key: Optional[str]) -> str:
    """部分遮盖API Key，显示前3位和后4位"""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}***{key[-4:]}"


async def get_embedding_config_from_db(db: AsyncSession, user_id: str) -> EmbeddingConfig:
    """从数据库获取嵌入配置（异步）"""
    # 嵌入配置始终来自系统默认（.env），不再允许用户覆盖
    print(f"[EmbeddingConfig] 返回系统默认嵌入配置（来自 .env）")
    return EmbeddingConfig(
        provider=settings.EMBEDDING_PROVIDER,
        model=settings.EMBEDDING_MODEL,
        api_key=mask_api_key(settings.EMBEDDING_API_KEY or settings.LLM_API_KEY),
        base_url=settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL,
        dimensions=settings.EMBEDDING_DIMENSION if settings.EMBEDDING_DIMENSION > 0 else None,
        batch_size=100,
    )




# ============ API Endpoints ============

@router.get("/providers", response_model=List[EmbeddingProvider])
async def list_embedding_providers(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取可用的嵌入模型提供商列表
    """
    return EMBEDDING_PROVIDERS


@router.get("/config", response_model=EmbeddingConfigResponse)
async def get_current_config(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取当前嵌入模型配置（从数据库读取）
    """
    config = await get_embedding_config_from_db(db, current_user.id)

    # 获取维度
    dimensions = config.dimensions
    if not dimensions or dimensions <= 0:
        dimensions = _get_model_dimensions(config.provider, config.model)

    return EmbeddingConfigResponse(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        dimensions=dimensions,
        batch_size=config.batch_size,
    )


@router.put("/config")
async def update_config(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    更新嵌入模型配置（已禁用，固定从 .env 读取）
    """
    return {"message": "嵌入模型配置已锁定，请在 .env 文件中进行修改", "provider": settings.EMBEDDING_PROVIDER, "model": settings.EMBEDDING_MODEL}


@router.post("/test", response_model=TestEmbeddingResponse)
async def test_embedding(
    request: TestEmbeddingRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """测试当前系统的嵌入模型配置"""
    import time
    from app.services.rag.embeddings import EmbeddingService
    
    try:
        start_time = time.time()
        
        # 始终使用系统的真实配置进行测试
        # API Key 优先级：EMBEDDING_API_KEY > LLM_API_KEY
        api_key = getattr(settings, "EMBEDDING_API_KEY", None) or settings.LLM_API_KEY
        
        service = EmbeddingService(
            provider=settings.EMBEDDING_PROVIDER,
            model=settings.EMBEDDING_MODEL,
            api_key=api_key,
            base_url=settings.EMBEDDING_BASE_URL,
            cache_enabled=False,
        )
        
        # 执行嵌入
        embedding = await service.embed(request.test_text)
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return TestEmbeddingResponse(
            success=True,
            message=f"嵌入成功! 提供商: {settings.EMBEDDING_PROVIDER}, 维度: {len(embedding)}",
            dimensions=len(embedding),
            sample_embedding=embedding[:5],  # 返回前 5 维
            latency_ms=latency_ms,
        )
        
    except Exception as e:
        print(f"❌ 嵌入测试失败: {str(e)}")
        return TestEmbeddingResponse(
            success=False,
            message=f"嵌入失败: {str(e)}",
        )


@router.get("/models/{provider}")
async def get_provider_models(
    provider: str,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取指定提供商的模型列表
    """
    provider_info = next((p for p in EMBEDDING_PROVIDERS if p.id == provider), None)
    
    if not provider_info:
        raise HTTPException(status_code=404, detail=f"提供商不存在: {provider}")
    
    return {
        "provider": provider,
        "models": provider_info.models,
        "default_model": provider_info.default_model,
        "requires_api_key": provider_info.requires_api_key,
    }


def _get_model_dimensions(provider: str, model: str) -> int:
    """获取模型维度"""
    dimensions_map = {
        # OpenAI
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
        
        # Ollama
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        "all-minilm": 384,
        "snowflake-arctic-embed": 1024,
        
        # Cohere
        "embed-english-v3.0": 1024,
        "embed-multilingual-v3.0": 1024,
        "embed-english-light-v3.0": 384,
        "embed-multilingual-light-v3.0": 384,
        
        # HuggingFace
        "sentence-transformers/all-MiniLM-L6-v2": 384,
        "sentence-transformers/all-mpnet-base-v2": 768,
        "BAAI/bge-large-zh-v1.5": 1024,
        "BAAI/bge-m3": 1024,
        
        # Jina
        "jina-embeddings-v2-base-code": 768,
        "jina-embeddings-v2-base-en": 768,
        "jina-embeddings-v2-base-zh": 768,
        
        # Qwen (DashScope)
        "text-embedding-v4": 1024,  # 支持维度: 2048, 1536, 1024(默认), 768, 512, 256, 128, 64
        "text-embedding-v3": 1024,  # 支持维度: 1024(默认), 768, 512, 256, 128, 64
        "text-embedding-v2": 1536,  # 支持维度: 1536
    }
    
    return dimensions_map.get(model, 768)

