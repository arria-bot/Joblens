"""Skill matching between a job's requirements and the user's skills."""


from database import get_job, get_requirements, get_user_skills
from utils import prompt_int


def match_skills(job_id: int, db_path: str | None = None):
    """Return ``(matched, missing)`` lists of requirement rows.

    Matching is case-insensitive on whitespace-trimmed names.  Fuzzy/alias
    matching (e.g. "APIs" vs "REST API") is a follow-up item, not part of P0.
    """
    requirements = get_requirements(job_id, db_path=db_path)
    user_skills = get_user_skills(db_path=db_path)
    user_skill_names = {row["skill"].strip().lower() for row in user_skills}

    matched = []
    missing = []
    for requirement in requirements:
        if requirement["skill"].strip().lower() in user_skill_names:
            matched.append(requirement)
        else:
            missing.append(requirement)

    return matched, missing


def match_skills_workflow(db_path: str | None = None) -> None:
    job_id = prompt_int("What's the job id? ")
    if job_id is None:
        return

    job = get_job(job_id, db_path=db_path)
    if job is None:
        print(f"Job with id {job_id} not found.")
        return

    matched, missing = match_skills(job_id, db_path=db_path)

    print("Matched skills:")
    for skill in matched:
        print(f"- {skill['skill']} ({skill['importance']})")

    print("Missing skills:")
    for skill in missing:
        print(f"- {skill['skill']} ({skill['importance']})")
