"""LLM client for Ollama - generates content via chat."""

import ollama
from typing import Callable, Optional

from cv_core import MODEL, clean_ai_output


def generate(
    prompt: str,
    label: str,
    model: str = MODEL,
    temperature: float = 0.2,
    log_step_fn: Optional[Callable] = None,
) -> str:
    """
    Call Ollama chat and return cleaned content.

    Args:
        prompt: User prompt
        label: Label for logging (e.g. "Professional Summary")
        model: Ollama model name
        temperature: Sampling temperature
        log_step_fn: Optional log_step(step_name, prompt=, raw_output=, processed_output=)

    Returns:
        Cleaned LLM output text
    """
    print(f"--> 🧠 Generating {label}...")
    try:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": temperature},
        )
        raw = response["message"]["content"]
        cleaned = clean_ai_output(raw)
        if log_step_fn:
            log_step_fn(label, prompt=prompt, raw_output=raw, processed_output=cleaned)
        return cleaned
    except Exception as e:
        print(f"⚠️ Error generating {label}: {e}")
        if log_step_fn:
            try:
                log_step_fn(label, extra={"error": str(e)})
            except Exception:
                pass
        raise
