import os, json, logging, yaml
from datetime import datetime, timezone, timedelta
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 設定ファイル読み込み
CONFIG_PATH = "/content/drive/MyDrive/2025 AIエンジニアリング/開発/config.yaml"
with open(CONFIG_PATH, "r") as f:
    cfg = yaml.safe_load(f)

# Slack設定
SLACK_BOT_TOKEN = cfg["slack"]["bot_token"]
SLACK_APP_TOKEN = cfg["slack"]["app_token"]
MONITOR_CHANNELS = set(cfg.get("monitor_channels", []))
ADMIN_USERS = cfg.get("admin_users", [])

# Google Sheets設定
SPREADSHEET_ID = cfg["google_sheets"]["spreadsheet_id"]
SHEET_NAME = cfg["google_sheets"]["sheet_name"]
CREDENTIALS_PATH = cfg["google_sheets"]["credentials_path"]

# Slackアプリ初期化
app = App(token=SLACK_BOT_TOKEN)
auth = app.client.auth_test()
BOT_USER_ID = auth["user_id"]
BOT_ID = auth["bot_id"]
logger.info("Bot user_id=%s bot_id=%s", BOT_USER_ID, BOT_ID)

# Gemini AI設定
genai.configure(api_key=cfg["gemini"]["api_key"])
MODEL_ID = "models/gemini-1.5-pro-latest"
gemini_model = genai.GenerativeModel(MODEL_ID)



# JSON応答スキーマ
SCHEMA = {
    "type": "object",
    "properties": {"violation": {"type": "boolean"}},
    "required": ["violation"],
}

GEN_CFG = GenerationConfig(
    temperature=0.0,
    max_output_tokens=16,
    response_mime_type="application/json",
    response_schema=SCHEMA,
)

# Google Sheets API初期化
def init_sheets_service():
    """Google Sheets APIサービスを初期化"""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            CREDENTIALS_PATH,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=credentials)
        logger.info("Google Sheets API初期化成功")
        return service
    except Exception as e:
        logger.error("Google Sheets API初期化失敗: %s", e)
        return None

sheets_service = init_sheets_service()

def get_user_info(client, user_id):
    """ユーザーIDから表示名を取得"""
    try:
        response = client.users_info(user=user_id)
        if response["ok"]:
            user = response["user"]
            # 表示名 > 実名 > ユーザー名の優先順位で取得
            return user.get("profile", {}).get("display_name") or \
                   user.get("profile", {}).get("real_name") or \
                   user.get("name", user_id)
    except Exception as e:
        logger.error("ユーザー情報取得失敗 (%s): %s", user_id, e)
    return user_id  # 取得失敗時はユーザーIDを返す

def log_to_spreadsheet(client, user_id, bot_id_in_event, message_text):
    """違反内容をスプレッドシートに記録"""
    if not sheets_service:
        logger.error("Google Sheets APIが初期化されていません")
        return
    
    try:
        # 日本時間（JST）で現在時刻を取得
        jst = timezone(timedelta(hours=9))
        timestamp = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S")
        
        # アカウント名を取得
        if user_id:
            account_name = get_user_info(client, user_id)
        else:
            account_name = f"Bot ({bot_id_in_event})"
        
        # スプレッドシートに書き込むデータ
        values = [[timestamp, account_name, message_text]]
        
        # シートに追記
        body = {'values': values}
        result = sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:C",  # A列:日時、B列:アカウント名、C列:発言内容
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        logger.info("スプレッドシートに記録: %s行追加", result.get('updates', {}).get('updatedRows', 0))
        
    except HttpError as e:
        logger.error("スプレッドシート書き込みエラー: %s", e)
    except Exception as e:
        logger.error("予期しないエラー: %s", e)

def analyze_text(text: str) -> bool:
    """テキストがガイドライン違反かどうかを分析"""
    prompt = (
        "あなたはモデレーション AI です。次の Slack メッセージが "
        "暴言・差別・脅迫・ハラスメントなどガイドラインに違反する場合は "
        "{\"violation\": true}、違反しない場合は false だけを返してください。\n"
        f"メッセージ: {json.dumps(text, ensure_ascii=False)}"
    )

    try:
        resp = gemini_model.generate_content(prompt, generation_config=GEN_CFG)
    except Exception as e:
        logger.error("Gemini API 呼び出し失敗: %s", e)
        return False

    if not resp.candidates:
        br = getattr(resp.prompt_feedback, "block_reason", "NONE")
        logger.warning("候補なし block_reason=%s", br)
        return False

    cand = resp.candidates[0]
    logger.info("finish_reason=%s", cand.finish_reason)

    parts = cand.content.parts or []
    if not parts or not hasattr(parts[0], "text"):
        return False

    try:
        verdict = json.loads(parts[0].text.strip())
        return verdict if isinstance(verdict, bool) else verdict.get("violation", False)
    except json.JSONDecodeError:
        logger.error("JSON 解析失敗: %s", parts[0].text[:80])
        return False

def notify_admins(client, channel_id, user_id, bot_id_in_event, msg):
    """管理者に違反を通知"""
    snippet = (msg[:200] + "...") if len(msg) > 200 else msg
    poster = f"<@{user_id}>" if user_id else f"BOT:{bot_id_in_event}"
    alert = (
        "⚠️ *ガイドライン違反の可能性を検出しました*\n"
        f"• チャンネル: <#{channel_id}>\n"
        f"• 投稿者   : {poster}\n"
        f"• メッセージ: {snippet}"
    )
    for admin in ADMIN_USERS:
        try:
            client.chat_postMessage(channel=admin, text=alert)
            logger.info("DM sent to %s", admin)
        except Exception as e:
            logger.error("DM 送信失敗 (%s): %s", admin, e)

@app.event("message")
def handle_message(event, client):
    """Slackメッセージを処理"""
    logger.info("📩 EVENT %s", event)

    # 編集・削除等は無視
    if event.get("subtype") and event["subtype"] != "file_share":
        return
    # 自身のメッセージは無視
    if event.get("user") == BOT_USER_ID:
        return
    if event.get("bot_id") == BOT_ID:
        return

    # 監視対象チャンネルかチェック
    ch_id = event.get("channel")
    if ch_id not in MONITOR_CHANNELS:
        return

    # メッセージテキスト取得
    text = event.get("text", "")
    if not text:
        return

    # ガイドライン違反をチェック
    if analyze_text(text):
        user_id = event.get("user")
        bot_id_in_event = event.get("bot_id")
        
        # 管理者に通知
        notify_admins(client, ch_id, user_id, bot_id_in_event, text)
        
        # スプレッドシートに記録
        log_to_spreadsheet(client, user_id, bot_id_in_event, text)
        
        
        
if __name__ == "__main__":
    logger.info("Slack ガイドライン違反監視 Bot 起動（スプレッドシート記録機能付き）")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()