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
            print(f"[GPT] Calling gpt-5-mini with {len(massages)} messages")
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=massages,
                timeout=30,
            )
            print(f"[GPT] Response received: {response}")
            if response.choices and len(response.choices) > 0:
                answer = response.choices[0].message.content
                print(f"[GPT] Answer extracted: {answer[:100]}...")
            else:
                print("[GPT] No choices in response")
                error_count += 1
                time.sleep(10)

        except Exception as e:
            print(f"[GPT] Exception occurred: {type(e).__name__}: {e}")
            trace = traceback.format_exc()
            print(trace)
            error_count += 1
            time.sleep(10)

    print(f"[GPT] Final answer: {answer}")
    return answer


def get_answer5_nano(prompt, text):
    answer = None
    error_count = 0
    while answer is None and error_count < 5:
        try:
            print(f"[GPT5] Calling gpt-5-nano with prompt length: {len(prompt)}")
            response = client.chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": f"{prompt}"},
                    {"role": "user", "content": f"{text}"},
                ],
                timeout=120,
            )
            print(f"[GPT5] Response received: {response}")
            if response.choices and len(response.choices) > 0:
                answer = response.choices[0].message.content
                print(f"[GPT5] Answer extracted: {answer[:100]}...")
            else:
                print("[GPT5] No choices in response")
                error_count += 1
                time.sleep(10)

        except Exception as e:
            print(f"[GPT5] Exception occurred: {type(e).__name__}: {e}")
            trace = traceback.format_exc()
            print(trace)
            error_count += 1
            time.sleep(10)

    print(f"[GPT5] Final answer: {answer}")
    return answer


def get_answer5(prompt, text):
    answer = None
    error_count = 0
    while answer is None and error_count < 5:
        try:
            print(f"[GPT5] Calling gpt-5 with prompt length: {len(prompt)}")
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": f"{prompt}"},
                    {"role": "user", "content": f"{text}"},
                ],
                timeout=120,
            )
            print(f"[GPT5] Response received: {response}")
            if response.choices and len(response.choices) > 0:
                answer = response.choices[0].message.content
                print(f"[GPT5] Answer extracted: {answer[:100]}...")
            else:
                print("[GPT5] No choices in response")
                error_count += 1
                time.sleep(10)

        except Exception as e:
            print(f"[GPT5] Exception occurred: {type(e).__name__}: {e}")
            trace = traceback.format_exc()
            print(trace)
            error_count += 1
            time.sleep(10)

    print(f"[GPT5] Final answer: {answer}")
    return answer
