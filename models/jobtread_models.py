from pydantic import BaseModel, Field
from typing import Optional


class JobTreadNote(BaseModel):
    id: str = ""
    content: str = ""
    created_at: str = ""
    created_by: str = ""


class JobTreadCustomer(BaseModel):
    id: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""


class JobTreadLocation(BaseModel):
    address: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""

    def full_address(self) -> str:
        parts = [self.address, self.city, self.state, self.zip]
        return ", ".join(p for p in parts if p)


class JobTreadJob(BaseModel):
    id: str = ""
    name: str = ""
    status: str = ""
    customer: Optional[JobTreadCustomer] = None
    location: Optional[JobTreadLocation] = None
    notes: list[JobTreadNote] = Field(default_factory=list)

    def summary_text(self) -> str:
        lines = [f"Job: {self.name} (ID: {self.id})", f"Status: {self.status}"]
        if self.customer:
            lines.append(f"Customer: {self.customer.name} | {self.customer.phone} | {self.customer.email}")
        if self.location:
            lines.append(f"Address: {self.location.full_address()}")
        if self.notes:
            lines.append(f"Recent notes ({len(self.notes)}):")
            for n in self.notes[-3:]:  # last 3 notes only
                lines.append(f"  [{n.created_at[:10] if n.created_at else '?'}] {n.content[:200]}")
        return "\n".join(lines)
