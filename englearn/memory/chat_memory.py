"""Chat memory using Mem0 with AWS Bedrock embeddings and local Qdrant."""
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
            "model": "anthropic.claude-3-haiku-20240307-v1:0",
            "aws_region": "us-east-1",
            "temperature": 0.1,
            "max_tokens": 500,
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


def _get_memory():
    """Lazily initialize Mem0 Memory instance."""
    global _memory, _init_failed
    if _memory is not None:
        return _memory
    if _init_failed:
        return None
    try:
        # Fix Mem0 factory bug: aws_bedrock mapped to BaseLlmConfig instead of AWSBedrockConfig
        from mem0.utils.factory import LlmFactory
        from mem0.configs.llms.aws_bedrock import AWSBedrockConfig
        LlmFactory.provider_to_class["aws_bedrock"] = (
            "mem0.llms.aws_bedrock.AWSBedrockLLM", AWSBedrockConfig
        )
        from mem0 import Memory
        os.makedirs(QDRANT_PATH, exist_ok=True)
        _memory = Memory.from_config(MEM0_CONFIG)
        logger.info("Chat memory initialized (Mem0 + Qdrant)")
        return _memory
    except Exception as e:
        logger.warning(f"Failed to initialize chat memory: {e}")
        _init_failed = True
        return None


def store_message(user_id: str, role_id: str, message: str):
    """Store a user message in the memory vector store."""
    mem = _get_memory()
    if mem is None:
        return
    try:
        mem.add(
            [{"role": "user", "content": message}],
            user_id=user_id,
            metadata={"role": role_id},
            infer=False,
        )
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
            if score > 0.03:
                memories.append(r["memory"])
        return memories
    except Exception as e:
        logger.warning(f"Failed to search memory: {e}")
        return []
