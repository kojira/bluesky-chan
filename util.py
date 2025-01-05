import requests
import json
import sqlite3
import traceback
from datetime import datetime


def insert_user_dialog(connection, did, text):
    params = {
        "did": did,
        "role": "user",
        "message": text,
    }
    sql = """
    INSERT INTO dialogs (did, role, message)
              VALUES (:did, :role, :message)
    """
    cur = connection.cursor()
    cur.execute(sql, params)
    connection.commit()


def insert_bot_dialog(connection, did, text):
    params = {
        "did": did,
        "role": "assistant",
        "message": text,
    }
    sql = """
    INSERT INTO dialogs (did, role, message)
              VALUES (:did, :role, :message)
    """
    cur = connection.cursor()
    cur.execute(sql, params)
    connection.commit()


def get_recent_dialogs(connection, did, limit=30):
    params = {
        "did": did,
        "limit": limit,
    }
    sql = """
    SELECT role, message, created_at
    FROM dialogs
    WHERE did = :did
    ORDER BY created_at DESC
    LIMIT :limit
    """
    cur = connection.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    dialogs = []
    for row in rows:
        timestamp = datetime.strptime(row[2], "%Y-%m-%d %H:%M:%S")
        formatted_date = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        role = row[0]
        content = f"[{formatted_date}] {row[1]}"
        dialogs.append({"role": role, "content": content})

    dialogs.reverse()

    return dialogs


def record_reaction(connection, eline):
    displayName = (
        eline.post.author.displayName if "displayName" in eline.post.author else ""
    )
    params = {
        "did": eline.post.author.did,
        "handle": eline.post.author.handle,
        "displayName": displayName,
        "created_at": eline.post.indexedAt,
    }
    sql = """
    INSERT INTO reactions (did, handle, displayName, created_at)
              VALUES (:did, :handle, :displayName, :created_at)
    """
    cur = connection.cursor()
    cur.execute(sql, params)
    connection.commit()


def get_fortune_counts(connection, did):
    params = {"did": did}
    sql = """
    SELECT COUNT(*) FROM reactions
      WHERE did = :did
    """
    cur = connection.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    counts = row[0]
    return counts


def create_user_settings(connection, did):
    sql = """
    INSERT INTO users (did, mode, analyze, points, all_points)
              VALUES (:did, 0, 0, 0, 0)
  """
    params = {
        "did": did,
    }
    cur = connection.cursor()
    cur.execute(sql, params)
    connection.commit()


def get_user_settings(connection, did):
    sql = """
    SELECT * FROM users WHERE did=:did
    """
    params = {
        "did": did,
    }
    cur = connection.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    settings = {}
    if row:
        for key in row.keys():
            settings[key] = row[key]
    else:
        create_user_settings(connection, did)
        settings = get_user_settings(connection, did)

    return settings


def update_user_settings(connection, did, settings):
    sql = """
    UPDATE users SET
      mode = :mode,
      analyze = :analyze,
      points = :points,
      all_points = :all_points
      WHERE did = :did
    """
    params = {
        "did": did,
        "mode": settings["mode"],
        "analyze": settings["analyze"],
        "points": settings["points"],
        "all_points": settings["all_points"],
    }
    cur = connection.cursor()
    cur.execute(sql, params)
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
    cur.execute(sql, {"did": did})
    row = cur.fetchone()
    return row


def has_mention(bot_names, eline):
    text = eline.post.record.text
    found = False
    for bot_name in bot_names:
        if bot_name in text:
            found = True
            break
        if "reply" in eline:
            if eline.reply.parent.author.handle == bot_name:
                found = True
                break

    return found


def get_did_list(after=None):
    url = "https://plc.directory/export"
    if after:
        url += f"?after={after}"
    response = requests.get(url, timeout=(15, 15))
    return response.text


def insert_did_many(connection, did_list):
    cur = connection.cursor()
    cur.executemany(
        """
    INSERT OR IGNORE INTO users
        (did, handle, endpoint, created_at)
        VALUES (?, ?, ?, ?)
    """,
        did_list,
    )
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
    params = {
        "did": did,
    }
    print(did)

    query = """
    SELECT created_at FROM users
      WHERE did = :did
    """
    cur.execute(query, params)
    row = cur.fetchone()
    if row:
        created_at = row[0]
        params = {
            "endpoint": "https://%",
            "except_endpoint1": "https://stems.social",
            "except_endpoint2": "%localhost%",
            "except_endpoint3": "%example.com",
            "except_endpoint4": "https://",
            "except_endpoint4": "https:///%",
            "except_endpoint5": "file://%",
            "except_endpoint6": "%;%",
            "except_endpoint7": "%<%",
            "except_endpoint8": "%>%",
            "except_endpoint9": "%|%",
            "except_endpoint10": "%534.bsky.social%",
            "except_endpoint11": "%test.invalid",
            "except_endpoint12": "%among.us.gov",
            "except_endpoint13": "https://na",
            "except_endpoint14": "https://test2",
            "except_endpoint15": "https://boobee.blue",
            "created_at": created_at,
        }

        query = """
          SELECT COUNT(*) FROM users
            WHERE
              endpoint like :endpoint and
              endpoint not like :except_endpoint1 and
              endpoint not LIKE :except_endpoint2 and
              endpoint not LIKE :except_endpoint3 and
              endpoint not LIKE :except_endpoint4 and
              endpoint not LIKE :except_endpoint5 and
              endpoint not LIKE :except_endpoint6 and
              endpoint not LIKE :except_endpoint7 and
              endpoint not LIKE :except_endpoint8 and
              endpoint not LIKE :except_endpoint9 and
              endpoint not LIKE :except_endpoint10 and
              endpoint not LIKE :except_endpoint11 and
              endpoint not LIKE :except_endpoint12 and
              endpoint not LIKE :except_endpoint13 and
              endpoint not LIKE :except_endpoint14 and
              endpoint not LIKE :except_endpoint15 and
              created_at <= :created_at
        ORDER BY created_at ASC
        """

        cur.execute(query, params)
        order = cur.fetchone()[0]
    else:
        order = None
        created_at = None

    return {"order": order, "created_at": created_at}


def get_user_count(connection):
    cur = connection.cursor()
    params = {
        "endpoint": "https://%",
        "except_endpoint1": "https://stems.social",
        "except_endpoint2": "%localhost%",
        "except_endpoint3": "%example.com",
        "except_endpoint4": "https://",
        "except_endpoint4": "https:///%",
        "except_endpoint5": "file://%",
        "except_endpoint6": "%;%",
        "except_endpoint7": "%<%",
        "except_endpoint8": "%>%",
        "except_endpoint9": "%|%",
        "except_endpoint10": "%534.bsky.social%",
        "except_endpoint11": "%test.invalid",
        "except_endpoint12": "%among.us.gov",
        "except_endpoint13": "https://na",
        "except_endpoint14": "https://test2",
        "except_endpoint15": "https://boobee.blue",
    }

    query = """
    SELECT COUNT(*) FROM users
      WHERE 
            endpoint like :endpoint and
            endpoint not like :except_endpoint1 and
            endpoint not LIKE :except_endpoint2 and
            endpoint not LIKE :except_endpoint3 and
            endpoint not LIKE :except_endpoint4 and
            endpoint not LIKE :except_endpoint5 and
            endpoint not LIKE :except_endpoint6 and
            endpoint not LIKE :except_endpoint7 and
            endpoint not LIKE :except_endpoint8 and
            endpoint not LIKE :except_endpoint9 and
            endpoint not LIKE :except_endpoint10 and
            endpoint not LIKE :except_endpoint11 and
            endpoint not LIKE :except_endpoint12 and
            endpoint not LIKE :except_endpoint13 and
            endpoint not LIKE :except_endpoint14 and
            endpoint not LIKE :except_endpoint15
    """
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
    did_list = []
    total = 0
    while True:
        did_list_text = get_did_list(last_created_at)
        did_json_list = did_list_text.split("\n")
        last_created_at_prev = last_created_at
        if len(did_list_text) > 0:
            for i, did_json in enumerate(did_json_list):
                # print(did_json)
                did_dict = json.loads(did_json)
                try:
                    createdAt = did_dict["createdAt"].replace("T", " ").replace("Z", "")
                    if did_dict["operation"]["type"] == "create":
                        endpoint = did_dict["operation"]["service"]
                        did_list.append(
                            (
                                did_dict["did"].replace("did:plc:", ""),
                                did_dict["operation"]["handle"],
                                endpoint,
                                createdAt,
                            )
                        )
                    elif did_dict["operation"]["type"] == "plc_operation":
                        if (
                            did_dict["operation"]["prev"] is None
                            and "atproto_pds" in did_dict["operation"]["services"]
                        ):
                            if len(did_dict["operation"]["alsoKnownAs"]) > 0:
                                handle = did_dict["operation"]["alsoKnownAs"][
                                    0
                                ].replace("at://", "")
                                endpoint = did_dict["operation"]["services"][
                                    "atproto_pds"
                                ]["endpoint"]
                                did_list.append(
                                    (
                                        did_dict["did"].replace("did:plc:", ""),
                                        handle,
                                        endpoint,
                                        createdAt,
                                    )
                                )
                except Exception as e:
                    traceback.print_exc()
                    print(repr(e))
                    print(str(e))
                    print("****************")
                    print(did_dict)
                    print("****************")
                    print(did_list_text)
                    exit(-1)
            last_created_at = did_dict["createdAt"]
            if len(did_list) > 10000:
                insert_did_many(connection, did_list)
                total += len(did_list)
                did_list = []
            print(last_created_at, total + len(did_list))

            if last_created_at == last_created_at_prev:
                break
        else:
            break
    if len(did_list) > 0:
        insert_did_many(connection, did_list)

    # count = get_user_count(connection)
    # return count


def put_log(connection, kind, param1="", param2="", param3="", param4=""):
    params = {
        "kind": kind,
        "param1": param1,
        "param2": param2,
        "param3": param3,
        "param4": param4,
    }
    sql = """
    INSERT INTO logs (kind, param1, param2, param3, param4)
              VALUES (:kind, :param1, :param2, :param3, :param4)
  """
    cur = connection.cursor()
    cur.execute(sql, params)
    connection.commit()


def put_command_log(did, command, param):
    global connection_logs
    put_log(connection_logs, kind=1, param1=did, param2=command, param3=param)


connection_logs = sqlite3.connect("logs.db")
connection_logs.row_factory = sqlite3.Row
cur_logs = connection_logs.cursor()

cur_logs.execute(
    """
CREATE TABLE IF NOT EXISTS logs
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   kind INTEGER, /* 0:error log 1:commands */
   param1 TEXT,
   param2 TEXT,
   param3 TEXT,
   param4 TEXT,
   created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
   )
"""
)


def get_stats():
    url = "https://bsky-search.jazco.io/stats"
    response = requests.get(url, timeout=(15, 15))
    return response.json()
