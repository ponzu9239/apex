import time
import threading
import requests
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

API_KEY = "あなたのYouTube APIキー"
LIVE_CHAT_ID = "取得したライブチャットID"
participants = []
processed_msg_ids = set()

# --- 認証関連 ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == "adminpass":
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
    return redirect("/")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

# --- 管理者画面 ---
@app.route("/admin", methods=["GET"])
@login_required
def admin():
    html = "<h1>管理者ページ</h1><ul>"
    for name in participants:
        html += f'''
        <li>{name}
            <form method="POST" action="/remove" style="display:inline;">
                <input type="hidden" name="name" value="{name}">
                <button type="submit">削除</button>
            </form>
        </li>'''
    html += "</ul><p><a href='/viewer'>▶ 一般画面へ</a></p><p><a href='/logout'>ログアウト</a></p>"
    return html

@app.route("/remove", methods=["POST"])
@login_required
def remove():
    name = request.form.get("name")
    if name in participants:
        participants.remove(name)
    return redirect("/admin")

# --- 一般画面（viewer） ---
@app.route("/viewer")
def viewer():
    return render_template_string("""
    <html>
    <head><title>参加者リスト</title></head>
    <body>
    <h1>📋 参加者リスト</h1>
    <ul id="list">読み込み中...</ul>
    <script>
    async function reload() {
        const res = await fetch("/api/participants");
        const data = await res.json();
        const ul = document.getElementById("list");
        ul.innerHTML = "";
        data.participants.forEach((name, i) => {
            const li = document.createElement("li");
            li.textContent = `${i + 1}. ${name}`;
            ul.appendChild(li);
        });
    }
    reload();
    setInterval(reload, 5000);
    </script>
    </body>
    </html>
    """)

@app.route("/api/participants")
def api():
    return jsonify({"participants": participants})

# --- チャット監視 ---
def fetch_messages():
    while True:
        try:
            url = "https://www.googleapis.com/youtube/v3/liveChat/messages"
            params = {
                "liveChatId": LIVE_CHAT_ID,
                "part": "snippet,authorDetails",
                "key": API_KEY
            }
            res = requests.get(url, params=params)
            res.raise_for_status()
            items = res.json().get("items", [])

            for item in items:
                msg_id = item["id"]
                if msg_id in processed_msg_ids:
                    continue
                processed_msg_ids.add(msg_id)

                text = item["snippet"]["textMessageDetails"]["messageText"].lower()
                author = item["authorDetails"]["displayName"]

                if any(kw in text for kw in ["参加", "入り", "いれ", "さんか"]):
                    if author not in participants:
                        participants.append(author)
                        print("✅ 追加:", author)
                elif any(kw in text for kw in ["やめ", "ぬけ", "キャンセル"]):
                    if author in participants:
                        participants.remove(author)
                        print("❌ 削除:", author)
        except Exception as e:
            print("⚠️ エラー:", e)

        time.sleep(5)

# --- 起動 ---
if __name__ == "__main__":
    threading.Thread(target=fetch_messages, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
