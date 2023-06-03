import os
from dotenv import load_dotenv
import time
import sqlite3
import requests
from datetime import datetime
import json
from tqdm import tqdm

connection = sqlite3.connect("atp.db")
cur = connection.cursor()


cur.execute("""
CREATE TABLE IF NOT EXISTS users
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   did TEXT UNIQUE,
   handle TEXT,
   endpoint TEXT,
   created_at DATETIME
   )
""")
connection.commit()

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)


def get_did_list(after=None):
  prev = datetime.utcnow()
  url = 'https://plc.directory/export'
  if after:
    url += f"?after={after}"
  response = requests.get(url)
  now = datetime.utcnow()
  print(now - prev)
  return response.text


def insert_did_many(connection, did_list):
  cur = connection.cursor()
  cur.executemany("""
  INSERT OR IGNORE INTO users 
    (did, handle, endpoint, created_at)
    VALUES (?, ?, ?, ?)
  """, did_list)
  connection.commit()


last_created_at = None

while True:
  did_list_text = get_did_list(last_created_at)
  did_json_list = did_list_text.split("\n")
  print(len(did_json_list))
  did_list = []
  last_created_at_prev = last_created_at

  for i, did_json in enumerate(tqdm(did_json_list)):
    did_dict = json.loads(did_json)
    if did_dict["operation"]["type"] == "create":
      endpoint = did_dict["operation"]["service"]
      did_list.append((did_dict["did"].replace("did:plc:", ""),
                      did_dict["operation"]["handle"],
                      endpoint,
                      did_dict["createdAt"]))
    elif did_dict["operation"]["type"] == "plc_operation":
      if did_dict["operation"]["prev"] is None and \
              "atproto_pds" in did_dict["operation"]["services"]:
        handle = did_dict["operation"]["alsoKnownAs"][0].replace("at://", "")
        endpoint = did_dict["operation"]["services"]["atproto_pds"]["endpoint"]
        did_list.append((did_dict["did"].replace("did:plc:", ""),
                        handle,
                        endpoint,
                        did_dict["createdAt"]))
  last_created_at = did_dict["createdAt"]
  if last_created_at == last_created_at_prev:
    break
  print(last_created_at)

  insert_did_many(connection, did_list)
  time.sleep(0.05)
