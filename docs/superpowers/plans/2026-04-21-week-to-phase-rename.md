# Week→Phase Rename + Project Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the project to "Agentic-RAG-project" and replace every "week N" reference with "phase N" across all files, then reinitialize git and push to a new GitHub repo.

**Architecture:** Pure rename/refactor pass — no logic changes. Work in text files first, then rename directories/files (so in-file references are updated before paths change), then git-reinit and push.

**Tech Stack:** sed/Python for bulk text replacement, `mv` for file/dir renames, `gh` CLI for GitHub repo creation.

---

## File Map

| File/Dir | Change Type | Notes |
|---|---|---|
| `pyproject.toml` | Modify | name = "Agentic-RAG-project" |
| `CLAUDE.md` | Modify | week → phase, project name |
| `README.md` | Modify | week → phase, project name, image paths, notebook paths |
| `step-by-step.md` | Modify | week → phase throughout |
| `airflow/README.md` | Modify | week → phase |
| `airflow/dags/hello_world_dag.py` | Modify | DAG name + tags |
| `notebooks/week*/README.md` (×7) | Modify + Move | update content, then move with parent dir |
| `notebooks/week*/week*.ipynb` (×7) | Modify + Rename | update cell content, then rename |
| `notebooks/week1/` → `notebooks/phase1/` (×7) | Rename dir | after content is updated |
| `static/week*.png` (×7) | Rename file | static images |
| `.gitignore` | Verify/Update | ensure comprehensive |
| `.git/` | Delete + Reinit | fresh git history |

---

### Task 1: Update `pyproject.toml` — project name

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

Change:
```toml
name = "moai-zero-to-rag"
description = "Mother-of-AI Phase-1-Zero to RAG"
```
To:
```toml
name = "Agentic-RAG-project"
description = "Agentic RAG system — arXiv Paper Curator"
```

- [ ] **Step 2: Verify**

```bash
grep -n "name\|description" pyproject.toml | head -5
```
Expected: shows `name = "Agentic-RAG-project"`

---

### Task 2: Bulk-replace "week" → "phase" in all text/markdown/python files (content only, no renames yet)

**Files:**
- Modify: `README.md`, `step-by-step.md`, `airflow/README.md`, `CLAUDE.md`, `airflow/dags/hello_world_dag.py`
- Modify: all `notebooks/week*/README.md` files (×7)

- [ ] **Step 1: Replace in root README.md**

Run this Python script (handles case-sensitive variants):
```bash
python3 -c "
import re, pathlib
p = pathlib.Path('README.md')
txt = p.read_text()
# Week N (capital)
txt = re.sub(r'\bWeek ([1-7])\b', r'Phase \1', txt)
# week N (lower)
txt = re.sub(r'\bweek([1-7])\b', r'phase\1', txt)
# week N.0 tags
txt = re.sub(r'\bweek([1-7])\.0\b', r'phase\1.0', txt)
# 'week' standalone lower
txt = re.sub(r'\bweek\b', 'phase', txt)
# 'Week' standalone capital
txt = re.sub(r'\bWeek\b', 'Phase', txt)
# image paths: static/week* -> static/phase*
txt = txt.replace('static/week', 'static/phase')
# notebook paths: notebooks/week* -> notebooks/phase*
txt = txt.replace('notebooks/week', 'notebooks/phase')
# project/repo name references
txt = txt.replace('production-agentic-rag-course', 'Agentic-RAG-project')
txt = txt.replace('moai-zero-to-rag', 'Agentic-RAG-project')
p.write_text(txt)
print('Done README.md')
"
```

- [ ] **Step 2: Replace in step-by-step.md**

```bash
python3 -c "
import re, pathlib
p = pathlib.Path('step-by-step.md')
txt = p.read_text()
txt = re.sub(r'\bWeek ([1-7])\b', r'Phase \1', txt)
txt = re.sub(r'\bweek([1-7])\b', r'phase\1', txt)
txt = re.sub(r'\bweek([1-7])\.0\b', r'phase\1.0', txt)
txt = re.sub(r'\bweek\b', 'phase', txt)
txt = re.sub(r'\bWeek\b', 'Phase', txt)
txt = txt.replace('notebooks/week', 'notebooks/phase')
txt = txt.replace('production-agentic-rag-course', 'Agentic-RAG-project')
p.write_text(txt)
print('Done step-by-step.md')
"
```

- [ ] **Step 3: Replace in CLAUDE.md**

```bash
python3 -c "
import re, pathlib
p = pathlib.Path('CLAUDE.md')
txt = p.read_text()
txt = re.sub(r'\bWeek ([1-7])\b', r'Phase \1', txt)
txt = re.sub(r'\bweek([1-7])\b', r'phase\1', txt)
txt = re.sub(r'\b7-week course\b', '7-phase course', txt)
txt = re.sub(r'\bweek\b', 'phase', txt)
txt = re.sub(r'\bWeek\b', 'Phase', txt)
txt = txt.replace('notebooks/week', 'notebooks/phase')
p.write_text(txt)
print('Done CLAUDE.md')
"
```

- [ ] **Step 4: Replace in airflow/README.md**

```bash
python3 -c "
import re, pathlib
p = pathlib.Path('airflow/README.md')
txt = p.read_text()
txt = re.sub(r'\bWeek ([1-7])\b', r'Phase \1', txt)
txt = re.sub(r'\bweek([1-7])\b', r'phase\1', txt)
txt = re.sub(r'\bweek\b', 'phase', txt)
txt = re.sub(r'\bWeek\b', 'Phase', txt)
p.write_text(txt)
print('Done airflow/README.md')
"
```

- [ ] **Step 5: Replace in airflow DAG Python file**

```bash
python3 -c "
import pathlib
p = pathlib.Path('airflow/dags/hello_world_dag.py')
txt = p.read_text()
txt = txt.replace('hello_world_week1', 'hello_world_phase1')
txt = txt.replace('week1', 'phase1')
txt = txt.replace('Week 1', 'Phase 1')
p.write_text(txt)
print('Done hello_world_dag.py')
"
```

- [ ] **Step 6: Replace in all notebooks/week*/README.md files**

```bash
python3 -c "
import re, pathlib
for readme in pathlib.Path('notebooks').rglob('README.md'):
    txt = readme.read_text()
    txt = re.sub(r'\bWeek ([1-7])\b', r'Phase \1', txt)
    txt = re.sub(r'\bweek([1-7])\b', r'phase\1', txt)
    txt = re.sub(r'\bweek\b', 'phase', txt)
    txt = re.sub(r'\bWeek\b', 'Phase', txt)
    # path references inside
    txt = txt.replace('notebooks/week', 'notebooks/phase')
    readme.write_text(txt)
    print(f'Done {readme}')
"
```

- [ ] **Step 7: Verify no stray "week" references remain in text files**

```bash
grep -rn --include="*.md" --include="*.py" --include="*.toml" --include="*.yml" --include="*.yaml" -i "week[1-7]" . --exclude-dir=.git --exclude-dir=.venv | grep -v "docs/superpowers"
```
Expected: zero results (or only acceptable internal uses like variable names that are intentional)

---

### Task 3: Update Jupyter notebook cell content (week → phase in .ipynb JSON)

**Files:**
- Modify: all `notebooks/week*/*.ipynb` files (×7)

- [ ] **Step 1: Bulk-update all notebook JSON content**

```bash
python3 -c "
import re, pathlib, json

notebooks = list(pathlib.Path('notebooks').rglob('*.ipynb'))
for nb_path in notebooks:
    txt = nb_path.read_text(encoding='utf-8')
    # Replace in all cell source strings
    txt = re.sub(r'\bWeek ([1-7])\b', r'Phase \1', txt)
    txt = re.sub(r'\bweek([1-7])\b', r'phase\1', txt)
    txt = re.sub(r'\bweek\b', 'phase', txt)
    txt = re.sub(r'\bWeek\b', 'Phase', txt)
    # notebook path refs
    txt = txt.replace('notebooks/week', 'notebooks/phase')
    nb_path.write_text(txt, encoding='utf-8')
    print(f'Updated {nb_path.name}')
"
```

- [ ] **Step 2: Verify notebooks are still valid JSON**

```bash
python3 -c "
import json, pathlib
for p in pathlib.Path('notebooks').rglob('*.ipynb'):
    try:
        json.loads(p.read_text())
        print(f'OK: {p}')
    except json.JSONDecodeError as e:
        print(f'BROKEN: {p} — {e}')
"
```
Expected: all lines print "OK: ..."

---

### Task 4: Rename notebook directories and files (week* → phase*)

**Files:**
- Rename dirs: `notebooks/week1/` → `notebooks/phase1/` through `notebooks/week7/` → `notebooks/phase7/`
- Rename files inside: e.g. `week1_setup.ipynb` → `phase1_setup.ipynb`

- [ ] **Step 1: Rename notebook .ipynb files first (before moving dirs)**

```bash
python3 -c "
import pathlib, os
for nb in pathlib.Path('notebooks').rglob('week*.ipynb'):
    new_name = nb.parent / nb.name.replace('week', 'phase')
    nb.rename(new_name)
    print(f'Renamed {nb.name} -> {new_name.name}')
"
```

- [ ] **Step 2: Rename the notebook directories**

```bash
for i in 1 2 3 4 5 6 7; do
    if [ -d "notebooks/week$i" ]; then
        mv "notebooks/week$i" "notebooks/phase$i"
        echo "Renamed week$i -> phase$i"
    fi
done
```

- [ ] **Step 3: Verify structure**

```bash
ls notebooks/
```
Expected: `phase1  phase2  phase3  phase4  phase5  phase6  phase7`

```bash
ls notebooks/phase1/
```
Expected: `phase1_setup.ipynb  README.md`

---

### Task 5: Rename static image files (week* → phase*)

**Files:**
- Rename: `static/week*.png` → `static/phase*.png` (×7)

- [ ] **Step 1: Rename all static images**

```bash
python3 -c "
import pathlib
for img in pathlib.Path('static').glob('week*.png'):
    new_name = img.parent / img.name.replace('week', 'phase')
    img.rename(new_name)
    print(f'Renamed {img.name} -> {new_name.name}')
"
```

- [ ] **Step 2: Verify**

```bash
ls static/
```
Expected: all images prefixed with `phase` instead of `week`

---

### Task 6: Final verification — no remaining "week" references

- [ ] **Step 1: Comprehensive scan for leftover "week" references**

```bash
grep -rn --include="*.md" --include="*.py" --include="*.toml" --include="*.yml" --include="*.yaml" --include="*.txt" -i "\bweek\b" . \
  --exclude-dir=.git \
  --exclude-dir=.venv \
  --exclude-dir=docs/superpowers \
  | grep -v ".ipynb_checkpoints"
```
Expected: zero results. If any remain, fix manually.

- [ ] **Step 2: Scan notebook files for "week"**

```bash
grep -rn --include="*.ipynb" -i "week[1-7]" notebooks/ | head -20
```
Expected: zero results.

- [ ] **Step 3: Verify directory names**

```bash
find . -name "*week*" -not -path "./.git/*" -not -path "./.venv/*" -not -path "./docs/superpowers/*"
```
Expected: zero results.

---

### Task 7: Update .gitignore for clean repo

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Verify .gitignore has all needed entries**

```bash
cat .gitignore | grep -E "\.env$|__pycache__|\.venv|\.ipynb_checkpoints|uv\.lock"
```

- [ ] **Step 2: Ensure .env is ignored (critical)**

```bash
grep "^\.env$" .gitignore || echo ".env" >> .gitignore
```

- [ ] **Step 3: Add uv.lock to tracking (should NOT be gitignored — it should be committed)**

```bash
grep "uv\.lock" .gitignore && echo "WARNING: uv.lock is gitignored — remove that line"
```
If uv.lock is gitignored, remove that line so lockfile is committed.

---

### Task 8: Delete .git and reinitialize

> ⚠️ This permanently destroys all git history. Confirm with user before proceeding.

- [ ] **Step 1: Delete existing .git directory**

```bash
rm -rf .git
echo "Deleted .git"
```

- [ ] **Step 2: Initialize fresh git repo**

```bash
git init
git branch -M main
echo "Initialized fresh git repo on branch main"
```

- [ ] **Step 3: Verify clean state**

```bash
git status
```
Expected: shows all files as untracked.

---

### Task 9: Create GitHub repo and push

- [ ] **Step 1: Check gh CLI authentication**

```bash
gh auth status
```
Expected: shows logged-in user. If not authenticated, user must run `gh auth login`.

- [ ] **Step 2: Create new GitHub repo**

```bash
gh repo create Agentic-RAG-project --public --description "Production-grade Agentic RAG system for arXiv paper curation" --source=. --remote=origin
```
If user prefers private: replace `--public` with `--private`.

- [ ] **Step 3: Stage all files**

```bash
git add .
git status
```
Verify: no `.env` file staged (check it is excluded by .gitignore).

- [ ] **Step 4: Initial commit**

```bash
git commit -m "$(cat <<'EOF'
feat: initial commit — Agentic-RAG-project

Renamed from production-agentic-rag-course. All week references
converted to phase (week1→phase1 through week7→phase7).
Project name updated to Agentic-RAG-project throughout.

Co-Authored-By: Claude Sonnet 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Push to GitHub**

```bash
git push -u origin main
```

- [ ] **Step 6: Verify on GitHub**

```bash
gh repo view --web
```
Opens browser to confirm repo is live with correct name and files.

---

## Self-Review

**Spec coverage check:**
- ✅ Project name → "Agentic-RAG-project": Task 1 (pyproject.toml), Task 2 (all markdown), Task 9 (GitHub repo name)
- ✅ week → phase in notebooks: Tasks 3 + 4
- ✅ week → phase in READMEs: Task 2
- ✅ week → phase in static images: Task 5
- ✅ week → phase in airflow DAG: Task 2 Step 5
- ✅ .gitignore maintained: Task 7
- ✅ Delete .git + reinit: Task 8
- ✅ Push to GitHub: Task 9
- ✅ Final verification pass: Task 6

**Placeholder scan:** None found — all steps have explicit commands.

**Type consistency:** No types — pure shell/Python scripting, consistent naming throughout.
