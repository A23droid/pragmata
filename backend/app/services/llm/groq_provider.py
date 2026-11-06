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
        import types
        from enum import Enum
        from typing import get_args, get_origin

        fields = schema.model_fields
        stub_data = {}
        for name, field in fields.items():
            if not field.is_required() and field.default is not None and field.default is not ...:
                continue

            ann = field.annotation
            origin = get_origin(ann)
            args = get_args(ann)

            # Unwrap Optional[X] / Union[X, None]
            if origin is types.UnionType or origin is getattr(types, "Union", None) or str(origin) == "typing.Union":
                non_none = [a for a in args if a is not type(None)]
                if non_none:
                    ann = non_none[0]
                    origin = get_origin(ann)
                    args = get_args(ann)

            if isinstance(ann, type) and issubclass(ann, Enum):
                stub_data[name] = list(ann)[0].value
            elif isinstance(ann, type) and issubclass(ann, BaseModel):
                stub_data[name] = self._build_stub_for_schema(ann)
            elif ann == str:
                stub_data[name] = f"Test {name}"
            elif ann == int:
                stub_data[name] = 1
            elif ann == float:
                stub_data[name] = 0.95
            elif ann == bool:
                stub_data[name] = True
            elif origin == list or ann == list:
                item_cls = args[0] if args else None
                min_len = 0
                for meta in getattr(field, "metadata", []):
                    if hasattr(meta, "min_length") and meta.min_length:
                        min_len = meta.min_length

                count = max(min_len, 2 if (item_cls and isinstance(item_cls, type) and issubclass(item_cls, BaseModel)) else (1 if min_len > 0 else 0))
                if count > 0 and item_cls:
                    items = []
                    for idx in range(count):
                        if isinstance(item_cls, type) and issubclass(item_cls, BaseModel):
                            items.append(self._build_stub_for_schema(item_cls))
                        elif item_cls == str:
                            items.append(f"sample_{name}_{idx}")
                        else:
                            items.append(None)
                    stub_data[name] = items
                else:
                    stub_data[name] = []
            elif origin == dict or ann == dict:
                stub_data[name] = {}
            else:
                stub_data[name] = None
        try:
            return schema.model_validate(stub_data)
        except ValidationError:
            return schema.model_construct(**stub_data)

