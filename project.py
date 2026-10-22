
from database import create_job_workflow, get_job, get_stored_jobs, init_db
from skills import match_skills_workflow



def main():
    init_db()

    while True:
        print_menu()

        choice = input("Choose an option: ").strip()

        if choice == "1":
            create_job_workflow()

        elif choice == "2":
            match_skills_workflow()

        elif choice == "3":
            view_job_workflow()


        elif choice == "4":
            view_jobs_workflow()


        elif choice == "5":
            print("Goodbye!")
            break

        else:
            print("Invalid option")







def print_menu():
    print("====== Joblens ======")
    print("1. Create a job")
    print("2. Match skills")
    print("3. View a job")
    print("4. View jobs")
    print("5. Exit")



def view_job_workflow():
    job_id = int(input("What's the job id?").strip())

    job = get_job(job_id)

    if job is None:
        print("Job not found. ")
        return

    print(f"Company: {job[1]}")
    print(f"Title: {job[2]}")
    print(f"Salary: {job[3]}")
    print(f"Status: {job[5]}")


def view_jobs_workflow():

    stored_jobs = get_stored_jobs()

    for job in stored_jobs:
        print(f"{job[0]}. {job[1]} - {job[2]}")



if __name__ == "__main__":
    main()
