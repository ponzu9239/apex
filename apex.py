import time
import threading
import requests
import os
import re
from flask import Flask, jsonify, render_template_string, request, session, redirect, url_for
from functools import wraps

app = Flask(__name__)
app.secret_key = "好きなランダム文字列をここに入れてね"  # セッション用秘密鍵

API_KEY = "AIzaSyCnrIVkU4DjK_8IipJ9AC8ABC_70p5Zoo0"

# 管理者パスワード（適宜変更してください）
ADMIN_PASSWORD = "your_password_here"

# グローバル変数
LIVE_CHAT_ID = None
participants = []
processed_msg_ids = set()
live_chat_id_lock = threading.Lock()

# 緩い参加・辞退キーワード（部分一致OK）
join_keywords = ["参加", "さんか", "出たい", "出ます", "入りたい", "行きたい", "希望", "はいり", "入る", "エントリー", "エントリ"]
cancel_keywords = ["やめ", "辞退", "抜け", "キャンセル", "やらない", "やめとく", "離脱", "辞める", "抜ける"]

# ログイン必須デコレータ
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ログインページ
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin"))
        else:
            error = "パスワードが違います"
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>ログイン</title></head>
    <body style="font-family:sans-serif; padding:2em;">
    <h1>管理者ログイン</h1>
    <form method="post">
        <input type="password" name="password" placeholder="パスワード" required>
        <button type="submit">ログイン</button>
    </form>
    {% if error %}
    <p style="color:red;">{{ error }}</p>
    {% endif %}
    </body>
    </html>
    """, error=error)

# 管理者ページ（ライブURL設定フォーム）
@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    global LIVE_CHAT_ID, participants, processed_msg_ids

    message = ""
    current_url = ""
    if request.method == "POST":
        url = request.form.get("live_url", "").strip()
        current_url = url

        video_id = extract_video_id(url)
        if not video_id:
            message = "❌ URLが不正かVideoIDが取得できませんでした。"
        else:
            live_chat_id = get_live_chat_id(video_id)
            if not live_chat_id:
                message = "❌ ライブチャットIDが取得できません。ライブ配信中か確認してください。"
            else:
                with live_chat_id_lock:
                    LIVE_CHAT_ID = live_chat_id
                    participants.clear()
                    processed_msg_ids.clear()
                message = f"✅ ライブチャットIDを設定しました。現在監視中のVideo ID: {video_id}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>管理者ページ</title></head>
    <body style="font-family:sans-serif; padding:2em;">
        <h1>管理者ページ - ライブURL設定</h1>
        <form method="post">
            <input type="text" name="live_url" size="50" placeholder="ライブ配信のURLをここに貼る" value="{current_url}" required>
            <button type="submit">設定</button>
        </form>
        <p>{message}</p>
        <hr>
        <p>現在の監視中ライブチャットID:<br>{LIVE_CHAT_ID or '未設定'}</p>
        <p><a href="/viewer">参加者リストページへ</a></p>
        <p><a href="/logout">ログアウト</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

# ログアウト処理
@app.route("/logout")
@login_required
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

# 参加者リストページ（自動更新対応）
@app.route("/viewer")
def viewer():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>参加者リスト</title>
        <style>
            body { font-family: sans-serif; padding: 2em; background: #f0f8ff; }
            h1 { color: #333; }
            ul { font-size: 1.2em; }
        </style>
    </head>
    <body>
        <h1>📋 参加者リスト</h1>
        <ul id="list"><li>読み込み中...</li></ul>
        <script>
            async function loadList() {
                const res = await fetch("/api/participants");
                const data = await res.json();
                const ul = document.getElementById("list");
                ul.innerHTML = "";
                if (data.participants.length === 0) {
                    ul.innerHTML = "<li>まだ誰もいません</li>";
                } else {
                    data.participants.forEach((name, i) => {
                        const li = document.createElement("li");
                        li.textContent = `${i + 1}. ${name}`;
                        ul.appendChild(li);
                    });
                }
            }
            loadList();
            setInterval(loadList, 3000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

# 参加者API（JSON返し）
@app.route("/api/participants")
def api_participants():
    return jsonify({"participants": participants})

# YouTube APIでライブチャットIDを取得
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
        items = data.get("items", [])
        if not items:
            return None
        live_details = items[0].get("liveStreamingDetails", {})
        return live_details.get("activeLiveChatId")
    except Exception as e:
        print("Error getting live chat ID:", e)
        return None

# URLからVideoID抽出（正規表現で対応）
def extract_video_id(url):
    patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([^&]+)",
        r"(?:https?://)?youtu\.be/([^?&]+)",
        r"(?:https?://)?youtube\.com/live/([^?&]+)"
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

# チャット監視スレッド
def fetch_live_chat_messages():
    global participants, processed_msg_ids, LIVE_CHAT_ID

    while True:
        time.sleep(5)
        with live_chat_id_lock:
            live_chat_id = LIVE_CHAT_ID
        if not live_chat_id:
            continue

        try:
            url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
            params = {
                "liveChatId": live_chat_id,
                "part": "snippet,authorDetails",
                "key": API_KEY
            }
            res = requests.get(url, params=params)
            res.raise_for_status()
            data = res.json()

            for item in data.get("items", []):
                msg_id = item["id"]
                if msg_id in processed_msg_ids:
                    continue
                processed_msg_ids.add(msg_id)

                msg_text = item["snippet"]["textMessageDetails"]["messageText"].strip().lower()
                author = item["authorDetails"]["displayName"]

                # 緩い参加判定
                if any(kw in msg_text for kw in join_keywords):
                    if author not in participants:
                        participants.append(author)
                        print(f"✅ 参加者追加: {author}")

                # 緩い辞退判定
                elif any(kw in msg_text for kw in cancel_keywords):
                    if author in participants:
                        participants.remove(author)
                        print(f"❌ 参加者削除: {author}")

        except Exception as e:
            print("⚠️ エラー:", e)

if __name__ == "__main__":
    threading.Thread(target=fetch_live_chat_messages, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
