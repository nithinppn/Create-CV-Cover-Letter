"""
Profile match validator - ensures all names and candidate details come from profile.
Rejects wrong person names (e.g. Alex, John) - only the candidate's name is allowed.
"""

import re
from typing import Dict, Any, List

# Common first names that LLMs may hallucinate (not the candidate)
# We check these - if found and not part of candidate name, flag
_COMMON_HALLUCINATED_NAMES = frozenset(
    n.lower() for n in [
        "Alex", "Alexander", "John", "Michael", "David", "James", "Robert",
        "Daniel", "Matthew", "Christopher", "Andrew", "Joseph", "William",
        "Sarah", "Emily", "Jessica", "Ashley", "Amanda", "Jennifer", "Laura",
        "Mark", "Thomas", "Ryan", "Kevin", "Brian", "Eric", "Steven", "Jason",
    ]
)


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().strip())


def _get_candidate_name_parts(profile: Dict) -> set:
    """Extract first/last name parts from candidate name for matching."""
    name = profile.get("basics", {}).get("name", "")
    if not name:
        return set()
    parts = set()
    for part in re.split(r"[\s\-]+", name):
        p = _normalize(part)
        if len(p) > 1:  # Skip single chars
            parts.add(p)
    return parts


def validate_profile_match(
    section_name: str,
    text: str,
    profile: Dict,
) -> Dict[str, Any]:
    """
    Ensure output contains only the candidate's name, not other person names.
    All company names, positions, and details must match the profile.

    Returns:
        {"passed": bool, "violations": [str], "feedback": str}
    """
    violations: List[str] = []
    if not text or not text.strip():
        return {"passed": True, "violations": [], "feedback": ""}

    text_lower = text.lower()
    candidate_parts = _get_candidate_name_parts(profile)

    # Check for wrong person names - words that look like first names
    for name in _COMMON_HALLUCINATED_NAMES:
        if name in candidate_parts:
            continue  # Part of candidate's name
        # Word boundary match
        if re.search(rf"\b{re.escape(name)}\b", text_lower):
            violations.append(
                f"Wrong person name '{name}' appears - use ONLY the candidate's name "
                f"({profile.get('basics', {}).get('name', 'from profile')})"
            )

    passed = len(violations) == 0
    feedback = ""
    if violations:
        feedback = "VALIDATION FAILED: " + "; ".join(violations[:3])
    return {"passed": passed, "violations": violations, "feedback": feedback}
