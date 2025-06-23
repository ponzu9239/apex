import time
import threading
import requests
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

API_KEY = "YOUR_YOUTUBE_API_KEY"
LIVE_CHAT_ID = ""
participants = []
candidates = {}
processed_msg_ids = set()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == "adminpass":
            session["logged_in"] = True
            return redirect("/admin")
        return "パスワードが違います"
    return '''<form method="post">
    パスワード: <input type="password" name="password">
    <button type="submit">ログイン</button></form>'''

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/")

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    global LIVE_CHAT_ID
    message = ""
    current_url = request.form.get("live_url") if request.method == "POST" else ""

    if request.method == "POST" and current_url:
        try:
            video_id = current_url.split("v=")[-1].split("&")[0].split("/")[-1]
            res = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
                "id": video_id,
                "part": "liveStreamingDetails",
                "key": API_KEY
            })
            res.raise_for_status()
            data = res.json()
            LIVE_CHAT_ID = data["items"][0]["liveStreamingDetails"]["activeLiveChatId"]
            message = f"✅ 設定完了: {LIVE_CHAT_ID}"
        except Exception as e:
            message = f"❌ エラー: {e}"

    participant_list_html = ''.join(f'<li><img src="{p["icon"]}" width="24"> {i+1}. {p["name"]} ({p["time"]}) <form method="post" action="/remove" style="display:inline;"><input type="hidden" name="name" value="{p["name"]}"><button type="submit">削除</button></form></li>' for i, p in enumerate(participants))

    candidate_list_html = ''.join(f'<li><img src="{icon}" width="24"> {name} <form method="post" action="/add_from_candidate" style="display:inline;"><input type="hidden" name="name" value="{name}"><button type="submit">参加に追加</button></form></li>' for name, icon in candidates.items() if name not in [p['name'] for p in participants])

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset='UTF-8'><title>管理者ページ</title></head>
    <body style='font-family:sans-serif; padding:2em;'>
        <h1>管理者ページ - ライブURL設定</h1>
        <form method='post'>
            <input type='text' name='live_url' size='50' placeholder='ライブ配信のURLをここに貼る' value='{current_url}' required>
            <button type='submit'>設定</button>
        </form>
        <p>{message}</p>
        <hr>
        <p>現在の監視中ライブチャットID:<br>{LIVE_CHAT_ID or '未設定'}</p>
        <hr>
        <h2>📋 現在の参加者リスト（{len(participants)}人）</h2>
        <ul>{participant_list_html}</ul>
        <hr>
        <h2>💬 コメントしたけど未参加の人たち</h2>
        <ul>{candidate_list_html or '<li>なし</li>'}</ul>
        <p><a href='/viewer'>▶ 参加者リストページへ</a></p>
        <p><a href='/logout'>🚪 ログアウト</a></p>
    </body>
    </html>
    """
    return html

@app.route("/remove", methods=["POST"])
@login_required
def remove_participant():
    name = request.form.get("name")
    global participants
    participants = [p for p in participants if p['name'] != name]
    return redirect(url_for("admin"))

@app.route("/add_from_candidate", methods=["POST"])
@login_required
def add_from_candidate():
    name = request.form.get("name")
    if name and name not in [p['name'] for p in participants]:
        participants.append({"name": name, "time": datetime.now().strftime("%H:%M:%S"), "icon": candidates.get(name, "")})
    return redirect(url_for("admin"))

@app.route("/")
def home():
    return redirect("/viewer")

@app.route("/viewer")
def viewer():
    viewer_html = """
    <!DOCTYPE html>
    <html>
    <head><meta charset='UTF-8'><title>参加者リスト</title>
    <style>body { font-family: sans-serif; padding: 2em; background: #f0f8ff; } h1 { color: #333; } ul { font-size: 1.2em; }</style>
    </head>
    <body>
        <h1>📋 参加者リスト</h1>
        <ul id='list'><li>読み込み中...</li></ul>
        <script>
            async function loadList() {
                const res = await fetch("/api/participants");
                const data = await res.json();
                const ul = document.getElementById("list");
                ul.innerHTML = "";
                data.participants.forEach((p, i) => {
                    const li = document.createElement("li");
                    li.innerHTML = `<img src="${p.icon}" width="24"> ${i + 1}. ${p.name} (${p.time})`;
                    ul.appendChild(li);
                });
            }
            setInterval(loadList, 2000);
            loadList();
        </script>
    </body>
    </html>
    """
    return render_template_string(viewer_html)

@app.route("/api/participants")
def api_participants():
    return jsonify({"participants": participants})

def fetch_live_chat_messages():
    global participants, processed_msg_ids, candidates
    while True:
        try:
            if not LIVE_CHAT_ID:
                time.sleep(5)
                continue
            url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
            params = {
                "liveChatId": LIVE_CHAT_ID,
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

                msg_text = item["snippet"].get("textMessageDetails", {}).get("messageText", "").lower()
                author = item["authorDetails"]["displayName"]
                icon_url = item["authorDetails"].get("profileImageUrl", "")
                candidates[author] = icon_url

                if any(kw in msg_text for kw in ["参加", "入り", "いれ", "さんか", "希望"]):
                    if author not in [p['name'] for p in participants]:
                        participants.append({"name": author, "time": datetime.now().strftime("%H:%M:%S"), "icon": icon_url})
                        print(f"✅ 参加者追加: {author}")
                elif any(kw in msg_text for kw in ["やめ", "ぬけ", "やめと", "キャンセル", "抜け"]):
                    participants = [p for p in participants if p['name'] != author]
                    print(f"❌ 参加者削除: {author}")
        except Exception as e:
            print("⚠️ エラー:", e)
        time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=fetch_live_chat_messages, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)