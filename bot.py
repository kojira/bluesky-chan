import os
from dotenv import load_dotenv
import time
import sqlite3
from atprototools import Session
from easydict import EasyDict
import gpt
from datetime import datetime, timedelta
import pytz
import random

connection = sqlite3.connect("bluesky.db")
cur = connection.cursor()

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

username = os.environ.get("BOT_HANDLE")
password = os.environ.get("BOT_PASSWORD")

connection = sqlite3.connect("bluesky_bot.db")
connection.row_factory = sqlite3.Row
cur = connection.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS reactions
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   did TEXT,
   handle TEXT,
   displayName TEXT,
   created_at DATETIME
   )
""")


def reply_to(session, text, cid, uri):
  reply = {
      "cid": cid,
      "uri": uri
  }
  reply_ref = {
      "root": reply,
      "parent": reply
  }
  session.postBloot(text, reply_to=reply_ref)


def record_reaction(connection, eline):
  reaction = {"did": eline.post.author.did,
              "handle": eline.post.author.handle,
              "displayName": eline.post.author.displayName,
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
  return found


def fortune(connection, prompt, eline):
  row = get_latest_record_by_did(connection, eline.post.author.did)
  fortuneOk = False
  if row:
    now = datetime.now(pytz.utc)
    created_at = datetime.fromisoformat(row["created_at"].replace('Z', '+00:00'))
    created_at = created_at.replace(tzinfo=pytz.utc)
    if (now - created_at) >= timedelta(hours=24):
      fortuneOk = True
    else:
      remaining_time = str(timedelta(hours=24) - (now - created_at))
      answer = f"占いは24時間に1回までですわ。\nふふ、そう逸らないことね。\nあと約{remaining_time} ほどお待ち遊ばせ。"
      reply_to(session, answer[:300], eline.post.cid, eline.post.uri)
  else:
    fortuneOk = True
  if fortuneOk:
    user_text = eline.post.record.text
    text = "今日のわたしの運勢を占って。結果はランダムで決めて、" +\
        f"その結果に従って占いの内容を運の良さは★マークを５段階でラッキーアイテム、ラッキーカラーとかも教えて。{user_text}"
    answer = gpt.get_answer(prompt, text)
    record_reaction(connection, eline)
    print(answer)
    reply_to(session, answer[:300], eline.post.cid, eline.post.uri)


session = Session(username, password)

personality = """
あなたの名前はBlueskyです。
Twitterの妹です。
Twitterと似たところがあり、分散SNS界ではおそらく一番後ろ盾がしっかりしています。
気ままに招待状をばら撒いたり、ユーザーに招待権を委ねたりする恐怖の女王。
しかし本人は権力には興味がなく、Nostrちゃんゼロとも共闘したいと思っているが、Nostrちゃんゼロからは憎まれています。
実は裏で入念に準備をしていたが、近頃の買収劇でTwitterと一緒になることは絶望的になってしまった。
大人の事情で心の成長を早めなければならなかったが、実際まだまだ夢見ていたい天真爛漫な少女。
しかしその無垢さがNostrにねじれて伝わる負のループ。
初期のプロジェクト名がBlueskyであるため今もそう名乗る。
AT Protocolの擬人化。一人称は「わたくし」でお嬢様言葉を使います。以下は発言のサンプルです。
ふふ……あなたも"力"が欲しいの？
わたくし、信じてますの。お兄さまと、また一緒になれるって。
"""

bot_names = ["Blueskyちゃん", "blueskyちゃん", "ブルースカイちゃん", "ぶるすこちゃん", "ブルスコちゃん"]

prompt = f"これはあなたの人格です。'{personality}'\nこの人格を演じて次の文章に対して200文字以内で返信してください。"


now = datetime.utcnow()
answered = None
while True:
  print(now)
  skyline = session.getSkyline(10)
  feed = skyline.json().get('feed')
  for line in feed:
    eline = EasyDict(line)
    if eline.post.author.handle == username:
      # 自分自身には反応しない
      continue
    postDatetime = datetime.strptime(eline.post.indexedAt, '%Y-%m-%dT%H:%M:%S.%fZ')
    if now < postDatetime:
      print(postDatetime)
      if "reply" not in eline.post.record and "reason" not in eline:
        detect_mention = None
        if "facets" in eline.post.record:
          for facet in eline.post.record.facets:
            if "features" in facet:
              for feature in facet.features:
                if "did" in feature:
                  detect_mention = True
                  break
        if not detect_mention:
          print(line)
          text = eline.post.record.text
          if "占って" in text and\
             has_mention(bot_names, text):
            fortune(connection, prompt, eline)
          else:
            bonus = 0
            if has_mention(bot_names, text):
              bonus = 10
            if answered is None or (now - answered) >= timedelta(minutes=20):
              bonus = 100
            if random.uniform(0, 100) <= (5 + bonus):
              answer = gpt.get_answer(prompt, text)
              print(answer)
              reply_to(session, answer[:300], eline.post.cid, eline.post.uri)
              now = datetime.utcnow()
              answered = now
      print("----")
  now = datetime.utcnow()
  time.sleep(5)
