"""Chat memory using Mem0 with AWS Bedrock (Claude Sonnet 4.5) and local Qdrant."""
import os
import logging

logger = logging.getLogger(__name__)

_memory = None
_init_failed = False

QDRANT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "qdrant")

MEM0_CONFIG = {
    "llm": {
        "provider": "aws_bedrock",
        "config": {
            "model": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "aws_region": "us-east-1",
            "temperature": 0.1,
            "max_tokens": 2000,
        }
    },
    "embedder": {
        "provider": "aws_bedrock",
        "config": {
            "model": "cohere.embed-multilingual-v3",
            "aws_region": "us-east-1",
        }
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "path": QDRANT_PATH,
            "collection_name": "englearn_chat",
            "embedding_model_dims": 1024,
            "on_disk": True,
        }
    }
}


def _apply_mem0_patches():
    """Apply patches for Mem0 bugs with AWS Bedrock.

    Fixes three known issues:
    1. LlmFactory maps aws_bedrock to BaseLlmConfig instead of AWSBedrockConfig
    2. extract_provider returns 'us' for inference profile IDs (us.anthropic.xxx)
    3. Converse API sends both temperature and topP (Claude 4.x rejects this)
    """
    # Fix 1: Factory config class
    from mem0.utils.factory import LlmFactory
    from mem0.configs.llms.aws_bedrock import AWSBedrockConfig
    LlmFactory.provider_to_class["aws_bedrock"] = (
        "mem0.llms.aws_bedrock.AWSBedrockLLM", AWSBedrockConfig
    )

    # Fix 2: extract_provider for cross-region inference profile IDs
    import mem0.llms.aws_bedrock as bedrock_module
    _orig_extract = bedrock_module.extract_provider

    def _fixed_extract(model_id):
        provider = _orig_extract(model_id)
        if provider in ("us", "eu", "global", "ap"):
            parts = model_id.split(".")
            if len(parts) >= 2:
                return parts[1]
        return provider

    bedrock_module.extract_provider = _fixed_extract

    # Fix 3: temperature + topP conflict in Converse API
    from mem0.llms.aws_bedrock import AWSBedrockLLM
    _orig_standard = AWSBedrockLLM._generate_standard

    def _fixed_standard(self, messages, stream=False):
        orig_converse = self.client.converse

        def safe_converse(**kwargs):
            ic = kwargs.get("inferenceConfig", {})
            if "temperature" in ic and "topP" in ic:
                del ic["topP"]
            return orig_converse(**kwargs)

        self.client.converse = safe_converse
        try:
            return _orig_standard(self, messages, stream)
        finally:
            self.client.converse = orig_converse

    AWSBedrockLLM._generate_standard = _fixed_standard


def _get_memory():
    """Lazily initialize Mem0 Memory instance."""
    global _memory, _init_failed
    if _memory is not None:
        return _memory
    if _init_failed:
        return None
    try:
        _apply_mem0_patches()
        from mem0 import Memory
        os.makedirs(QDRANT_PATH, exist_ok=True)
        _memory = Memory.from_config(MEM0_CONFIG)
        logger.info("Chat memory initialized (Mem0 + Claude Sonnet 4.5 + Qdrant)")
        return _memory
    except Exception as e:
        logger.warning(f"Failed to initialize chat memory: {e}")
        _init_failed = True
        return None


def store_message(user_id: str, role_id: str, message: str):
    """Store a user message in memory with LLM fact extraction."""
    mem = _get_memory()
    if mem is None:
        return
    try:
        mem.add(message, user_id=user_id, metadata={"role": role_id})
    except Exception as e:
        logger.warning(f"Failed to store memory: {e}")


def search_memories(user_id: str, query: str, limit: int = 5) -> list:
    """Search for relevant memories by semantic similarity.

    Returns list of memory strings sorted by relevance.
    """
    mem = _get_memory()
    if mem is None:
        return []
    try:
        results = mem.search(query, user_id=user_id, limit=limit)
        memories = []
        for r in results.get("results", []):
            score = r.get("score", 0)
            if score > 0.3:
                memories.append(r["memory"])
        return memories
    except Exception as e:
        logger.warning(f"Failed to search memory: {e}")
        return []
