"""
JobTread Pave API Client
All requests POST to https://api.jobtread.com/pave with a GraphQL-like JSON body.
"""
import os
import httpx
from models.jobtread_models import JobTreadJob, JobTreadCustomer, JobTreadLocation, JobTreadNote

PAVE_URL = "https://api.jobtread.com/pave"


class JobTreadClient:
    def __init__(self):
        self._grant_key = os.getenv("JOBTREAD_GRANT_KEY", "")

    def _post(self, query: dict) -> dict:
        if not self._grant_key:
            return {"error": "JOBTREAD_GRANT_KEY not configured"}
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(PAVE_URL, json={"query": query})
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def _grant(self) -> dict:
        return {"$": {"grantKey": self._grant_key}}

    def get_job(self, job_id: str) -> JobTreadJob | None:
        query = {
            **self._grant(),
            "getJobs": {
                "$": {"where": {"id": {"eq": job_id}}},
                "id": {}, "name": {}, "status": {},
                "customer": {"name": {}, "email": {}, "phone": {}},
                "location": {"address": {}, "city": {}, "state": {}, "zip": {}},
                "notes": {"$": {"limit": 5, "orderBy": [{"createdAt": "desc"}]},
                          "id": {}, "content": {}, "createdAt": {}, "createdBy": {"name": {}}},
            }
        }
        data = self._post(query)
        jobs = data.get("getJobs", {}).get("nodes", [])
        if not jobs:
            return None
        return self._parse_job(jobs[0])

    def search_jobs(self, search_text: str) -> list[JobTreadJob]:
        query = {
            **self._grant(),
            "getJobs": {
                "$": {"where": {"name": {"contains": search_text}}, "limit": 5},
                "id": {}, "name": {}, "status": {},
                "customer": {"name": {}, "email": {}, "phone": {}},
                "location": {"address": {}, "city": {}, "state": {}, "zip": {}},
            }
        }
        data = self._post(query)
        jobs = data.get("getJobs", {}).get("nodes", [])
        return [self._parse_job(j) for j in jobs]

    def add_note(self, job_id: str, content: str) -> bool:
        query = {
            **self._grant(),
            "createNote": {
                "$": {"input": {"jobId": job_id, "content": content}},
                "id": {},
            }
        }
        data = self._post(query)
        return "error" not in data and bool(data.get("createNote", {}).get("id"))

    def ping(self) -> bool:
        """Verify the grant key is valid."""
        query = {**self._grant(), "getAccount": {"id": {}}}
        data = self._post(query)
        return "error" not in data

    @staticmethod
    def _parse_job(raw: dict) -> JobTreadJob:
        customer_raw = raw.get("customer") or {}
        location_raw = raw.get("location") or {}
        notes_raw = raw.get("notes", {}).get("nodes", []) if isinstance(raw.get("notes"), dict) else []

        notes = [
            JobTreadNote(
                id=n.get("id", ""),
                content=n.get("content", ""),
                created_at=n.get("createdAt", ""),
                created_by=(n.get("createdBy") or {}).get("name", ""),
            )
            for n in notes_raw
        ]

        return JobTreadJob(
            id=raw.get("id", ""),
            name=raw.get("name", ""),
            status=raw.get("status", ""),
            customer=JobTreadCustomer(
                id=customer_raw.get("id", ""),
                name=customer_raw.get("name", ""),
                email=customer_raw.get("email", ""),
                phone=customer_raw.get("phone", ""),
            ) if customer_raw else None,
            location=JobTreadLocation(
                address=location_raw.get("address", ""),
                city=location_raw.get("city", ""),
                state=location_raw.get("state", ""),
                zip=location_raw.get("zip", ""),
            ) if location_raw else None,
            notes=notes,
        )
