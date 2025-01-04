from openai import OpenAI
from dotenv import load_dotenv
import os
import traceback
import time

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def get_answer(prompt, text, massages=[]):
    answer = None
    error_count = 0
    massages.extend(
        [
            {"role": "system", "content": f"{prompt}"},
            {"role": "user", "content": f"{text}"},
        ]
    )
    while answer is None and error_count < 5:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=massages,
                presence_penalty=-0.5,
                frequency_penalty=-0,
                top_p=0.9,
                timeout=30,
            )
            answer = response.choices[0].message.content

        except Exception as e:
            trace = traceback.format_exc()
            print(trace)
            error_count += 1
            time.sleep(10)

    return answer


def get_answer4(prompt, text):
    answer = None
    error_count = 0
    while answer is None and error_count < 5:
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": f"{prompt}"},
                    {"role": "user", "content": f"{text}"},
                ],
                presence_penalty=-0.5,
                frequency_penalty=-0,
                top_p=0.9,
                timeout=120,
            )
            answer = response.choices[0].message.content

        except Exception as e:
            trace = traceback.format_exc()
            print(trace)
            error_count += 1
            time.sleep(10)

    return answer
