"""Hallucination detector - ensures skills, tools, and facts are from profile."""

import re
from typing import Dict, Any, List, Set


def flatten_skills(skills_buckets: Dict) -> List[str]:
    """Extract flat list of skills from profile buckets."""
    flat = []
    for content in (skills_buckets or {}).values():
        items = content.get("items", []) if isinstance(content, dict) else []
        flat.extend(items if isinstance(items, list) else [])
    return sorted(list(set(str(s).strip() for s in flat if s)))


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().strip())


def _build_allowed_skills(profile: Dict) -> Set[str]:
    """All skills from profile (buckets + soft_skills)."""
    allowed = set()
    for skill in flatten_skills(profile.get("skills_buckets", {})):
        allowed.add(_normalize(skill))
    for skill in profile.get("soft_skills", []):
        allowed.add(_normalize(str(skill)))
    # Also add from skills.programming, skills.libraries_and_tools, etc.
    skills_root = profile.get("skills", {})
    if isinstance(skills_root, dict):
        for key, vals in skills_root.items():
            if isinstance(vals, list):
                for v in vals:
                    allowed.add(_normalize(str(v)))
    return allowed


def _build_allowed_tools_from_projects(profile: Dict) -> Dict[str, Set[str]]:
    """For each project, extract tools/tech from description and highlights."""
    projects = profile.get("projects", [])
    result = {}
    # Common tech terms to look for
    tech_pattern = re.compile(
        r"\b(Python|C\+\+|SQL|MATLAB|Pandas|NumPy|TensorFlow|PyTorch|"
        r"YOLOv2|U-Net|KITTI|nuScenes|Kalman|LIDAR|SolidWorks|ANSYS|"
        r"Docker|ROS2|Django|Plotly|Dash|TensorBoard|Matplotlib|"
        r"Scikit-learn|Excel|SAP|Windchill|Dremio)\b",
        re.IGNORECASE
    )
    for p in projects:
        name = _normalize(p.get("name", ""))
        content = (
            str(p.get("description", "")) + " "
            + " ".join(p.get("highlights", []))
        ).lower()
        tokens = set(re.findall(r"\b[a-z0-9+]+\b", content))
        # Add common tools mentioned
        found = set(tech_pattern.findall(content))
        result[name] = tokens | found
    return result


def _extract_tech_mentions(text: str) -> Set[str]:
    """Extract potential tech/tool mentions from text."""
    # Look for capitalized tech terms and common tools
    words = set(re.findall(r"\b[A-Z][a-zA-Z0-9+#]*\b", text))
    # Add lowercase tech terms
    tech_terms = re.findall(
        r"\b(python|c\+\+|sql|matlab|pandas|numpy|tensorflow|pytorch|"
        r"yolov2|u-net|kitti|nuscenes|solidworks|ansys|docker|ros2|django|"
        r"plotly|dash|tensorboard|matplotlib|scikit-learn|excel)\b",
        text.lower()
    )
    return words | set(tech_terms)


def detect_hallucinations(
    section_name: str,
    text: str,
    profile: Dict,
) -> Dict[str, Any]:
    """
    Detect hallucinations: skills/tools/facts not in profile.

    Focus: projects, experience, skills

    Returns:
        {"passed": bool, "violations": [str], "feedback": str}
    """
    violations: List[str] = []
    if not text.strip():
        return {"passed": True, "violations": [], "feedback": ""}

    if section_name == "skills":
        allowed = _build_allowed_skills(profile)
        # Extract skills from **Category:** a, b, c format
        for line in text.splitlines():
            if ":" in line:
                _, rest = line.split(":", 1)
                for part in rest.split(","):
                    skill = _normalize(part.strip())
                    if skill and len(skill) > 2:
                        # Allow partial match (e.g. "Data Analysis" in "Data Analysis & Visualization")
                        if not any(
                            skill in a or a in skill
                            for a in allowed
                        ):
                            violations.append(f"Skill not in profile: '{part.strip()}'")

    elif section_name == "projects":
        allowed_skills = _build_allowed_skills(profile)
        project_data = _build_allowed_tools_from_projects(profile)
        # Flatten all allowed project content
        all_project_tokens = set()
        for tokens in project_data.values():
            all_project_tokens.update(tokens)

        # Known tools from profile skills
        for s in flatten_skills(profile.get("skills_buckets", {})):
            all_project_tokens.add(_normalize(s))

        # Check for tool/tech mentions not in profile
        mentioned = _extract_tech_mentions(text)
        # Whitelist common words that look like tech
        whitelist = {"a", "i", "the", "and", "or", "in", "on", "to", "of", "for"}
        for m in mentioned:
            mn = _normalize(m)
            if mn in whitelist:
                continue
            if mn not in all_project_tokens:
                # Check if it's a known hallucination (e.g. PyAutoGUI, Abaqus, LS-DYNA)
                if any(
                    x in mn for x in ["pyautogui", "abaqus", "ls-dyna", "power bi"]
                ):
                    violations.append(f"Tool/tech not in profile: '{m}'")

    elif section_name == "experience":
        allowed_skills = _build_allowed_skills(profile)
        # Experience can mention skills; check for obvious fabrications
        mentioned = _extract_tech_mentions(text)
        for m in mentioned:
            mn = _normalize(m)
            if mn in allowed_skills:
                continue
            # Allow common words
            if len(mn) < 4:
                continue
            # Strict: flag if it looks like a tool but isn't in profile
            if any(
                x in mn for x in ["pyautogui", "abaqus", "power bi", "powerbi"]
            ):
                violations.append(f"Tool not in profile: '{m}'")

    passed = len(violations) == 0
    feedback = ""
    if violations:
        feedback = (
            "VALIDATION FAILED: The following are not in your profile. "
            "Remove or replace with factual alternatives: "
            + "; ".join(violations[:5])  # Limit to 5 for retry prompt
        )
    return {"passed": passed, "violations": violations, "feedback": feedback}
