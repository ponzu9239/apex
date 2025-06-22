import time
import threading
import requests
from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
from functools import wraps

app = Flask(__name__)
app.secret_key = "好きなランダム文字列をここに入れてね"  # セッション用の秘密キー

# ↓↓ 必ず自分のAPIキーとLIVE_CHAT_IDに書き換えてください ↓↓
API_KEY = "YOUR_API_KEY"
LIVE_CHAT_ID = "YOUR_LIVE_CHAT_ID"

# 管理者ログイン用パスワード（好きなものに変えてOK）
ADMIN_PASSWORD = "your_password_here"

participants = []
processed_msg_ids = set()

# 参加希望キーワード（漢字＋ひらがな大量版）
join_keywords = [
    "参加", "参戦", "出場", "出場希望", "参加希望", "参加申込", "参加申請", "参加受付",
    "申し込み", "応募", "入隊", "加入", "加入希望", "入場", "出席", "出席希望", "入場希望",
    "出撃", "参入", "参画", "参加申請します", "参加表明", "参加決定", "参戦希望", "エントリー",
    "参加可能", "出場可能", "参戦可能", "参加中", "参加登録", "参加承認", "参加賛同", "加入申請",
    "申し込み済み", "参加登録済み", "出場登録", "参加申込済み",
    "さんか", "さんかします", "さんかしたい", "さんかする", "さんかおねがい", "はいりたい", "はいります",
    "はいる", "はいるよ", "はいってもいい", "はいるね", "いりたい", "いります", "いります！",
    "でたい", "でます", "でる", "でるよ", "でます！", "でたいです", "しゅつじょう", "しゅつじょうきぼう",
    "もうしこみ", "もうしこみします", "もうしこみました", "おうぼ", "おうぼします", "のりこみ",
    "のりこみます", "まざります", "まざる", "よろしく", "よろ", "よろしくおねがいします", "よろしくね",
    "よろしくです", "おねがいします", "よろです", "よろしくおねがいします！", "よろしくね！"
]

# 辞退・やめるキーワード（漢字＋ひらがな大量版）
cancel_keywords = [
    "辞退", "退出", "脱退", "離脱", "撤退", "放棄", "キャンセル", "辞退します", "退出します",
    "脱退します", "離脱します", "撤退します", "放棄します", "キャンセルします", "辞退した",
    "退出した", "脱退した", "離脱した", "撤退した", "放棄した", "キャンセルした", "やめる",
    "やめます", "辞めます", "やめたい", "辞めたい", "やらない", "やらなくなる", "辞めた", "辞退した",
    "キャンセル希望", "参加辞退", "参加キャンセル", "参加放棄", "参加撤回", "参加辞退します",
    "参加やめます", "参加やめたい", "参加しません", "参加停止", "参加断念", "もう出ません", "もうやりません",
    "降ります", "降参", "脱落", "放棄", "断念", "離脱申請", "離脱希望", "脱退申請", "退会", "退席",
    "脱会", "退場", "離席", "去ります", "退出申請", "退出希望",
    "やめ", "やめます", "やめたい", "やめとく", "やめときます", "やらない", "もうやらない", "きゃんせる",
    "きゃんせるします", "きゃんせるした", "じたい", "じたいします", "じたいした", "ぬけ", "ぬけます",
    "ぬけたい", "りだつ", "りだつします", "たいかい", "たいかいします", "きょひ", "きょひします",
    "もうでない", "もうでません", "もうさんかしない", "たいきょ", "たいきょします", "やめた", "辞めた",
    "ぬけた", "脱退", "離脱", "放棄", "断念"
]

# 参加者リスト表示用HTMLテンプレート
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
        setInterval(loadList, 2000);  // 2秒ごとに自動更新
        loadList();
    </script>
</body>
</html>
"""

# 管理者ログイン画面HTMLテンプレート
login_html = """
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
"""

# 管理者認証デコレータ
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def home():
    return "ホームページだよ！"

@app.route("/viewer")
def viewer():
    return render_template_string(viewer_html)

@app.route("/api/participants")
def api_participants():
    return jsonify({"participants": participants})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("admin"))
        else:
            return render_template_string(login_html, error="パスワードが違います")
    return render_template_string(login_html, error=None)

@app.route("/admin")
@login_required
def admin():
    # 管理者画面の内容は自由に拡張できます
    return """
    <h1>管理者画面</h1>
    <p>ここに参加者管理機能や設定画面を追加しましょう。</p>
    <p><a href="/logout">ログアウト</a></p>
    """

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

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

                # 参加希望判定（コメント中にキーワードが含まれていたらOK）
                if any(kw in msg_text for kw in join_keywords):
                    if author not in participants:
                        participants.append(author)
                        print(f"✅ 参加者追加: {author}")
                # 辞退判定
                elif any(kw in msg_text for kw in cancel_keywords):
                    if author in participants:
                        participants.remove(author)
                        print(f"❌ 参加者削除: {author}")

        except Exception as e:
            print("⚠️ エラー:", e)

        time.sleep(5)  # 5秒に1回チェック

if __name__ == "__main__":
    threading.Thread(target=fetch_live_chat_messages, daemon=True).start()
    print("🌐 参加者リスト → http://localhost:8000/viewer")
    print("🔐 管理者ログイン → http://localhost:8000/login")
    app.run(host="0.0.0.0", port=8000)
