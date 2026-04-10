"""
HTML formatter — converts agent outputs to styled HTML for browser display.
"""
from models.estimate_models import Estimate, ProductEstimate


def estimate_to_html(estimate: Estimate) -> str:
    parts = []

    if estimate.narrative:
        parts.append(f'<p class="narrative">{estimate.narrative}</p>')

    for pe in estimate.products:
        parts.append(f'<div class="product-section">')
        title = f"{pe.manufacturer} {pe.product_line}"
        if pe.color:
            title += f" — {pe.color}"
        parts.append(f'<h3 class="product-title">{title}</h3>')
        parts.append(f'<p class="meta">{pe.squares_needed} SQ needed ({pe.waste_factor_pct}% waste included)</p>')

        parts.append('<table class="line-items"><thead><tr>'
                     '<th>Category</th><th>Description</th><th>Qty</th><th>Unit</th><th>Total</th>'
                     '</tr></thead><tbody>')

        for li in pe.line_items:
            parts.append(
                f'<tr><td>{li.category}</td><td>{li.description}</td>'
                f'<td class="num">{li.quantity:.2f}</td><td>{li.unit}</td>'
                f'<td class="num money">${li.total:,.2f}</td></tr>'
            )

        parts.append(
            f'<tr class="subtotal"><td colspan="4"><strong>Material Subtotal</strong></td>'
            f'<td class="num money"><strong>${pe.subtotal_materials:,.2f}</strong></td></tr>'
        )
        parts.append('</tbody></table>')
        parts.append('</div>')

    return "\n".join(parts)


def letter_to_html(letter_text: str) -> str:
    lines = letter_text.split("\n")
    html_parts = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            html_parts.append('<br>')
        else:
            html_parts.append(f'<p class="letter-line">{stripped}</p>')
    return "\n".join(html_parts)


def jobtread_to_html(note_text: str, job_summary: str = "") -> str:
    parts = []
    if job_summary:
        parts.append(f'<div class="jt-job-info"><pre>{job_summary}</pre></div>')
    if note_text:
        parts.append('<div class="jt-note">')
        parts.append('<h4>Generated Status Update:</h4>')
        for line in note_text.split("\n"):
            parts.append(f'<p>{line}</p>')
        parts.append('</div>')
    return "\n".join(parts)
