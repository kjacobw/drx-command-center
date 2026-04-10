"""
JobTread Agent — reads job info from JobTread and writes status update notes.
Uses haiku for reading/summarizing, sonnet for generating notes.
"""
import os
from pathlib import Path
from agents.base_agent import BaseAgent
from integrations.anthropic_client import MODEL_ROUTER, MODEL_GENERATOR
from integrations.jobtread_client import JobTreadClient
from models.jobtread_models import JobTreadJob

PROMPT_DIR = Path(__file__).parent.parent / "templates" / "system_prompts"


def _load_jt_prompt() -> str:
    path = PROMPT_DIR / "jobtread.txt"
    return path.read_text() if path.exists() else "Write a brief job status update."


class JobTreadAgent(BaseAgent):
    model = MODEL_ROUTER   # haiku for most ops
    max_tokens = 512
    temperature = 0.2

    def __init__(self):
        self._client = JobTreadClient()

    def get_job_summary(self, job_id: str | None, job_name: str | None = None) -> tuple[str, dict]:
        """
        Look up a job and return a formatted summary.
        Returns (summary_text, usage_dict).
        """
        job: JobTreadJob | None = None
        usage = {}

        if job_id:
            job = self._client.get_job(job_id)
        elif job_name:
            results = self._client.search_jobs(job_name)
            if results:
                job = results[0]

        if not job:
            return f"No job found for {'ID: ' + job_id if job_id else 'name: ' + (job_name or '?')}", usage

        return job.summary_text(), usage

    def write_status_update(
        self,
        brain_dump: str,
        job_id: str | None,
        job_name: str | None = None,
        write_to_jobtread: bool = False,
    ) -> tuple[str, dict, bool]:
        """
        Generate a status update note for a job and optionally write it to JobTread.
        Returns (note_text, usage_dict, was_written_to_jt).
        """
        # Read current job state first
        job_context = ""
        job: JobTreadJob | None = None

        if job_id:
            job = self._client.get_job(job_id)
        elif job_name:
            results = self._client.search_jobs(job_name)
            if results:
                job = results[0]

        if job:
            job_context = f"\n\nCurrent job state from JobTread:\n{job.summary_text()}"

        # Generate the note using sonnet (switching model for generation)
        self.model = MODEL_GENERATOR
        self.max_tokens = 400

        system_prompt = _load_jt_prompt()
        user_message = f"""Write a status update note for this job.

USER INPUT:
{brain_dump}
{job_context}

Write a clear, concise status update (under 150 words) appropriate for the team to read in JobTread.
Include: what happened/was completed, current status, and next steps."""

        note_text, usage = self._call(system_prompt, user_message)
        self.model = MODEL_ROUTER  # reset

        written = False
        if write_to_jobtread and job and job.id:
            written = self._client.add_note(job.id, note_text.strip())

        return note_text.strip(), usage, written

    def search_jobs(self, query: str) -> tuple[list[JobTreadJob], dict]:
        results = self._client.search_jobs(query)
        return results, {}
