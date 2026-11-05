import json
import logging
from typing import Optional, Type, TypeVar
import httpx
from pydantic import BaseModel, ValidationError

from backend.app.core.config import settings
from backend.app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GroqProvider(LLMProvider):
    """
    Groq provider implementation supporting fast reasoning models (e.g. LLaMA 3.3 70B).
    Handles structured JSON generation and error handling with graceful fallback.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: str = "https://api.groq.com/openai/v1",
    ):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        self.base_url = base_url.rstrip("/")

    async def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        if not self.api_key:
            logger.warning("No GROQ_API_KEY set. Returning deterministic development response.")
            return f"[Dev Mode Mock response for: {prompt[:80]}]"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
            return data["choices"][0]["message"]["content"]

    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
    ) -> T:
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        augmented_system = (
            (system_instruction or "You are an expert AI software engineer.")
            + f"\n\nCRITICAL: You MUST respond strictly with a valid JSON object matching this schema:\n{schema_json}\n"
            + "Output ONLY the raw JSON object, no markdown codeblocks, no explanations."
        )

        if not self.api_key:
            # Deterministic mock generation for offline/test environments
            logger.info(f"Generating stub instance for schema: {schema.__name__}")
            return self._build_stub_for_schema(schema)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = [
            {"role": "system", "content": augmented_system},
            {"role": "user", "content": prompt},
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
            raw_content = data["choices"][0]["message"]["content"]
            parsed = json.loads(raw_content)
            return schema.model_validate(parsed)

    def _build_stub_for_schema(self, schema: Type[T]) -> T:
        """Create a minimally valid stub instance for testing when offline."""
        fields = schema.model_fields
        stub_data = {}
        for name, field in fields.items():
            if field.annotation == str:
                stub_data[name] = f"Test {name}"
            elif field.annotation == int:
                stub_data[name] = 1
            elif field.annotation == float:
                stub_data[name] = 0.95
            elif field.annotation == bool:
                stub_data[name] = True
            elif getattr(field.annotation, "__origin__", None) == list:
                stub_data[name] = []
            elif getattr(field.annotation, "__origin__", None) == dict:
                stub_data[name] = {}
            else:
                stub_data[name] = None
        try:
            return schema.model_validate(stub_data)
        except ValidationError:
            # Fallback if defaults suffice
            return schema.model_construct(**stub_data)

