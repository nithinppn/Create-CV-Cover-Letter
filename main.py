import yaml
import ollama
import os
import sys
import json
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
MODEL = "phi3:latest"  # Using Phi-3 (ollama pull phi3)
PROFILE_PATH = "profile.yaml"
TEMPLATE_PATH = "template_cv.md"
PROMPTS_PATH = "prompts.yaml"
JOB_INPUT_FILE = "job_input.yaml"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# CV Constraints
MAX_PROJECTS_TO_SHOW = 3      # The AI will pick the best N projects
MAX_BULLETS_PER_ROLE = 5      # Max bullets per job experience
CANDIDATE_POOL_SIZE = 8       # Python sends top N matches to AI to save context

# Phrases to strip from AI output to ensure clean Markdown
BANNED_PREFIXES = (
    "Here is", "Here are", "Below is", "Sure,", "Certainly",
    "Note:", "I selected", "I've selected", "Based on",
    "These", "This demonstrates", "Let me know",
    "In this version", "The following", "Here's",
    "Note that "
)

# Loaded from prompts.yaml (fallback if file missing)
TASK_ARCHETYPES = [
    "data_analytics", "software_engineering", "embedded_systems",
    "mechanical_engineering", "project_management", "research_ml",
    "cloud_devops", "manufacturing_quality", "supply_chain",
    "consulting_enablement", "digital_transformation"
]
_PROMPTS_CONFIG = None


def load_prompts_config():
    """Load prompts from prompts.yaml. Falls back to defaults if file missing."""
    global _PROMPTS_CONFIG, TASK_ARCHETYPES
    try:
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            _PROMPTS_CONFIG = yaml.safe_load(f)
        if _PROMPTS_CONFIG and "task_archetypes" in _PROMPTS_CONFIG:
            TASK_ARCHETYPES = _PROMPTS_CONFIG["task_archetypes"]
        return _PROMPTS_CONFIG or {"prompts": {}}
    except (FileNotFoundError, yaml.YAMLError):
        _PROMPTS_CONFIG = {"prompts": {}}
        return _PROMPTS_CONFIG


def render_prompt(template_name, **kwargs):
    """Render a prompt template with the given placeholders."""
    if _PROMPTS_CONFIG is None:
        load_prompts_config()
    prompts = _PROMPTS_CONFIG.get("prompts", {})
    template = prompts.get(template_name, "")
    for key, value in kwargs.items():
        placeholder = f"<<{key}>>"
        template = template.replace(placeholder, str(value))
    return template.strip()
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

def fix_unicode_escapes(text):
    """Convert Python-style \\xNN and \\uNNNN escapes in LLM output to actual Unicode."""
    if not text:
        return text
    text = re.sub(r'\\x([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r'\\u([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), text)
    return text


def clean_ai_output(text):
    """Removes code blocks and conversational filler from LLM output."""
    text = fix_unicode_escapes(text)
    # Remove markdown code fences
    text = re.sub(r'```[a-zA-Z]*', '', text)
    text = text.replace('```', '')
    
    # Filter conversational lines
    cleaned_lines = []
    for line in text.splitlines():
        if not any(line.strip().startswith(prefix) for prefix in BANNED_PREFIXES):
            cleaned_lines.append(line)
    
    return "\n".join(cleaned_lines).strip()

def extract_json_from_text(text):
    """Finds and parses JSON object within text."""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None

def flatten_skills(skills_buckets):
    """Extracts a unique list of all skills from the profile buckets."""
    flat_list = []
    for content in skills_buckets.values():
        flat_list.extend(content.get('items', []))
    # Remove duplicates and sort
    return sorted(list(set(flat_list)))

def enforce_bullet_limit(text, max_bullets):
    """
    Parses text line-by-line. 
    Resets bullet count when a non-bullet line (Header) is found.
    """
    lines = text.split('\n')
    cleaned_lines = []
    current_bullet_count = 0

    for line in lines:
        line = line.strip()
        if not line: 
            continue  # Skip empty lines to prevent double spacing issues

        # Check if line is a bullet point
        if line.startswith('- ') or line.startswith('* '):
            if current_bullet_count < max_bullets:
                cleaned_lines.append(line)
                current_bullet_count += 1
        
        # If not a bullet, it's a Header/Role line
        else:
            # Add a newline before a new header (unless it's the very first line)
            if cleaned_lines:
                cleaned_lines.append("") 
            
            cleaned_lines.append(line)
            current_bullet_count = 0  # Reset counter for the new role
    
    return "\n".join(cleaned_lines)


# ---------- LOGIC ENGINES ----------

def pre_filter_projects(all_projects, jd_text):
    """
    Python-side heuristic:
    Counts how many words from the JD appear in the project details.
    Returns the top N candidates to the LLM to save token space.
    """
    if not all_projects: return []
    
    # Normalize JD words
    jd_tokens = set(re.findall(r'\w+', jd_text.lower()))
    scored_projects = []

    for p in all_projects:
        # Create a "bag of words" for the project
        p_content = (
            str(p.get('name', '')) + " " + 
            str(p.get('description', '')) + " " + 
            " ".join(p.get('highlights', []))
        ).lower()
        
        p_tokens = re.findall(r'\w+', p_content)
        
        # Calculate score: number of intersecting words
        score = sum(1 for token in p_tokens if token in jd_tokens)
        scored_projects.append((score, p))

    # Sort by score descending
    scored_projects.sort(key=lambda x: x[0], reverse=True)

    # Return top N projects (stripping the score)
    result = [p for s, p in scored_projects[:CANDIDATE_POOL_SIZE]]
    log_step(
        "Project Pre-filter",
        extra={
            "total_projects": len(all_projects),
            "candidates_count": len(result),
            "candidate_names": [p.get("name") for p in result],
        },
    )
    return result


# ---------- AI GENERATORS ----------

def generate_professional_summary(profile, jd, archetypes):
    """
    Generates a 3-4 sentence professional summary tailored to the JD.
    """
    basics = profile.get('basics', {})
    prompt = render_prompt(
        "professional_summary",
        CURRENT_ROLE=basics.get('label', 'Professional'),
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:800],
        BACKGROUND_SUMMARY=basics.get('summary', ''),
    )
    return generate(prompt, "Professional Summary")


def generate(prompt, label):
    print(f"--> 🧠 Generating {label}...")
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={'temperature': 0.2}  # Low temp for strict adherence
        )
        raw_content = response["message"]["content"]
        cleaned_content = clean_ai_output(raw_content)
        log_step(label, prompt=prompt, raw_output=raw_content, processed_output=cleaned_content)
        return cleaned_content
    except Exception as e:
        print(f"⚠️ Error generating {label}: {e}")
        if _logger:
            _logger.exception(f"Error generating {label}: {e}")
        return ""

def identify_archetypes(jd):
    prompt = render_prompt(
        "archetype_analysis",
        TASK_ARCHETYPES=TASK_ARCHETYPES,
        JD_EXCERPT=jd[:1500],
    )
    raw = generate(prompt, "Archetype Analysis")
    data = extract_json_from_text(raw)
    archetypes = data.get("archetypes", []) if data else []
    log_step("Archetype Parsing", processed_output=str(archetypes), extra={"parsed_json": str(data)})
    return archetypes


def clean_skills_output(text):
    """
    Removes any explanatory lines accidentally added by the LLM.
    Keeps only lines that look like skill categories.
    """
    cleaned = []

    for line in text.splitlines():
        line = line.strip()

        # Keep only category lines like: **Category:** ...
        if re.match(r"\*\*.+?\:\*\*", line):
            cleaned.append(line)

    return "\n".join(cleaned)

def generate_smart_soft_skills(profile, jd):
    """
    Selects the top 3-4 soft skills from the profile based on the JD.
    """
    soft_pool = profile.get("soft_skills", [])
    
    # If no soft skills in YAML, return empty string
    if not soft_pool:
        return ""

    prompt = render_prompt(
        "smart_soft_skills",
        JD_EXCERPT=jd[:800],
        SOFT_SKILLS_JSON=json.dumps(soft_pool),
    )
    return generate(prompt, "Smart Soft Skills")


def generate_smart_skills(profile, jd, archetypes):
    """
    Feeds ALL skills to the LLM and asks it to curate a specific list.
    """
    all_skills = flatten_skills(profile.get("skills_buckets", {}))
    prompt = render_prompt(
        "smart_skills",
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:1000],
        ALL_SKILLS_JSON=json.dumps(all_skills),
    )

    # --- Safety Net: Clean Tech Skills Redundancy ---
    raw_ai_skills = generate(prompt, "Smart Skills Section")
    cleaned_tech_skills = clean_skills_output(raw_ai_skills)
    log_step("Skills Post-process", raw_output=raw_ai_skills, processed_output=cleaned_tech_skills)

    final_tech_lines = []
    for line in cleaned_tech_skills.split('\n'):
        if ':' in line:
            category_part, skills_part = line.split(':', 1)
            clean_cat = category_part.replace('*', '').strip().lower()
            
            # Filter skills that repeat the category name
            filtered = [s.strip() for s in skills_part.split(',') 
                        if s.strip().lower() not in clean_cat]
            
            if filtered:
                final_tech_lines.append(f"{category_part}: {', '.join(filtered)}")
        else:
            final_tech_lines.append(line)

    # --- PART 2: Smart Soft Skills (AI) ---
    smart_soft_skills = generate_smart_soft_skills(profile, jd)

    # --- PART 3: Languages (Python Mandatory) ---
    languages = profile.get('languages', [])
    formatted_languages = ""
    if languages:
        lang_entries = []
        for item in languages:
            if isinstance(item, dict):
                lang_name = item.get('language', '')
                fluency = item.get('fluency', '')
                entry = f"{lang_name} ({fluency})" if fluency else lang_name
                lang_entries.append(entry)
            elif isinstance(item, str):
                lang_entries.append(item)
        if lang_entries:
            formatted_languages = "**Languages:** " + ", ".join(lang_entries)

    # --- PART 4: Combine All ---
    # We use a list to join them with newlines, filtering out empty strings
    sections = [
        "\n".join(final_tech_lines),
        smart_soft_skills,
        formatted_languages
    ]
    
    # Join with newlines and strip extra whitespace
    combined = "\n".join([s for s in sections if s]).strip()
    log_step("Skills Final Combined", processed_output=combined)
    return combined


def generate_smart_projects(profile, jd, archetypes):
    all_projects = profile.get("projects", [])
    if not all_projects: return ""

    # 1. Python Pre-filter
    candidates = pre_filter_projects(all_projects, jd)
    print(f"    (Filtered {len(all_projects)} total projects down to {len(candidates)} candidates)")

    # 2. LLM Selection
    prompt = render_prompt(
        "smart_projects",
        MAX_PROJECTS=MAX_PROJECTS_TO_SHOW,
        JD_EXCERPT=jd[:1000],
        CANDIDATE_PROJECTS_YAML=yaml.dump(candidates),
    )
    return generate(prompt, "Smart Projects Section")


def generate_experience(profile, jd, archetypes):
    prompt = render_prompt(
        "experience",
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:600],
        EXPERIENCE_YAML=yaml.dump(profile['experience']),
    )
    raw_experience = generate(prompt, "Experience Section")
    text = enforce_bullet_limit(raw_experience, MAX_BULLETS_PER_ROLE)
    log_step("Experience Bullet Limit", raw_output=raw_experience, processed_output=text)
    return text


def generate_cover_letter(profile, jd, archetypes):
    career_goals = profile.get('cover_letter_preferences', {}) or {}
    goals = career_goals.get('career_goals')
    goals_str = goals if isinstance(goals, str) else (", ".join(goals) if goals else "")
    prompt = render_prompt(
        "cover_letter",
        JD_EXCERPT=jd[:800],
        ARCHETYPES=archetypes,
        CANDIDATE_NAME=profile['basics']['name'],
        CANDIDATE_LABEL=profile['basics']['label'],
        CAREER_GOALS=goals_str,
    )
    return generate(prompt, "Cover Letter")

def generate_smart_education(profile, jd, archetypes):
    education = profile.get("education", [])

    if not education:
        return ""

    prompt = render_prompt(
        "education",
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:800],
        EDUCATION_YAML=yaml.dump(education),
    )
    return generate(prompt, "Smart Education Section")

def generate_smart_certifications(profile, jd, archetypes):
    certs = profile.get("certifications", [])

    if not certs:
        return ""

    prompt = render_prompt(
        "certifications",
        ARCHETYPES=archetypes,
        JD_EXCERPT=jd[:800],
        CERTIFICATIONS_YAML=yaml.dump(certs),
    )
    return generate(prompt, "Smart Certifications Section")

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
    setup_logging()
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

    # 1. Analyze
    archetypes = identify_archetypes(jd_text)
    print(f"\n🔎 Identified Archetypes: {archetypes}\n")
    log_step("Archetypes Final", processed_output=str(archetypes))

    # 2. Generate Content
    summary_md = normalize_spacing(generate_professional_summary(profile, jd_text, archetypes))
    education_md = normalize_spacing(generate_smart_education(profile, jd_text, archetypes))
    skills_md = normalize_spacing(generate_smart_skills(profile, jd_text, archetypes))
    certs_md = normalize_spacing(generate_smart_certifications(profile, jd_text, archetypes))
    projects_md = normalize_spacing(generate_smart_projects(profile, jd_text, archetypes))
    experience_md = normalize_spacing(generate_experience(profile, jd_text, archetypes))

    cover_letter_md = generate_cover_letter(profile, jd_text, archetypes)

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
