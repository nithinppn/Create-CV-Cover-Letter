# 📄 AI-Powered CV & Cover Letter Generator

Automatically generate tailored, ATS-optimized CVs and cover letters
from job descriptions using a local LLM.

This project uses **Ollama (Phi-3)** for privacy-friendly inference and
generates professional documents in **Markdown and PDF format** using
**Pandoc and LaTeX**.

------------------------------------------------------------------------

## 🚀 Features

-   🔍 Analyzes job descriptions using a local LLM
-   🎯 Automatically tailors CV and cover letter content
-   📑 Generates Markdown (.md) and PDF (.pdf) files
-   🧠 Filters relevant skills, projects, and experience
-   🔐 Fully local processing (no cloud APIs)
-   📁 Stores generated files in a dedicated /docs folder
-   🧾 ATS-friendly formatting

------------------------------------------------------------------------

## 🏗 Project Structure

    project-root/
    │
    ├── main.py
    ├── profile.yaml
    ├── prompts.yaml              # LLM prompt templates (edit to customize)
    ├── template_cv.md
    ├── resume_template.tex       # XeLaTeX (primary)
    ├── resume_template_pdflatex.tex   # pdflatex fallback
    ├── test_pdf_generation.py    # PDF-only test (no LLM)
    ├── job_input.example.yaml    # Template for job_input.yaml
    ├── requirements.txt
    ├── README.md
    │
    └── docs/
        ├── CV_<Company>_<Date>.pdf
        ├── CV_<Company>_<Date>.md
        ├── CoverLetter_<Company>_<Date>.pdf
        └── CoverLetter_<Company>_<Date>.md

------------------------------------------------------------------------

## ⚙️ Requirements

### 1️⃣ Python (3.9+)

### 2️⃣ Ollama

    ollama serve
    ollama pull phi3

### 3️⃣ Pandoc

### 4️⃣ LaTeX (BasicTeX or MacTeX)

PDF generation uses **XeLaTeX** by default. If XeLaTeX is not found, **pdflatex** is used automatically.

BasicTeX (minimal, ~100 MB):
    brew install --cask basictex
    # After install, RESTART your terminal (or Cursor) so PATH is updated.
    # Or run: eval "$(/usr/libexec/path_helper -s)"

MacTeX (full, ~4 GB): `brew install --cask mactex`

**Troubleshooting (PDF fails):**

1. Restart terminal after installing BasicTeX so PATH updates.
2. Find TeX location and set TEXBIN:
        find /usr/local/texlive /Library/TeX -name xelatex -type f 2>/dev/null
        export TEXBIN=/usr/local/texlive/2024/bin/universal-darwin
3. Test PDF generation without running the full LLM flow:
        python test_pdf_generation.py

------------------------------------------------------------------------

## 📦 Install Python Dependencies

    pip install -r requirements.txt

Example `requirements.txt`:

    pyyaml
    ollama
    jinja2
    pypandoc

------------------------------------------------------------------------

## 🧪 Testing PDF Generation

Test PDF conversion without running the full LLM pipeline:

    python test_pdf_generation.py

Uses sample files in docs/ or creates minimal samples. Requires xelatex or pdflatex in PATH. Enable debug logs with `CV_DEBUG=1`.

------------------------------------------------------------------------

## ▶️ Usage

Start Ollama:

    ollama serve

**Option A – Input from file (recommended):**

    cp job_input.example.yaml job_input.yaml
    # Edit job_input.yaml: set company and job_description (use | for multiline JD)
    python main.py

    # Or specify a different file:
    python main.py -i my_job.yaml

**Option B – Interactive:**

    python main.py

Enter company name and paste job description (type DONE when finished).

Generated files will be saved in /docs.

------------------------------------------------------------------------

## 🔍 Workflow

1.  Load structured profile from profile.yaml
2.  Analyze job description via LLM
3.  Identify relevant skills and experience
4.  Generate tailored summary and content
5.  Render Markdown via Jinja2
6.  Convert Markdown → PDF using Pandoc + XeLaTeX (or pdflatex fallback)
7.  Save output to /docs

------------------------------------------------------------------------

## 🧠 Why This Project?

Applying to multiple roles requires constant CV customization.\
This tool automates that process while ensuring:

-   Relevance\
-   Keyword alignment\
-   Clean formatting\
-   Data privacy

------------------------------------------------------------------------

## ✏️ Customizing Prompts

All LLM prompts are defined in `prompts.yaml`. Edit this file to:
- Adjust tone, format, or instructions for each section
- Add or modify task archetypes for job analysis
- Change placeholder content

Placeholders use `<<NAME>>` format and are documented in the file.

------------------------------------------------------------------------

## 📌 Future Improvements

-   Embedding-based similarity matching\
-   Web UI (Streamlit)\
-   Docker containerization\
-   CI pipeline for PDF builds\
-   Multi-model support

------------------------------------------------------------------------

## 📄 License

MIT License
