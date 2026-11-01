"""Evolt 360 scan parser.

Primary path is the PDF text layer via pdfplumber. Claude vision is a fallback
for a scan with no text layer, and only then: it costs money, it is slower, and
a regex over real text is more trustworthy than a model reading a picture of a
number.

Every parsed scan is range-checked by engine.ti.body.validate_scan before it is
stored. A scan that fails goes in with needs_review set rather than being
silently trusted or silently dropped.

The field patterns below were written against the real 13 Sep 2026 scan:
weight 66.7kg, body fat 14.1%, skeletal muscle 32.0kg, lean mass 57.3kg,
BMR 1607, TEE 2474, bio age 19, BWI 8.6, visceral fat level 5.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.ti.body import validate_scan

log = logging.getLogger(__name__)

# Each pattern captures one number. Ordered alternatives let a label drift
# slightly between Evolt firmware versions without breaking the parse.
#
# GAP spans the padding between a label and its value. Evolt prints these as
# wide columns: "BMR" to "1,607" is 22 spaces on the real report, so a narrow
# allowance silently drops the field. It is non-greedy and matches non-digits
# only, so it stops at the first number after the label.
GAP = r"\D{0,40}?"

PATTERNS: dict[str, str] = {
    "weight_kg":          r"(?:Weight|Total Weight)" + GAP + r"([\d.]+)\s*kg",
    "body_fat_pct":       r"(?:Total Body Fat|Body Fat)\s*%?" + GAP + r"([\d.]+)\s*%",
    "skeletal_muscle_kg": r"Skeletal Muscle(?: Mass)?" + GAP + r"([\d.]+)\s*kg",
    "lean_mass_kg":       r"Lean Body Mass" + GAP + r"([\d.]+)\s*kg",
    "fat_mass_kg":        r"Body Fat Mass" + GAP + r"([\d.]+)\s*kg",
    "visceral_fat_level": r"Visceral Fat Level" + GAP + r"([\d.]+)",
    "bmr_kcal":           r"BMR" + GAP + r"([\d,]+)",
    "tee_kcal":           r"TEE" + GAP + r"([\d,]+)",
    "bio_age":            r"(?:Bio(?:logical)? Age)" + GAP + r"([\d.]+)",
    "bwi":                r"BWI(?: Score)?" + GAP + r"([\d.]+)",
}

DATE_PATTERNS = [
    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})",
    r"(\d{4}-\d{2}-\d{2})",
    r"(\d{1,2}/\d{1,2}/\d{4})",
]

INT_FIELDS = {"bmr_kcal", "tee_kcal"}


@dataclass
class ParsedScan:
    values: dict[str, Any] = field(default_factory=dict)
    scanned_at: datetime | None = None
    parse_method: str = "pdfplumber"
    needs_review: bool = False
    review_reason: str | None = None
    raw_text: str = ""


def extract_text(pdf_path: str | Path) -> str:
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError("pdfplumber is not installed") from e

    out: list[str] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    return "\n".join(out)


def parse_text(text: str) -> ParsedScan:
    scan = ParsedScan(raw_text=text)

    for key, pattern in PATTERNS.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        raw = m.group(1).replace(",", "")
        try:
            scan.values[key] = int(raw) if key in INT_FIELDS else float(raw)
        except ValueError:
            log.warning("could not parse %s from %r", key, m.group(0))

    scan.scanned_at = _parse_date(text)
    scan.values["segmental"] = _parse_segmental(text)

    ok, reason = validate_scan(scan.values)
    if not ok:
        scan.needs_review = True
        scan.review_reason = reason

    if not scan.values.get("weight_kg"):
        scan.needs_review = True
        scan.review_reason = "; ".join(filter(None, [scan.review_reason, "no weight found"]))

    return scan


def _parse_date(text: str) -> datetime | None:
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue
        for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(m.group(1), fmt)
            except ValueError:
                continue
    return None


SEGMENT_LABELS = ("Left Arm", "Right Arm", "Trunk", "Torso", "Left Leg", "Right Leg")


def _parse_segmental(text: str) -> dict[str, dict[str, float]]:
    """Per-segment lean and fat mass, where the report prints them."""
    out: dict[str, dict[str, float]] = {}
    for label in SEGMENT_LABELS:
        m = re.search(rf"{label}\D{{0,40}}?([\d.]+)\s*kg\D{{0,40}}?([\d.]+)\s*kg",
                      text, re.IGNORECASE)
        if m:
            out[label.lower().replace(" ", "_")] = {
                "lean_kg": float(m.group(1)),
                "fat_kg": float(m.group(2)),
            }
    return out


def parse_pdf(pdf_path: str | Path, allow_vision_fallback: bool = True,
              api_key: str | None = None) -> ParsedScan:
    """Parse a scan PDF, falling back to vision only if there is no text."""
    text = ""
    try:
        text = extract_text(pdf_path)
    except RuntimeError as e:
        log.warning("text extraction unavailable: %s", e)

    if text.strip():
        scan = parse_text(text)
        # A text layer that yielded almost nothing is as good as no text layer.
        if len([k for k in scan.values if k != "segmental"]) >= 3:
            return scan
        log.info("text layer present but yielded %d fields, trying vision",
                 len(scan.values))

    if not allow_vision_fallback:
        scan = ParsedScan(parse_method="pdfplumber", needs_review=True,
                          review_reason="no usable text layer and vision fallback disabled")
        return scan

    return _parse_with_vision(pdf_path, api_key)


def _parse_with_vision(pdf_path: str | Path, api_key: str | None) -> ParsedScan:
    """Last resort. Marked needs_review so a human confirms the numbers.

    Note the Garmin terms question does not apply here: an Evolt scan is not
    Garmin-sourced data.
    """
    if not api_key:
        return ParsedScan(parse_method="vision", needs_review=True,
                          review_reason="no text layer and ANTHROPIC_API_KEY not set")
    try:
        import base64

        import anthropic
    except ImportError:
        return ParsedScan(parse_method="vision", needs_review=True,
                          review_reason="no text layer and anthropic sdk not installed")

    client = anthropic.Anthropic(api_key=api_key)
    pdf_b64 = base64.standard_b64encode(Path(pdf_path).read_bytes()).decode()

    message = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text":
                    "Extract these fields from this Evolt 360 body scan as strict JSON, "
                    "using null for anything not printed. Do not calculate or infer any "
                    "value that is not on the page. Keys: weight_kg, body_fat_pct, "
                    "skeletal_muscle_kg, lean_mass_kg, fat_mass_kg, visceral_fat_level, "
                    "bmr_kcal, tee_kcal, bio_age, bwi, scanned_date (YYYY-MM-DD)."},
            ],
        }],
    )

    import json
    raw = "".join(b.text for b in message.content if b.type == "text")
    scan = ParsedScan(parse_method="vision", needs_review=True,
                      review_reason="parsed by vision fallback, confirm against the printout")
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        scan.review_reason = "vision fallback returned unparseable output"
        return scan

    if data.get("scanned_date"):
        try:
            scan.scanned_at = datetime.strptime(data["scanned_date"], "%Y-%m-%d")
        except ValueError:
            pass
    scan.values = {k: v for k, v in data.items() if k != "scanned_date" and v is not None}

    ok, reason = validate_scan(scan.values)
    if not ok:
        scan.review_reason = "; ".join(filter(None, [scan.review_reason, reason]))
    return scan


def to_row(scan: ParsedScan, pdf_path: str | None = None, conditions: dict | None = None) -> dict:
    row = {
        "scanned_at": scan.scanned_at or datetime.now(),
        "parse_method": scan.parse_method,
        "needs_review": scan.needs_review,
        "review_reason": scan.review_reason,
        "pdf_path": pdf_path,
        "conditions": conditions or {},
        "segmental": scan.values.get("segmental") or {},
    }
    for key in PATTERNS:
        if key in scan.values:
            row[key] = scan.values[key]
    return row
