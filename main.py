import yaml
import ollama
import os
import sys
import json
import re
from jinja2 import Template
from datetime import date
import pypandoc
import unicodedata


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
MODEL = "llama3"  # Make sure to run: ollama pull llama3
PROFILE_PATH = "profile.yaml"
TEMPLATE_PATH = "template_cv.md"

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

# Task archetypes for context analysis
TASK_ARCHETYPES = [
    "data_analytics", "software_engineering", "embedded_systems",
    "mechanical_engineering", "project_management", "research_ml",
    "cloud_devops", "manufacturing_quality", "supply_chain",
    "consulting_enablement", "digital_transformation"
]
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

def clean_ai_output(text):
    """Removes code blocks and conversational filler from LLM output."""
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
    return [p for s, p in scored_projects[:CANDIDATE_POOL_SIZE]]


# ---------- AI GENERATORS ----------

def generate_professional_summary(profile, jd, archetypes):
    """
    Generates a 3-4 sentence professional summary tailored to the JD.
    """
    basics = profile.get('basics', {})
    current_role = basics.get('label', 'Professional')
    
    prompt = f"""
        Write a generic but powerful Professional Summary (Profile) for a CV.
        
        MY ROLE: {current_role}
        TARGET ARCHETYPES: {archetypes}
        JOB DESCRIPTION HIGHLIGHTS: {jd[:800]}
        
        MY BACKGROUND SUMMARY:
        {basics.get('summary', '')}
        
        INSTRUCTIONS:
        1. Write exactly 3-4 lines.
        2. Tone: Professional, confident, and tailored to the Job Description.
        3. Do NOT use "I" or "My". Use implied first person (e.g., "Experienced Software Engineer with..." rather than "I am an experienced...").
        4. Highlight the intersection of my experience and the job requirements.
        5. Output plain text only. No headers.
        6. Use ONLY the provided skills.
        7. Do not hallucinate.
        """
    
    return generate(prompt, "Professional Summary")


def generate(prompt, label):
    print(f"--> 🧠 Generating {label}...")
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={'temperature': 0.2} # Low temp for strict adherence
        )
        return clean_ai_output(response["message"]["content"])
    except Exception as e:
        print(f"⚠️ Error generating {label}: {e}")
        return ""

def identify_archetypes(jd):
    prompt = f"""
        Analyze the Job Description and identify the top 3 relevant archetypes from this list:
        {TASK_ARCHETYPES}
        
        Return ONLY a JSON object: {{ "archetypes": ["match1", "match2"] }}
        
        Job Description:
        {jd[:1500]}
        """
    raw = generate(prompt, "Archetype Analysis")
    data = extract_json_from_text(raw)
    return data.get("archetypes", []) if data else []


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

    prompt = f"""
    Select the top 4 Soft Skills from the list below that are most relevant to this Job.
    
    JOB EXCERPT: {jd[:800]}
    
    MY SOFT SKILLS POOL:
    {json.dumps(soft_pool)}
    
    INSTRUCTIONS:
    1. Select exactly 3 or 4 skills that best fit the job description.
    2. Format strictly as: **Soft Skills:** Skill 1, Skill 2, Skill 3
    3. Do NOT invent new skills. Use ONLY the provided list.
    4. Output ONLY the single formatted line.
    """
    
    return generate(prompt, "Smart Soft Skills")


def generate_smart_skills(profile, jd, archetypes):
    """
    Feeds ALL skills to the LLM and asks it to curate a specific list.
    """
    all_skills = flatten_skills(profile.get("skills_buckets", {}))
    
    prompt = f"""
        Create a highly targeted 'Skills' section for a CV.

        JOB CONTEXT:
        Archetypes: {archetypes}
        JD Excerpt: {jd[:1000]}

        MY MASTER SKILL LIST:
        {json.dumps(all_skills)}

        INSTRUCTIONS:
        1. Select ONLY the skills from my list that are relevant to this job.
        2. Group them into 3–4 logical categories named specifically for this role.
        3. Format: **Category Name:** Skill, Skill, Skill (repeat as reuired) \n
        4. Use ONLY the provided skills.
        5. Output MUST contain ONLY formatted skill lines.
        6. Do NOT write explanations, notes, comments, or summaries.
        7. Do NOT use "*", "-", or numbered lists.
        8. Do NOT mention ATS, JD, or filtering.
        9. If you add any text outside the format, the output is invalid.
        10. Do NOT include a "Languages" category (I will add this manually).
        11. AVOID REDUNDANCY: If a skill name is contained in the Category Name, 
            OMIT the skill from the list. 
            (Example: If Category is 'Data Analysis', do NOT list 'Data Analysis' inside it. 
            Just list the tools like 'Pandas', 'Excel').
        """

    # --- Safety Net: Clean Tech Skills Redundancy ---
    raw_ai_skills = generate(prompt, "Smart Skills Section")
    cleaned_tech_skills = clean_skills_output(raw_ai_skills)

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
    return "\n".join([s for s in sections if s]).strip()


def generate_smart_projects(profile, jd, archetypes):
    all_projects = profile.get("projects", [])
    if not all_projects: return ""

    # 1. Python Pre-filter
    candidates = pre_filter_projects(all_projects, jd)
    print(f"    (Filtered {len(all_projects)} total projects down to {len(candidates)} candidates)")

    # 2. LLM Selection
    prompt = f"""
        Select the best {MAX_PROJECTS_TO_SHOW} projects from the candidates below.
        
        JOB CONTEXT: {jd[:1000]}
        
        CANDIDATE PROJECTS:
        {yaml.dump(candidates)}
        
        INSTRUCTIONS:
        1. Pick exactly {MAX_PROJECTS_TO_SHOW} projects.
        2. Format strictly as:

        **Project Name**, date (put name in bold) \n
        - Bullet point
        - Bullet point
        - Bullet point (repeat as needed)
        3. CRITICAL: DO NOT HALLUCINATE TOOLS. If a project used Python/C++, 
        do NOT write that it used Power BI just because the Job Description asks for it.
        4. Instead, highlight the *transferable skills* in sentences(
        e.g., "Complex Data Handling", "Optimization", "Algorithm Design") if the specific tool doesn't match.
        5. NO intro text.
        6. Use "-" only.
        8. Do not put the dat/year in quotations.
        """
    return generate(prompt, "Smart Projects Section")


def generate_experience(profile, jd, archetypes):

    prompt = f"""
        Rewrite the EXPERIENCE section for a CV.

        CONTEXT: {archetypes}
        JD SUMMARY: {jd[:600]}

        EXPERIENCE:
        {yaml.dump(profile['experience'])}

        INSTRUCTIONS:
        1. Output plain text.
        2. One role per block.
        3. Format strictly as:

        **Role**, Company, Location, Date
        Start Date – End Date
        - Bullet point
        - Bullet point
        - Bullet point (repeat as needed)
        4. No markdown headers.
        5. Use "-" only.
        6. If required, add upto 5 points.
        7. Make sure all the points are ATS friendly and compliant.
        """

    text = generate(prompt, "Experience Section")
    text = enforce_bullet_limit(text, MAX_BULLETS_PER_ROLE)

    return text


def generate_cover_letter(profile, jd, archetypes):
    prompt = f"""
        Write a German-market style Cover Letter BODY.
        
        JOB: {jd[:800]}
        ARCHETYPES: {archetypes}
        
        CANDIDATE:
        Name: {profile['basics']['name']}
        Current: {profile['basics']['label']}
        Motivation: {profile['cover_letter_preferences'].get('career_goals')}
        
        INSTRUCTIONS:
        1. Three paragraphs (Motivation, Experience Proof, Closing).
        2. Tone: Professional, direct, enthusiastic.
        3. Highlight specific overlap between my profile and the job.
        4. No placeholders.
        """
    return generate(prompt, "Cover Letter")

def generate_smart_education(profile, jd, archetypes):
    education = profile.get("education", [])

    if not education:
        return ""

    prompt = f"""
        Create a targeted EDUCATION section for a CV.

        JOB CONTEXT:
        Archetypes: {archetypes}
        JD Excerpt: {jd[:800]}

        EDUCATION DATA:
        {yaml.dump(education)}

        INSTRUCTIONS:
        1. Keep each degree.
        2. Under each degree, select ONLY the 2-4 most relevant courses.
        3. Format strictly as:

        **Degree** — Institution, Dates \n
        - Relevant Coursework: Course 1, Course 2 (repeat as needed)
        4. Do NOT invent courses.
        5. No explanations.
        6. Keep it concise.
        7. Do not give any headings, such as 'EDUCATION'
        8. Bold only the degree name, not the instituition and dates
        """

    return generate(prompt, "Smart Education Section")

def generate_smart_certifications(profile, jd, archetypes):
    certs = profile.get("certifications", [])

    if not certs:
        return ""

    prompt = f"""
        Create a targeted CERTIFICATIONS section for a CV.

        JOB CONTEXT:
        Archetypes: {archetypes}
        JD Excerpt: {jd[:800]}

        MY CERTIFICATIONS:
        {yaml.dump(certs)}


        INSTRUCTIONS:
        1. Select ONLY the 2–4 most relevant certifications.
        2. If fewer are relevant, select fewer.
        3. Output ONLY bullet points.
        4. Format strictly as:

        - Certification Name — Issuer (Year) \n

        5. Do NOT write any headers or labels.
        6. Do NOT invent certifications.
        7. No explanations.
        """

    return generate(prompt, "Smart Certifications Section")

def convert_md_to_pdf(md_file, pdf_file):

    print("🔧 Generating PDF...")

    try:
        os.environ["PATH"] += os.pathsep + "/Library/TeX/texbin"

        template_path = os.path.abspath("resume_template.tex")
        print("📄 Using template:", template_path)

        output = pypandoc.convert_file(
            md_file,
            "pdf",
            outputfile=pdf_file,
            extra_args=[
                "--pdf-engine=xelatex",
                "--template=resume_rendered.tex",
                "--wrap=preserve"
            ]
        )

        print("Pandoc output:", output)
        print(f"✅ PDF created: {pdf_file}")

    except Exception as e:
        print("❌ PDF conversion failed:")
        print("Error:", e)


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
        os.environ["PATH"] += os.pathsep + "/Library/TeX/texbin"

        output = pypandoc.convert_file(
            md_file,
            "pdf",
            outputfile=pdf_file,
            extra_args=[
                "--pdf-engine=xelatex",
                "--wrap=preserve"
            ]
        )

        print(f"✅ Cover Letter PDF created: {pdf_file}")

    except Exception as e:
        print("❌ Cover Letter PDF conversion failed:")
        print("Error:", e)


# ---------- MAIN EXECUTION ----------

if __name__ == "__main__":
    check_ollama_connection()
    
    DOCS_DIR = "docs"
    os.makedirs(DOCS_DIR, exist_ok=True)

    # Load Data
    profile = load_yaml(PROFILE_PATH)
    template_str = load_file(TEMPLATE_PATH)


    # Escape LaTeX-sensitive fields (IMPORTANT)
    escaped_basics = {
        k: latex_escape(v) if isinstance(v, str) else v
        for k, v in profile["basics"].items()
    }

    print("\n" + "=" * 50)
    print("🏢 ENTER COMPANY NAME")
    print("=" * 50)
    company_input = input("Target Company: ").strip()
    
    # Sanitize company name for filename (remove spaces/special chars)
    company_safe = re.sub(r'[^a-zA-Z0-9_-]', '', company_input.replace(' ', '_'))
    if not company_safe:
        company_safe = "General"
    
    # Get Job Description
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

    # 1. Analyze
    archetypes = identify_archetypes(jd_text)
    print(f"\n🔎 Identified Archetypes: {archetypes}\n")

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
    print("=" * 50)
