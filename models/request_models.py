from pydantic import BaseModel, Field
from typing import Optional
from models.roofr_models import RoofrReport
from models.estimate_models import Estimate


class RouterOutput(BaseModel):
    """Structured output from the router agent (haiku)."""
    intents: list[str] = Field(default_factory=list)
    # Possible values: "estimate", "insurance_letter", "claim_update",
    # "jobtread_read", "jobtread_write", "sales_proposal", "follow_up"

    carrier: Optional[str] = None       # "security_first" | "american_integrity"
    job_id: Optional[str] = None        # JobTread job ID if mentioned
    job_name: Optional[str] = None      # Customer/job name if mentioned
    claim_number: Optional[str] = None
    products_requested: list[str] = Field(default_factory=list)  # product IDs or names
    property_address: Optional[str] = None
    customer_name: Optional[str] = None
    urgency: str = "normal"             # "normal" | "urgent"
    extracted_context: dict = Field(default_factory=dict)  # any other extracted facts


class ProcessRequest(BaseModel):
    """Incoming brain dump request (parsed from multipart form)."""
    brain_dump: str
    carrier_override: Optional[str] = None


class AgentResult(BaseModel):
    """Output from a single agent run."""
    agent: str
    success: bool
    html_preview: str = ""          # formatted HTML for browser display
    docx_filename: Optional[str] = None
    pdf_filename: Optional[str] = None
    jobtread_written: bool = False
    error: Optional[str] = None
    token_usage: dict = Field(default_factory=dict)


class ProcessResponse(BaseModel):
    """Final aggregated response returned to the browser."""
    success: bool
    router_output: Optional[RouterOutput] = None
    roofr_summary: Optional[str] = None   # PDF parse summary if PDF was uploaded
    results: list[AgentResult] = Field(default_factory=list)
    total_tokens_used: int = 0
    error: Optional[str] = None
