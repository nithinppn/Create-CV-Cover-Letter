"""Section format validator - validates LLM output format per section."""

import re
from typing import Dict, Any, Optional
import yaml
import os


def _load_rules() -> Dict:
    """Load validation rules from config."""
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "validation_rules.yaml"
    )
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}


def validate_section_format(
    section_name: str,
    text: str,
    rules: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Validate section output format against rules.

    Args:
        section_name: One of professional_summary, education, skills, projects,
                      experience, certifications, cover_letter
        text: LLM output text to validate
        rules: Optional rules dict; loads from config if not provided

    Returns:
        {"valid": bool, "errors": [...]}
    """
    if rules is None:
        rules = _load_rules()

    errors = []
    text = (text or "").strip()

    if section_name == "professional_summary":
        errors = _validate_professional_summary(text, rules.get("professional_summary", {}))
    elif section_name == "education":
        errors = _validate_education(text, rules.get("education", {}))
    elif section_name == "skills":
        errors = _validate_skills(text, rules.get("skills", {}))
    elif section_name == "projects":
        errors = _validate_projects(text, rules.get("projects", {}))
    elif section_name == "experience":
        errors = _validate_experience(text, rules.get("experience", {}))
    elif section_name == "certifications":
        errors = _validate_certifications(text, rules.get("certifications", {}))
    elif section_name == "cover_letter":
        errors = _validate_cover_letter(text, rules.get("cover_letter", {}))
    else:
        return {"valid": True, "errors": []}  # Unknown section: skip validation

    return {"valid": len(errors) == 0, "errors": errors}


def _validate_professional_summary(text: str, r: Dict) -> list:
    errors = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    if r.get("min_lines") and len(lines) < r["min_lines"]:
        errors.append(f"Summary should have at least {r['min_lines']} lines, got {len(lines)}")
    if r.get("max_lines") and len(lines) > r["max_lines"]:
        errors.append(f"Summary should have at most {r['max_lines']} lines, got {len(lines)}")

    for pat in r.get("forbidden_patterns", []):
        if re.search(pat, text, re.IGNORECASE):
            errors.append(f"Forbidden pattern found: {pat}")

    return errors


def _validate_education(text: str, r: Dict) -> list:
    if not text.strip():
        return []
    errors = []
    if r.get("degree_line_pattern") and not re.search(r["degree_line_pattern"], text):
        errors.append("Education must include degree lines in format: **Degree** — Institution, Dates")
    return errors


def _validate_skills(text: str, r: Dict) -> list:
    if not text.strip():
        return []
    errors = []
    if r.get("category_line_pattern"):
        matches = re.findall(r["category_line_pattern"], text)
        if not matches and "**" in text:
            errors.append("Skills should use **Category:** skill, skill format")
    return errors


def _validate_projects(text: str, r: Dict) -> list:
    if not text.strip():
        return []
    errors = []
    # Check for per-project structure: each project should have **Name** and bullets
    blocks = re.split(r"(?=\*\*[^*]+\*\*)", text)
    project_headers = [b for b in blocks if re.match(r"^\*\*[^*]+\*\*", b.strip())]

    if r.get("min_projects") and len(project_headers) < r["min_projects"]:
        errors.append(
            f"Projects should have at least {r['min_projects']} distinct project blocks "
            f"(each starting with **Project Name**), found {len(project_headers)}"
        )

    # Check for merged blocks: each **Name** block should have its own bullets, not one giant block
    for block in blocks:
        block = block.strip()
        if not block or not block.startswith("**"):
            continue
        bullet_count = len(re.findall(r"^- ", block, re.MULTILINE))
        max_bullets = r.get("max_bullets_per_project", 10)
        if bullet_count > max_bullets:
            errors.append(
                f"A single project block has {bullet_count} bullets; "
                f"max {max_bullets} per project. Possible merged projects."
            )

    return errors


def _validate_experience(text: str, r: Dict) -> list:
    if not text.strip():
        return []
    errors = []
    # Count bullets per role
    lines = text.splitlines()
    bullets_in_role = 0
    for line in lines:
        if line.strip().startswith("- "):
            bullets_in_role += 1
        elif line.strip() and not line.strip().startswith("-"):
            if bullets_in_role > r.get("max_bullets_per_role", 5):
                errors.append(
                    f"Experience role has {bullets_in_role} bullets; "
                    f"max {r.get('max_bullets_per_role', 5)} per role"
                )
            bullets_in_role = 0
    if bullets_in_role > r.get("max_bullets_per_role", 5):
        errors.append(
            f"Experience role has {bullets_in_role} bullets; "
            f"max {r.get('max_bullets_per_role', 5)} per role"
        )
    return errors


def _validate_certifications(text: str, r: Dict) -> list:
    if not text.strip():
        return []
    errors = []
    if r.get("bullet_pattern"):
        bullets = re.findall(r"^- ", text)
        if bullets and not re.search(r"[—–-].*\([^)]+\)", text):
            errors.append("Certifications should use format: - Name — Issuer (Year)")
    return errors


def _validate_cover_letter(text: str, r: Dict) -> list:
    if not text.strip():
        return []
    errors = []
    words = len(text.split())
    if r.get("min_words") and words < r["min_words"]:
        errors.append(f"Cover letter should have at least {r['min_words']} words, got {words}")
    if r.get("max_words") and words > r["max_words"]:
        errors.append(f"Cover letter should have at most {r['max_words']} words, got {words}")
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if r.get("min_paragraphs") and len(paragraphs) < r["min_paragraphs"]:
        errors.append(
            f"Cover letter should have at least {r['min_paragraphs']} paragraphs, "
            f"got {len(paragraphs)}"
        )
    return errors
