"""
Estimating Agent — generates line-item material estimates.
Uses structured catalog data (no LLM for pricing) + Sonnet for narrative.
"""
import json
import os
from pathlib import Path
from datetime import date
from agents.base_agent import BaseAgent
from integrations.anthropic_client import MODEL_GENERATOR
from models.roofr_models import RoofrReport
from models.estimate_models import LineItem, ProductEstimate, Estimate

CATALOG_DIR = Path(__file__).parent.parent / "catalog"

SYSTEM_PROMPT = """You are an expert roofing estimator for a licensed Florida roofing contractor.
You have been given a structured material estimate with all quantities and prices already calculated.
Your job is to write a professional 2-3 sentence narrative summary of the estimate that:
1. Confirms the scope of work (re-roof, product selected, number of squares)
2. Highlights any notable features of the selected product (wind rating, warranty, certifications)
3. Notes the inclusion of all required accessories and code-required items

Be direct and professional. Do not repeat every line item — just write the summary paragraph.
Do not include any dollar amounts in the narrative (they are in the line items below)."""


def _load_catalog(filename: str) -> list[dict]:
    path = CATALOG_DIR / filename
    with open(path, "r") as f:
        data = json.load(f)
    return data.get("products", data.get("items", []))


def _load_accessories() -> list[dict]:
    return _load_catalog("accessories.json")


def _find_product(product_identifier: str, catalog: list[dict]) -> dict | None:
    """Find a product by ID or by fuzzy name match."""
    identifier_lower = product_identifier.lower()
    # Exact ID match first
    for p in catalog:
        if p["id"] == identifier_lower:
            return p
    # Fuzzy match on manufacturer + product_line
    for p in catalog:
        combined = f"{p['manufacturer']} {p['product_line']}".lower()
        if identifier_lower in combined or any(
            word in combined for word in identifier_lower.split() if len(word) > 3
        ):
            return p
    return None


def _build_product_estimate(
    product: dict,
    report: RoofrReport,
    accessories: list[dict],
    color: str = "",
) -> ProductEstimate:
    """Build a ProductEstimate with calculated line items from catalog + report data."""
    sq_needed = report.squares_needed()
    waste_pct = report.waste_factor_pct

    line_items: list[LineItem] = []

    # --- Primary material ---
    line_items.append(LineItem.calculate(
        category="Roofing Material",
        description=f"{product['manufacturer']} {product['product_line']}" + (f" - {color}" if color else ""),
        unit="SQ",
        quantity=sq_needed,
        unit_price=product["price_per_square"],
        notes=f"{product.get('warranty_years', '?')}-yr warranty | {product.get('wind_rating_mph', '?')} mph wind rating",
    ))

    # --- Accessories (auto-calculated from report data) ---
    for acc in accessories:
        calc = acc.get("calculation", "")
        qty = 0.0

        if "1:1 with total squares" in calc:
            qty = sq_needed

        elif "eave_length × 3ft / 100" in calc:
            # Ice & water at eaves: 3ft wide strip
            qty = round((report.eave_length * 3) / 100, 2)
            if qty == 0:
                qty = round(sq_needed * 0.10, 2)  # fallback: 10% of squares

        elif "ridge_length + hip_length" in calc:
            qty = report.ridge_length + report.hip_length
            if qty == 0:
                qty = round(report.total_squares * 3, 0)  # rough fallback

        elif "eave_length + rake_length" in calc:
            qty = report.eave_length + report.rake_length
            if qty == 0:
                qty = round(report.total_squares * 10, 0)  # rough fallback

        elif "step_flashing_length" in calc:
            qty = report.step_flashing_length

        elif "manual" in calc.lower():
            continue  # Skip manual items — added individually by user

        if qty <= 0:
            continue

        line_items.append(LineItem.calculate(
            category="Accessories",
            description=acc["name"],
            unit=acc["unit"],
            quantity=qty,
            unit_price=acc["price_per_unit"],
            notes=acc.get("notes", ""),
        ))

    pe = ProductEstimate(
        product_id=product["id"],
        manufacturer=product["manufacturer"],
        product_line=product["product_line"],
        color=color,
        squares_needed=sq_needed,
        waste_factor_pct=waste_pct,
        line_items=line_items,
    )
    pe.compute_totals()
    return pe


class EstimatingAgent(BaseAgent):
    model = MODEL_GENERATOR
    max_tokens = 512
    temperature = 0.2

    def __init__(self):
        self._shingles = _load_catalog("shingles.json")
        self._metal = _load_catalog("metal_roofing.json")
        self._accessories = _load_accessories()
        self._all_products = self._shingles + self._metal

    def estimate(
        self,
        report: RoofrReport,
        products_requested: list[str],
        brain_dump: str = "",
        prepared_by: str = "",
    ) -> tuple[Estimate, dict]:
        """
        Build an Estimate for one or more requested products.
        Returns (Estimate, usage_dict).
        """
        # Resolve products
        resolved: list[tuple[dict, str]] = []  # (product_dict, color)
        for req in products_requested:
            product = _find_product(req, self._all_products)
            if product:
                resolved.append((product, ""))
            else:
                # If nothing resolved, default to GAF Timberline HDZ
                fallback = _find_product("gaf-timberline-hdz", self._all_products)
                if fallback:
                    resolved.append((fallback, ""))

        # If still empty, use first two shingle products
        if not resolved:
            for p in self._shingles[:2]:
                resolved.append((p, ""))

        # Build per-product estimates
        product_estimates = []
        for product, color in resolved:
            pe = _build_product_estimate(product, report, self._accessories, color)
            product_estimates.append(pe)

        # Generate narrative (small Sonnet call)
        narrative_context = self._build_narrative_context(product_estimates, report)
        narrative_text, usage = self._call(SYSTEM_PROMPT, narrative_context)

        estimate = Estimate(
            property_address=report.property_address,
            date_prepared=str(date.today()),
            prepared_by=prepared_by or os.getenv("COMPANY_NAME", "DRX Roofing"),
            products=product_estimates,
            narrative=narrative_text.strip(),
        )

        return estimate, usage

    def _build_narrative_context(self, products: list[ProductEstimate], report: RoofrReport) -> str:
        lines = [
            f"Property: {report.property_address or 'Subject Property'}",
            f"Roof measurements: {report.total_squares} squares | Pitch: {report.predominant_pitch} | Waste: {report.waste_factor_pct}%",
            f"Squares to order (with waste): {report.squares_needed()}",
            "",
            "Products being estimated:",
        ]
        for pe in products:
            lines.append(f"  - {pe.manufacturer} {pe.product_line}: ${pe.subtotal_materials:,.2f} total")
            for li in pe.line_items[:3]:
                lines.append(f"    • {li.description}: {li.quantity} {li.unit} × ${li.unit_price:.2f} = ${li.total:,.2f}")
        return "\n".join(lines)
