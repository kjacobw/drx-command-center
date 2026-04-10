"""
Shared Anthropic SDK wrapper.
Centralizes model selection and provides a simple messages helper.
"""
import os
from anthropic import Anthropic

# Model constants — change here to update everywhere
MODEL_ROUTER = "claude-haiku-4-5-20251001"      # cheap, fast — routing/classification
MODEL_GENERATOR = "claude-sonnet-4-6"            # capable — document generation

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
        _client = Anthropic(api_key=api_key)
    return _client


def chat(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> tuple[str, dict]:
    """
    Simple blocking chat call.
    Returns (response_text, usage_dict).
    """
    client = get_client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = response.content[0].text if response.content else ""
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model": model,
    }
    return text, usage
