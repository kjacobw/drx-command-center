from pydantic import BaseModel, Field
from typing import Optional


class LineItem(BaseModel):
    category: str               # e.g. "Shingles", "Underlayment", "Ridge Cap"
    description: str            # e.g. "GAF Timberline HDZ - Charcoal"
    unit: str                   # e.g. "SQ", "LF", "EA"
    quantity: float
    unit_price: float
    total: float
    notes: str = ""

    @classmethod
    def calculate(cls, category: str, description: str, unit: str,
                  quantity: float, unit_price: float, notes: str = "") -> "LineItem":
        return cls(
            category=category,
            description=description,
            unit=unit,
            quantity=round(quantity, 2),
            unit_price=round(unit_price, 2),
            total=round(quantity * unit_price, 2),
            notes=notes,
        )


class ProductEstimate(BaseModel):
    """One full estimate for a single product selection (e.g. GAF Timberline HDZ)."""
    product_id: str
    manufacturer: str
    product_line: str
    color: str = ""
    squares_needed: float
    waste_factor_pct: float
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal_materials: float = 0.0
    notes: str = ""

    def compute_totals(self) -> None:
        self.subtotal_materials = round(sum(li.total for li in self.line_items), 2)


class Estimate(BaseModel):
    """Container for one or more side-by-side product estimates."""
    property_address: str = ""
    date_prepared: str = ""
    prepared_by: str = ""
    products: list[ProductEstimate] = Field(default_factory=list)
    narrative: str = ""         # LLM-generated summary paragraph
    disclaimer: str = (
        "This estimate is based on aerial measurements and is subject to adjustment "
        "upon physical inspection. Prices are valid for 30 days."
    )
