"""Command-line interface.

Two ways in:

* ``joblens <command> ...`` (or ``python project.py ...``) for scriptable use;
* no arguments at all starts the original interactive menu.

This module owns all printing.  The layers below return data and raise
exceptions; nothing else writes to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from joblens import __version__, config
from joblens.db.repository import Repository
from joblens.errors import JobLensError
from joblens.models import Job, MatchResult, UserSkill
from joblens.prompts import prompt_int, prompt_status, prompt_text, read_multiline
from joblens.services.jobs import JobService

# --- presentation -----------------------------------------------------------


def _job_to_dict(job: Job, include_description: bool = True) -> dict[str, Any]:
    data = asdict(job)
    if not include_description:
        data.pop("description", None)
    return data


def print_job(job: Job) -> None:
    print(f"Job {job.id}")
    print(f"  Company:  {job.company}")
    print(f"  Title:    {job.title}")
    print(f"  Salary:   {job.salary or '-'}")
    print(f"  Status:   {job.status}")
    print(f"  Analysis: {job.analysis_status}")
    print(f"  Created:  {job.created_at}")
    print(f"  Description: {len(job.description)} characters")


def print_jobs(jobs: list[Job]) -> None:
    if not jobs:
        print("No jobs stored yet.")
        return
    for job in jobs:
        print(job.summary())


def print_match(result: MatchResult) -> None:
    total = result.total
    print(f"Matched skills ({len(result.matched)}/{total}, score {result.score}%):")
    for match in result.matched:
        if match.method == "exact":
            print(f"- {match.skill} ({match.importance})")
        else:
            print(
                f'- {match.skill} ({match.importance}) -> your "{match.your_skill}"'
                f" [{match.method}]"
            )
    if not result.matched:
        print("- (none)")

    print("Missing skills:")
    for match in result.missing:
        print(f"- {match.skill} ({match.importance})")
    if not result.missing:
        print("- (none)")


def print_skills(skills: list[UserSkill]) -> None:
    if not skills:
        print('No skills stored yet. Add one with: joblens skills add "Python"')
        return
    for skill in skills:
        line = f"- {skill.skill} ({skill.level})"
        if skill.evidence:
            line += f" — {skill.evidence}"
        print(line)


def _emit_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# --- service wiring --------------------------------------------------------


def _build_service(db_path: str | None) -> JobService:
    repo = Repository(db_path)
    repo.init()
    return JobService(repo)


def _resolve_db_path(value: str | None) -> Path:
    return Path(value) if value else Path(config.get_db_path())


# --- commands --------------------------------------------------------------


def cmd_add(args: argparse.Namespace) -> int:
    service = _build_service(args.db)

    company = args.company or prompt_text("Company")
    title = args.title or prompt_text("Title")
    salary = args.salary if args.salary is not None else prompt_text("Salary", default="-")
    status = args.status or prompt_status()

    if args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8")
    else:
        print("Paste the job description.")
        description = read_multiline()

    job, reused, requirements = service.add_job(
        company=company,
        title=title,
        salary="" if salary == "-" else salary,
        status=status,
        description=description,
    )
    if reused:
        print(
            f"An identical description already exists; job {job.id} was updated "
            f"with {len(requirements)} skills."
        )
    else:
        print(f"Job created! Job id is {job.id} ({len(requirements)} skills saved).")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    service = _build_service(args.db)
    jobs = service.list_jobs(limit=args.limit, offset=args.offset)
    if args.json:
        _emit_json([_job_to_dict(job, include_description=False) for job in jobs])
        return 0

    print_jobs(jobs)
    total = service.repo.count_jobs()
    if total > len(jobs):
        first = args.offset + 1
        last = args.offset + len(jobs)
        print(f"Showing {first}-{last} of {total}. Use --offset {last} to see more.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    service = _build_service(args.db)
    job = service.get_job(args.job_id)
    requirements = service.repo.get_requirements(job.id)
    if args.json:
        payload = _job_to_dict(job)
        payload["requirements"] = [asdict(requirement) for requirement in requirements]
        _emit_json(payload)
    else:
        print_job(job)
        if requirements:
            print("  Skills:")
            for requirement in requirements:
                print(f"  - {requirement.skill} ({requirement.importance})")
    return 0


def cmd_match(args: argparse.Namespace) -> int:
    result = _build_service(args.db).match(args.job_id)
    if args.json:
        _emit_json(
            {
                "job_id": result.job_id,
                "score": result.score,
                "matched": [asdict(match) for match in result.matched],
                "missing": [asdict(match) for match in result.missing],
            }
        )
    else:
        print_match(result)
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    requirements = _build_service(args.db).reanalyze(args.job_id, force=args.force)
    print(f"Job {args.job_id} now has {len(requirements)} skills.")
    return 0


def cmd_skills_add(args: argparse.Namespace) -> int:
    skill = _build_service(args.db).add_skill(
        args.skill, level=args.level, evidence=args.evidence or ""
    )
    print(f"Saved skill: {skill.skill} ({skill.level})")
    return 0


def cmd_skills_list(args: argparse.Namespace) -> int:
    skills = _build_service(args.db).list_skills()
    if args.json:
        _emit_json([asdict(skill) for skill in skills])
    else:
        print_skills(skills)
    return 0


def cmd_skills_remove(args: argparse.Namespace) -> int:
    removed = _build_service(args.db).remove_skill(args.skill)
    if not removed:
        print(f"No such skill: {args.skill}")
        return 1
    print(f"Removed skill: {args.skill}")
    return 0


# --- interactive menu ------------------------------------------------------


MENU = """====== Joblens ======
1. Create a job
2. Match skills
3. View a job
4. View jobs
5. Add a skill
6. List my skills
7. Remove a skill
8. Exit"""


def _menu_create(service: JobService) -> None:
    company = prompt_text("Company")
    title = prompt_text("Title")
    salary = prompt_text("Salary", default="-")
    status = prompt_status()
    print("Paste the job description.")
    description = read_multiline()

    job, reused, requirements = service.add_job(
        company=company,
        title=title,
        salary="" if salary == "-" else salary,
        status=status,
        description=description,
    )
    if reused:
        print(f"Job {job.id} updated with {len(requirements)} skills (duplicate description).")
    else:
        print(f"Job created! Job id is {job.id} ({len(requirements)} skills saved).")


def _menu_match(service: JobService) -> None:
    job_id = prompt_int("What's the job id? ")
    if job_id is None:
        return
    print_match(service.match(job_id))


def _menu_view(service: JobService) -> None:
    job_id = prompt_int("What's the job id? ")
    if job_id is None:
        return
    print_job(service.get_job(job_id))


def _menu_list(service: JobService) -> None:
    print_jobs(service.list_jobs())


def _menu_add_skill(service: JobService) -> None:
    skill = prompt_text("Skill")
    level = prompt_text("Level", default="Intermediate")
    evidence = prompt_text("Evidence (optional)", default="")
    saved = service.add_skill(skill, level=level, evidence=evidence)
    print(f"Saved skill: {saved.skill} ({saved.level})")


def _menu_list_skills(service: JobService) -> None:
    print_skills(service.list_skills())


def _menu_remove_skill(service: JobService) -> None:
    skill = prompt_text("Skill to remove")
    if service.remove_skill(skill):
        print(f"Removed skill: {skill}")
    else:
        print(f"No such skill: {skill}")


MENU_ACTIONS = {
    "1": _menu_create,
    "2": _menu_match,
    "3": _menu_view,
    "4": _menu_list,
    "5": _menu_add_skill,
    "6": _menu_list_skills,
    "7": _menu_remove_skill,
}


def run_interactive(db_path: str | None = None) -> int:
    service = _build_service(db_path)
    while True:
        print(MENU)
        try:
            choice = input("Choose an option: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            return 0

        if choice == "8":
            print("Goodbye!")
            return 0

        action = MENU_ACTIONS.get(choice)
        if action is None:
            print("Invalid option")
            continue
        try:
            action(service)
        except JobLensError as exc:
            print(f"Error: {exc}")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
        except Exception as exc:  # noqa: BLE001 - a REPL must survive one bad command
            print(f"Unexpected error: {type(exc).__name__}: {exc}")


# --- argument parsing ------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="joblens",
        description="Compare a job posting's required skills against your own.",
    )
    parser.add_argument("--db", help="database file (default: jobs.db next to the project)")
    parser.add_argument("--version", action="version", version=f"joblens {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    add = subparsers.add_parser("add", help="add a job and extract its skills")
    add.add_argument("--company")
    add.add_argument("--title")
    add.add_argument("--salary")
    add.add_argument("--status", choices=config.ALLOWED_STATUSES)
    add.add_argument("--description-file", help="read the posting from a file")
    add.set_defaults(func=cmd_add)

    list_parser = subparsers.add_parser("list", help="list stored jobs")
    list_parser.add_argument("--limit", type=int, default=100)
    list_parser.add_argument("--offset", type=int, default=0)
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_list)

    show = subparsers.add_parser("show", help="show one job")
    show.add_argument("job_id", type=int)
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)

    match = subparsers.add_parser("match", help="compare a job against your skills")
    match.add_argument("job_id", type=int)
    match.add_argument("--json", action="store_true")
    match.set_defaults(func=cmd_match)

    analyze = subparsers.add_parser("analyze", help="re-run skill extraction")
    analyze.add_argument("job_id", type=int)
    analyze.add_argument("--force", action="store_true", help="re-analyse even if done")
    analyze.set_defaults(func=cmd_analyze)

    skills = subparsers.add_parser("skills", help="manage your own skills")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)

    skills_add = skills_sub.add_parser("add", help="add or update a skill")
    skills_add.add_argument("skill")
    skills_add.add_argument("--level", default="Intermediate")
    skills_add.add_argument("--evidence", default="")
    skills_add.set_defaults(func=cmd_skills_add)

    skills_list = skills_sub.add_parser("list", help="list your skills")
    skills_list.add_argument("--json", action="store_true")
    skills_list.set_defaults(func=cmd_skills_list)

    skills_remove = skills_sub.add_parser("remove", help="remove a skill")
    skills_remove.add_argument("skill")
    skills_remove.set_defaults(func=cmd_skills_remove)

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:  # avoid UnicodeEncodeError on legacy consoles
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        try:
            return run_interactive(args.db)
        except JobLensError as exc:
            print(f"Error: {exc}")
            return 1

    try:
        handler: Callable[[argparse.Namespace], int] = args.func
        return handler(args)
    except JobLensError as exc:
        print(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
