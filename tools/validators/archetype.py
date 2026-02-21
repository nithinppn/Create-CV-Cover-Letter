"""Archetype validator - ensures parsed archetypes are valid."""

from typing import List, Dict, Any


def validate_archetypes(
    archetypes: List[str],
    allowed_archetypes: List[str],
    expected_count: int = 3,
) -> Dict[str, Any]:
    """
    Validate that archetypes from identify_archetypes() are valid.

    Args:
        archetypes: Parsed archetype list from LLM
        allowed_archetypes: Allowed archetype names (from TASK_ARCHETYPES)
        expected_count: Expected number of archetypes (default 3)

    Returns:
        {"valid": bool, "errors": [...]}
    """
    errors = []
    allowed_set = set(allowed_archetypes)

    if not isinstance(archetypes, list):
        return {"valid": False, "errors": ["Archetypes must be a list"]}

    if len(archetypes) != expected_count:
        errors.append(
            f"Expected exactly {expected_count} archetypes, got {len(archetypes)}"
        )

    for i, arch in enumerate(archetypes):
        if not isinstance(arch, str):
            errors.append(f"Archetype at index {i} must be a string, got {type(arch)}")
        elif arch not in allowed_set:
            errors.append(
                f"Invalid archetype '{arch}' at index {i}. "
                f"Choose only from: {allowed_archetypes}"
            )

    valid = len(errors) == 0
    return {"valid": valid, "errors": errors}
