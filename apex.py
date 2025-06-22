import time
import threading
import requests
import os
import re
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

API_KEY = "AIzaSyCnrIVkU4DjK_8IipJ9AC8ABC_70p5Zoo0"

# グローバル変数
LIVE_CHAT_ID = None
participants = []
processed_msg_ids = set()
live_chat_id_lock = threading.Lock()

# 参加・辞退キーワード
join_keywords = ["参加", "さんか", "出たい", "出ます", "入りたい", "行きたい", "希望"]
cancel_keywords = ["やめ", "辞退", "抜け", "キャンセル", "やらない", "やめとく", "離脱"]

# ======= 管理者ページ =======
@app.route("/admin", methods=["GET", "POST"])
def admin():
    global LIVE_CHAT_ID, participants, processed_msg_ids

    message = ""
    current_url = ""
    if request.method == "POST":
        url = request.form.get("live_url", "").strip()
        current_url = url

        # URLからVideo ID抽出
        video_id = extract_video_id(url)
        if not video_id:
            message = "❌ URLが不正かVideoIDが取得できませんでした。"
        else:
            # Video IDからLIVE_CHAT_ID取得
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
    </body>
    </html>
    """
    return render_template_string(html)

# ======= 参加者リストページ =======
@app.route("/viewer")
def viewer():
    list_html = "<br>".join(f"{i+1}. {name}" for i, name in enumerate(participants))
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>参加者リスト</title></head>
    <body style="font-family:sans-serif; padding:2em; background:#f0f8ff;">
        <h1>📋 参加者リスト</h1>
        {list_html or "（まだ誰もいません）"}
        <hr>
        <p><a href="/admin">管理者ページへ戻る</a></p>
        <script>
            async function loadList() {{
                const res = await fetch("/api/participants");
                const data = await res.json();
                const ul = document.getElementById("list");
                if(!ul) return;
                ul.innerHTML = "";
                if(data.participants.length === 0) {{
                    ul.innerHTML = "<li>まだ誰もいません</li>";
                }} else {{
                    data.participants.forEach((name, i) => {{
                        const li = document.createElement("li");
                        li.textContent = `${{i + 1}}. ${{name}}`;
                        ul.appendChild(li);
                    }});
                }}
            }}
            setInterval(loadList, 3000);
            window.onload = loadList;
        </script>
        <ul id="list"><li>読み込み中...</li></ul>
    </body>
    </html>
    """
    return render_template_string(html)

# ======= 参加者API =======
@app.route("/api/participants")
def api_participants():
    return jsonify({"participants": participants})

# ======= YouTube APIでライブチャットIDを取得 =======
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

# ======= URLからVideoIDを抽出 =======
def extract_video_id(url):
    # YouTube URLの代表的な形式に対応
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

# ======= チャット監視スレッド =======
def fetch_live_chat_messages():
    global participants, processed_msg_ids, LIVE_CHAT_ID

    while True:
        time.sleep(5)
        with live_chat_id_lock:
            live_chat_id = LIVE_CHAT_ID
        if not live_chat_id:
            continue  # 未設定なら何もしない

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

                # 参加・辞退判定
                if any(kw in msg_text for kw in join_keywords):
                    if author not in participants:
                        participants.append(author)
                        print(f"✅ 参加者追加: {author}")
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
