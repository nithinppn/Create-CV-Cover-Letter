"""
Section generators for CV and Cover Letter.
Extracted from main.py - each generator produces one section.
"""

import json
import re
import yaml
from typing import Dict, List, Callable, Optional

from cv_core import (
    render_prompt,
    extract_json_from_text,
    flatten_skills,
    enforce_bullet_limit,
    clean_skills_output,
    MAX_PROJECTS_TO_SHOW,
    MAX_BULLETS_PER_ROLE,
    CANDIDATE_POOL_SIZE,
)
from llm_client import generate as llm_generate
from tools.pre_filter import pre_filter_projects


def identify_archetypes(
    jd: str,
    task_archetypes: List[str],
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
) -> List[str]:
    """Identify top 3 archetypes from JD."""
    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))
    prompt = render_prompt(
        "archetype_analysis",
        TASK_ARCHETYPES=task_archetypes,
        JD_EXCERPT=jd[:1500],
    )
    raw = gen(prompt, "Archetype Analysis")
    data = extract_json_from_text(raw)
    archetypes = data.get("archetypes", []) if data else []
    if log_step_fn:
        log_step_fn("Archetype Parsing", processed_output=str(archetypes), extra={"parsed_json": str(data)})
    return archetypes


def generate_professional_summary(
    profile: Dict,
    jd: str,
    archetypes: List[str],
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
    feedback: Optional[str] = None,
) -> str:
    """Generate 3-4 sentence professional summary."""
    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))
    prompt = render_prompt(
        "professional_summary",
        CURRENT_ROLE=profile.get("basics", {}).get("label", "Professional"),
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:800],
        BACKGROUND_SUMMARY=profile.get("basics", {}).get("summary", ""),
    )
    if feedback:
        prompt = prompt + "\n\n" + feedback
    return gen(prompt, "Professional Summary")


def generate_smart_education(
    profile: Dict,
    jd: str,
    archetypes: List[str],
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
    feedback: Optional[str] = None,
) -> str:
    """Generate education section with relevant coursework."""
    education = profile.get("education", [])
    if not education:
        return ""
    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))
    prompt = render_prompt(
        "education",
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:800],
        EDUCATION_YAML=yaml.dump(education),
    )
    if feedback:
        prompt = prompt + "\n\n" + feedback
    return gen(prompt, "Smart Education Section")


def generate_smart_certifications(
    profile: Dict,
    jd: str,
    archetypes: List[str],
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
    feedback: Optional[str] = None,
) -> str:
    """Generate certifications section."""
    certs = profile.get("certifications", [])
    if not certs:
        return ""
    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))
    prompt = render_prompt(
        "certifications",
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:800],
        CERTIFICATIONS_YAML=yaml.dump(certs),
    )
    if feedback:
        prompt = prompt + "\n\n" + feedback
    return gen(prompt, "Smart Certifications Section")


def generate_smart_soft_skills(
    profile: Dict,
    jd: str,
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
) -> str:
    """Select 3-4 soft skills from profile based on JD."""
    soft_pool = profile.get("soft_skills", [])
    if not soft_pool:
        return ""
    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))
    prompt = render_prompt(
        "smart_soft_skills",
        JD_EXCERPT=jd[:800],
        SOFT_SKILLS_JSON=json.dumps(soft_pool),
    )
    return gen(prompt, "Smart Soft Skills")


def generate_smart_skills(
    profile: Dict,
    jd: str,
    archetypes: List[str],
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
) -> str:
    """Generate combined tech + soft skills + languages section."""
    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))

    all_skills = flatten_skills(profile.get("skills_buckets", {}))
    prompt = render_prompt(
        "smart_skills",
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:1000],
        ALL_SKILLS_JSON=json.dumps(all_skills),
    )
    raw = gen(prompt, "Smart Skills Section")
    cleaned_tech = clean_skills_output(raw)
    if log_step_fn:
        log_step_fn("Skills Post-process", raw_output=raw, processed_output=cleaned_tech)

    final_tech_lines = []
    for line in cleaned_tech.split("\n"):
        if ":" in line:
            cat_part, skills_part = line.split(":", 1)
            clean_cat = cat_part.replace("*", "").strip().lower()
            filtered = [
                s.strip()
                for s in skills_part.split(",")
                if s.strip().lower() not in clean_cat
            ]
            if filtered:
                final_tech_lines.append(f"{cat_part}: {', '.join(filtered)}")
        else:
            final_tech_lines.append(line)

    smart_soft = generate_smart_soft_skills(profile, jd, generate_fn, log_step_fn)

    languages = profile.get("languages", [])
    lang_str = ""
    if languages:
        entries = []
        for item in languages:
            if isinstance(item, dict):
                name = item.get("language", "")
                fluency = item.get("fluency", "")
                entries.append(f"{name} ({fluency})" if fluency else name)
            else:
                entries.append(str(item))
        if entries:
            lang_str = "**Languages:** " + ", ".join(entries)

    combined = "\n".join([s for s in ["\n".join(final_tech_lines), smart_soft, lang_str] if s]).strip()
    if log_step_fn:
        log_step_fn("Skills Final Combined", processed_output=combined)
    return combined


def generate_smart_projects(
    profile: Dict,
    jd: str,
    archetypes: List[str],
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
    feedback: Optional[str] = None,
) -> str:
    """Generate projects section with pre-filter."""
    projects = profile.get("projects", [])
    if not projects:
        return ""

    candidates = pre_filter_projects(
        projects, jd,
        candidate_pool_size=CANDIDATE_POOL_SIZE,
        log_step_fn=log_step_fn,
    )
    print(f"    (Filtered {len(projects)} total projects down to {len(candidates)} candidates)")

    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))
    prompt = render_prompt(
        "smart_projects",
        MAX_PROJECTS=MAX_PROJECTS_TO_SHOW,
        JD_EXCERPT=jd[:1000],
        CANDIDATE_PROJECTS_YAML=yaml.dump(candidates),
    )
    if feedback:
        prompt = prompt + "\n\n" + feedback
    return gen(prompt, "Smart Projects Section")


def generate_experience(
    profile: Dict,
    jd: str,
    archetypes: List[str],
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
    feedback: Optional[str] = None,
) -> str:
    """Generate experience section with bullet limit."""
    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))
    prompt = render_prompt(
        "experience",
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:600],
        EXPERIENCE_YAML=yaml.dump(profile.get("experience", [])),
    )
    if feedback:
        prompt = prompt + "\n\n" + feedback
    raw = gen(prompt, "Experience Section")
    text = enforce_bullet_limit(raw, MAX_BULLETS_PER_ROLE)
    if log_step_fn:
        log_step_fn("Experience Bullet Limit", raw_output=raw, processed_output=text)
    return text


def generate_cover_letter(
    profile: Dict,
    jd: str,
    archetypes: List[str],
    generate_fn: Optional[Callable] = None,
    log_step_fn: Optional[Callable] = None,
    feedback: Optional[str] = None,
) -> str:
    """Generate cover letter body."""
    gen = generate_fn or (lambda p, l: llm_generate(p, l, log_step_fn=log_step_fn))
    goals = profile.get("cover_letter_preferences", {}).get("career_goals")
    goals_str = goals if isinstance(goals, str) else (", ".join(goals) if goals else "")
    prompt = render_prompt(
        "cover_letter",
        JD_EXCERPT=jd[:800],
        ARCHETYPES=archetypes,
        CANDIDATE_NAME=profile["basics"]["name"],
        CANDIDATE_LABEL=profile["basics"]["label"],
        CAREER_GOALS=goals_str,
    )
    if feedback:
        prompt = prompt + "\n\n" + feedback
    return gen(prompt, "Cover Letter")
