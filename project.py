"""JobLens command-line entry point.

P0 hardening: one shared database path, no unguarded ``int(input())``, and a
menu loop that survives bad input, Ctrl-C and EOF instead of dying.
"""

import sys

from database import create_job_workflow, get_job, get_stored_jobs, init_db
from errors import JobLensError
from skills import match_skills_workflow
from utils import prompt_int


def _configure_stdout() -> None:
    """Avoid UnicodeEncodeError on legacy Windows consoles (e.g. GBK)."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - console specific
            pass


def print_menu() -> None:
    print("====== Joblens ======")
    print("1. Create a job")
    print("2. Match skills")
    print("3. View a job")
    print("4. View jobs")
    print("5. Exit")


def view_job_workflow(db_path=None) -> None:
    job_id = prompt_int("What's the job id? ")
    if job_id is None:
        return

    job = get_job(job_id, db_path=db_path)
    if job is None:
        print(f"Job with id {job_id} not found.")
        return

    print(f"Company: {job['company']}")
    print(f"Title: {job['title']}")
    print(f"Salary: {job['salary']}")
    print(f"Status: {job['status']}")
    print(f"Analysis: {job['analysis_status']}")
    print(f"Created: {job['created_at']}")


def view_jobs_workflow(db_path=None) -> None:
    stored_jobs = get_stored_jobs(db_path=db_path)
    if not stored_jobs:
        print("No jobs stored yet.")
        return

    for job in stored_jobs:
        print(f"{job['id']}. {job['company']} - {job['title']} [{job['status']}]")


def main(db_path=None) -> None:
    _configure_stdout()
    path = init_db(db_path)
    db_path = path

    while True:
        try:
            print_menu()
            choice = input("Choose an option: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        try:
            if choice == "1":
                create_job_workflow(db_path)
            elif choice == "2":
                match_skills_workflow(db_path)
            elif choice == "3":
                view_job_workflow(db_path)
            elif choice == "4":
                view_jobs_workflow(db_path)
            elif choice == "5":
                print("Goodbye!")
                break
            else:
                print("Invalid option")
        except JobLensError as exc:
            # Expected, actionable failures (bad API answer, missing key, ...).
            print(f"Error: {exc}")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
        except Exception as exc:  # noqa: BLE001 - a REPL must not die on one command
            print(f"Unexpected error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
