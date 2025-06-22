import time
import threading
import requests
import os
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# 🔑 環境変数またはハードコード（安全な場所で管理推奨）
API_KEY = "AIzaSyCnrIVkU4DjK_8IipJ9AC8ABC_70p5Zoo0"
LIVE_CHAT_ID = "Cg0KC2lKNUhLQklLNlMwKicKGFVDYWx3NkF0YnV1NVNOS3dlUkpCMHVRZxILaUo1SEtCSUs2UzA"

participants = []
processed_msg_ids = set()

# 🌐 ホーム（確認用）
@app.route("/")
def home():
    return "ホームページだよ！"

# 🌐 viewer画面にリストを表示
@app.route("/viewer")
def viewer():
    list_html = "<br>".join(f"{i+1}. {name}" for i, name in enumerate(participants))
    html = f"""
    <html>
    <head><title>参加者リスト</title></head>
    <body style="font-family:sans-serif; padding:2em; background:#f0f8ff;">
        <h1>📋 参加者リスト</h1>
        {list_html or "（まだ誰もいません）"}
    </body>
    </html>
    """
    return render_template_string(html)

# 🔁 APIで参加者リスト（使わないなら削除OK）
@app.route("/api/participants")
def api_participants():
    return jsonify({"participants": participants})

# 🎥 YouTubeライブチャットから定期取得
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

        time.sleep(5)  # 🔁 5秒ごとにチェック

# 🚀 起動（Renderでも動くようにPORT環境変数に対応）
if __name__ == "__main__":
    threading.Thread(target=fetch_live_chat_messages, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
