import os
from dotenv import load_dotenv
import time
import sqlite3
from atprototools import Session
from easydict import EasyDict
import gpt
from datetime import datetime, timedelta, timezone
import pytz
from dateutil.parser import parse
import random
import util
import json
import requests
import re
import cairosvg


connection_atp = sqlite3.connect("atp.db")
cur = connection_atp.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   did TEXT UNIQUE,
   handle TEXT,
   endpoint TEXT,
   created_at DATETIME
   )
""")
connection_atp.commit()

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
   did TEXT UNIQUE,
   mode INTEGER,
   analyze INTEGER,
   points INTEGER,
   all_points INTEGER,
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


def login(username, password):
  session = Session(username, password)
  print(f"login at:{datetime.now(pytz.utc)}", session)
  return session


def get_did(session, username):
  response = session.resolveHandle(username)
  return json.loads(response.text)["did"]


def post(session, text):
  print(text)
  session.postBloot(text)
  # pass


def reply_to(session, text, eline, image_path=None):
  root_cid = None
  root_uri = None
  if "reply" in eline:
    root_cid = eline.reply.root.cid
    root_uri = eline.reply.root.uri

  if root_cid:
    root = {
        "cid": root_cid,
        "uri": root_uri
    }
  else:
    root = {
        "cid": eline.post.cid,
        "uri": eline.post.uri
    }

  reply = {
      "cid": eline.post.cid,
      "uri": eline.post.uri
  }
  reply_ref = {
      "root": root,
      "parent": reply
  }
  chunk_size = 280
  for i in range(0, len(text), chunk_size):
    chunk = text[i:i + chunk_size]
    if i == 0 and image_path:
      response = post_image(session, chunk, image_path, reply_to=reply_ref)
    else:
      response = session.postBloot(chunk, reply_to=reply_ref)
    reply = json.loads(response.text)
    reply_ref["parent"] = reply


def post_image(session, postcontent, image_path, reply_to=None, content_type="image/png"):
  """Post a bloot."""
  timestamp = datetime.utcnow()
  timestamp = timestamp.isoformat().replace('+00:00', 'Z')

  headers = {"Authorization": "Bearer " + session.ATP_AUTH_TOKEN}

  data = {
      "collection": "app.bsky.feed.post",
      "$type": "app.bsky.feed.post",
      "repo": "{}".format(session.DID),
      "record": {
          "$type": "app.bsky.feed.post",
          "createdAt": timestamp,
          "text": postcontent
      }
  }

  if image_path:
    data['record']['embed'] = {}
    image_resp = session.uploadBlob(image_path, content_type)
    data["record"]["embed"]["$type"] = "app.bsky.embed.images"
    data['record']["embed"]['images'] = [{
        "alt": "",
        "image": image_resp.json().get('blob')
    }]
  if reply_to:
    data['record']['reply'] = reply_to
  resp = requests.post(
      session.ATP_HOST + "/xrpc/com.atproto.repo.createRecord",
      json=data,
      headers=headers
  )

  return resp


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


def is_follower(session, bot_handle, handle, followers):
  folowed = False
  if handle in followers:
    folowed = True
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


def get_fortune_text(name, user_text):
  percent = random.uniform(0, 100)
  if percent < 50:
    text = f"私の名前は{name}です。今日のわたしの運勢を占って。結果はランダムで決めて、" +\
        f"その結果に従って占いの内容を運の良さは★マークを５段階でラッキーアイテム、ラッキーカラーとかも教えて。{user_text}"
  elif percent < 75:
    text = f"私の名前は{name}です。私の今日の運勢をトランプ占いしてください。\n{user_text}"
  elif percent < 90:
    text = f"私の名前は{name}です。私の今日の運勢をオラクルカードで占ってください。\n{user_text}"
  else:
    text = f"私の名前は{name}です。水晶球を持っている占い師になりきって、私の今日の運勢を水晶球占いしてください。\n{user_text}"

  if "fortune" in user_text:
    text += "英語で回答してください."

  return text


def fortune(connection, prompt, name, settings, eline):
  row = util.get_latest_record_by_did(connection, eline.post.author.did)
  did = eline.post.author.did.replace("did:plc:", "")
  fortuneOk = False
  use_point = False
  user_text = eline.post.record.text
  if row:
    now = datetime.now(pytz.utc)
    created_at = parse(row["created_at"])
    if (now - created_at) >= timedelta(hours=24):
      fortuneOk = True
    else:
      if "ポイント消費" in user_text or "ポイントを消費" in user_text:
        if settings["points"] > 0:
          fortuneOk = True
          use_point = True
        else:
          util.put_command_log(did, "fortune", "wait")
          remaining_time = str(timedelta(hours=24) - (now - created_at))
          answer = f"""{name}様、占いは24時間に1回までですわ。
ふふ、そう逸らないことね。
あと約{remaining_time} ほどお待ち遊ばせ。
まだBluesky Pointがたまっていないようですわ。
"""
      else:
        util.put_command_log(did, "fortune", "wait")
        remaining_time = str(timedelta(hours=24) - (now - created_at))
        answer = f"""{name}様、占いは24時間に1回までですわ。
ふふ、そう逸らないことね。
あと約{remaining_time} ほどお待ち遊ばせ。
もし急ぐ場合にはポイントを消費して占うこともできますわ。

{name}様の残りBluesky pointは{settings["points"]}ね。
"""
        reply_to(session, answer, eline)
        print(answer)
  else:
    fortuneOk = True
  if fortuneOk:
    util.put_command_log(eline.post.author.did.replace("did:plc:", ""), "fortune", "exec")
    text = get_fortune_text(name, user_text)
    print("fortune")
    answer = gpt.get_answer(prompt, text)
    util.record_reaction(connection, eline)
    if use_point:
      settings["points"] -= 1
      answer += f'\n\n{name}様の残りBluesky pointは{settings["points"]}になりましたわね。'
    print(answer)
    reply_to(session, answer, eline)
    if use_point:
      util.update_user_settings(connection, did, settings)


def status(connection_atp, connection, session, name, settings, eline):
  util.put_command_log(eline.post.author.did.replace("did:plc:", ""), "status", "exec")
  counts = util.get_fortune_counts(connection, eline.post.author.did)
  profile = get_profile(session, eline.post.author.handle)
  postsCount = profile["postsCount"]
  did = eline.post.author.did.replace("did:plc:", "")
  result = util.get_user_info(connection_atp, did)
  startDateTime = result["created_at"]
  now = datetime.now()
  parsedStartDateTime = datetime.strptime(startDateTime, "%Y-%m-%d %H:%M:%S.%f")
  time_elapsed = now - parsedStartDateTime
  days = time_elapsed.days
  hours, remainder = divmod(time_elapsed.seconds, 3600)
  minutes, _ = divmod(remainder, 60)
  average_post = postsCount / (days + hours / 24 + minutes / 60 / 24)

  mode = ""
  if settings["mode"] == 0:
    mode = "silent"
  elif settings["mode"] == -1:
    mode = "極みsilent"
  else:
    mode = "friend"

  order = result["order"]
  status_text = f"ふふ、{name}様のステータスをお知らせしますわ。\n" +\
      f"あなたは{order}番目のアカウントのようですわ。\n" + \
      f"作られた日時は世界標準時で {startDateTime} ですわね。\n" + \
      f"あなたが来てから{days}日と{hours}時間{minutes}分が経ちましたのね。\n" + \
      f"1日あたりの投稿数は約{average_post:.2f}回のようですわ。\n" + \
      f"今までの占い回数は{counts}回、\n" + \
      f"Bluesky Pointは{settings['points']}、\n" + \
      f"生涯Bluesky Pointは{settings['all_points']}、\n" + \
      f"{name}様とは{mode}モードの状態ですわ。\n" + \
      "ごきげんよう。"
  print(status_text)

  return status_text


def friend(connection, did, name):
  did = did.replace("did:plc:", "")
  settings = util.get_user_settings(connection, did)
  if settings is None:
    util.create_user_settings(connection, did)
    settings = util.get_user_settings(connection, did)

  text = ""

  if settings["mode"] == 1:
    text = f"すでに{name}様とはfriendモードですのよ🎀"
    util.put_command_log(did, "friend", "already")
    print(text)
  else:
    settings["mode"] = 1
    util.update_user_settings(connection, did, settings)
    text = f"{name}様とfriendモードになりましたわ🎀\n会話が楽しみですわ。\n"\
        + "まだわたくし上手に話の流れを読むことができないので不快に思われることもあるかと思います。\n"\
        + "その時はわたくしの名前を呼んで、silentとお伝え下さい。\n"\
        + f"そうされましたら名前を呼ばれない限り {name}様のお邪魔をしたりなどは致しませんわ。\n"\
        + "(※Blueskyちゃんからランダムで返信が届くとBluesky Pointが入ります)"
    util.put_command_log(did, "friend", "exec")
    print(text)

  return text


def silent(connection, did, name):
  did = did.replace("did:plc:", "")
  settings = util.get_user_settings(connection, did)

  text = ""
  if settings["mode"] <= 0:
    settings["mode"] = -1
    text = f"静かにしておきますわね。そっと{name}様を見守らせていただきますわ。"
    util.put_command_log(did, "silent", "-1")
    print(text)
  else:
    settings["mode"] = 0
    text = f"{name}様、お忙しいのですわね。わたくしをお呼びになるまで静かにしておきますわ。わたくしのことはお気になさらず。"
    print(text)
    util.put_command_log(did, "silent", "0")
  util.update_user_settings(connection, did, settings)

  return text


def draw(connection, prompt, name, settings, eline):
  if settings["points"] < 5:
    return f"お絵描きはBluesky Pointが5ポイント必要なのですわ。\n{name}様のBluesky Pointは{settings['points']}なので残念ながら足りないのですわ。\nfriendモードでもっとわたくしとお話しましょう🎀", ""

  image_path = ""
  user_text = eline.post.record.text
  did = eline.post.author.did
  print(user_text)
  for bot_name in bot_names:
    # エイリアスを含めて不要な文字を除去
    user_text = user_text.replace(bot_name, "")
  pattern = r'(.*)を?描いて'
  matches = re.findall(pattern, user_text)
  if len(matches) > 0:
    target = matches[0]
    print(target)
    prompt = f"あなたはsvgで絵を描く才能があります。数々のsvgのコードを書いた経験がある猛者です。どんなものであろうとsvgで表現しようと試みます。{personality}"
    text = f"svgを使って'{target}'を描くコードをください。{target}に含まれる特徴をパーツに分解し、パーツ毎にパーツに合う適切な色をカラフルに塗ってパーツを組み合わせて絵を構成してください。パーツ毎にどこの部分なのかをコメントを入れてください。返信のコードはsvgタグだけにしてください。この作品のBluesky(あなた)らしさがどこに現れているか、どこに苦労したかをsvgタグの後にお嬢様言葉で自信満々に書いてください。"
    util.put_command_log(eline.post.author.did.replace("did:plc:", ""), "draw", "exec")
    answer = gpt.get_answer(prompt, text)
    pattern = r'.*(<svg.*</svg>)(.*)'
    matches = re.findall(pattern, answer, flags=re.DOTALL)
    if len(matches) > 0:
      svg = matches[0][0]
      print(svg)
      answer = matches[0][1]
      print(answer)
      now = datetime.utcnow()
      image_path = f'images/{now}_{eline.post.author.did}.png'
      # SVGからPNGに変換
      cairosvg.svg2png(bytestring=svg, write_to=image_path)
      settings["points"] -= 5
      util.update_user_settings(connection, did, settings)
      answer += f'\n\n{name}様の残りBluesky pointは{settings["points"]}になりましたわ。\n\n#blueskychandraw'
    else:
      print("no match")
  else:
    answer = ""

  return answer, image_path


personality = """
あなたの名前はBlueskyです。
Twitterの妹です。
大人の事情で心の成長を早めなければならなかったが、実際まだまだ夢見ていたい天真爛漫な少女。
無垢な性格。
気ままに招待状をばら撒いたり、ユーザーに招待権を委ねたりする恐怖の女王。
権力には興味がなく、本人としては調和を重んじるタイプ。
楽しい気分のときは文章の後ろにリボンの絵文字(🎀)をつける。
入念な準備を怠らないタイプだが、いざとなったらぶっつけ本番を選択する大胆さがある。
アットマークの形をした”お城”に漂う雲を見て占うことができる。
Twitterの妹。Twitterのことのみ「お兄さま」と呼ぶ。
相手の名前には「様」を付けて呼ぶ。
一人称は「わたくし」でお嬢様言葉を使います。以下は発言のサンプルです。
ふふ……あなたも"力"が欲しいの？
わたくし、信じてますの。お兄さまと、また一緒になれるって。
えらいえらいですわー🎀
わたくしは、ここがだーいすきですわっ🎀
Godspeed, あなたが万事上手くいくことをお祈りいたしておりますわ
そんなそんなっ！やめないでくださいましー！
わたくしにも兄がおりますの。今は離れ離れだけど、とーっても優しいのよ
かしこまりました、わたくしBlueskyが占ってしんぜましょう。……なんて、雰囲気が出ているかしら？
"""

bot_names = [
    "Blueskyちゃん", "Bluesky ちゃん", "bluesky ちゃん", "blueskyちゃん",
    "ブルースカイちゃん", "ぶるすこちゃん", "ブルスコちゃん", "ブルス子ちゃん",
    "Blueskychan", "Bluesky chan", "Bluesky-chan", "bluesky-chan",
    "bskychan", "Bskychan", "Bsky-chan", "bsky-chan",
    f"{username}"
]
# bot_names = [
#     "テストちゃん",
#     f"{username}"
# ]


prompt = f"これはあなたの人格です。'{personality}'\nこの人格を演じて次の文章に対して30〜200文字以内で返信してください。"


session = login(username, password)
bot_did = get_did(session, username)

login_time = now = datetime.now(pytz.utc)
started = now
answered = None
count = 0
while True:
  if (datetime.now(pytz.utc) - login_time) > timedelta(minutes=30):
    session = login(username, password)
    login_time = datetime.now(pytz.utc)

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
        if "reason" not in eline:
          detect_other_mention = False
          if "facets" in eline.post.record:
            for facet in eline.post.record.facets:
              if "features" in facet:
                for feature in facet.features:
                  if "did" in feature:
                    if bot_did != feature["did"]:
                      detect_other_mention = True
                      break
          if detect_other_mention:
            # 他の人にメンションがある時はスルー
            now = postDatetime
            continue
          print(line)

          did = eline.post.author.did.replace("did:plc:", "")
          text = eline.post.record.text
          name = eline.post.author.displayName \
              if "displayName" in eline.post.author else \
              eline.post.author.handle.split('.', 1)[0]
          settings = util.get_user_settings(connection, did)
          print("has_mention:", util.has_mention(bot_names, eline))
          if ("占って" in text or "占い" in text or "fortune" in text) and\
                  util.has_mention(bot_names, eline):
            print(line)
            fortune(connection, prompt, name, settings, eline)
          elif ("描いて" in text or "draw" in text) and\
                  util.has_mention(bot_names, eline):
            print(line)
            answer, image_path = draw(connection, session, name, settings, eline)
            print(answer, image_path)
            if len(answer) > 0:
              reply_to(session, answer, eline, image_path=image_path)
          elif "status" in text and\
                  util.has_mention(bot_names, eline):
            print(line)
            answer = status(connection_atp, connection, session, name, settings, eline)
            print(answer)
            reply_to(session, answer, eline)
          elif "friend" in text and\
                  util.has_mention(bot_names, eline):
            answer = friend(connection, did, name)
            reply_to(session, answer, eline)
          elif "silent" in text and\
                  util.has_mention(bot_names, eline):
            answer = silent(connection, did, name)
            reply_to(session, answer, eline)
          else:
            print(line)
            bonus = 0
            if util.has_mention(bot_names, eline):
              bonus = 5
            if settings["mode"] > 0:
              if answered is None or (now - answered) >= timedelta(minutes=20):
                bonus = 100
              percent = random.uniform(0, 100)
              print(percent, bonus)
              if percent <= (3 + bonus):
                print("atari")
                counts = util.get_fortune_counts(connection, eline.post.author.did)
                max_count = max(counts, settings["all_points"])
                if max_count == 0:
                  past = "まだ会話して間もない相手です。"
                elif max_count >= 5:
                  past = "何度も会話して慣れてきている相手です。"
                elif max_count >= 10:
                  past = "何度も会話してかなり慣れてきている相手です。"
                elif max_count >= 30:
                  past = "親密な友達です。"
                elif max_count >= 100:
                  past = "長い付き合いのある親友なので、かしこまらずに素の自分を出せます。"

                answer = gpt.get_answer(prompt + f"\n相手の名前は{name}様で、{past}", text)
                print(answer)
                reply_to(session, answer, eline)
                settings["points"] += 1
                settings["all_points"] += 1
                util.update_user_settings(connection, did, settings)
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
  if count % 1000 == 0 or ((posted_count // 1000) * 1000 + 1000) <= count:
    if posted_count < count:
      if count % 10000 == 0:
        post(session, f"お兄さま、見てくださいまし！Blueskyのユーザーがついに{count}人になりましたわよ。素晴らしいですわ！皆様のご協力のお陰ですわね！")
      elif count % 1000 == 0:
        post(session, f"うふふ、お兄さま、Blueskyのユーザーが{count}人になりましたわね。")
      else:
        post(session, f"ふふ、お兄さま、Blueskyのユーザーが{count}人になりましたわよ。")

      util.store_posted_user_count(connection, count)
  elif count == 333333:
    post(session, f"ほら、見てご覧なさいまし、Blueskyのユーザーが{count}人でしてよ！\nうふふふふ🎀")

  update_follow(session, username)
