import sqlite3

from analyzer import analyze_job






def init_db(db_path="jobs.db"):
    db = sqlite3.connect(db_path)

    db.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            company TEXT,
            title TEXT,
            salary TEXT,
            description TEXT,
            status TEXT
            )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS requirements (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            skill TEXT,
            importance TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS user_skills (
            id INTEGER PRIMARY KEY,
            skill TEXT,
            level TEXT,
            evidence TEXT
            )
    """)

    db.commit()
    db.close()




def get_job_from_user():
    company = input("Company: ").strip()
    title = input("Title: ").strip()
    salary = input("Salary: ").strip()
    status = input("Status: ").strip()

    print("Paste the job description.")
    print("Type END on a new line when finished:")

    lines = []

    while True:
        line = input()

        if line == "END":
            break

        lines.append(line)

    description = "\n".join(lines)

    return company, title, salary, description, status



def create_job(company, title, salary, status, description):
    db = sqlite3.connect("jobs.db")

    cursor = db.execute("""
        INSERT INTO jobs (company, title, salary, status, description)
        VALUES (?, ?, ?, ?, ?)
        """, (
            company,
            title,
            salary,
            status,
            description
        ))

    job_id = cursor.lastrowid

    db.commit()
    db.close()

    return job_id



def create_job_workflow():
    company, title, salary, description, status = get_job_from_user()

    job_id = create_job(company, title, salary, status, description)

    stored_description = get_job_description(job_id)

    if stored_description is None:
        print("No description")
    else:
        requirements = analyze_job(stored_description)
        save_requirements(job_id, requirements)

    print(f"Job has created! Job id is {job_id}.")




def get_job_description(job_id):
    db = sqlite3.connect("jobs.db")
    job_description = db.execute("""
            SELECT description
            FROM jobs
            WHERE id = ?
            """, (job_id,)).fetchone()  # tuple

    db.close()

    if job_description is None:
        return None

    return job_description[0]






def save_requirements(job_id, requirements):
    db = sqlite3.connect("jobs.db")

    for requirement in requirements:
        db.execute("""
            INSERT INTO requirements (job_id, skill, importance)
            VALUES (?, ?, ?)
            """, (
                job_id,
                requirement["skill"],
                requirement["importance"]
            ))

    db.commit()
    db.close()





def get_job(job_id):
    db = sqlite3.connect("jobs.db")

    job = db.execute("""
            SELECT *
            FROM jobs
            WHERE id = ?
        """, (job_id,)).fetchone()

    db.close()

    return job


def get_stored_jobs():
    db = sqlite3.connect("jobs.db")
    stored_jobs = db.execute("SELECT * FROM jobs").fetchall()

    db.close()

    return stored_jobs



