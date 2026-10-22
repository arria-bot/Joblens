from database import get_job
import sqlite3


def match_skills(job_id):
    db = sqlite3.connect("jobs.db")

    requirements = db.execute("""
        SELECT skill, importance
        FROM requirements
        WHERE job_id = ?
        """, (job_id,)).fetchall()

    user_skills = db.execute("""
        SELECT skill
        FROM user_skills
        """).fetchall()

    db.close()

    user_skill_names = [skill[0].lower() for skill in user_skills]

    matched = []
    missing = []

    for requirement in requirements:
        skill = requirement[0]

        if skill.lower() in user_skill_names:
            matched.append(requirement)
        else:
            missing.append(requirement)

    return matched, missing






def match_skills_workflow():
    try:
        job_id = int(input("What's the job id?").strip())
    except ValueError:
        print("Invalid input. Please enter valid number.")
        return

    job = get_job(job_id)
    if job is None:
        print(f"Job with id {job_id} not found.")
        return

    matched, missing = match_skills(job_id)

    print("Matched skills: ")
    for skill in matched:
        print(f"- {skill[0]} ({skill[1]})")

    print("Missing skills:")
    for skill in missing:
        print(f"- {skill[0]} ({skill[1]})")

