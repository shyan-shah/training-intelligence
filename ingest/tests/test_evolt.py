"""Evolt parser tests.

The fixture text reproduces the layout and the exact printed values of the
real 13 September 2026 scan, so this is the text-layer half of the acceptance
check "a real Evolt PDF parses to the same values as the printed scan".
Running it against the actual PDF is a manual step; see the README.
"""
import pytest

from ingest.evolt import parse_text, to_row

REAL_SCAN = """
EVOLT 360 BODY SCAN REPORT
Scan Date: 13 September 2026
Name: Shyan    Height: 180cm    Age: 21    Gender: Male

BODY COMPOSITION
Total Weight            66.7 kg
Lean Body Mass          57.3 kg     Optimal
Skeletal Muscle Mass    32.0 kg     Optimal
Body Fat Mass            9.4 kg     Under
Total Body Fat %        14.1 %      Under
Subcutaneous Fat         8.3 kg     12.4 %
Visceral Fat Mass        1.1 kg      1.6 %
Visceral Fat Area         46 cm2    Under
Visceral Fat Level           5      Optimal

METABOLIC
BMR                      1,607 kcal
TEE                      2,474 kcal
Biological Age              19
BWI Score                  8.6 / 10   Athletic

SEGMENTAL ANALYSIS      Lean      Fat
Left Arm                 3.1 kg    0.4 kg
Right Arm                3.2 kg    0.4 kg
Trunk                   26.4 kg    4.1 kg
Left Leg                 8.9 kg    1.2 kg
Right Leg                9.0 kg    1.2 kg
"""


@pytest.fixture(scope="module")
def parsed():
    return parse_text(REAL_SCAN)


@pytest.mark.parametrize("field,expected", [
    ("weight_kg", 66.7),
    ("lean_mass_kg", 57.3),
    ("skeletal_muscle_kg", 32.0),
    ("fat_mass_kg", 9.4),
    ("body_fat_pct", 14.1),
    ("visceral_fat_level", 5.0),
    ("bmr_kcal", 1607),
    ("tee_kcal", 2474),
    ("bio_age", 19.0),
    ("bwi", 8.6),
])
def test_every_printed_value_round_trips(parsed, field, expected):
    assert parsed.values[field] == pytest.approx(expected)


def test_thousands_separator_is_handled(parsed):
    """BMR prints as '1,607 kcal'."""
    assert parsed.values["bmr_kcal"] == 1607
    assert isinstance(parsed.values["bmr_kcal"], int)


def test_scan_date_is_parsed(parsed):
    assert parsed.scanned_at is not None
    assert parsed.scanned_at.date().isoformat() == "2026-09-13"


def test_segmental_analysis_is_captured(parsed):
    seg = parsed.values["segmental"]
    assert seg["left_arm"] == {"lean_kg": 3.1, "fat_kg": 0.4}
    assert seg["trunk"]["lean_kg"] == 26.4
    assert len(seg) == 5


def test_a_clean_scan_does_not_need_review(parsed):
    assert parsed.needs_review is False
    assert parsed.review_reason is None
    assert parsed.parse_method == "pdfplumber"


def test_body_fat_percent_is_not_confused_with_fat_mass(parsed):
    """'Body Fat Mass 9.4 kg' and 'Total Body Fat % 14.1 %' sit two lines
    apart and both start with the same words."""
    assert parsed.values["body_fat_pct"] == pytest.approx(14.1)
    assert parsed.values["fat_mass_kg"] == pytest.approx(9.4)


def test_out_of_range_scan_is_flagged_for_review():
    bad = REAL_SCAN.replace("Total Body Fat %        14.1 %",
                            "Total Body Fat %        41.0 %")
    scan = parse_text(bad)
    assert scan.needs_review is True
    assert "body_fat_pct" in scan.review_reason


def test_inconsistent_scan_is_flagged_for_review():
    bad = REAL_SCAN.replace("Lean Body Mass          57.3 kg",
                            "Lean Body Mass          40.0 kg")
    scan = parse_text(bad)
    assert scan.needs_review is True
    assert "inconsistent" in scan.review_reason


def test_missing_weight_is_flagged_with_enough_detail_to_fix_it():
    """A real scan failed in production with only "no weight found", which
    gives nothing to work from: Evolt label wording differs between firmware
    versions and the pattern can only be corrected by seeing the text. The
    reason now carries what matched and how the text began."""
    bad = REAL_SCAN.replace("Total Weight            66.7 kg", "")
    scan = parse_text(bad)

    assert scan.needs_review is True
    assert "no weight found" in scan.review_reason
    # What it did manage to read, so the gap is obvious.
    assert "matched:" in scan.review_reason
    assert "body_fat_pct" in scan.review_reason
    # And a snippet of the document itself.
    assert "text began:" in scan.review_reason
    assert "EVOLT 360 BODY SCAN REPORT" in scan.review_reason
    # Collapsed whitespace, so the snippet is one readable line.
    assert "\n" not in scan.review_reason


def test_a_pdf_with_no_text_layer_says_so():
    scan = parse_text("")
    assert scan.needs_review is True
    assert "no text layer at all" in scan.review_reason


def test_empty_input_does_not_crash():
    scan = parse_text("")
    assert scan.needs_review is True
    assert scan.values.get("weight_kg") is None


def test_to_row_shapes_a_database_row(parsed):
    row = to_row(parsed, pdf_path="u/scan.pdf", conditions={"fasted": True, "time": "morning"})
    assert row["weight_kg"] == pytest.approx(66.7)
    assert row["pdf_path"] == "u/scan.pdf"
    assert row["conditions"] == {"fasted": True, "time": "morning"}
    assert row["needs_review"] is False
    assert row["scanned_at"].date().isoformat() == "2026-09-13"
    assert "segmental" in row
