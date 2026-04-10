"""
Sales / Marketing Agent — generates customer-facing proposals, follow-ups, and messages.
"""
from pathlib import Path
from agents.base_agent import BaseAgent
from integrations.anthropic_client import MODEL_GENERATOR
from models.estimate_models import Estimate

PROMPT_DIR = Path(__file__).parent.parent / "templates" / "system_prompts"


def _load_sales_prompt() -> str:
    path = PROMPT_DIR / "sales.txt"
    return path.read_text() if path.exists() else "You are a roofing sales specialist."


class SalesAgent(BaseAgent):
    model = MODEL_GENERATOR
    max_tokens = 1200
    temperature = 0.5   # slightly more creative for sales copy

    def generate(
        self,
        brain_dump: str,
        intent: str = "sales_proposal",
        estimate: Estimate | None = None,
        customer_name: str | None = None,
    ) -> tuple[str, dict]:
        """
        Generate a sales document (proposal, follow-up, customer message).
        Returns (document_text, usage_dict).
        """
        system_prompt = _load_sales_prompt()

        estimate_context = ""
        if estimate and estimate.products:
            lines = ["\nEstimate Summary:"]
            for pe in estimate.products:
                lines.append(f"  - {pe.manufacturer} {pe.product_line}: ${pe.subtotal_materials:,.2f}")
            estimate_context = "\n".join(lines)

        intent_instruction = {
            "sales_proposal": "Write a complete sales proposal letter for the homeowner.",
            "follow_up": "Write a friendly but professional follow-up message to the homeowner.",
            "customer_message": "Write a clear, helpful message to the homeowner.",
        }.get(intent, "Write a professional document for the homeowner.")

        user_message = f"""{intent_instruction}

CONTEXT:
{brain_dump}
{estimate_context}

Customer name: {customer_name or 'the homeowner'}

Include a clear call to action at the end."""

        text, usage = self._call(system_prompt, user_message)
        return text.strip(), usage
