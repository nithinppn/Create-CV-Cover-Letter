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
    """Extract companies, positions, locations, dates per role for strict matching."""
    exp = profile.get("experience", [])
    companies = set()
    positions = set()
    locations = set()
    roles = []  # Full role data for strict matching
    for e in exp:
        c = _normalize(e.get("company", ""))
        p = _normalize(e.get("position", ""))
        loc = _normalize(e.get("location", ""))
        if c:
            companies.add(c)
        if p:
            positions.add(p)
        if loc:
            locations.add(loc)
        roles.append({
            "company": c,
            "position": p,
            "location": loc,
            "startDate": _normalize(str(e.get("startDate", ""))),
            "endDate": _normalize(str(e.get("endDate", ""))),
        })
    return {
        "companies": companies,
        "positions": positions,
        "locations": locations,
        "roles": roles,
    }


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
        # STRICT: Every company in profile must appear in output
        for company in exp["companies"]:
            if not company:
                continue
            # Allow partial match (e.g. "Mercedes Benz AG" vs "Mercedes Benz")
            if company not in text_norm:
                first_word = company.split()[0] if company else ""
                if not first_word or first_word not in text_norm:
                    violations.append(
                        Violation(
                            claim=f"Company '{company}' missing",
                            source="experience",
                            expected="All companies from profile must appear exactly",
                        )
                    )
        # STRICT: Every position must appear
        for pos in exp["positions"]:
            if not pos or len(pos) < 4:
                continue
            if pos not in text_norm:
                first_word = pos.split()[0] if pos else ""
                if not first_word or first_word not in text_norm:
                    violations.append(
                        Violation(
                            claim=f"Position '{pos}' missing or altered",
                            source="experience",
                            expected="Use exact position titles from profile",
                        )
                    )
        # Check for fabricated companies: output companies must be in profile
        # Extract company-like phrases after **Role**, (format: **Role**, Company, Location)
        role_blocks = re.split(r"(?=\*\*[^*]+\*\*)", text)
        for block in role_blocks:
            if not block.strip() or not block.strip().startswith("**"):
                continue
            # First line is **Position**, Company, Location, Date
            first_line = block.strip().split("\n")[0]
            # Extract text between first ** and end - get Company part (after first comma)
            match = re.search(r"\*\*([^*]+)\*\*\s*,\s*([^,]+)", first_line)
            if match:
                company_in_output = _normalize(match.group(2).strip())
                if company_in_output and not any(
                    company_in_output in c or c in company_in_output
                    for c in exp["companies"]
                ):
                    violations.append(
                        Violation(
                            claim=f"Company '{match.group(2).strip()}' not in profile",
                            source="experience",
                            expected="Use ONLY companies from profile",
                        )
                    )

    passed = len(violations) == 0
    v_list = [{"claim": v.claim, "source": v.source, "expected": v.expected} for v in violations]
    feedback = ""
    if not passed:
        feedback = "VALIDATION FAILED: " + "; ".join(
            f"{v.claim} ({v.expected})" for v in violations[:5]
        )
    return {
        "passed": passed,
        "violations": v_list,
        "feedback": feedback,
    }
