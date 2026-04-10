from pydantic import BaseModel, Field
from typing import Optional


class Facet(BaseModel):
    pitch: str = ""            # e.g. "6/12"
    area_sq_ft: float = 0.0
    area_squares: float = 0.0
    slope_factor: float = 1.0
    description: str = ""      # e.g. "Main Roof - South"


class RoofrReport(BaseModel):
    # Core measurements
    total_squares: float = 0.0
    total_area_sq_ft: float = 0.0
    predominant_pitch: str = ""       # e.g. "6/12"
    lowest_pitch: str = ""
    highest_pitch: str = ""

    # Waste
    waste_factor_pct: float = 10.0    # e.g. 10 means 10%
    squares_with_waste: float = 0.0

    # Linear measurements (feet)
    ridge_length: float = 0.0
    hip_length: float = 0.0
    valley_length: float = 0.0
    eave_length: float = 0.0
    rake_length: float = 0.0
    step_flashing_length: float = 0.0

    # Flat / low-slope area
    flat_area_sq_ft: float = 0.0

    # Facet breakdown
    facets: list[Facet] = Field(default_factory=list)

    # Meta
    property_address: str = ""
    report_date: str = ""
    parsed_ok: bool = True
    parse_warnings: list[str] = Field(default_factory=list)
    raw_text_fallback: str = ""       # populated if structured parse fails

    def squares_needed(self, extra_waste_pct: float = 0.0) -> float:
        """Total squares to order including waste."""
        if self.squares_with_waste:
            return self.squares_with_waste
        total_waste = self.waste_factor_pct + extra_waste_pct
        return round(self.total_squares * (1 + total_waste / 100), 2)

    def summary_text(self) -> str:
        """Short human-readable summary for use in prompts."""
        lines = [
            f"Total squares: {self.total_squares}",
            f"Squares with {self.waste_factor_pct}% waste: {self.squares_needed()}",
            f"Predominant pitch: {self.predominant_pitch}",
            f"Ridge: {self.ridge_length} LF | Hip: {self.hip_length} LF | Valley: {self.valley_length} LF",
            f"Eave: {self.eave_length} LF | Rake: {self.rake_length} LF",
        ]
        if self.property_address:
            lines.insert(0, f"Property: {self.property_address}")
        if self.parse_warnings:
            lines.append(f"Parser warnings: {'; '.join(self.parse_warnings)}")
        return "\n".join(lines)
