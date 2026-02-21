"""
Orchestrator agent - coordinates section generation with validation and retry.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional, Callable

from cv_core import load_prompts_config, TASK_ARCHETYPES, fix_unicode_escapes
from llm_client import generate as llm_generate
from agents import generators
from tools.validators import (
    validate_archetypes as validate_archetypes_tool,
    validate_section_format,
    fact_check,
    detect_hallucinations,
    validate_length,
)
from tools.validators.format import _load_rules

_logger: Optional[logging.Logger] = None


def _get_logger() -> Optional[logging.Logger]:
    return _logger


def set_logger(logger: Optional[logging.Logger]):
    global _logger
    _logger = logger


def _log_step(step_name: str, prompt=None, raw_output=None, processed_output=None, extra=None):
    """Delegate to main's log_step if available."""
    if _logger and getattr(_logger, "_debug_enabled", False):
        _logger.info("=" * 60)
        _logger.info(f"STEP: {step_name}")
        _logger.info("=" * 60)
        if prompt is not None:
            _logger.debug(f"PROMPT (len={len(prompt)}):\n{prompt}")
        if raw_output is not None:
            _logger.debug(f"RAW LLM OUTPUT:\n{raw_output}")
        if processed_output is not None:
            _logger.debug(f"PROCESSED OUTPUT:\n{processed_output}")
        if extra:
            for k, v in extra.items():
                _logger.debug(f"{k}: {v}")


def _generate_with_log(prompt: str, label: str) -> str:
    """Wrapper that calls llm_generate with log_step."""
    return llm_generate(prompt, label, log_step_fn=_log_step)


def _generate_with_feedback(
    section_name: str,
    gen_fn: Callable[[], str],
    validators: List[Callable[[str], Dict]],
    max_retries: int = 2,
) -> str:
    """
    Generate section with retry on validation failure.

    Args:
        section_name: For logging
        gen_fn: Callable that returns generated text (may accept feedback)
        validators: List of (text) -> {valid/passed: bool, errors/violations/feedback: ...}
        max_retries: Max retries before accepting output

    Returns:
        Generated text (possibly after retries)
    """
    feedback_parts: List[str] = []
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"    (Retry {attempt}/{max_retries} for {section_name})")
        text = gen_fn(feedback_parts[-1] if feedback_parts else None)
        text = (text or "").strip()
        text = fix_unicode_escapes(text)

        all_pass = True
        new_feedback = []

        for v_fn in validators:
            result = v_fn(text)
            if "valid" in result and not result["valid"]:
                all_pass = False
                new_feedback.extend(result.get("errors", []))
            if "passed" in result and not result["passed"]:
                all_pass = False
                new_feedback.append(result.get("feedback", ""))
                new_feedback.extend(result.get("violations", []))

        if all_pass:
            return text

        feedback = "VALIDATION FAILED: " + "; ".join(str(x) for x in new_feedback if x)
        feedback_parts.append(feedback)
        if _logger:
            _logger.info(f"Validation failed for {section_name}: {feedback}")

    return text  # Return last attempt even if validation failed


def run(
    profile: Dict,
    jd: str,
    max_retries: int = 2,
    use_parallel: bool = True,
    log_step_fn: Optional[Callable] = None,
) -> Dict[str, str]:
    """
    Run the full agentic CV generation pipeline.

    Returns:
        Dict with keys: summary, education, skills, certifications, projects,
        experience, cover_letter, archetypes
    """
    global _log_step
    if log_step_fn:
        _log_step = log_step_fn

    load_prompts_config()
    rules = _load_rules()
    max_retries = rules.get("max_retries", max_retries)

    # 1. Archetype analysis with validation and retry
    archetypes = []
    for attempt in range(max_retries + 1):
        archetypes = generators.identify_archetypes(
            jd, TASK_ARCHETYPES,
            generate_fn=_generate_with_log,
            log_step_fn=_log_step,
        )
        result = validate_archetypes_tool(archetypes, TASK_ARCHETYPES, expected_count=3)
        if result["valid"]:
            break
        if attempt < max_retries:
            print(f"    (Retry archetypes: {result['errors']})")
        # TODO: could inject feedback into prompt for retry

    print(f"\n🔎 Identified Archetypes: {archetypes}\n")

    def _normalize_spacing(t: str) -> str:
        import re
        if not t:
            return ""
        t = re.sub(r"\n{2,}", "\n\n", t)
        t = re.sub(r"(?<!\n)\n(?!\n)", "\n\n", t)
        return t.strip()

    def _validators_for(section: str, profile_data: Dict):
        v = []
        v.append(lambda txt: validate_section_format(section, txt, rules))
        if section in ("education", "certifications", "projects", "experience"):
            v.append(lambda txt: fact_check(section, txt, profile_data))
        if section in ("projects", "experience", "skills"):
            v.append(lambda txt: detect_hallucinations(section, txt, profile_data))
        if section == "cover_letter":
            v.append(
                lambda txt: validate_length(
                    section, txt,
                    min_words=180, max_words=350,
                )
            )
        return v

    # Closure for generators that need to accept feedback
    feedback_holder: List[Optional[str]] = [None]

    def _make_gen(section: str, gen_callable, *args, **kwargs):
        def _gen(feedback: Optional[str] = None):
            feedback_holder[0] = feedback
            extra = f"\n\n{feedback}" if feedback else ""
            # Generators don't support feedback injection yet - we pass via prompt
            # For now, just call the generator; full feedback would need prompt modification
            return gen_callable(*args, **kwargs)
        return _gen

    # 2. Parallel: Education, Certifications, Soft Skills (soft skills merged into skills)
    education_md = ""
    certs_md = ""
    if use_parallel:
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {
                ex.submit(
                    generators.generate_smart_education,
                    profile, jd, archetypes,
                    _generate_with_log, _log_step,
                ): "education",
                ex.submit(
                    generators.generate_smart_certifications,
                    profile, jd, archetypes,
                    _generate_with_log, _log_step,
                ): "certifications",
            }
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    out = fut.result()
                    if name == "education":
                        education_md = _normalize_spacing(out)
                    else:
                        certs_md = _normalize_spacing(out)
                except Exception as e:
                    print(f"⚠️ Error generating {name}: {e}")
                    if _logger:
                        _logger.exception(f"Error generating {name}")
    else:
        education_md = _normalize_spacing(
            generators.generate_smart_education(
                profile, jd, archetypes, _generate_with_log, _log_step
            )
        )
        certs_md = _normalize_spacing(
            generators.generate_smart_certifications(
                profile, jd, archetypes, _generate_with_log, _log_step
            )
        )

    # 3. Summary
    summary_md = _normalize_spacing(
        generators.generate_professional_summary(
            profile, jd, archetypes, _generate_with_log, _log_step
        )
    )

    # 4. Skills
    skills_md = _normalize_spacing(
        generators.generate_smart_skills(
            profile, jd, archetypes, _generate_with_log, _log_step
        )
    )

    # 5. Projects (with validation + retry)
    def _gen_projects(fb):
        return generators.generate_smart_projects(
            profile, jd, archetypes, _generate_with_log, _log_step, feedback=fb
        )
    proj_validators = _validators_for("projects", profile)
    projects_md = _normalize_spacing(
        _generate_with_feedback("projects", _gen_projects, proj_validators, max_retries)
    )

    # 6. Experience (with validation + retry)
    def _gen_experience(fb):
        return generators.generate_experience(
            profile, jd, archetypes, _generate_with_log, _log_step, feedback=fb
        )
    exp_validators = _validators_for("experience", profile)
    experience_md = _normalize_spacing(
        _generate_with_feedback("experience", _gen_experience, exp_validators, max_retries)
    )

    # 7. Cover Letter
    cover_letter_md = generators.generate_cover_letter(
        profile, jd, archetypes, _generate_with_log, _log_step
    )

    return {
        "summary": summary_md,
        "education": education_md,
        "skills": skills_md,
        "certifications": certs_md,
        "projects": projects_md,
        "experience": experience_md,
        "cover_letter": cover_letter_md,
        "archetypes": archetypes,
    }
