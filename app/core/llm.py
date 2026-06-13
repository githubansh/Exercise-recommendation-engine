from abc import ABC, abstractmethod
import json
import re
from typing import Any

from app.core.config import settings


class LLMClient(ABC):
    @abstractmethod
    def chat(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float = 0,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def chat_with_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        max_tool_calls: int = 5,
    ) -> dict[str, Any]:
        raise NotImplementedError


class NullLLMClient(LLMClient):
    def chat(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
    ) -> str:
        raise RuntimeError("No LLM provider is configured.")

    def structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float = 0,
    ) -> dict[str, Any]:
        raise RuntimeError("No LLM provider is configured.")

    def chat_with_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        max_tool_calls: int = 5,
    ) -> dict[str, Any]:
        raise RuntimeError("No LLM provider is configured.")


class GeminiLLMClient(LLMClient):
    def __init__(self, api_key: str, model_name: str) -> None:
        try:
            import google.generativeai as genai
        except Exception as exc:  # pragma: no cover - depends on optional package.
            raise RuntimeError("Install requirements.txt to enable Gemini.") from exc

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)

    def chat(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
    ) -> str:
        prompt = (
            f"{system_prompt}\n\n"
            "Conversation:\n"
            f"{json.dumps(messages, indent=2)}\n\n"
            "Reply as the assistant. Keep it short, helpful, and conversational."
        )
        response = self._model.generate_content(prompt, generation_config={"temperature": temperature})
        return response.text.strip()

    def structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        temperature: float = 0,
    ) -> dict[str, Any]:
        prompt = (
            f"{system_prompt}\n\n"
            "Return only JSON matching this JSON schema. Do not include markdown.\n"
            f"Schema:\n{json.dumps(schema, indent=2)}\n\n"
            f"User text:\n{user_prompt}"
        )
        response = self._model.generate_content(
            prompt,
            generation_config={"temperature": temperature, "response_mime_type": "application/json"},
        )
        return json.loads(extract_json(response.text))

    def chat_with_tools(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        max_tool_calls: int = 5,
    ) -> dict[str, Any]:
        # The app-level coach service owns tool execution and validation. This
        # method returns a suggested action envelope instead of executing tools.
        prompt = (
            f"{system_prompt}\n\n"
            "Choose at most one tool call. Return JSON with keys: "
            "`message` and optional `tool_call` {name, arguments}. "
            "Available tools:\n"
            f"{json.dumps(tools, indent=2)}\n\n"
            f"Conversation:\n{json.dumps(messages, indent=2)}"
        )
        response = self._model.generate_content(
            prompt,
            generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
        )
        return json.loads(extract_json(response.text))


def extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    return stripped


def get_llm_client() -> LLMClient:
    if settings.gemini_api_key:
        return GeminiLLMClient(settings.gemini_api_key, settings.gemini_model)
    return NullLLMClient()
