"""
Base agent class. All specialized agents inherit from this.
Provides: model selection, retry logic, token tracking.
"""
import json
import re
from integrations.anthropic_client import chat, MODEL_ROUTER, MODEL_GENERATOR


class BaseAgent:
    model = MODEL_GENERATOR  # subclasses override as needed
    max_tokens = 2048
    temperature = 0.3

    def _call(self, system: str, user: str) -> tuple[str, dict]:
        """Make a single LLM call. Returns (text, usage)."""
        return chat(
            model=self.model,
            system=system,
            user=user,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code fences."""
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try extracting just the JSON object/array
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"Could not parse JSON from response: {text[:300]}")
