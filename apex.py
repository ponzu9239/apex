import time
import threading
import requests
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "ホームページだよ！"

@app.route("/viewer")
def viewer():
    return "参加者リストページだよ！"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

API_KEY = "AIzaSyCnrIVkU4DjK_8IipJ9AC8ABC_70p5Zoo0"
LIVE_CHAT_ID = "Cg0KC2lKNUhLQklLNlMwKicKGFVDYWx3NkF0YnV1NVNOS3dlUkpCMHVRZxILaUo1SEtCSUs2UzA"

participants = []
processed_msg_ids = set()

viewer_html = """
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
            data.participants.forEach((name, i) => {
                const li = document.createElement("li");
                li.textContent = `${i + 1}. ${name}`;
                ul.appendChild(li);
            });
        }
        setInterval(loadList, 2000);
        loadList();
    </script>
</body>
</html>
"""

@app.route("/viewer")
def viewer():
    return render_template_string(viewer_html)

@app.route("/api/participants")
def api_participants():
    return jsonify({"participants": participants})

def fetch_live_chat_messages():
    global participants, processed_msg_ids
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
            data = res.json()

            for item in data.get("items", []):
                msg_id = item["id"]
                if msg_id in processed_msg_ids:
                    continue
                processed_msg_ids.add(msg_id)

                msg_text = item["snippet"]["textMessageDetails"]["messageText"].strip().lower()
                author = item["authorDetails"]["displayName"]

                if msg_text == "参加希望":
                    if author not in participants:
                        participants.append(author)
                        print(f"✅ 参加者追加: {author}")
                elif msg_text == "やめます":
                    if author in participants:
                        participants.remove(author)
                        print(f"❌ 参加者削除: {author}")

        except Exception as e:
            print("⚠️ エラー:", e)

        time.sleep(5)  # 5秒ごとにチェック

if __name__ == "__main__":
    # 別スレッドでチャット監視開始
    threading.Thread(target=fetch_live_chat_messages, daemon=True).start()

    print("🌐 サンカリスト → http://localhost:8000/viewer")
    app.run(host="0.0.0.0", port=8000)
