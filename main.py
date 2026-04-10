"""
DRX Command Center — FastAPI backend
Brain dump → router → specialized agents → deliverables
"""
import json
import os
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents.router_agent import RouterAgent
from agents.estimating_agent import EstimatingAgent
from agents.insurance_agent import InsuranceAgent
from agents.jobtread_agent import JobTreadAgent
from agents.sales_agent import SalesAgent
from parsers.roofr_parser import parse_roofr_pdf
from integrations.jobtread_client import JobTreadClient
from output.docx_builder import build_estimate_docx, build_letter_docx
from output.formatter import estimate_to_html, letter_to_html, jobtread_to_html
from models.roofr_models import RoofrReport

app = FastAPI(title="DRX Command Center", version="1.0.0")

# Serve static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Temp directory for generated files
TMP_DIR = Path(tempfile.gettempdir()) / "drx_output"
TMP_DIR.mkdir(exist_ok=True)

# Agent singletons (initialized once)
_router = RouterAgent()
_estimating = EstimatingAgent()
_insurance = InsuranceAgent()
_jobtread_agent = JobTreadAgent()
_sales = SalesAgent()


# --------------------------------------------------------------------------- #
#  Routes
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = static_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse("<h1>DRX Command Center</h1><p>Static files not found.</p>")


@app.get("/api/health")
async def health():
    jt_client = JobTreadClient()
    jt_ok = jt_client.ping() if os.getenv("JOBTREAD_GRANT_KEY") else False
    anthropic_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
    return {
        "status": "ok",
        "anthropic_configured": anthropic_ok,
        "jobtread_configured": bool(os.getenv("JOBTREAD_GRANT_KEY")),
        "jobtread_live": jt_ok,
    }


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    safe_name = Path(filename).name
    file_path = TMP_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found or expired")
    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path=str(file_path), filename=safe_name, media_type=media_type)


@app.post("/api/process")
async def process(
    brain_dump: str = Form(...),
    carrier_override: str = Form(default=""),
    write_to_jobtread: str = Form(default="false"),
    pdf_file: UploadFile | None = File(default=None),
):
    """
    Main processing endpoint. Runs all agents synchronously and returns a
    single JSON response. More reliable than SSE through Replit's proxy.
    """
    total_tokens = 0
    log: list[str] = []
    results = []
    roofr_summary = ""

    try:
        # ----------------------------------------------------------------
        # Step 1: Parse PDF if attached
        # ----------------------------------------------------------------
        report: RoofrReport | None = None
        has_pdf = False

        if pdf_file and pdf_file.filename:
            log.append("Parsing Roofr PDF...")
            pdf_bytes = await pdf_file.read()
            report = parse_roofr_pdf(pdf_bytes)
            has_pdf = True

            if report.parse_warnings:
                log.append(f"Warning: {' | '.join(report.parse_warnings)}")

            if report.total_squares:
                roofr_summary = report.summary_text()
                log.append(f"PDF parsed — {report.total_squares} SQ, pitch {report.predominant_pitch}")
            else:
                log.append("PDF parsed but measurements not extracted — using as context only")

        # ----------------------------------------------------------------
        # Step 2: Route intent (haiku — cheap)
        # ----------------------------------------------------------------
        log.append("Analyzing your request...")
        routing, router_usage = _router.route(brain_dump, has_pdf=has_pdf)
        total_tokens += router_usage.get("input_tokens", 0) + router_usage.get("output_tokens", 0)

        if carrier_override and carrier_override not in ("", "auto"):
            routing.carrier = carrier_override

        intents = routing.intents or []
        if not intents:
            return JSONResponse({
                "success": False,
                "error": "Could not determine what you need. Try being more specific — e.g. 'give me an estimate' or 'write a claim letter to Security First'.",
                "log": log,
            })

        log.append(f"Routing to: {', '.join(intents)}")

        # ----------------------------------------------------------------
        # Step 3: Dispatch agents
        # ----------------------------------------------------------------

        # ESTIMATE
        if "estimate" in intents:
            log.append("Generating material estimate...")
            if not report:
                report = RoofrReport(total_squares=0)

            estimate, est_usage = _estimating.estimate(
                report=report,
                products_requested=routing.products_requested or [],
                brain_dump=brain_dump,
                prepared_by=os.getenv("COMPANY_NAME", ""),
            )
            total_tokens += est_usage.get("input_tokens", 0) + est_usage.get("output_tokens", 0)

            est_filename = f"estimate_{uuid.uuid4().hex[:8]}.docx"
            (TMP_DIR / est_filename).write_bytes(build_estimate_docx(estimate))

            results.append({
                "agent": "estimate",
                "title": "Material Estimate",
                "html": estimate_to_html(estimate),
                "docx_url": f"/api/download/{est_filename}",
            })
            log.append("Estimate complete")

        # INSURANCE LETTER / CLAIM UPDATE
        if any(i in intents for i in ("insurance_letter", "claim_update")):
            intent_type = "insurance_letter" if "insurance_letter" in intents else "claim_update"
            carrier_key = routing.carrier or (carrier_override if carrier_override not in ("", "auto") else None)
            log.append(f"Writing {intent_type.replace('_', ' ')}...")

            letter_text, ins_usage = _insurance.write_letter(
                brain_dump=brain_dump,
                carrier_key=carrier_key,
                report=report,
                claim_number=routing.claim_number,
                property_address=routing.property_address or (report.property_address if report else None),
                intent=intent_type,
            )
            total_tokens += ins_usage.get("input_tokens", 0) + ins_usage.get("output_tokens", 0)

            letter_filename = f"letter_{uuid.uuid4().hex[:8]}.docx"
            (TMP_DIR / letter_filename).write_bytes(build_letter_docx(letter_text))

            results.append({
                "agent": "insurance",
                "title": "Insurance Letter",
                "html": letter_to_html(letter_text),
                "docx_url": f"/api/download/{letter_filename}",
            })
            log.append("Insurance letter complete")

        # JOBTREAD
        if any(i in intents for i in ("jobtread_read", "jobtread_write")):
            should_write = "jobtread_write" in intents and write_to_jobtread.lower() == "true"
            log.append("Looking up JobTread job...")

            note_text, jt_usage, was_written = _jobtread_agent.write_status_update(
                brain_dump=brain_dump,
                job_id=routing.job_id,
                job_name=routing.job_name,
                write_to_jobtread=should_write,
            )
            total_tokens += jt_usage.get("input_tokens", 0) + jt_usage.get("output_tokens", 0)

            job_summary = ""
            if routing.job_id or routing.job_name:
                job_summary, _ = _jobtread_agent.get_job_summary(routing.job_id, routing.job_name)

            results.append({
                "agent": "jobtread",
                "title": "JobTread Update",
                "html": jobtread_to_html(note_text, job_summary),
                "written_to_jt": was_written,
                "note_text": note_text,
            })
            log.append("JobTread update complete")

        # SALES
        if any(i in intents for i in ("sales_proposal", "follow_up", "customer_message")):
            active_intent = next(i for i in intents if i in ("sales_proposal", "follow_up", "customer_message"))
            log.append("Generating sales document...")

            sales_text, sales_usage = _sales.generate(
                brain_dump=brain_dump,
                intent=active_intent,
                customer_name=routing.customer_name,
            )
            total_tokens += sales_usage.get("input_tokens", 0) + sales_usage.get("output_tokens", 0)

            sales_filename = f"sales_{uuid.uuid4().hex[:8]}.docx"
            (TMP_DIR / sales_filename).write_bytes(build_letter_docx(sales_text))

            results.append({
                "agent": "sales",
                "title": "Sales Document",
                "html": letter_to_html(sales_text),
                "docx_url": f"/api/download/{sales_filename}",
            })
            log.append("Sales document complete")

        log.append("All done!")
        return JSONResponse({
            "success": True,
            "roofr_summary": roofr_summary,
            "log": log,
            "results": results,
            "total_tokens": total_tokens,
        })

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return JSONResponse({
            "success": False,
            "error": str(e),
            "detail": tb[:1000],
            "log": log,
        }, status_code=500)


@app.post("/api/jobtread/write-note")
async def write_note(job_id: str = Form(...), note_text: str = Form(...)):
    client = JobTreadClient()
    written = client.add_note(job_id, note_text)
    return {"written": written}
