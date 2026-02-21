"""Project pre-filter - bag-of-words overlap to reduce candidate pool for LLM."""

import re
from typing import List, Dict, Any

# Default pool size (override via parameter)
DEFAULT_CANDIDATE_POOL_SIZE = 8


def pre_filter_projects(
    all_projects: List[Dict],
    jd_text: str,
    candidate_pool_size: int = DEFAULT_CANDIDATE_POOL_SIZE,
    log_step_fn=None,
) -> List[Dict]:
    """
    Python-side heuristic: count how many words from the JD appear in project details.
    Returns the top N candidates to the LLM to save token space.

    Args:
        all_projects: List of project dicts with name, description, highlights
        jd_text: Job description text
        candidate_pool_size: Max number of projects to return
        log_step_fn: Optional logging function(step_name, extra={})

    Returns:
        Top N projects by JD overlap score
    """
    if not all_projects:
        return []

    jd_tokens = set(re.findall(r"\w+", jd_text.lower()))
    scored_projects = []

    for p in all_projects:
        p_content = (
            str(p.get("name", ""))
            + " "
            + str(p.get("description", ""))
            + " "
            + " ".join(p.get("highlights", []))
        ).lower()
        p_tokens = re.findall(r"\w+", p_content)
        score = sum(1 for token in p_tokens if token in jd_tokens)
        scored_projects.append((score, p))

    scored_projects.sort(key=lambda x: x[0], reverse=True)
    result = [p for s, p in scored_projects[:candidate_pool_size]]

    if log_step_fn:
        log_step_fn(
            "Project Pre-filter",
            extra={
                "total_projects": len(all_projects),
                "candidates_count": len(result),
                "candidate_names": [p.get("name") for p in result],
            },
        )
    return result
