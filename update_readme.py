from pathlib import Path

readme = Path("README.md")
start = "<!-- BEGIN REPORTS -->"
end = "<!-- END REPORTS -->"

text = readme.read_text(encoding="utf-8")

# Remove previously generated reports
if start in text and end in text:
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    text = (before.rstrip() + "\n\n" + after.strip()).rstrip()

# Find all candidate reports
files = sorted(Path(".").glob("seat-*-report.txt"))
if not files:
    raise SystemExit("No candidate reports found.")

# Append updated reports in monospaced blocks
text += f"\n\n{start}\n"

for file in files:
    content = file.read_text(encoding="utf-8").rstrip()
    text += f"\n## {file.stem}\n\n```text\n{content}\n```\n"

text += f"\n{end}\n"

readme.write_text(text, encoding="utf-8")
print(f"Updated README.md with {len(files)} reports.")
