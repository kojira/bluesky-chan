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
from pathlib import Path
import traceback

FORTUNE_CYCLE = 8

connection_atp = sqlite3.connect("atp.db")
cur = connection_atp.cursor()

cur.execute(
    """
CREATE TABLE IF NOT EXISTS users
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   did TEXT UNIQUE,
   handle TEXT,
   endpoint TEXT,
   created_at DATETIME
   )
"""
)
connection_atp.commit()

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

debug = os.getenv("DEBUG", False) == "true"

username = os.environ.get("BOT_HANDLE")
password = os.environ.get("BOT_PASSWORD")

connection = sqlite3.connect("bluesky_bot.db")
connection.row_factory = sqlite3.Row
cur = connection.cursor()

cur.execute(
    """
CREATE TABLE IF NOT EXISTS reactions
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   did TEXT,
   handle TEXT,
   displayName TEXT,
   created_at DATETIME
   )
"""
)

cur.execute(
    """
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
"""
)

cur.execute(
    """
CREATE TRIGGER IF NOT EXISTS update_users_timestamp
AFTER UPDATE ON users
FOR EACH ROW
BEGIN
  UPDATE users SET update_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
"""
)

cur.execute(
    """
CREATE TABLE IF NOT EXISTS count_post
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   count INTEGER,
   created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
   )
"""
)

cur.execute(
    """
CREATE TABLE IF NOT EXISTS dialogs
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   did TEXT,
   role TEXT,
   message TEXT,
   created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
   )
"""
)

cur.execute(
    """
CREATE TABLE IF NOT EXISTS notification_cursor
  (id INTEGER PRIMARY KEY AUTOINCREMENT,
   last_processed_at DATETIME NOT NULL,
   cursor TEXT,
   created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
   updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
   )
"""
)

cur.execute(
    """
CREATE TRIGGER IF NOT EXISTS update_notification_cursor_timestamp
AFTER UPDATE ON notification_cursor
FOR EACH ROW
BEGIN
  UPDATE notification_cursor SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
"""
)


def login(username, password):
    now = datetime.now(pytz.utc)
    if not debug:
        if os.path.exists("login.txt"):
            with open("login.txt", mode="r") as f:
                last_line = (f.readlines()[-1]).strip()
            dt = datetime.fromisoformat(last_line)
            delta = now - dt
            if delta < timedelta(minutes=5):
                wait_time = (timedelta(minutes=5) - delta).total_seconds()
                print(f"login wait:{wait_time}")
                time.sleep(wait_time)

    session = Session(username, password)
    with open("login.txt", mode="a") as f:
        f.write(f"{now}\n")
    print(f"login at:{now}", session)
    return session


def get_did(session, username):
    response = session.resolveHandle(username)
    return json.loads(response.text)["did"]


def get_last_processed_notification_time():
    """最後に処理したNotificationの時刻を取得"""
    try:
        cur = connection.cursor()
        cur.execute(
            "SELECT last_processed_at FROM notification_cursor ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            return parse(row["last_processed_at"])
        else:
            # 初回起動時：現在時刻をDBに記録して返す
            current_time = datetime.now(pytz.utc)
            cur.execute(
                "INSERT INTO notification_cursor (last_processed_at) VALUES (?)",
                (current_time.isoformat(),),
            )
            connection.commit()
            return current_time
    except Exception as e:
        print(f"Error getting last processed notification time: {e}")
        return datetime.now(pytz.utc)


def update_last_processed_notification_time(processed_at):
    """最後に処理したNotificationの時刻を更新"""
    try:
        cur = connection.cursor()
        # 既存レコードがあるかチェック
        cur.execute("SELECT id FROM notification_cursor ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()

        if row:
            # 更新
            cur.execute(
                "UPDATE notification_cursor SET last_processed_at = ? WHERE id = ?",
                (processed_at.isoformat(), row["id"]),
            )
        else:
            # 新規作成
            cur.execute(
                "INSERT INTO notification_cursor (last_processed_at) VALUES (?)",
                (processed_at.isoformat(),),
            )
        connection.commit()
    except Exception as e:
        print(f"Error updating last processed notification time: {e}")


def get_notifications(session, limit=50, cursor=None):
    """Bluesky Notificationを取得する"""
    try:
        headers = {"Authorization": "Bearer " + session.ATP_AUTH_TOKEN}

        url = (
            session.ATP_HOST
            + f"/xrpc/app.bsky.notification.listNotifications?limit={limit}"
        )
        if cursor:
            url += f"&cursor={cursor}"

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = json.loads(response.text)
            return data
        else:
            print(
                f"[ERROR] Failed to get notifications: {response.status_code}, "
                f"{response.text}"
            )
            return None
    except Exception as e:
        print(f"[ERROR] Exception in get_notifications: {e}")
        import traceback

        traceback.print_exc()
        return None


def post(session, text):
    print(text)
    session.postBloot(text)
    pass


def reply_to(session, text, eline, image_path=None):
    root_cid = None
    root_uri = None
    if "reply" in eline:
        root_cid = eline.reply.root.cid
        root_uri = eline.reply.root.uri

    if root_cid:
        root = {"cid": root_cid, "uri": root_uri}
    else:
        root = {"cid": eline.post.cid, "uri": eline.post.uri}

    reply = {"cid": eline.post.cid, "uri": eline.post.uri}
    reply_ref = {"root": root, "parent": reply}
    chunk_size = 280
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        if i == 0 and image_path:
            response = post_image(session, chunk, image_path, reply_to=reply_ref)
        else:
            print(chunk)
            response = session.postBloot(chunk, reply_to=reply_ref)
        reply = json.loads(response.text)
        reply_ref["parent"] = reply
    did = eline.post.author.did.replace("did:plc:", "")
    util.insert_user_dialog(connection, did, eline.post.record.text)
    bot_text = text if image_path is None else text + " (添付画像あり)"
    util.insert_bot_dialog(connection, did, bot_text)


def post_image(
    session, postcontent, image_path, reply_to=None, content_type="image/png"
):
    """Post a bloot."""
    timestamp = datetime.now(timezone.utc)
    print("timestamp:", timestamp.isoformat())
    timestamp = timestamp.isoformat().replace("+00:00", "Z")
    print("timestamp:", timestamp)

    headers = {"Authorization": "Bearer " + session.ATP_AUTH_TOKEN}

    data = {
        "collection": "app.bsky.feed.post",
        "$type": "app.bsky.feed.post",
        "repo": "{}".format(session.DID),
        "record": {
            "$type": "app.bsky.feed.post",
            "createdAt": timestamp,
            "text": postcontent,
        },
    }

    if image_path:
        data["record"]["embed"] = {}
        image_resp = session.uploadBlob(image_path, content_type)
        data["record"]["embed"]["$type"] = "app.bsky.embed.images"
        data["record"]["embed"]["images"] = [
            {"alt": "", "image": image_resp.json().get("blob")}
        ]
        print(image_resp.json())
    if reply_to:
        data["record"]["reply"] = reply_to
    resp = requests.post(
        session.ATP_HOST + "/xrpc/com.atproto.repo.createRecord",
        json=data,
        headers=headers,
    )
    print(resp, resp.json())
    return resp


def get_profile(session, handle):
    response = session.get_profile(handle)
    return json.loads(response.text)


def _get_follows(session, handle, limit=100, cursor=None):
    headers = {"Authorization": "Bearer " + session.ATP_AUTH_TOKEN}

    url = (
        session.ATP_HOST
        + f"/xrpc/app.bsky.graph.getFollows?actor={handle}&limit={limit}"
    )
    if cursor:
        url += f"&cursor={cursor}"

    response = requests.get(url, headers=headers)

    return json.loads(response.text)


def _get_followers(session, handle, limit=100, cursor=None):
    headers = {"Authorization": "Bearer " + session.ATP_AUTH_TOKEN}

    url = (
        session.ATP_HOST
        + f"/xrpc/app.bsky.graph.getFollowers?actor={handle}&limit={limit}"
    )
    if cursor:
        url += f"&cursor={cursor}"

    response = requests.get(url, headers=headers)

    return json.loads(response.text)


def get_follows(session, handle):
    cursor = None
    all_follow_list = []
    try:
        while True:
            response = _get_follows(session, handle, limit=100, cursor=cursor)
            follows = response["follows"]
            follow_list = [follow["did"] for follow in follows]
            all_follow_list.extend(follow_list)
            prev_cursor = cursor
            if "cursor" in response:
                cursor = response["cursor"]
            if cursor is None or prev_cursor == cursor:
                break
    except KeyError as e:
        print(response)
        print(e)
        all_follow_list = None

    return all_follow_list


def get_followers(session, handle):
    cursor = None
    all_follower_list = []
    try:
        while True:
            response = _get_followers(session, handle, limit=100, cursor=cursor)
            followers = response["followers"]
            follower_list = [
                (follower["handle"], follower["did"]) for follower in followers
            ]
            all_follower_list.extend(follower_list)
            prev_cursor = cursor
            if "cursor" in response:
                cursor = response["cursor"]
            if cursor is None or prev_cursor == cursor:
                break
    except KeyError as e:
        print(response)
        print(e)
        all_follower_list = None

    return all_follower_list


def is_follower(session, bot_handle, did, followers):
    folowed = False
    if did in followers:
        folowed = True
    return folowed


def update_follow(session, bot_handle):
    bot_follows = get_follows(session, bot_handle)
    bot_followers = get_followers(session, bot_handle)
    if bot_follows and bot_followers:
        # unfollows = [item for item in bot_follows if item not in bot_followers]
        followbacks = [item for item in bot_followers if item[1] not in bot_follows]
        print(f"bot_follows:{len(bot_follows)} bot_followers:{len(bot_followers)}")
        for handle in followbacks:
            print(f"follow back:{handle}")
            response = session.follow(
                username=None, did_of_person_you_wanna_follow=handle[1]
            )
            print(f"follow back:{handle}:{response}")
            time.sleep(0.05)


def get_fortune_text(name, user_text):
    percent = random.uniform(0, 100)
    if percent < 50:
        text = (
            f"私の名前は{name}です。今日のわたしの運勢を占って。結果はランダムで決めて、"
            + f"その結果に従って占いの内容を運の良さは★マークを５段階でラッキーアイテム、ラッキーカラーとかも教えて。{user_text}"
        )
    elif percent < 75:
        text = f"私の名前は{name}です。私の今日の運勢をトランプ占いしてください。\n{user_text}"
    elif percent < 90:
        text = f"私の名前は{name}です。私の今日の運勢をオラクルカードで占ってください。\n{user_text}"
    else:
        text = f"私の名前は{name}です。水晶球を持っている占い師になりきって、私の今日の運勢を水晶球占いしてください。\n{user_text}"

    if "fortune" in user_text:
        text += "英語で回答してください."

    return text


def fortune(connection, session, prompt, name, settings, eline):
    row = util.get_latest_record_by_did(connection, eline.post.author.did)
    did = eline.post.author.did.replace("did:plc:", "")
    fortuneOk = False
    use_point = False
    user_text = eline.post.record.text
    if row:
        now = datetime.now(pytz.utc)
        created_at = parse(row["created_at"])
        if (now - created_at) >= timedelta(hours=FORTUNE_CYCLE):
            fortuneOk = True
        else:
            if "ポイント消費" in user_text or "ポイントを消費" in user_text:
                if settings["points"] > 0:
                    fortuneOk = True
                    use_point = True
                else:
                    util.put_command_log(did, "fortune", "wait")
                    remaining_time = str(
                        timedelta(hours=FORTUNE_CYCLE) - (now - created_at)
                    )
                    answer = f"""{name}様、占いは{FORTUNE_CYCLE}時間に1回までですわ。
ふふ、そう逸らないことね。
あと約{remaining_time} ほどお待ち遊ばせ。
まだBluesky Pointがたまっていないようですわ。
"""
            else:
                util.put_command_log(did, "fortune", "wait")
                remaining_time = str(
                    timedelta(hours=FORTUNE_CYCLE) - (now - created_at)
                )
                answer = f"""{name}様、占いは{FORTUNE_CYCLE}時間に1回までですわ。
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
        util.put_command_log(
            eline.post.author.did.replace("did:plc:", ""), "fortune", "exec"
        )
        text = get_fortune_text(name, user_text)
        print("fortune")
        answer = gpt.get_answer(prompt, text)
        util.record_reaction(connection, eline)
        update_point = False
        if use_point:
            settings["points"] -= 1
            answer += f'\n\n{name}様の残りBluesky Pointは{settings["points"]}になりましたわね。'
            update_point = True
        else:
            # ランダムでBlueskuy Pointを付与
            percent = random.uniform(0, 100)
            if percent < 20:
                point = random.randint(1, 10)
                settings["points"] += point
                settings["all_points"] += point
                answer += (
                    f"\nあら素敵、Bluesky Pointが{point}ポイント降ってきましたわ🎀"
                )
                answer += f'\n{name}様の残りBluesky Pointは{settings["points"]}になりましたわ🎀'
                update_point = True

        print(answer)
        reply_to(session, answer, eline)
        if update_point:
            util.update_user_settings(connection, did, settings)


def status(connection_atp, connection, session, name, settings, eline):
    util.put_command_log(
        eline.post.author.did.replace("did:plc:", ""), "status", "exec"
    )
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
    status_text = (
        f"ふふ、{name}様のステータスをお知らせしますわ。\n"
        + f"あなたは{order}番目のアカウントのようですわ。\n"
        + f"作られた日時は世界標準時で {startDateTime} ですわね。\n"
        + f"あなたが来てから{days}日と{hours}時間{minutes}分が経ちましたのね。\n"
        + f"1日あたりの投稿数は約{average_post:.2f}回のようですわ。\n"
        + f"今までの占い回数は{counts}回、\n"
        + f"Bluesky Pointは{settings['points']}、\n"
        + f"生涯Bluesky Pointは{settings['all_points']}、\n"
        + f"{name}様とは{mode}モードの状態ですわ。\n"
        + "ごきげんよう。"
    )
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
        text = (
            f"{name}様とfriendモードになりましたわ🎀\n会話が楽しみですわ。\n"
            + "まだわたくし上手に話の流れを読むことができないので不快に思われることもあるかと思います。\n"
            + "その時はわたくしの名前を呼んで、silentとお伝え下さい。\n"
            + f"そうされましたら名前を呼ばれない限り {name}様のお邪魔をしたりなどは致しませんわ。\n"
            + "(※Blueskyちゃんからランダムで返信が届くとBluesky Pointが入ります)"
            + "(※Blueskyちゃんに返信するとBluesky Pointを1消費します)"
        )
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


def draw(connection, prompt, name, did, settings, eline):
    if settings["points"] < 5:
        return (
            f"お絵描きはBluesky Pointが5ポイント必要なのですわ。\n{name}様のBluesky Pointは{settings['points']}なので残念ながら足りないのですわ。\nfriendモードでもっとわたくしとお話しましょう🎀",
            "",
        )

    image_path = ""
    user_text = eline.post.record.text
    print(user_text)
    for bot_name in bot_names:
        # エイリアスを含めて不要な文字を除去
        user_text = user_text.replace(bot_name, "")
    pattern = r"(.*)を?描いて"
    matches = re.findall(pattern, user_text)
    if len(matches) > 0:
        target = matches[0]
        print(target)
        prompt = f"あなたはsvgで絵を描く才能があります。数々のsvgのコードを書いた経験がある猛者です。どんなものであろうとsvgで表現しようと試みます。{personality}"
        text = f"svgを使って'{target}'を描くコードをください。{target}に含まれる特徴をパーツに分解し、パーツ毎にパーツに合う適切な色をカラフルに塗ってパーツを組み合わせて絵を構成してください。パーツ毎にどこの部分なのかをコメントを入れてください。コメントはSVGの中に入れないでください。返信のコードはsvgタグだけにしてください。この作品のBluesky(あなた)らしさがどこに現れているか、どこに苦労したかをsvgタグの後にお嬢様言葉で自信満々に書いてください。コメントの長さは300文字以内に収まるようにしてください。textのfontはNoto Sans JPを使用してください。"
        util.put_command_log(
            eline.post.author.did.replace("did:plc:", ""), "draw", "exec"
        )
        answer = gpt.get_answer(prompt, text)
        pattern = r".*(<svg.*</svg>)(.*)"
        matches = re.findall(pattern, answer, flags=re.DOTALL)
        if len(matches) > 0:
            svg = matches[0][0]
            print(svg)
            answer = matches[0][1]
            answer = (
                answer.replace("```", "")
                .replace("</body>", "")
                .replace("</html>", "")
                .strip()
            )
            print(answer)
            now = datetime.utcnow()
            image_path = f"images/{now}_{eline.post.author.did}.png"
            # SVGからPNGに変換
            cairosvg.svg2png(bytestring=svg, write_to=image_path)
            settings["points"] -= 5
            util.update_user_settings(connection, did, settings)
            answer += f'\n\n{name}様の残りBluesky pointは{settings["points"]}になりましたわ。\n\n#blueskychandraw'
        else:
            answer = "残念ながら、うまく描けませんでしたわ。ポイントは消費していないのでご安心くださいまし。少し間を空けてからまたお声がけくださいまし。"
            image_path = None
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
    "Blueskyちゃん",
    "Bluesky ちゃん",
    "bluesky ちゃん",
    "blueskyちゃん",
    "ブルースカイちゃん",
    "ブルスカちゃん",
    "ぶるすこちゃん",
    "ブルスコちゃん",
    "ブルス子ちゃん",
    "Blueskychan",
    "Bluesky chan",
    "Bluesky-chan",
    "bluesky-chan",
    "bskychan",
    "Bskychan",
    "Bsky-chan",
    "bsky-chan",
    f"{username}",
]
if debug:
    bot_names = ["テストちゃん", f"{username}"]


prompt = f"これはあなたの人格です。'{personality}'\nこの人格を演じて次の文章に対して30〜200文字以内で返信してください。回答に過去の会話ログにある日時は含めないでください"


def is_self_mention_or_reply(notification, bot_did):
    """
    自分へのメンションまたはリプライかを判定する
    複数人を巻き込んだリプライの場合はFalseを返す
    """
    if not notification.get("record"):
        return False

    record = notification["record"]
    reason = notification.get("reason")

    # リプライの場合の判定
    if reason == "reply":
        # 複数人への言及がないかチェック
        if "facets" in record:
            mention_count = 0
            other_mentions = []
            for facet in record["facets"]:
                if "features" in facet:
                    for feature in facet["features"]:
                        if feature.get("$type") == "app.bsky.richtext.facet#mention":
                            mention_count += 1
                            mentioned_did = feature.get("did")
                            if mentioned_did != bot_did:
                                other_mentions.append(mentioned_did)

            # 複数人を巻き込んだリプライは除外
            if len(other_mentions) > 0:
                return False

        return True

    # メンションの場合の判定
    elif reason == "mention":
        # 複数人への言及がないかチェック
        if "facets" in record:
            mention_count = 0
            bot_mentioned = False
            other_mentions = []
            for facet in record["facets"]:
                if "features" in facet:
                    for feature in facet["features"]:
                        if feature.get("$type") == "app.bsky.richtext.facet#mention":
                            mention_count += 1
                            mentioned_did = feature.get("did")
                            if mentioned_did == bot_did:
                                bot_mentioned = True
                            else:
                                other_mentions.append(mentioned_did)

            # 自分がメンションされており、他の人への言及がない場合のみTrue
            return bot_mentioned and len(other_mentions) == 0

    return False


def process_notifications(session, bot_did, now, answered, previous_reply_did):
    """Notificationを処理して反応する"""
    # DBから最後に処理した時刻を取得
    last_processed_at = get_last_processed_notification_time()

    notifications_data = get_notifications(session, limit=50)

    if not notifications_data:
        print("[ERROR] notifications_data is None or empty")
        return now, answered, previous_reply_did

    if "notifications" not in notifications_data:
        print(
            f"[ERROR] 'notifications' key not found in data. Keys: {list(notifications_data.keys())}"
        )
        return now, answered, previous_reply_did

    notifications = notifications_data["notifications"]
    processed_count = 0
    latest_processed_time = last_processed_at

    for notification in notifications:
        try:
            author = notification.get("author", {})
            notif_datetime = parse(notification.get("indexedAt"))

            # 既読のNotificationはスキップ
            if notification.get("isRead", False):
                continue

            # 最後に処理した時刻より新しいNotificationのみ処理
            if last_processed_at >= notif_datetime:
                continue

            # 自分自身の投稿には反応しない
            if author.get("handle") == username:
                continue

            # 自分へのメンションまたはリプライかチェック
            if not is_self_mention_or_reply(notification, bot_did):
                continue

            # フォロワーでない場合はスキップ
            author_viewer = notification.get("author", {}).get("viewer", {})

            if author_viewer.get("muted"):
                continue
            if author_viewer.get("blockedBy"):
                continue
            if "followedBy" not in author_viewer:
                continue

            author_did = notification.get("author", {}).get("did")
            followed_by = author_viewer.get("followedBy", [])

            if author_did not in followed_by:
                continue

            print(
                f"Processing notification: {notification.get('reason')} from {author.get('handle')}"
            )

            # EasyDictでラップして既存の処理関数を再利用
            # 既存のprocess_timeline関数の処理と同様の形式に変換
            fake_line = {
                "post": {
                    "author": notification["author"],
                    "record": notification["record"],
                    "cid": notification.get("cid"),
                    "uri": notification.get("uri"),
                    "indexedAt": notification.get("indexedAt"),
                }
            }

            # リプライの場合はreply情報を追加
            if "reply" in notification.get("record", {}):
                fake_line["reply"] = notification["record"]["reply"]

            eline = EasyDict(fake_line)

            # 既存の処理ロジックを使用
            did = eline.post.author.did.replace("did:plc:", "")
            text = eline.post.record.text
            name = (
                eline.post.author.displayName
                if "displayName" in eline.post.author
                else eline.post.author.handle.split(".", 1)[0]
            )
            settings = util.get_user_settings(connection, did)

            # Notificationでは既に自分への言及確認済みなので、util.has_mentionは不要
            if "占って" in text or "占い" in text or "fortune" in text:
                fortune(connection, session, prompt, name, settings, eline)
            elif "描いて" in text or "draw" in text:
                answer, image_path = draw(
                    connection, prompt, name, did, settings, eline
                )
                if len(answer) > 0:
                    reply_to(session, answer, eline, image_path=image_path)
            elif "status" in text:
                print(fake_line)
                answer = status(
                    connection_atp, connection, session, name, settings, eline
                )
                print(answer)
                reply_to(session, answer, eline)
            elif "friend" in text:
                answer = friend(connection, did, name)
                reply_to(session, answer, eline)
            elif "silent" in text:
                answer = silent(connection, did, name)
                reply_to(session, answer, eline)
            else:
                print(fake_line)
                bonus = 0
                friend_talk = False
                # Notificationでは既に自分への言及確認済み
                if settings["mode"] > 0:
                    if settings["points"] > 0:
                        bonus = 100
                        friend_talk = True
                else:
                    bonus = 5
                if settings["mode"] > 0:
                    if answered is None or (notif_datetime - answered) >= timedelta(
                        minutes=60
                    ):
                        bonus = 100
                    percent = random.uniform(0, 100)
                    print(percent, bonus)
                    if percent <= (1 + bonus):
                        print("atari")
                        counts = util.get_fortune_counts(
                            connection, eline.post.author.did
                        )
                        max_count = max(counts, settings["all_points"])
                        past = "初めての会話相手です。"
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

                        messages = util.get_recent_dialogs(connection, did)
                        print(f"messages:{messages}")
                        answer = gpt.get_answer(
                            prompt + f"\n相手の名前は{name}様で、{past}",
                            text,
                            messages,
                        )
                        print(answer)
                        if friend_talk:
                            pass
                        else:
                            settings["points"] += 1
                            settings["all_points"] += 1
                            answer = f"{answer}\n\nBP:{settings['points']}(+1)"
                        reply_to(session, answer, eline)
                        util.update_user_settings(connection, did, settings)
                        answered = notif_datetime
                        previous_reply_did = eline.post.author.did
                    else:
                        print("hazure")

            now = notif_datetime
            processed_count += 1

            # 処理した最新の時刻を記録
            if notif_datetime > latest_processed_time:
                latest_processed_time = notif_datetime

            # 一度に処理しすぎないよう制限
            if processed_count >= 5:
                break

        except Exception as e:
            print(f"Error processing notification: {e}")
            traceback.print_exc()

    # 処理完了後、最新の処理時刻をDBに保存
    if latest_processed_time > last_processed_at:
        update_last_processed_notification_time(latest_processed_time)

    return now, answered, previous_reply_did


def process_timeline(session, bot_did, now, answered, sorted_feed, previous_reply_did):
    feed_len = len(sorted_feed)
    for i in range(feed_len):
        line = sorted_feed[i]
        eline = EasyDict(line)
        if eline.post.author.handle == username:
            # 自分自身には反応しない
            continue
        # print(eline.post.indexedAt)
        try:
            postDatetime = parse(eline.post.indexedAt)
            if now < postDatetime:
                # print(eline)
                can_reply = False
                if (
                    not eline.post.author.viewer.muted
                    and not eline.post.author.viewer.blockedBy
                    and "followedBy" in eline.post.author.viewer
                    and eline.post.author.did in eline.post.author.viewer.followedBy
                ):
                    can_reply = True
                if can_reply:
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
                        elif "reply" in eline:
                            if eline.reply.parent.author.handle != username:
                                detect_other_mention = True
                        if detect_other_mention:
                            # 他の人にメンション、リプライの場合はスルー
                            now = postDatetime
                            continue
                        print(line)

                        did = eline.post.author.did.replace("did:plc:", "")
                        text = eline.post.record.text
                        name = (
                            eline.post.author.displayName
                            if "displayName" in eline.post.author
                            else eline.post.author.handle.split(".", 1)[0]
                        )
                        settings = util.get_user_settings(connection, did)
                        # タイムライン処理では名前を呼ばれても反応しない
                        # （Notification処理で対応するため）

                        # コマンドが含まれている場合はスキップ（二重返信防止）
                        if util.has_mention(bot_names, eline):
                            if any(
                                cmd in text
                                for cmd in [
                                    "占って",
                                    "占い",
                                    "fortune",
                                    "描いて",
                                    "draw",
                                    "status",
                                    "friend",
                                    "silent",
                                ]
                            ):
                                print(
                                    f"→ SKIPPED: Command detected in timeline, will be handled by notification processing"
                                )
                                now = postDatetime
                                continue

                        # ランダム反応のみ実行（friendモードのユーザーに対して）
                        if settings["mode"] > 0:
                            if answered is None or (now - answered) >= timedelta(
                                minutes=60
                            ):
                                bonus = 100
                            else:
                                bonus = 0
                            percent = random.uniform(0, 100)
                            print(percent, bonus)
                            if percent <= (1 + bonus):
                                print("atari - random timeline reaction")
                                counts = util.get_fortune_counts(
                                    connection, eline.post.author.did
                                )
                                max_count = max(counts, settings["all_points"])
                                past = "初めての会話相手です。"
                                if max_count == 0:
                                    past = "まだ会話して間もない相手です。"
                                elif max_count >= 5:
                                    past = "何度も会話して慣れてきている相手です。"
                                elif max_count >= 10:
                                    past = (
                                        "何度も会話してかなり慣れてきている相手です。"
                                    )
                                elif max_count >= 30:
                                    past = "親密な友達です。"
                                elif max_count >= 100:
                                    past = "長い付き合いのある親友なので、かしこまらずに素の自分を出せます。"

                                messages = util.get_recent_dialogs(connection, did)
                                print(f"messages:{messages}")
                                answer = gpt.get_answer(
                                    prompt + f"\n相手の名前は{name}様で、{past}",
                                    text,
                                    messages,
                                )
                                print(answer)
                                settings["points"] += 1
                                settings["all_points"] += 1
                                answer = f"{answer}\n\nBP:{settings['points']}(+1)"
                                reply_to(session, answer, eline)
                                util.update_user_settings(connection, did, settings)
                                answered = datetime.now(pytz.utc)
                                previous_reply_did = eline.post.author.did
                            else:
                                print("hazure")
                now = postDatetime
        except Exception as e:
            print(eline)
            traceback.print_exc()
            print(repr(e))
            print(str(e))

    return now, answered, previous_reply_did


import threading


def aggregate_and_count(session):
    if not hasattr(aggregate_and_count, "prev_count"):
        aggregate_and_count.prev_count = 0
    # スレッド内で新たにDBコネクションを作成
    local_connection_atp = sqlite3.connect("atp.db")
    local_connection_atp.row_factory = sqlite3.Row
    # bluesky_bot.dbとは別にcount_post専用DBを用意
    local_count_post_connection = sqlite3.connect("count_post.db")
    local_count_post_connection.row_factory = sqlite3.Row

    # サブスレッド開始時にcount_postテーブルがなければ作成
    cur_count_post = local_count_post_connection.cursor()
    cur_count_post.execute(
        """
    CREATE TABLE IF NOT EXISTS count_post
      (id INTEGER PRIMARY KEY AUTOINCREMENT,
       count INTEGER,
       created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
       )
    """
    )
    local_count_post_connection.commit()

    try:
        while True:
            try:
                Path("./alive").touch()
                util.aggregate_users(local_connection_atp)
                posted_count = util.get_posted_user_count(local_count_post_connection)
                stats = util.get_stats()
                jaz_count = stats["total_users"]
                if aggregate_and_count.prev_count != jaz_count:
                    print("user count:", jaz_count)
                base_low = (jaz_count // 1000000) * 1000000
                base_high = (jaz_count // 10000000 + 1) * 10000000
                if base_low < jaz_count < base_high:
                    if (
                        jaz_count % 100000 == 0
                        or ((posted_count // 100000) * 100000 + 100000) <= jaz_count
                    ):
                        prompt = f"これはあなたの人格です。'{personality}'\nこの人格を演じて次の文章に対して80文字以内で返信してください。"
                        text = f"ユーザー数が{base_high}人になるまで100000人ずつカウントアップしています。SNSのBlueskyのユーザーが{jaz_count}人になり{base_high}人にもう少しであることをBlueskyのユーザーに向けて伝える投稿をしてください。人数は正確に書いてください。"
                        answer = gpt.get_answer5(prompt, text)
                        post(session, answer)
                        util.store_posted_user_count(
                            local_count_post_connection, jaz_count
                        )
                elif jaz_count >= base_high:
                    prompt = f"これはあなたの人格です。'{personality}'\nこの人格を演じて次の文章に対して80文字以内で返信してください。"
                    text = f"SNSのBlueskyのユーザーが{jaz_count}人になりました。大変な偉業です。Blueskyの開発チームの人達とBlueskyのユーザーに向けて感謝の言葉を伝える投稿をしてください。"
                    answer = gpt.get_answer5(prompt, text)
                    post(session, answer)
                    util.store_posted_user_count(local_count_post_connection, jaz_count)
                elif (
                    jaz_count % 50000 == 0
                    or ((posted_count // 50000) * 50000 + 50000) <= jaz_count
                ):
                    if posted_count < jaz_count:
                        if jaz_count >= 100000 == 0:
                            post(
                                session,
                                f"お兄さま、見てくださいまし！！Blueskyのユーザーがついに{jaz_count}人になりましたわよ。感無量ですわ🎀",
                            )
                        elif jaz_count % 100000 == 0:
                            post(
                                session,
                                f"お兄さま、見てくださいまし！Blueskyのユーザーがついに{jaz_count}人になりましたわよ。素晴らしいですわ！皆様のご協力のお陰ですわね！",
                            )
                    elif jaz_count % 50000 == 0:
                        post(
                            session,
                            f"うふふ、お兄さま、Blueskyのユーザーが{jaz_count}人になりましたわね。",
                        )
                    else:
                        post(
                            session,
                            f"ふふ、お兄さま、Blueskyのユーザーが{jaz_count}人になりましたわよ。",
                        )

                    util.store_posted_user_count(local_count_post_connection, jaz_count)

                aggregate_and_count.prev_count = jaz_count
                time.sleep(60)

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.HTTPError,
            ) as e:
                print(f"Network error in aggregate_and_count: {e}")
                print("Retrying in 60 seconds...")
                time.sleep(60)
                continue

            except Exception as e:
                print(f"Error in aggregate_and_count loop: {e}")
                traceback.print_exc()
                print("Retrying in 60 seconds...")
                time.sleep(60)
                continue
    except Exception as e:
        traceback.print_exc()
        print(repr(e))
        print(str(e))

    finally:
        local_connection_atp.close()
        local_count_post_connection.close()


def main():
    session = login(username, password)
    bot_did = get_did(session, username)

    login_time = now = datetime.now(pytz.utc)
    answered = None
    previous_reply_did = None

    # 集計スレッドを常駐で起動
    aggregate_thread = threading.Thread(
        target=aggregate_and_count, args=(session,), daemon=True
    )
    aggregate_thread.start()

    retry_count = 0
    max_retries = 5
    base_delay = 5

    while True:
        try:
            if (datetime.now(pytz.utc) - login_time) > timedelta(minutes=60):
                session = login(username, password)
                login_time = datetime.now(pytz.utc)

            # Notificationを優先的に処理
            now, answered, previous_reply_did = process_notifications(
                session, bot_did, now, answered, previous_reply_did
            )

            # 既存のタイムライン処理も継続（フォロワー以外のフォード投稿なども含む）
            skyline = session.getSkyline(50)
            feed = skyline.json().get("feed")
            if feed is None:
                print("Warning: feed is None, skipping this iteration")
                time.sleep(3)
                continue
            sorted_feed = sorted(feed, key=lambda x: parse(x["post"]["indexedAt"]))
            now, answered, previous_reply_did = process_timeline(
                session, bot_did, now, answered, sorted_feed, previous_reply_did
            )

            # 成功した場合はリトライカウントをリセット
            retry_count = 0

            # 1回の実行後に3秒スリープ
            time.sleep(3)

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.HTTPError,
        ) as e:
            retry_count += 1
            if retry_count > max_retries:
                print(
                    f"Max retries ({max_retries}) exceeded. Resetting retry count and continuing..."
                )
                retry_count = 0
                delay = base_delay * 6  # より長い待機時間
            else:
                # 指数バックオフ: 5, 10, 20, 40, 80秒
                delay = base_delay * (2 ** (retry_count - 1))

            print(f"Network error occurred (attempt {retry_count}): {e}")
            print(f"Retrying in {delay} seconds...")
            time.sleep(delay)
            continue

        except Exception as e:
            print(f"Unexpected error occurred: {e}")
            print("Retrying in 5 seconds...")
            time.sleep(5)
            continue


if __name__ == "__main__":
    main()
