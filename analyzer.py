from openai import OpenAI
import os
import json
import sqlite3





def analyze_job(stored_description):
    # Ask AI: What skills are in this JD?
    client = OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com"
    )

    response = client.chat.completions.create(
        model="deepseek-flash",
        messages=[
            {
                "role": "user",
                "content": f"""
                Read this job description and extract the technical skills.

                Return ONLY valid JSON in this exact format:
                {{
                    "requirements": [
                        {{"skill": "C#", "importance": "required"}},
                        {{"skill": ".NET", "importance": "required"}}
                    ]
                }}

                Use "required" for skills that the job explicitly asks for.
                Use "preferred" for skills that are mentioned but not clearly required.

                Job description:
                {stored_description}
                """
            }
        ]
    )

    content = response.choices[0].message.content
    try:
        data = json.loads(content)
        return data["requirements"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Failed to parse LLM response: {e}")
        return []












