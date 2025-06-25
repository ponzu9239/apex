import time
import threading
import requests
import os
import re
from flask import Flask, jsonify, render_template_string, request, session, redirect, url_for
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_here"

API_KEY = "AIzaSyCoPuKVZtMbk5vVlLv1z8JGPTBCmbRz164"
ADMIN_PASSWORD = "catkun1234"

LIVE_CHAT_ID = None
participants = []
candidates = {}
processed_msg_ids = set()
lock = threading.Lock()

join_keywords = ["参加", "さんか", "出たい", "出ます", "入りたい", "行きたい", "希望", "はいり", "入る", "エントリー"]
cancel_keywords = ["やめ", "辞退", "抜け", "キャンセル", "やらない", "やめとく", "離脱", "辞める", "抜ける"]

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapped

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect("/admin")
        return "パスワードが違います"
    return '''
    <form method="post">
        パスワード: <input type="password" name="password">
        <button type="submit">ログイン</button>
    </form>
    '''

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/login")

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    global LIVE_CHAT_ID, TWITCH_CHANNEL
    message = ""
    current_url = ""

    if request.method == "POST":
        mode = request.form.get("mode")
        current_url = request.form.get("live_url", "").strip()

        if mode == "youtube":
            video_id = extract_video_id(current_url)
            if video_id:
                chat_id = get_live_chat_id(video_id)
                if chat_id:
                    with lock:
                        LIVE_CHAT_ID = chat_id
                        TWITCH_CHANNEL = None
                        participants.clear()
                        candidates.clear()
                        processed_msg_ids.clear()
                    message = f"✅ YouTubeモード開始（Video ID: {video_id}）"
                else:
                    message = "❌ ライブチャットIDが取得できません。ライブ中ですか？"
            else:
                message = "❌ URLが無効です"

        elif mode == "twitch":
            channel = extract_twitch_channel(current_url)
            if channel:
                with lock:
                    TWITCH_CHANNEL = channel
                    LIVE_CHAT_ID = None
                    participants.clear()
                    candidates.clear()
                    processed_msg_ids.clear()
                message = f"✅ Twitchモード開始（チャンネル: {channel}）"
            else:
                message = "❌ TwitchのチャンネルURLが無効です"

    # 参加者と候補者をHTMLに変換
    part_list_html = ""
    for i, p in enumerate(participants):
        name = p["name"]
        part_list_html += f"""
            <li>{i+1}. {name}
                <form method='post' action='/remove' style='display:inline;'>
                    <input type='hidden' name='name' value="{name}">
                    <button style='margin-left:10px;'>削除</button>
                </form>
            </li>
        """

    cand_list_html = ""
    for name in candidates:
        if name not in [p["name"] for p in participants]:
            cand_list_html += f"""
                <li>{name}
                    <form method='post' action='/add' style='display:inline;'>
                        <input type='hidden' name='name' value="{name}">
                        <button style='margin-left:10px;'>追加</button>
                    </form>
                </li>
            """

    return render_template_string(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>管理者ページ</title>
        <style>
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: #f0f8ff;
                padding: 2em;
                color: #333;
            }}
            input[type=text] {{
                width: 400px;
                padding: 0.5em;
                margin-bottom: 1em;
            }}
            button {{
                padding: 0.4em 1em;
                border-radius: 6px;
            }}
            h2 {{
                margin-top: 2em;
            }}
            ul {{
                list-style: none;
                padding: 0;
            }}
            li {{
                margin-bottom: 0.6em;
            }}
        </style>
    </head>
    <body>
        <h1>🎮 管理者ページ</h1>
        <form method="post">
            <p>配信URL:</p>
            <input type="text" name="live_url" placeholder="https://..." value="{current_url}" required>
            <br>
            <button name="mode" value="youtube">🎥 YouTubeで開始</button>
            <button name="mode" value="twitch">🟣 Twitchで開始</button>
        </form>
        <p>{message}</p>

        <h2>📋 参加者リスト（{len(participants)}人）</h2>
        <ul>
            {part_list_html or "<li>現在参加者はいません</li>"}
        </ul>

        <h2>💬 コメント済み未参加ユーザー</h2>
        <ul>
            {cand_list_html or "<li>未参加者はいません</li>"}
        </ul>

        <p><a href="/viewer">▶ 一般画面へ</a> / <a href="/logout">🚪 ログアウト</a></p>
    </body>
    </html>
    """)
    
@app.route("/remove", methods=["POST"])
@login_required
def remove():
    name = request.form.get("name")
    global participants
    participants = [p for p in participants if p["name"] != name]
    return redirect("/admin")

@app.route("/add", methods=["POST"])
@login_required
def add():
    name = request.form.get("name")
    if name and name not in [p["name"] for p in participants]:
        participants.append({"name": name, "time": datetime.now().strftime("%H:%M:%S")})
    return redirect("/admin")

@app.route("/viewer")
def viewer():
    return '''
    <h1>参加者リスト</h1>
    <ul id="list">読み込み中...</ul>
    <script>
    async function load() {
        const res = await fetch("/api/participants");
        const data = await res.json();
        let html = "";
        data.participants.forEach((p, i) => {
            html += `<li>${i + 1}. ${p.name}</li>`;
        });
        document.getElementById("list").innerHTML = html;
    }
    setInterval(load, 3000);
    load();
    </script>
    '''

@app.route("/api/participants")
def api_participants():
    return jsonify({"participants": participants})

@app.route("/api/all_participants")
@login_required
def api_all():
    return jsonify({
        "participants": participants,
        "candidates": list(candidates.keys())
    })

def extract_video_id(url):
    patterns = [r"v=([^&]+)", r"youtu\.be/([^?&]+)", r"/live/([^?&]+)"]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def get_live_chat_id(video_id):
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "liveStreamingDetails",
            "id": video_id,
            "key": API_KEY
        }
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()
        return data["items"][0]["liveStreamingDetails"]["activeLiveChatId"]
    except Exception as e:
        print("💥 Chat ID取得エラー:", e)
        return None

def monitor_chat():
    while True:
        time.sleep(5)
        if not LIVE_CHAT_ID:
            continue
        try:
            url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
            res = requests.get(url, params={
                "liveChatId": LIVE_CHAT_ID,
                "part": "snippet,authorDetails",
                "key": API_KEY
            })
            res.raise_for_status()
            for item in res.json().get("items", []):
                msg_id = item["id"]
                if msg_id in processed_msg_ids:
                    continue
                processed_msg_ids.add(msg_id)

                msg = item["snippet"]["textMessageDetails"]["messageText"]
                author = item["authorDetails"]["displayName"]

                if any(k in msg for k in join_keywords):
                    if author not in [p["name"] for p in participants]:
                        participants.append({"name": author, "time": datetime.now().strftime("%H:%M:%S")})
                        print(f"✅ 追加: {author}")
                elif any(k in msg for k in cancel_keywords):
                    participants[:] = [p for p in participants if p["name"] != author]
                    print(f"❌ 削除: {author}")
                else:
                    if author not in candidates:
                        candidates[author] = True
        except Exception as e:
            print("❗監視エラー:", e)

if __name__ == "__main__":
    threading.Thread(target=monitor_chat, daemon=True).start()
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
