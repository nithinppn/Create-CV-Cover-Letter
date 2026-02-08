# Create-CV-Cover-Letter
## 📄 AI-Powered CV & Cover Letter Generator

This project automatically generates tailored CVs and cover letters in Markdown and PDF format based on a job description and a personal profile.
It uses Ollama (LLM), Pandoc, and LaTeX to create professional, ATS-friendly application documents.

🚀 Features

Generates customized CV and cover letter for each job application

Uses local LLMs via Ollama (privacy-friendly)

Automatically tailors content to job descriptions

Produces both Markdown (.md) and PDF (.pdf) files

Supports LaTeX-based professional formatting

Filters and selects relevant projects and skills

Stores generated files in a dedicated output folder

project-root/
│
├── main.py                  # Main generator script
├── profile.yaml             # Personal profile data
├── template_cv.md           # CV Markdown template
├── resume_template.tex      # LaTeX template for PDF rendering
├── resume_rendered.tex      # Auto-generated LaTeX file
├── docs/                    # Generated output files (ignored by Git)
├── .gitignore
└── README.md

### 📂 Output Files (docs/)

All generated files are stored in the docs/ folder:

CV in Markdown: CV_<Company>_<Date>.md

CV in PDF: CV_<Company>_<Date>.pdf

Cover Letter in Markdown: CoverLetter_<Company>_<Date>.md

Cover Letter in PDF: CoverLetter_<Company>_<Date>.pdf
docs/
├── CV_Bosch_2026-02-08.pdf
├── CV_Bosch_2026-02-08.md
├── CoverLetter_Bosch_2026-02-08.pdf
└── CoverLetter_Bosch_2026-02-08.md

⚙️ Requirements

Make sure the following are installed:

1. Python (3.9+ recommended)
2. Ollama

Install and pull the model:

ollama serve
ollama pull llama3

3. Pandoc
4. LaTeX (MacTeX / TeX Live)

### 📦 Python Dependencies

Install required packages:

pip install pyyaml ollama jinja2 pypandoc

## 📝 Configuration Files
### profile.yaml

Contains your personal and professional data:

Basics (name, title, summary)

Education

Experience

Skills

Projects

Certifications

Languages

Edit this file to customize your profile.

### template_cv.md

Markdown template for the CV layout.

Uses Jinja2 placeholders for dynamic content.

### resume_template.tex

LaTeX template used to render the final PDF.

Controls fonts, margins, and visual style.

## ▶️ How to Use

Start Ollama:

ollama serve


Run the generator:

python main.py


Enter company name when prompted

Paste job description

Type:

DONE (press enter afterwards)


Files will be generated in docs/

## 🔍 Workflow Overview

Load profile data from profile.yaml

Analyze job description using LLM

Identify relevant archetypes

Generate tailored sections:

- Summary

- Skills

- Experience

- Projects

- Education

- Certifications

Render Markdown via Jinja2

Convert Markdown → PDF using Pandoc + LaTeX

Save output to docs/