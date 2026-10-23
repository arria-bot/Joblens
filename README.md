# JobLens

JobLens is a command-line tool that answers one question: **how well does my
skill set match this job posting?**

Paste a job description, and JobLens asks an LLM (DeepSeek by default) to extract
the technical skills it requires, stores them in a local SQLite database, and
compares them against the skills you have recorded — reporting what matches, what
is missing, and a weighted coverage score.

Video demo: https://youtu.be/rdMpn5FCKic

Originally built as the final project for **CS50P: Introduction to Programming
with Python**, since restructured into a small layered application.

## Features

- **Add a job** — paste a description in the terminal or read it from a file.
- **Automatic skill extraction** — one structured call to an OpenAI-compatible
  API, with JSON output mode, retries and a prompt-size cap.
- **Skill matching** — exact names, known aliases (`JS` ↔ `JavaScript`), token
  containment (`APIs` ⊂ `REST API / API integration`) and a fuzzy fallback.
- **Weighted score** — `required` counts double; the result is a 0–100 coverage
  percentage rather than a yes/no.
- **Your skills are editable** — add, list and remove them from the CLI.
- **Persistent storage** — a single SQLite file, migrated automatically.
- **Scriptable** — subcommands plus `--json` output; interactive menu if you
  prefer typing numbers.

## Quick start

```bash
git clone https://github.com/arria-bot/Joblens.git
cd Joblens

python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

pip install -e ".[dev]"          # or: pip install -r requirements.txt
```

Set your API key (get one from DeepSeek):

```bash
export DEEPSEEK_API_KEY="your_api_key_here"
```

Windows PowerShell: `$env:DEEPSEEK_API_KEY="your_api_key_here"`

Then run:

```bash
python project.py                # interactive menu (works without installing)
joblens --help                   # installed entry point (pip install -e .)
python -m joblens --help         # same, once installed (or with PYTHONPATH=src)
```

## Usage

### Record your own skills first

Matching needs something to compare against:

```bash
joblens skills add "Python" --level Intermediate --evidence "CS50x, JobLens"
joblens skills add "SQL" --level Intermediate --evidence "CS50x"
joblens skills add "REST API / API integration" --level Beginner --evidence "Crypto Buddy"
joblens skills list
joblens skills remove "Rust"
```

### Add a job

```bash
joblens add
# Company: Acme
# Title: Backend Developer
# Salary: $90k
# Status (saved/applied/interview/offer/rejected) [saved]: applied
# Paste the job description.
# Type END on a new line when finished:
# ...
# END
# Job created! Job id is 1 (7 skills saved).
```

Or non-interactively:

```bash
joblens add --company Acme --title "Backend Developer" --status applied \
            --description-file jd.txt
```

### Match it against your skills

```bash
joblens match 1
```

```text
Matched skills (3/7, score 71.4%):
- SQL (required)
- APIs (preferred) -> your "REST API / API integration" [token]
- Python (required)
Missing skills:
- .NET (required)
- Angular (required)
- C# (required)
- TypeScript (required)
```

`[...]` shows *why* a skill matched: `exact`, `alias`, `token` or `fuzzy`.

### Inspect and re-analyse

```bash
joblens list                 # all stored jobs (newest pages via --offset)
joblens list --limit 5 --offset 5 --json
joblens show 1               # details + extracted skills
joblens analyze 1 --force    # re-run extraction, replacing the old skills
```

### Interactive mode

Running with no arguments opens the original menu:

```text
====== Joblens ======
1. Create a job
2. Match skills
3. View a job
4. View jobs
5. Add a skill
6. List my skills
7. Remove a skill
8. Exit
```

## Data and configuration

Everything lives in one SQLite file. By default that is `jobs.db` in the project
root; the program therefore behaves the same no matter which directory you start
it from.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | *(required)* | API key for skill extraction |
| `JOBLENS_DB` | `jobs.db` | Database file location |
| `JOBLENS_MODEL` | `deepseek-chat` | Model used for extraction |
| `JOBLENS_API_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible endpoint |
| `JOBLENS_MAX_JD_CHARS` | `8000` | Longer descriptions are truncated |
| `JOBLENS_TIMEOUT` | `30` | Per-request timeout, seconds |
| `JOBLENS_MAX_RETRIES` | `3` | Attempts on 429/5xx |
| `JOBLENS_FUZZY_THRESHOLD` | `0.86` | Similarity needed for a fuzzy match |
| `JOBLENS_ALIAS_FILE` | *(none)* | Extra skill aliases, merged over the bundled table |

Schema changes are applied on start-up through versioned migrations
(`PRAGMA user_version`), so older databases keep working.

### Teaching it your own skill aliases

The bundled equivalences live in `src/joblens/data/skill_aliases.json`. To add
your own without touching the package, point `JOBLENS_ALIAS_FILE` at a JSON file
shaped like `{"canonical": ["spelling", "another spelling"]}`:

```json
{ "kubernetes": ["k8s", "kube"] }
```

Groups are merged, so you can extend an existing canonical name instead of
replacing it.

## Project layout

```text
src/joblens/
├── cli.py              # argparse subcommands + interactive menu; all printing
├── config.py           # paths, limits, allowed values
├── models.py           # Job, Requirement, UserSkill, SkillMatch, MatchResult
├── prompts.py          # input helpers (whole numbers, statuses, multi-line)
├── errors.py           # JobLensError / ValidationError / NotFoundError / AnalysisError
├── data/
│   └── skill_aliases.json  # bundled alias table (user file merges on top)
├── db/
│   ├── connection.py   # connection factory: FK, WAL, busy_timeout, Row
│   ├── migrations.py   # versioned, rebuild-style migrations
│   └── repository.py   # the only place with SQL; returns typed models
└── services/
    ├── aliases.py      # normalisation + alias table loading
    ├── analyzer.py     # LLM extraction: JSON mode, retries, validation
    ├── matching.py     # exact → alias → token → fuzzy matching
    └── jobs.py         # use cases: add (analyse first), re-analyse, match

project.py              # thin launcher: python project.py still works
tests/                  # pytest suite, fully offline
.github/workflows/      # CI: lint, format, types, tests on 3.10–3.13
```

Dependencies point one way only: `cli → services → db`. The database layer knows
nothing about the LLM, and nothing below the CLI prints.

## Development

```bash
pip install -e ".[dev]"

pytest                 # ~100 tests, no API key or network required
pytest --cov=joblens   # coverage (CI enforces 85%)
ruff check .           # lint
ruff format .          # formatting
mypy                   # strict type checking of src/
pre-commit install     # optional: run the same checks before each commit
```

The test suite injects a fake LLM client, so it runs offline and never spends
API credit. CI runs lint, format check, `mypy` and the test suite on Python
3.10–3.13 (see `.github/workflows/ci.yml`).

## License

MIT — see [LICENSE](LICENSE).
