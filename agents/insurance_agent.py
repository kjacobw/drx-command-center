"""
Insurance Communication Agent — generates carrier-specific letters and claim updates.
Loads carrier config JSON to overlay tone/style on the base insurance system prompt.
"""
import json
import os
from pathlib import Path
from agents.base_agent import BaseAgent
from integrations.anthropic_client import MODEL_GENERATOR
from models.roofr_models import RoofrReport

CARRIER_DIR = Path(__file__).parent.parent / "templates" / "carriers"
PROMPT_DIR = Path(__file__).parent.parent / "templates" / "system_prompts"

CARRIER_MAP = {
    "security_first": "security_first.json",
    "sfi": "security_first.json",
    "security first": "security_first.json",
    "american_integrity": "american_integrity.json",
    "aii": "american_integrity.json",
    "american integrity": "american_integrity.json",
}


def _load_carrier(carrier_key: str) -> dict | None:
    filename = CARRIER_MAP.get(carrier_key.lower().replace(" ", "_"))
    if not filename:
        return None
    path = CARRIER_DIR / filename
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _load_base_prompt() -> str:
    path = PROMPT_DIR / "insurance_base.txt"
    return path.read_text() if path.exists() else ""


def _build_system_prompt(carrier: dict | None) -> str:
    base = _load_base_prompt()
    if not carrier:
        return base
    overlay = carrier.get("system_prompt_overlay", "")
    tone = carrier.get("tone", {})
    avoid = tone.get("avoid_phrases", [])
    avoid_line = f"\nNEVER use these phrases: {', '.join(repr(p) for p in avoid)}" if avoid else ""
    return f"{base}\n\n--- CARRIER-SPECIFIC INSTRUCTIONS ({carrier['carrier_name']}) ---\n{overlay}{avoid_line}"


def _build_signature_block(carrier: dict | None) -> str:
    company = os.getenv("COMPANY_NAME", "DRX Roofing & General Contracting")
    license_num = os.getenv("COMPANY_LICENSE", "FL CGC#______")
    phone = os.getenv("COMPANY_PHONE", "")
    email = os.getenv("COMPANY_EMAIL", "")

    lines = ["", "Sincerely,", "", company]
    if license_num:
        lines.append(license_num)
    if phone:
        lines.append(phone)
    if email:
        lines.append(email)

    if carrier:
        sig_block = carrier.get("signature_block", {})
        if sig_block.get("include_preferred_vendor_status"):
            preferred_text = sig_block.get("preferred_vendor_text", "Preferred Contractor")
            lines.append(preferred_text)

    return "\n".join(lines)


class InsuranceAgent(BaseAgent):
    model = MODEL_GENERATOR
    max_tokens = 1500
    temperature = 0.3

    def write_letter(
        self,
        brain_dump: str,
        carrier_key: str | None,
        report: RoofrReport | None = None,
        claim_number: str | None = None,
        property_address: str | None = None,
        intent: str = "insurance_letter",
    ) -> tuple[str, dict]:
        """
        Generate a carrier-appropriate insurance letter or claim update.
        Returns (letter_text, usage_dict).
        """
        carrier = _load_carrier(carrier_key) if carrier_key else None
        system_prompt = _build_system_prompt(carrier)
        signature = _build_signature_block(carrier)

        # Build user message
        tone = carrier.get("tone", {}) if carrier else {}
        salutation = tone.get("salutation", "Dear Claims Department,")
        opener_template = tone.get("preferred_opener", "")
        opener = opener_template.format(
            property_address=property_address or report.property_address if report else "{property_address}",
            claim_number=claim_number or "{claim_number}",
        ) if opener_template else ""

        required_docs = ""
        if carrier and carrier.get("required_documentation"):
            docs = carrier["required_documentation"]
            required_docs = "\n\nRequired documentation for this carrier:\n" + "\n".join(f"- {d}" for d in docs)

        measurement_summary = ""
        if report and report.total_squares:
            measurement_summary = f"\n\nRoof measurement data (Roofr report):\n{report.summary_text()}"

        user_message = f"""Write a {intent.replace('_', ' ')} based on the following information:

USER CONTEXT:
{brain_dump}

LETTER DETAILS:
- Salutation: {salutation}
- Preferred opening: {opener}
- Claim number: {claim_number or 'See context above'}
- Property: {property_address or (report.property_address if report else 'See context above')}
{measurement_summary}{required_docs}

SIGNATURE BLOCK TO USE AT THE END:
{signature}

Write the complete letter, ready to send. Include the date line at the top."""

        text, usage = self._call(system_prompt, user_message)
        return text.strip(), usage
