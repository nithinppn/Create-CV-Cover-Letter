#!/usr/bin/env python3
"""
Run PDF generation tests using sample Markdown outputs.
Tests convert_md_to_pdf and convert_cover_letter_to_pdf without running the full LLM flow.

Requires: xelatex or pdflatex (BasicTeX or MacTeX).
  Install: brew install --cask basictex
  After install: restart terminal or run: eval "$(/usr/libexec/path_helper -s)"
  If PATH is wrong: export TEXBIN=/path/to/texlive/.../bin/universal-darwin
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shutil
from main import (
    load_yaml,
    load_file,
    latex_escape,
    ensure_tex_in_path,
    convert_md_to_pdf,
    convert_cover_letter_to_pdf,
)
from jinja2 import Template

PROFILE_PATH = "profile.yaml"
DOCS_DIR = "docs"
TEST_OUTPUT_DIR = "docs/pdf_test"


def run_pdf_tests():
    os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

    # 0. Check TeX availability (xelatex or pdflatex)
    ensure_tex_in_path()
    has_tex = shutil.which("xelatex") or shutil.which("pdflatex")
    if not has_tex:
        print("⚠️  Neither xelatex nor pdflatex found. PDF tests will fail.")
        print("   Install: brew install --cask basictex")
        print("   Then: eval \"$(/usr/libexec/path_helper -s)\"")
        print()

    # 1. Load profile and render resume_rendered.tex (required for CV PDF)
    print("Loading profile and rendering LaTeX template...")
    profile = load_yaml(PROFILE_PATH)
    escaped_basics = {
        k: latex_escape(v) if isinstance(v, str) else v
        for k, v in profile["basics"].items()
    }
    latex_template_str = load_file("resume_template.tex")
    latex_template = Template(latex_template_str)
    rendered_latex = latex_template.render(basics=escaped_basics)
    with open("resume_rendered.tex", "w", encoding="utf-8") as f:
        f.write(rendered_latex)
    print("  resume_rendered.tex written")

    # 2. Use existing sample files or create minimal samples
    cv_md = os.path.join(DOCS_DIR, "CV_TestCompany_2026-02-21.md")
    cl_md = os.path.join(DOCS_DIR, "CoverLetter_TestCompany_2026-02-21.md")

    if not os.path.exists(cv_md):
        # Create minimal sample CV
        cv_md = os.path.join(TEST_OUTPUT_DIR, "sample_cv.md")
        with open(cv_md, "w", encoding="utf-8") as f:
            f.write("""## Professional Summary
Sample summary for PDF test.

## Education
**Degree** — Institution, 2020

## Experience
**Role** — Company, 2021

- Bullet point
""")
        print(f"  Created sample CV: {cv_md}")

    if not os.path.exists(cl_md):
        cl_md = os.path.join(TEST_OUTPUT_DIR, "sample_cover_letter.md")
        with open(cl_md, "w", encoding="utf-8") as f:
            f.write("Dear Hiring Manager,\n\nSample cover letter body for PDF test.\n\nBest regards")
        print(f"  Created sample cover letter: {cl_md}")

    # 3. Run PDF conversions
    cv_pdf = os.path.join(TEST_OUTPUT_DIR, "CV_Test.pdf")
    cl_pdf = os.path.join(TEST_OUTPUT_DIR, "CoverLetter_Test.pdf")

    print("\n--- CV PDF Test ---")
    convert_md_to_pdf(cv_md, cv_pdf)

    print("\n--- Cover Letter PDF Test ---")
    convert_cover_letter_to_pdf(cl_md, cl_pdf)

    print("\n" + "=" * 50)
    print("PDF TEST COMPLETE")
    cv_ok = os.path.exists(cv_pdf) and os.path.getsize(cv_pdf) > 0
    cl_ok = os.path.exists(cl_pdf) and os.path.getsize(cl_pdf) > 0
    print(f"  CV PDF:         {cv_pdf} {'✓' if cv_ok else '✗ FAILED'}")
    print(f"  Cover Letter:   {cl_pdf} {'✓' if cl_ok else '✗ FAILED'}")
    print("=" * 50)
    sys.exit(0 if (cv_ok and cl_ok) else 1)


if __name__ == "__main__":
    run_pdf_tests()
