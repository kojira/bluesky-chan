import openai
from dotenv import load_dotenv
import os
import traceback
import time

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

openai.api_key = os.environ.get("OPENAI_API_KEY")


def get_answer(prompt, text):
  answer = None
  error_count = 0
  while answer is None and error_count < 5:
    try:
      response = openai.ChatCompletion.create(
          model="gpt-3.5-turbo-0613",
          messages=[
              {"role": "system", "content": f"{prompt}"},
              {"role": "user", "content": f"{text}"},
          ],
          presence_penalty=-0.5,
          frequency_penalty=-0,
          top_p=0.9,
          timeout=30,
      )
      answer = response["choices"][0]["message"]["content"]

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
      response = openai.ChatCompletion.create(
          model="gpt-4-0613",
          messages=[
              {"role": "system", "content": f"{prompt}"},
              {"role": "user", "content": f"{text}"},
          ],
          presence_penalty=-0.5,
          frequency_penalty=-0,
          top_p=0.9,
          timeout=30,
      )
      answer = response["choices"][0]["message"]["content"]

    except Exception as e:
      trace = traceback.format_exc()
      print(trace)
      error_count += 1
      time.sleep(10)

  return answer
