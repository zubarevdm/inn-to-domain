"""LLM-слой: клиент GigaChat и промпты."""
from .gigachat import GigaChatClient, GigaChatError, parse_json_object
from .prompts import SYSTEM_PROMPT, build_user_prompt

__all__ = [
    "GigaChatClient",
    "GigaChatError",
    "parse_json_object",
    "SYSTEM_PROMPT",
    "build_user_prompt",
]
