# 📄 AI-Powered CV & Cover Letter Generator

Automatically generate tailored, ATS-optimized CVs and cover letters
from job descriptions using a local LLM.

This project uses **Ollama (llama3)** for privacy-friendly inference and
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
    ├── template_cv.md
    ├── template_cover_letter.md
    ├── resume_template.tex
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
    ollama pull llama3

### 3️⃣ Pandoc

### 4️⃣ LaTeX (TeX Live / MacTeX)

------------------------------------------------------------------------

## 📦 Install Python Dependencies

    pip install -r requirements.txt

Example `requirements.txt`:

    pyyaml
    ollama
    jinja2
    pypandoc

------------------------------------------------------------------------

## ▶️ Usage

Start Ollama:

    ollama serve

Run the generator:

    python main.py

Enter: - Company name - Paste job description - Type DONE when finished

Generated files will be saved in /docs.

------------------------------------------------------------------------

## 🔍 Workflow

1.  Load structured profile from profile.yaml\
2.  Analyze job description via LLM\
3.  Identify relevant skills and experience\
4.  Generate tailored summary and content\
5.  Render Markdown via Jinja2\
6.  Convert Markdown → PDF using Pandoc + LaTeX\
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

## 📌 Future Improvements

-   Embedding-based similarity matching\
-   Web UI (Streamlit)\
-   Docker containerization\
-   CI pipeline for PDF builds\
-   Multi-model support

------------------------------------------------------------------------

## 📄 License

MIT License
