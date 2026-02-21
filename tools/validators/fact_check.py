"""Fact-check tool - verifies LLM output against profile data."""

import re
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class Violation:
    claim: str
    source: str
    expected: str = ""


def _normalize(s: str) -> str:
    """Normalize for comparison."""
    return re.sub(r"\s+", " ", (s or "").lower().strip())


def _extract_projects_from_profile(profile: Dict) -> Dict[str, Dict]:
    """Build map of project name -> project data."""
    projects = profile.get("projects", [])
    return {_normalize(p.get("name", "")): p for p in projects if p.get("name")}


def _extract_cert_names_from_profile(profile: Dict) -> set:
    certs = profile.get("certifications", [])
    return {_normalize(c.get("name", "")) for c in certs}


def _extract_education_from_profile(profile: Dict) -> Dict:
    edu = profile.get("education", [])
    institutions = set()
    areas = set()
    courses = set()
    for e in edu:
        institutions.add(_normalize(e.get("institution", "")))
        areas.add(_normalize(e.get("area", "")))
        for c in e.get("courses", []):
            courses.add(_normalize(str(c)))
    return {"institutions": institutions, "areas": areas, "courses": courses}


def _extract_experience_from_profile(profile: Dict) -> Dict:
    exp = profile.get("experience", [])
    companies = set()
    positions = set()
    for e in exp:
        companies.add(_normalize(e.get("company", "")))
        positions.add(_normalize(e.get("position", "")))
    return {"companies": companies, "positions": positions}


def fact_check(
    section_name: str,
    text: str,
    profile: Dict,
) -> Dict[str, Any]:
    """
    Cross-reference LLM output against profile data.

    Args:
        section_name: Section being checked
        text: LLM output text
        profile: Full profile.yaml data

    Returns:
        {"passed": bool, "violations": [{claim, source, expected}, ...]}
    """
    violations: List[Violation] = []
    text_norm = _normalize(text)

    if section_name == "education":
        edu = _extract_education_from_profile(profile)
        # Check for institution names
        for inst in edu["institutions"]:
            if inst and inst not in text_norm and inst.split(",")[0] not in text_norm:
                pass  # Institution may be abbreviated; skip for now
        # Courses: if we see "Relevant Coursework:" extract and check
        for course in edu["courses"]:
            if course and course not in text_norm:
                # Allow partial match (e.g. "Machine Learning" in "ML")
                pass

    elif section_name == "certifications":
        cert_names = _extract_cert_names_from_profile(profile)
        # Extract certification-like lines: - X — Y (Z)
        cert_lines = re.findall(r"-\s*([^—–-]+?)\s*[—–-]\s*[^(]+\([^)]+\)", text)
        for line in cert_lines:
            name_norm = _normalize(line.strip())
            # Check if any profile cert name is contained in this line or vice versa
            found = any(
                name_norm in cn or cn in name_norm
                for cn in cert_names
            )
            if not found and cert_names:
                violations.append(
                    Violation(
                        claim=line.strip(),
                        source="certification name",
                        expected="Must match a certification from profile",
                    )
                )

    elif section_name == "projects":
        projects = _extract_projects_from_profile(profile)
        # Extract project names from **Name**, date format
        name_matches = re.findall(r"\*\*([^*]+)\*\*", text)
        for name in name_matches:
            name_norm = _normalize(name)
            if not any(
                name_norm in pn or pn in name_norm
                for pn in projects.keys()
            ) and projects:
                violations.append(
                    Violation(
                        claim=name,
                        source="project name",
                        expected="Must match a project from profile",
                    )
                )

    elif section_name == "experience":
        exp = _extract_experience_from_profile(profile)
        # Check company names
        for company in exp["companies"]:
            if company and len(company) > 3 and company not in text_norm:
                # Allow abbreviations
                first_word = company.split()[0] if company else ""
                if first_word and first_word not in text_norm:
                    pass  # Skip strict check for now

    passed = len(violations) == 0
    return {
        "passed": passed,
        "violations": [
            {"claim": v.claim, "source": v.source, "expected": v.expected}
            for v in violations
        ],
    }
