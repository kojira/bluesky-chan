import requests
import json


def record_reaction(connection, eline):
  displayName = eline.post.author.displayName if "displayName" in eline.post.author else ""
  reaction = {"did": eline.post.author.did,
              "handle": eline.post.author.handle,
              "displayName": displayName,
              "created_at": eline.post.indexedAt}
  sql = """
    INSERT INTO reactions (did, handle, displayName, created_at)
              VALUES (:did, :handle, :displayName, :created_at)
  """
  cur = connection.cursor()
  cur.execute(sql, reaction)
  connection.commit()


def get_latest_record_by_did(connection, did):
  sql = """
    SELECT *
    FROM reactions
    WHERE did = :did
    ORDER BY created_at DESC
    LIMIT 1
  """
  cur = connection.cursor()
  cur.execute(sql, {'did': did})
  row = cur.fetchone()
  return row


def has_mention(bot_names, text):
  found = False
  for bot_name in bot_names:
    if bot_name in text:
      found = True
      break
  print("found:", found)
  return found


def get_did_list(after=None):
  url = 'https://plc.directory/export'
  if after:
    url += f"?after={after}"
  response = requests.get(url)
  return response.text


def insert_did_many(connection, did_list):
  cur = connection.cursor()
  cur.executemany("""
  INSERT OR IGNORE INTO users 
    (did, handle, endpoint, created_at)
    VALUES (?, ?, ?, ?)
  """, did_list)
  connection.commit()


def get_last_created_at(connection):
  cur = connection.cursor()
  sql = """
    SELECT *
    FROM users
    ORDER BY created_at DESC
    LIMIT 1
  """
  cur = connection.cursor()
  cur.execute(sql)
  row = cur.fetchone()
  return row[4]


def get_user_info(connection, did):
  cur = connection.cursor()
  params = {'endpoint': 'https://bsky.social', 'did': did}
  print(did)

  query = '''
    SELECT created_at FROM users
      WHERE endpoint = :endpoint AND did = :did
  '''
  cur.execute(query, params)
  row = cur.fetchone()
  if row:
    created_at = row[0]

    params = {'endpoint': 'https://bsky.social',
              'created_at': created_at
              }
    query = '''
      SELECT COUNT(*) FROM users
        WHERE endpoint = :endpoint AND
          created_at <= :created_at
        ORDER BY created_at ASC
    '''

    cur.execute(query, params)
    order = cur.fetchone()[0]
  else:
    order = None
    created_at = None

  return {"order": order, "created_at": created_at}


def get_user_count(connection):
  cur = connection.cursor()
  params = {'endpoint': 'https://bsky.social'}

  query = '''
    SELECT COUNT(*) FROM users
      WHERE endpoint = :endpoint
  '''
  cur.execute(query, params)
  row = cur.fetchone()
  count = row[0]
  return count


def store_posted_user_count(connection, count):
  cur = connection.cursor()
  sql = """
    INSERT INTO count_post (count)
              VALUES (:count)
  """
  cur = connection.cursor()
  cur.execute(sql, {"count": count})
  connection.commit()


def get_posted_user_count(connection):
  cur = connection.cursor()
  sql = """
    SELECT count FROM count_post ORDER BY created_at DESC LIMIT 1
  """
  cur = connection.cursor()
  cur.execute(sql)
  row = cur.fetchone()
  count = 0
  if row:
    count = row[0]
  return count


def aggregate_users(connection, last_created_at=None):
  if last_created_at is None:
    last_created_at = get_last_created_at(connection)
    # print(last_created_at)
  did_list_text = get_did_list(last_created_at)
  did_json_list = did_list_text.split("\n")
  did_list = []
  if len(did_list_text) > 0:
    for i, did_json in enumerate(did_json_list):
      # print(did_json)
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
    if len(did_list) > 0:
      insert_did_many(connection, did_list)

  count = get_user_count(connection)
  return count
