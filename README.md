    # Joblens
    #### Video Demo:  https://youtu.be/rdMpn5FCKic
    #### Description:
    JobLens is a Python command-line tool that helps job seekers analyze how well their skills match a given job description. It extracts technical skill requirements from job postings using the DeepSeek API, stores them in a local SQLite database, and compares them against your personal skill set to identify matched and missing skills.

    The project was built as the final project for CS50P: Introduction to Programming with Python (Harvard University). It demonstrates core Python concepts including file I/O, database interaction, API calls, JSON parsing, exception handling, and unit testing.


    #### Features:
    Create job entries — paste a job description directly into the terminal.

    Automatic skill extraction — uses the DeepSeek API to parse the job description and return a structured list of required and preferred skills.

    Skill matching — compares job requirements against your personal skills, ignoring case.

    View jobs — list all stored jobs or view a single job's details.

    Persistent storage — all data is stored in a local SQLite database (jobs.db).


    #### Tech Stack:
    Python 3.13

    SQLite — lightweight local database

    DeepSeek API — LLM for extracting skills from unstructured text

    pytest — unit testing framework


    #### Project Structure:
    cs50p_project
    project.py       # Main CLI entry point
    database.py      # SQLite operations (create, read, update)
    analyzer.py      # DeepSeek API integration
    skills.py        # Skill matching logic
    config.py        # Paths, model and limits (single source of truth)
    migrations.py    # Versioned schema migrations (PRAGMA user_version)
    errors.py        # Domain exceptions
    utils.py         # CLI input helpers
    test_project.py  # Unit tests
    requirements.txt # Dependencies
    README.md


    #### Installation:
    1. Clone the repository (or download the source):
    bash:
    git clone https://github.com/username/joblens.git
    cd joblens

    2. Create a virtual environment(recommended):
    bash:
    python -m venv .venv
    source .venv/bin/activate   # macOS/Linux
    # .venv\Scripts\activate    # Windows

    3. Install dependencies:
    bash:
    pip install -r requirements.txt

    4. Set up your DeepSeek API key:
    Get an API key from DeepSeek, and set it as an environment variable:
    bash:
    export DEEPSEEK_API_KEY="your_api_key_here"

    5. Optional settings (all have sensible defaults):
    bash:
    export JOBLENS_DB="path/to/jobs.db"      # default: jobs.db next to the code
    export JOBLENS_MODEL="deepseek-chat"     # model used for extraction
    export JOBLENS_MAX_JD_CHARS="8000"       # longer postings are truncated

    The database file is created next to the source code, not in the current
    directory, so the program can be started from anywhere.


    #### Usage
    Run the main program:
    bash:
    python project.py
    You will see a menu:
    ====== JobLens ======
    1. Create a job
    2. Match skills
    3. View a job
    4. View jobs
    5. Exit

    Select 1, then enter the company, title, salary and status. Paste the full job description, and type END on a new line when finished. The Program will call the DeepSeek API to extract skills and save them to the database.

    Select 2, then enter the job ID, the program compares the job's requirements with your stored skills and prints like this:
    Matched skills:
    - Python (required)
    - SQL (preferred)

    Missing skills:
    - C# (required)
    - .NET (required)

    Select 3 to view a single job by ID.

    Select 4 to list all stored jobs.


