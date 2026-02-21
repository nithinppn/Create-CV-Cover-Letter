"""
Core utilities and config for CV generation.
Shared by main.py, agents, and tools.
"""

import re
import json
import yaml
import os
from typing import Dict, List, Any, Optional

# ================= CONFIGURATION =================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = "profile.yaml"
TEMPLATE_PATH = "template_cv.md"
PROMPTS_PATH = "prompts.yaml"
JOB_INPUT_FILE = "job_input.yaml"

MODEL = "phi3:latest"
MAX_PROJECTS_TO_SHOW = 3
MAX_BULLETS_PER_ROLE = 5
CANDIDATE_POOL_SIZE = 8

TASK_ARCHETYPES = [
    "data_analytics", "software_engineering", "embedded_systems",
    "mechanical_engineering", "project_management", "research_ml",
    "cloud_devops", "manufacturing_quality", "supply_chain",
    "consulting_enablement", "digital_transformation"
]

BANNED_PREFIXES = (
    "Here is", "Here are", "Below is", "Sure,", "Certainly",
    "Note:", "I selected", "I've selected", "Based on",
    "These", "This demonstrates", "Let me know",
    "In this version", "The following", "Here's",
    "Note that "
)

# Additional patterns to strip (Phase 5.1 - strengthen clean_ai_output)
BANNED_PATTERNS = (
    "---", "### Follow Up Question", "### Additional", "### Follow-up",
    "### Followup", "### Next Steps", "### Note:",
)

_PROMPTS_CONFIG: Optional[Dict] = None


def load_prompts_config(prompts_path: str = PROMPTS_PATH) -> Dict:
    """Load prompts from prompts.yaml."""
    global _PROMPTS_CONFIG, TASK_ARCHETYPES
    try:
        path = prompts_path if os.path.isabs(prompts_path) else os.path.join(SCRIPT_DIR, prompts_path)
        with open(path, "r", encoding="utf-8") as f:
            _PROMPTS_CONFIG = yaml.safe_load(f)
        if _PROMPTS_CONFIG and "task_archetypes" in _PROMPTS_CONFIG:
            TASK_ARCHETYPES = _PROMPTS_CONFIG["task_archetypes"]
        return _PROMPTS_CONFIG or {"prompts": {}}
    except (FileNotFoundError, yaml.YAMLError):
        _PROMPTS_CONFIG = {"prompts": {}}
        return _PROMPTS_CONFIG


def render_prompt(template_name: str, **kwargs) -> str:
    """Render a prompt template with placeholders."""
    if _PROMPTS_CONFIG is None:
        load_prompts_config()
    prompts = (_PROMPTS_CONFIG or {}).get("prompts", {})
    template = prompts.get(template_name, "")
    for key, value in kwargs.items():
        template = template.replace(f"<<{key}>>", str(value))
    return template.strip()


# ---------- UTILITIES ----------

def fix_unicode_escapes(text: str) -> str:
    """Convert Python-style \\xNN and \\uNNNN escapes to actual Unicode."""
    if not text:
        return text
    text = re.sub(r"\\x([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"\\u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), text)
    return text


def clean_ai_output(text: str) -> str:
    """Removes code blocks, conversational filler, and banned patterns from LLM output."""
    text = fix_unicode_escapes(text)
    text = re.sub(r"```[a-zA-Z]*", "", text)
    text = text.replace("```", "")

    # Remove whole lines matching banned patterns
    for pattern in BANNED_PATTERNS:
        text = re.sub(rf"^{re.escape(pattern)}.*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(rf"\n{re.escape(pattern)}.*", "\n", text, flags=re.IGNORECASE)

    # Remove horizontal rules and similar
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)

    cleaned_lines = []
    for line in text.splitlines():
        if not any(line.strip().startswith(prefix) for prefix in BANNED_PREFIXES):
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def extract_json_from_text(text: str) -> Optional[Dict]:
    """Find and parse JSON object within text."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def flatten_skills(skills_buckets: Dict) -> List[str]:
    """Extract flat list of skills from profile buckets."""
    flat = []
    for content in (skills_buckets or {}).values():
        items = content.get("items", []) if isinstance(content, dict) else []
        flat.extend(items if isinstance(items, list) else [])
    return sorted(list(set(flat)))


def enforce_bullet_limit(text: str, max_bullets: int) -> str:
    """Limit bullets per role/block; reset on header lines."""
    lines = text.split("\n")
    cleaned = []
    count = 0
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if line_stripped.startswith("- ") or line_stripped.startswith("* "):
            if count < max_bullets:
                cleaned.append(line_stripped)
                count += 1
        else:
            if cleaned:
                cleaned.append("")
            cleaned.append(line_stripped)
            count = 0
    return "\n".join(cleaned)


def clean_skills_output(text: str) -> str:
    """Keep only skill category lines (**Category:** ...)."""
    result = []
    for line in text.splitlines():
        if re.match(r"\*\*.+?\*\*:", line.strip()):
            result.append(line.strip())
    return "\n".join(result)
