"""Quick runner: executes editor pipeline on execution_001 and prints results."""
import sys
from pathlib import Path

from editor.pipeline import run_editor_pipeline

run_dir = Path("output/execution_001")
result = run_editor_pipeline(run_dir, ieee_format="journal", verbose_log=True)

print()
print("=== SUMMARY ===")
if result.plan:
    print(f"Plan     : {len(result.plan.sections)} sections, {len(result.plan.figures)} figures")
    print(f"Title    : {result.plan.article_title}")
    for s in result.plan.ordered_sections:
        slugs = len(s.research_slugs)
        print(f"  [{s.order:02d}] {s.heading:<40}  {s.max_words}w  {slugs} slugs")

print()
ok_s = len(result.successful_sections)
tot_s = len(result.sections)
print(f"Sections : {ok_s}/{tot_s} OK")
for d in result.sections:
    tag = "OK  " if d.success else "FAIL"
    err = f"  [{d.error[:60]}]" if d.error else ""
    print(f"  [{tag}] {d.section_id:<20} {d.word_count:>4}w{err}")

print()
ok_f = len(result.successful_figures)
tot_f = len(result.figures)
print(f"Figures  : {ok_f}/{tot_f} OK")
for f in result.figures:
    tag = "OK  " if f.success else "FAIL"
    err = f"  [{(f.error or '')[:60]}]" if not f.success else ""
    print(f"  [{tag}] {f.figure_id}{err}")

print()
v_pass = sum(1 for v in result.validation if v.verdict == "pass")
v_warn = sum(1 for v in result.validation if v.verdict == "warn")
v_fail = sum(1 for v in result.validation if v.verdict == "fail")
print(f"Validate : {v_pass} pass / {v_warn} warn / {v_fail} fail")
for v in result.validation:
    if v.verdict != "pass" or v.issues:
        issues_str = "; ".join(v.issues[:2])
        print(f"  [{v.verdict.upper():<4}] {v.section_id:<20} {issues_str[:80]}")

print()
if result.manuscript_tex:
    lines = result.manuscript_tex.count("\n")
    print(f"Manuscript: {lines} lines -> output/execution_001/13_ieee_manuscript/main.tex")
else:
    print("Manuscript: NOT generated")

from pathlib import Path
if result.pdf_path and Path(result.pdf_path).exists():
    size_kb = round(Path(result.pdf_path).stat().st_size / 1024, 1)
    print(f"PDF       : {result.pdf_path} ({size_kb} KB)")
elif not result.pdf_path:
    print("PDF       : not compiled (pdflatex not found or manuscript failed)")

if result.errors:
    print()
    print("Errors:")
    for e in result.errors:
        print(f"  - {e[:120]}")

sys.exit(0 if not result.errors else 1)
