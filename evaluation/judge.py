"""DeepEval judge model backed by the project's OpenAI-compatible LLM gateway.

Uses the same LLM_BASE_URL / LLM_API_KEY the agent already uses, so no separate
OpenAI key is required. Credentials come from the environment only.
"""

from __future__ import annotations

import json
from typing import Any

from deepeval.models import DeepEvalBaseLLM
from openai import OpenAI

from eval_utils import extract_json

_JSON_SUFFIX = (
    "\n\nReturn ONLY a single valid JSON object that matches the requested schema. "
    "No markdown fences, no commentary."
)


class GatewayJudge(DeepEvalBaseLLM):
    def __init__(self, model: str, base_url: str, api_key: str, max_parse_retries: int = 2):
        self._model_name = model
        self._client = OpenAI(base_url=base_url or None, api_key=api_key, max_retries=2)
        self._max_parse_retries = max_parse_retries

    def load_model(self) -> Any:
        return self._client

    def get_model_name(self) -> str:
        return self._model_name

    def _complete(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    def generate(self, prompt: str, schema: Any = None) -> Any:
        if schema is None:
            return self._complete(prompt)

        last_err: Exception | None = None
        for _ in range(self._max_parse_retries + 1):
            text = self._complete(prompt + _JSON_SUFFIX)
            try:
                return schema(**extract_json(text))
            except (json.JSONDecodeError, TypeError, ValueError) as err:
                last_err = err
        raise ValueError(f"judge returned unparseable JSON after retries: {last_err}")

    async def a_generate(self, prompt: str, schema: Any = None) -> Any:
        return self.generate(prompt, schema)
