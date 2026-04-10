"""
Roofr PDF Parser
Extracts structured measurement data from Roofr report PDFs using pdfplumber.
No LLM calls — pure regex + table extraction to minimize token costs.
"""
import re
import io
from typing import Optional
from models.roofr_models import RoofrReport, Facet

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


# --------------------------------------------------------------------------- #
#  Regex patterns for Roofr report fields
# --------------------------------------------------------------------------- #

# Matches "22.5 squares" or "22.50 Squares"
_TOTAL_SQUARES = re.compile(r"(\d+\.?\d*)\s*squares?", re.IGNORECASE)

# Matches pitch like "6/12" or "4:12"
_PITCH = re.compile(r"(\d{1,2})[/:]12")

# Matches waste percentage like "10%" or "Waste Factor: 15%"
_WASTE = re.compile(r"(?:waste|suggested\s+waste)[^\d]*(\d+\.?\d*)\s*%", re.IGNORECASE)

# Matches total area like "2,250 sq ft" or "2250 sqft"
_TOTAL_AREA = re.compile(r"([\d,]+)\s*sq\.?\s*ft", re.IGNORECASE)

# Linear measurement labels
_RIDGE = re.compile(r"ridge[^\d]*(\d+\.?\d*)", re.IGNORECASE)
_HIP = re.compile(r"hip[^\d]*(\d+\.?\d*)", re.IGNORECASE)
_VALLEY = re.compile(r"valley[^\d]*(\d+\.?\d*)", re.IGNORECASE)
_EAVE = re.compile(r"eave[^\d]*(\d+\.?\d*)", re.IGNORECASE)
_RAKE = re.compile(r"rake[^\d]*(\d+\.?\d*)", re.IGNORECASE)
_STEP = re.compile(r"step\s*flashing[^\d]*(\d+\.?\d*)", re.IGNORECASE)

# Property address — look for common patterns
_ADDRESS = re.compile(r"\d{1,5}\s+[A-Z][A-Za-z\s]+(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Ter|Circle|Cir)\b[^\n]*", re.IGNORECASE)


def _extract_float(pattern: re.Pattern, text: str, default: float = 0.0) -> float:
    m = pattern.search(text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except (ValueError, IndexError):
            pass
    return default


def _extract_pitches(text: str) -> list[str]:
    return list(dict.fromkeys(_PITCH.findall(text)))  # unique, order-preserved


def parse_roofr_pdf(pdf_bytes: bytes) -> RoofrReport:
    """
    Parse a Roofr PDF report from raw bytes.
    Returns a RoofrReport with as many fields populated as possible.
    Falls back gracefully if pdfplumber is unavailable or the format is unexpected.
    """
    if not PDFPLUMBER_AVAILABLE:
        return RoofrReport(
            parsed_ok=False,
            parse_warnings=["pdfplumber not installed — run: pip install pdfplumber"],
        )

    warnings: list[str] = []
    full_text = ""
    tables: list[list] = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"
                page_tables = page.extract_tables() or []
                for t in page_tables:
                    tables.extend(t)
    except Exception as e:
        return RoofrReport(
            parsed_ok=False,
            parse_warnings=[f"PDF read error: {str(e)}"],
            raw_text_fallback="",
        )

    # ------------------------------------------------------------------ #
    #  Field extraction
    # ------------------------------------------------------------------ #
    total_squares = _extract_float(_TOTAL_SQUARES, full_text)
    total_area_sq_ft = _extract_float(_TOTAL_AREA, full_text)
    waste_pct = _extract_float(_WASTE, full_text, default=10.0)

    # Pitches
    pitches = _extract_pitches(full_text)
    predominant_pitch = f"{pitches[0]}/12" if pitches else ""
    lowest_pitch = f"{min(pitches, key=lambda x: int(x))}/12" if pitches else ""
    highest_pitch = f"{max(pitches, key=lambda x: int(x))}/12" if pitches else ""

    # Linear measurements
    ridge = _extract_float(_RIDGE, full_text)
    hip = _extract_float(_HIP, full_text)
    valley = _extract_float(_VALLEY, full_text)
    eave = _extract_float(_EAVE, full_text)
    rake = _extract_float(_RAKE, full_text)
    step = _extract_float(_STEP, full_text)

    # Address
    addr_match = _ADDRESS.search(full_text)
    property_address = addr_match.group(0).strip() if addr_match else ""

    # Squares with waste
    if total_squares and waste_pct is not None:
        squares_with_waste = round(total_squares * (1 + waste_pct / 100), 2)
    else:
        squares_with_waste = 0.0

    # ------------------------------------------------------------------ #
    #  Facet table extraction
    #  Roofr tables typically: [Pitch, Area (sq ft), Area (squares), Slope Factor]
    # ------------------------------------------------------------------ #
    facets: list[Facet] = []
    for row in tables:
        if not row or len(row) < 3:
            continue
        # Skip header rows
        if any(str(c).lower() in ("pitch", "area", "slope") for c in row if c):
            continue
        pitch_cell = str(row[0] or "").strip()
        if not _PITCH.search(pitch_cell):
            continue
        try:
            area_sqft = float(str(row[1] or "0").replace(",", "").strip())
            area_sq = float(str(row[2] or "0").replace(",", "").strip()) if len(row) > 2 else area_sqft / 100
            slope = float(str(row[3] or "1.0").replace(",", "").strip()) if len(row) > 3 else 1.0
            facets.append(Facet(
                pitch=pitch_cell,
                area_sq_ft=area_sqft,
                area_squares=area_sq,
                slope_factor=slope,
            ))
        except (ValueError, IndexError):
            continue

    # ------------------------------------------------------------------ #
    #  Validation
    # ------------------------------------------------------------------ #
    fields_found = sum([
        bool(total_squares),
        bool(total_area_sq_ft),
        bool(predominant_pitch),
        bool(ridge or hip or valley or eave),
    ])

    if fields_found < 4:
        warnings.append(
            f"Only {fields_found}/4 key fields extracted — PDF format may differ from expected. "
            "Raw text is available as fallback."
        )

    # Cross-check squares vs area (1 square = 100 sq ft)
    if total_squares and total_area_sq_ft:
        expected_area = total_squares * 100
        if abs(expected_area - total_area_sq_ft) / max(expected_area, 1) > 0.15:
            warnings.append(
                f"Measurement mismatch: {total_squares} SQ × 100 = {expected_area} sq ft, "
                f"but report shows {total_area_sq_ft} sq ft. Please verify."
            )

    return RoofrReport(
        total_squares=total_squares,
        total_area_sq_ft=total_area_sq_ft,
        predominant_pitch=predominant_pitch,
        lowest_pitch=lowest_pitch,
        highest_pitch=highest_pitch,
        waste_factor_pct=waste_pct,
        squares_with_waste=squares_with_waste,
        ridge_length=ridge,
        hip_length=hip,
        valley_length=valley,
        eave_length=eave,
        rake_length=rake,
        step_flashing_length=step,
        facets=facets,
        property_address=property_address,
        parsed_ok=fields_found >= 4,
        parse_warnings=warnings,
        raw_text_fallback=full_text if fields_found < 4 else "",
    )
