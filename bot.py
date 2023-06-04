import os
from dotenv import load_dotenv
import time
import sqlite3
from atprototools import Session
from easydict import EasyDict
import gpt
from datetime import datetime, timedelta
import pytz
from dateutil.parser import parse
import random
import util
import json
import requests

connection_atp = sqlite3.connect("atp.db")

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

cur.execute("""
CREATE TABLE IF NOT EXISTS users
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   DID TEXT,
   handle TEXT,
   post_count INTEGER,
   pref TEXT,
   created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
   update_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
   )
""")

cur.execute("""
CREATE TRIGGER IF NOT EXISTS update_users_timestamp
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
  UPDATE users SET update_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS count_post
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   count INTEGER,
   created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
   )
""")


def post(session, text):
  session.postBloot(text)


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


def get_profile(session, handle):
  response = session.get_profile(handle)
  return json.loads(response.text)


def _get_follows(session, handle, limit=100, cursor=None):
  headers = {"Authorization": "Bearer " + session.ATP_AUTH_TOKEN}

  url = session.ATP_HOST +\
      f"/xrpc/app.bsky.graph.getFollows?actor={handle}&limit={limit}"
  if cursor:
    url += f"&cursor={cursor}"

  response = requests.get(
      url,
      headers=headers
  )

  return json.loads(response.text)


def _get_followers(session, handle, limit=100, cursor=None):
  headers = {"Authorization": "Bearer " + session.ATP_AUTH_TOKEN}

  url = session.ATP_HOST +\
      f"/xrpc/app.bsky.graph.getFollowers?actor={handle}&limit={limit}"
  if cursor:
    url += f"&cursor={cursor}"

  response = requests.get(
      url,
      headers=headers
  )

  return json.loads(response.text)


def get_follows(session, handle):
  cursor = None
  all_follow_list = []
  while True:
    response = _get_follows(session, handle, limit=100, cursor=cursor)
    follows = response["follows"]
    follow_list = [follow["handle"] for follow in follows]
    all_follow_list.extend(follow_list)
    prev_cursor = cursor
    if "cursor" in response:
      cursor = response["cursor"]
    if cursor is None or prev_cursor == cursor or len(follow_list) < 100:
      break

  return all_follow_list


def get_followers(session, handle):
  cursor = None
  all_follower_list = []
  while True:
    response = _get_followers(session, handle, limit=100, cursor=cursor)
    followers = response["followers"]
    follower_list = [follower["handle"] for follower in followers]
    all_follower_list.extend(follower_list)
    prev_cursor = cursor
    if "cursor" in response:
      cursor = response["cursor"]
    if cursor is None or prev_cursor == cursor or len(follower_list) < 100:
      break

  return all_follower_list


def is_follower(session, bot_handle, handle, followers=None):
  cursor = None
  folowed = False
  while True:
    if followers is None:
      response = _get_followers(session, bot_handle, limit=100, cursor=cursor)
      followers = response["followers"]
      follower_list = [follower["handle"] for follower in followers]
    else:
      follower_list = followers
    if handle in follower_list:
      folowed = True
      break

    prev_cursor = cursor
    if "cursor" in response:
      cursor = response["cursor"]
    if cursor is None or prev_cursor == cursor or len(follower_list) < 100:
      break
    time.sleep(0.05)

  return folowed


def update_follow(session, bot_handle):
  bot_follows = get_follows(session, bot_handle)
  bot_followers = get_followers(session, bot_handle)
  # unfollows = [item for item in bot_follows if item not in bot_followers]
  followbacks = [item for item in bot_followers if item not in bot_follows]
  for handle in followbacks:
    response = session.follow(handle)
    print(f"follow back:{handle}:{response}")
    time.sleep(0.05)


def fortune(connection, prompt, eline):
  row = util.get_latest_record_by_did(connection, eline.post.author.did)
  fortuneOk = False
  if row:
    now = datetime.now(pytz.utc)
    created_at = parse(row["created_at"])
    if (now - created_at) >= timedelta(hours=24):
      fortuneOk = True
    else:
      remaining_time = str(timedelta(hours=24) - (now - created_at))
      answer = f"占いは24時間に1回までですわ。\nふふ、そう逸らないことね。\nあと約{remaining_time} ほどお待ち遊ばせ。"
      reply_to(session, answer[:300], eline.post.cid, eline.post.uri)
      print(answer)
  else:
    fortuneOk = True
  if fortuneOk:
    user_text = eline.post.record.text
    text = "今日のわたしの運勢を占って。結果はランダムで決めて、" +\
        f"その結果に従って占いの内容を運の良さは★マークを５段階でラッキーアイテム、ラッキーカラーとかも教えて。{user_text}"
    print("fortune")
    answer = gpt.get_answer(prompt, text)
    util.record_reaction(connection, eline)
    print(answer)
    reply_to(session, answer[:300], eline.post.cid, eline.post.uri)


def status(connection_atp, session, eline):
  profile = get_profile(session, eline.post.author.handle)
  postsCount = profile["postsCount"]
  did = eline.post.author.did.replace("did:plc:", "")
  result = util.get_user_info(connection_atp, did)
  startDateTime = result["created_at"]
  parsedStartDateTime = parse(startDateTime)
  now = datetime.now(pytz.utc)
  time_elapsed = now - parsedStartDateTime
  days = time_elapsed.days
  hours, remainder = divmod(time_elapsed.seconds, 3600)
  minutes, _ = divmod(remainder, 60)
  average_post = postsCount / (days + hours / 24 + minutes / 60 / 24)

  order = result["order"]
  status_text = "ふふ、あなたのステータスをお知らせしますわ。\n" +\
      f"あなたは{order}番目のアカウントのようですわ。\n" + \
      f"作られた日時は世界標準時で {startDateTime} ですわね。\n" + \
      f"あなたが来てから{days}日と{hours}時間{minutes}分が経ちましたのね。\n" + \
      f"1日あたりの投稿数は約{average_post:.2f}回のようですわ。\n" + \
      "ごきげんよう。"

  return status_text


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

bot_names = [
    "Blueskyちゃん", "Bluesky ちゃん", "bluesky ちゃん", "blueskyちゃん",
    "ブルースカイちゃん", "ぶるすこちゃん", "ブルスコちゃん", "ブルス子ちゃん",
]
bot_names = [
    "テストちゃん"
]


prompt = f"これはあなたの人格です。'{personality}'\nこの人格を演じて次の文章に対して30〜200文字以内で返信してください。"


now = datetime.now(pytz.utc)
started = now
answered = None
count = 0
while True:
  skyline = session.getSkyline(50)
  feed = skyline.json().get('feed')
  sorted_feed = sorted(feed, key=lambda x: parse(x["post"]["indexedAt"]))
  bot_followers = get_followers(session, username)

  for line in sorted_feed:
    eline = EasyDict(line)
    if eline.post.author.handle == username:
      # 自分自身には反応しない
      continue
    # print(eline.post.indexedAt)
    postDatetime = parse(eline.post.indexedAt)
    if now < postDatetime:
      print(postDatetime)
      if is_follower(session,
                     username,
                     eline.post.author.handle,
                     followers=bot_followers):
        # フォロワのみ反応する
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
            text = eline.post.record.text
            if "占って" in text and\
                    util.has_mention(bot_names, text):
              print(line)
              fortune(connection, prompt, eline)
            elif "status" in text and\
                    util.has_mention(bot_names, text):
              print(line)
              answer = status(connection_atp, session, eline)
              print(answer)
              reply_to(session, answer[:300], eline.post.cid, eline.post.uri)
            else:
              print(line)
              bonus = 0
              if util.has_mention(bot_names, text):
                bonus = 5
              if answered is None or (now - answered) >= timedelta(minutes=20):
                bonus = 100
              percent = random.uniform(0, 100)
              print(percent, bonus)
              if percent <= (3 + bonus):
                print("atari")
                answer = gpt.get_answer(prompt, text)
                print(answer)
                reply_to(session, answer[:300], eline.post.cid, eline.post.uri)
                answered = datetime.now(pytz.utc)
              else:
                print("hazure")
      now = postDatetime
  time.sleep(3)
  prev_count = count
  count = util.aggregate_users(connection_atp)
  posted_count = util.get_posted_user_count(connection)
  if prev_count != count:
    print(count)
  if count % 100 == 0 or (posted_count + 100) <= count:
    if posted_count < count:
      if count % 10000 == 0:
        post(session, f"お兄さま、見てくださいまし！Blueskyのユーザーがついに{count}人になりましたわよ。素晴らしいですわ！皆様の努力の賜物ですわね！")
      elif count % 1000 == 0:
        post(session, f"うふふ、お兄さま、Blueskyのユーザーが{count}人になりましたわね。")
      else:
        post(session, f"ふふ、お兄さま、Blueskyのユーザーが{count}人になりましたわよ。")

      util.store_posted_user_count(connection, count)

  update_follow(session, username)
