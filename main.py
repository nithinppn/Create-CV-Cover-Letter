import yaml
import ollama
import os
import sys
import re
import glob
import logging
import shutil
from jinja2 import Template
from datetime import date, datetime
import pypandoc
import unicodedata


def ensure_tex_in_path():
    """Add TeX bin to PATH if xelatex/pdflatex not found. Supports MacTeX and BasicTeX on macOS."""
    # Allow user override: export TEXBIN=/path/to/texlive/.../bin/universal-darwin
    texbin = os.environ.get("TEXBIN")
    if texbin and os.path.isdir(texbin):
        os.environ["PATH"] = texbin + os.pathsep + os.environ.get("PATH", "")
    if shutil.which("xelatex") or shutil.which("pdflatex"):
        return
    # Refresh PATH from macOS path_helper (loads /etc/paths.d/ including TeX)
    try:
        import subprocess
        result = subprocess.run(
            ["/usr/libexec/path_helper", "-s"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0 and "PATH=" in result.stdout:
            for part in result.stdout.strip().split(";"):
                part = part.strip()
                if part.startswith("PATH="):
                    path_val = part.split("=", 1)[1].strip().strip('"')
                    os.environ["PATH"] = path_val
                    break
    except Exception:
        pass
    if shutil.which("xelatex") or shutil.which("pdflatex"):
        return
    candidates = [
        "/Library/TeX/texbin",  # MacTeX / BasicTeX (Homebrew)
        "/usr/local/texlive/2025/bin/universal-darwin",
        "/usr/local/texlive/2025/bin/arm64-darwin",
        "/usr/local/texlive/2025/bin/x86_64-darwin",
        "/usr/local/texlive/2024/bin/universal-darwin",
        "/usr/local/texlive/2024/bin/arm64-darwin",
        "/usr/local/texlive/2024/bin/x86_64-darwin",
        "/usr/local/texlive/2024basic/bin/universal-darwin",
        "/usr/local/texlive/2024basic/bin/arm64-darwin",
        "/usr/local/texlive/2024basic/bin/x86_64-darwin",
    ]
    for pattern in ["/usr/local/texlive/*/bin/*-darwin", "/usr/local/texlive/*/bin/universal-darwin"]:
        candidates.extend(glob.glob(pattern))
    for path in candidates:
        if path and os.path.isdir(path):
            xelatex_path = os.path.join(path, "xelatex")
            pdflatex_path = os.path.join(path, "pdflatex")
            if os.path.isfile(xelatex_path) or os.path.isfile(pdflatex_path):
                os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
                return

# ---------- LOGGING ----------
LOG_DIR = "debug_logs"
DEBUG = os.environ.get("CV_DEBUG", "0") == "1"
_logger = None


def setup_logging():
    """Configure logging. Set CV_DEBUG=1 to enable verbose debug output to file and console."""
    global _logger
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"run_{timestamp}.log")

    if DEBUG:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s | %(levelname)s | %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(),
            ],
            force=True,
        )
        logging.getLogger().info(f"Debug logging enabled. Log file: {log_file}")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(message)s", force=True)

    _logger = logging.getLogger(__name__)
    return _logger


def log_step(step_name, prompt=None, raw_output=None, processed_output=None, extra=None):
    """Log a processing step with inputs and outputs."""
    if not DEBUG or _logger is None:
        return
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


def latex_escape(text):
    """
    Normalize, flatten, and escape text for LaTeX macros.
    """
    if not text:
        return ""

    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)

    # Replace smart punctuation
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")

    # Remove line breaks and multiple spaces
    text = re.sub(r"\s+", " ", text).strip()

    # Escape LaTeX specials
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "\\": r"\textbackslash{}"
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    return text


# ================= CONFIGURATION =================
PROFILE_PATH = "profile.yaml"
TEMPLATE_PATH = "template_cv.md"
PROMPTS_PATH = "prompts.yaml"
JOB_INPUT_FILE = "job_input.yaml"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# =================================================


# ---------- UTILITIES ----------

def check_ollama_connection():
    """Checks if Ollama is running before starting."""
    try:
        ollama.list()
    except Exception:
        print("\n❌ Error: Could not connect to Ollama.")
        print("   Please open a terminal and run: 'ollama serve'")
        sys.exit(1)

def load_yaml(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"❌ Error parsing YAML: {e}")
        sys.exit(1)

def load_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"❌ Error: File not found: {path}")
        sys.exit(1)

def convert_md_to_pdf(md_file, pdf_file):

    print("🔧 Generating PDF...")

    try:
        ensure_tex_in_path()
        use_xelatex = shutil.which("xelatex")
        use_pdflatex = shutil.which("pdflatex")
        if not use_xelatex and not use_pdflatex:
            raise RuntimeError(
                "Neither xelatex nor pdflatex found. Install BasicTeX: brew install --cask basictex\n"
                "Then restart the terminal or run: eval \"$(/usr/libexec/path_helper -s)\""
            )

        if use_xelatex:
            engine, template = "xelatex", "resume_rendered.tex"
            print("📄 Using XeLaTeX with resume_rendered.tex")
        else:
            # pdflatex fallback: render pdflatex-compatible template
            from jinja2 import Template as JinjaTemplate
            profile = load_yaml(PROFILE_PATH)
            escaped_basics = {
                k: latex_escape(v) if isinstance(v, str) else v
                for k, v in profile["basics"].items()
            }
            pdflatex_template_str = load_file("resume_template_pdflatex.tex")
            rendered = JinjaTemplate(pdflatex_template_str).render(basics=escaped_basics)
            with open("resume_rendered_pdflatex.tex", "w", encoding="utf-8") as f:
                f.write(rendered)
            engine, template = "pdflatex", "resume_rendered_pdflatex.tex"
            print("📄 Using pdflatex fallback (resume_rendered_pdflatex.tex)")

        output = pypandoc.convert_file(
            md_file,
            "pdf",
            outputfile=pdf_file,
            extra_args=[
                f"--pdf-engine={engine}",
                f"--template={template}",
                "--wrap=preserve"
            ]
        )

        print("Pandoc output:", output)
        print(f"✅ PDF created: {pdf_file}")
        log_step("CV PDF Conversion", extra={"input": md_file, "output": pdf_file, "status": "success"})

    except Exception as e:
        print("❌ PDF conversion failed:")
        print("Error:", e)
        log_step("CV PDF Conversion", extra={"input": md_file, "output": pdf_file, "status": "failed", "error": str(e)})


def normalize_spacing(text):
    """
    Ensures blank lines between blocks for Pandoc.
    """
    if not text:
        return ""

    # Ensure double line breaks between paragraphs
    text = re.sub(r'\n{2,}', '\n\n', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', '\n\n', text)

    return text.strip()

def convert_cover_letter_to_pdf(md_file, pdf_file):

    print("🔧 Generating Cover Letter PDF...")

    try:
        ensure_tex_in_path()
        engine = "xelatex" if shutil.which("xelatex") else ("pdflatex" if shutil.which("pdflatex") else None)
        if not engine:
            raise RuntimeError(
                "Neither xelatex nor pdflatex found. Install BasicTeX: brew install --cask basictex"
            )
        if engine == "pdflatex":
            print("📄 Using pdflatex for cover letter")

        output = pypandoc.convert_file(
            md_file,
            "pdf",
            outputfile=pdf_file,
            extra_args=[
                f"--pdf-engine={engine}",
                "--wrap=preserve"
            ]
        )

        print(f"✅ Cover Letter PDF created: {pdf_file}")
        log_step("Cover Letter PDF Conversion", extra={"input": md_file, "output": pdf_file, "status": "success"})

    except Exception as e:
        print("❌ Cover Letter PDF conversion failed:")
        print("Error:", e)
        log_step("Cover Letter PDF Conversion", extra={"input": md_file, "output": pdf_file, "status": "failed", "error": str(e)})


# ---------- MAIN EXECUTION ----------

if __name__ == "__main__":
    from agents.orchestrator import run as orchestrator_run

    setup_logging()
    from cv_core import load_prompts_config
    load_prompts_config()
    check_ollama_connection()

    DOCS_DIR = "docs"
    os.makedirs(DOCS_DIR, exist_ok=True)

    # Load Data
    profile = load_yaml(PROFILE_PATH)
    template_str = load_file(TEMPLATE_PATH)

    log_step("Startup", extra={
        "profile_basics": str(profile.get("basics", {})),
        "profile_keys": list(profile.keys()),
    })

    # Escape LaTeX-sensitive fields (IMPORTANT)
    escaped_basics = {
        k: latex_escape(v) if isinstance(v, str) else v
        for k, v in profile["basics"].items()
    }

    # Resolve input file path (script dir or cwd)
    input_path = os.path.join(SCRIPT_DIR, JOB_INPUT_FILE)
    if not os.path.exists(input_path):
        input_path = JOB_INPUT_FILE
    # Support --input / -i
    if len(sys.argv) > 1 and sys.argv[1] in ("--input", "-i") and len(sys.argv) > 2:
        input_path = sys.argv[2]
        if not os.path.isabs(input_path):
            input_path = os.path.join(SCRIPT_DIR, input_path)

    # Read input: from file if present, else interactive
    if os.path.exists(input_path):
        if not (input_path.endswith(".yaml") or input_path.endswith(".yml")):
            print(f"❌ Input file must be YAML (.yaml or .yml): {input_path}")
            sys.exit(1)
        data = load_yaml(input_path)
        company_input = (data.get("company") or "").strip() or "General"
        jd_text = (data.get("job_description") or "").strip()
        print(f"📂 Read input from {input_path}")
        print(f"   Company: {company_input}")
        print(f"   JD length: {len(jd_text)} chars")
    else:
        print("\n" + "=" * 50)
        print("🏢 ENTER COMPANY NAME (or create job_input.yaml - see job_input.example.yaml)")
        print("=" * 50)
        company_input = input("Target Company: ").strip()
        if not company_input:
            company_input = "General"
        print("\n" + "=" * 50)
        print("📋 PASTE JOB DESCRIPTION (Type 'DONE' to finish)")
        print("=" * 50)
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "DONE":
                    break
                lines.append(line)
            except EOFError:
                break
        jd_text = "\n".join(lines)

    company_safe = re.sub(r'[^a-zA-Z0-9_-]', '', company_input.replace(' ', '_'))
    if not company_safe:
        company_safe = "General"

    log_step("User Input", extra={
        "company": company_input,
        "company_safe": company_safe,
        "jd_length": len(jd_text),
        "jd_text": jd_text,
    })

    # Run agentic pipeline (orchestrator with validation + retry)
    result = orchestrator_run(
        profile=profile,
        jd=jd_text,
        max_retries=2,
        use_parallel=True,
        log_step_fn=log_step,
    )
    archetypes = result["archetypes"]
    summary_md = result["summary"]
    education_md = result["education"]
    skills_md = result["skills"]
    certs_md = result["certifications"]
    projects_md = result["projects"]
    experience_md = result["experience"]
    cover_letter_md = result["cover_letter"]

    log_step("Archetypes Final", processed_output=str(archetypes))

    # 3. Render Markdown Template (Jinja → Markdown)
    template = Template(
        template_str,
        trim_blocks=False,
        lstrip_blocks=False
    )

    final_cv = template.render(
        basics=escaped_basics,
        summary_placeholder=summary_md,
        education_placeholder=education_md,
        certifications_placeholder=certs_md,
        skills_placeholder=skills_md,
        projects_placeholder=projects_md,
        experience_placeholder=experience_md
    )

    log_step("Final Placeholders (pre-render)", extra={
        "summary_preview": (summary_md[:300] + "...") if len(summary_md) > 300 else summary_md,
        "education_preview": (education_md[:300] + "...") if len(education_md) > 300 else education_md,
        "skills_preview": (skills_md[:300] + "...") if len(skills_md) > 300 else skills_md,
        "projects_preview": (projects_md[:300] + "...") if len(projects_md) > 300 else projects_md,
        "experience_preview": (experience_md[:300] + "...") if len(experience_md) > 300 else experience_md,
        "cover_letter_preview": (cover_letter_md[:300] + "...") if len(cover_letter_md) > 300 else cover_letter_md,
    })
    log_step("Final CV Markdown", processed_output=final_cv[:1500] + ("..." if len(final_cv) > 1500 else ""))
    log_step("Final Cover Letter Markdown", processed_output=cover_letter_md)

    # 4. Render LaTeX Template (Jinja → LaTeX)
    latex_template_str = load_file("resume_template.tex")
    latex_template = Template(latex_template_str)

    rendered_latex = latex_template.render(
        basics=escaped_basics
    )

    with open("resume_rendered.tex", "w", encoding="utf-8") as f:
        f.write(rendered_latex)

    # 5. Save Markdown & Cover Letter
    today_iso = date.today().isoformat()

    cv_filename = os.path.join(DOCS_DIR, f"CV_{company_safe}_{today_iso}.md")
    cl_filename = os.path.join(DOCS_DIR, f"CoverLetter_{company_safe}_{today_iso}.md")

    with open(cv_filename, "w", encoding="utf-8") as f:
        f.write(final_cv)

    with open(cl_filename, "w", encoding="utf-8") as f:
        f.write(cover_letter_md)

    # 6. Convert CV to PDF (using rendered LaTeX template)
    pdf_filename = os.path.join(DOCS_DIR, f"CV_{company_safe}_{today_iso}.pdf")

    convert_md_to_pdf(cv_filename, pdf_filename)

    # Convert Cover Letter to PDF
    cl_pdf_filename = os.path.join(DOCS_DIR, f"CoverLetter_{company_safe}_{today_iso}.pdf")
    convert_cover_letter_to_pdf(cl_filename, cl_pdf_filename)

    print("\n" + "=" * 50)
    print("✅ GENERATION COMPLETE")
    print(f"📄 CV: {cv_filename}")
    print(f"📄 CV (PDF): {pdf_filename}")
    print(f"✉️  Cover Letter: {cl_filename}")
    if DEBUG:
        print(f"📋 Debug log: {LOG_DIR}/run_*.log")
    print("=" * 50)
