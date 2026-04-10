"""
Router Agent — uses claude-haiku for cheap, fast intent classification.
Takes the brain dump text and returns a RouterOutput JSON object.
"""
from agents.base_agent import BaseAgent
from integrations.anthropic_client import MODEL_ROUTER
from models.request_models import RouterOutput


SYSTEM_PROMPT = """You are a routing assistant for a roofing and general contracting business.
Your ONLY job is to analyze a brain dump message and extract structured intent data as JSON.

Output ONLY valid JSON matching this exact schema:
{
  "intents": [],          // array of strings from: "estimate", "insurance_letter", "claim_update", "jobtread_read", "jobtread_write", "sales_proposal", "follow_up"
  "carrier": null,        // "security_first" or "american_integrity" (null if not mentioned)
  "job_id": null,         // JobTread job ID if mentioned (e.g. "JT-1234")
  "job_name": null,       // customer or job name if mentioned
  "claim_number": null,   // insurance claim number if mentioned
  "products_requested": [], // product names mentioned (e.g. ["GAF Timberline HDZ", "OC Duration"])
  "property_address": null, // property address if mentioned
  "customer_name": null,  // customer name if mentioned
  "urgency": "normal",    // "urgent" if user says rush/urgent/ASAP, else "normal"
  "extracted_context": {} // any other useful facts as key-value pairs
}

Intent definitions:
- estimate: user wants a material cost estimate or price quote
- insurance_letter: user wants a formal letter to an insurance carrier
- claim_update: user wants a claim status update or progress note
- jobtread_read: user wants to look up or read a job from JobTread
- jobtread_write: user wants to add a note or update a job in JobTread
- sales_proposal: user wants a sales proposal or bid for a customer
- follow_up: user wants a follow-up email or message to a customer

Carrier detection:
- "Security First", "SFI", "Security First Financial" → "security_first"
- "American Integrity", "AII", "American Integrity Insurance" → "american_integrity"

Output ONLY the JSON object. No explanation, no preamble."""


class RouterAgent(BaseAgent):
    model = MODEL_ROUTER
    max_tokens = 512
    temperature = 0.0   # deterministic classification

    def route(self, brain_dump: str, has_pdf: bool = False) -> tuple[RouterOutput, dict]:
        """
        Classify the brain dump and return a RouterOutput.
        Returns (RouterOutput, usage_dict).
        """
        context = brain_dump
        if has_pdf:
            context = "[USER ATTACHED A ROOFR PDF MEASUREMENT REPORT]\n\n" + context

        text, usage = self._call(SYSTEM_PROMPT, context)

        try:
            data = self._parse_json(text)
            # Ensure estimate intent is added if PDF was attached and no intents found
            if has_pdf and not data.get("intents"):
                data["intents"] = ["estimate"]
            elif has_pdf and "estimate" not in data.get("intents", []):
                data["intents"] = ["estimate"] + data.get("intents", [])
            return RouterOutput(**data), usage
        except Exception as e:
            # Fallback: if JSON parsing fails, return a safe default
            fallback = RouterOutput(
                intents=["estimate"] if has_pdf else [],
                extracted_context={"router_error": str(e), "raw_response": text[:200]},
            )
            return fallback, usage
