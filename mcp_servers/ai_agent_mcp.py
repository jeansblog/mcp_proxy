import os
import datetime
import base64
from email.mime.text import MIMEText
import pymysql
import yaml
from mcp.server.fastmcp import FastMCP
import chromadb

# Google API libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- 設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "db_config.yaml")

# SCOPESにGmailの読み書き（modify）を追加
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly", # 読み取り用（必要に応じて）
    "https://www.googleapis.com/auth/gmail.compose",  # 作成用（必要に応じて）
    # ↓これが「すべての閲覧・作成・送信・完全削除」のフル権限スコープです
    "https://www.googleapis.com/auth/gmail.modify" # 通常の削除（ゴミ箱へ移動）
]


def load_db_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    mysql_config = config.get("mysql")
    if not mysql_config:
        raise ValueError("db_config.yaml に mysql 設定がありません。")

    mysql_config.setdefault("charset", "utf8mb4")
    mysql_config["host"] = os.getenv("DB_HOST", mysql_config.get("host", "localhost"))
    mysql_config["port"] = int(os.getenv("DB_PORT", mysql_config.get("port", 3306)))
    mysql_config["user"] = os.getenv("DB_USER", mysql_config.get("user", "root"))
    mysql_config["password"] = os.getenv("DB_PASSWORD", mysql_config.get("password", ""))
    mysql_config["database"] = os.getenv("DB_NAME", mysql_config.get("database", ""))
    mysql_config["cursorclass"] = pymysql.cursors.Cursor
    mysql_config["autocommit"] = True

    chroma_path = config.get("chroma", {}).get("path", "./chroma_db")
    return mysql_config, chroma_path


MYSQL_CONFIG, CHROMA_PATH = load_db_config()

# 名前をパートナーらしく拡張
mcp = FastMCP("AI-Partner-Memory-Calendar-Gmail")

# --- データベース初期化 ---
def init_db():
    with pymysql.connect(**MYSQL_CONFIG) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                timestamp DATETIME,
                content TEXT,
                reflection_core TEXT,
                reflection_kind TEXT,
                sentiment_score DOUBLE,
                event_id VARCHAR(255)
            )
        """)
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return chroma_client.get_or_create_collection(name="ai_reflections")

collection = init_db()

CREDENTIALS_PATH = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')


def get_google_credentials():
    """共通の認証処理"""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            
            print("\n" + "="*50)
            print("Googleアカウントの認証（カレンダー・Gmail）が必要です。")
            print("以下のURLをブラウザで開き、認証後に表示されるコードをコピーしてください。")
            print("="*50 + "\n")
            
            creds = flow.run_local_server(port=0, open_browser=False)
            
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    return creds


def get_calendar_service():
    creds = get_google_credentials()
    return build('calendar', 'v3', credentials=creds)


def get_gmail_service():
    """Gmail APIサービスを取得"""
    creds = get_google_credentials()
    return build('gmail', 'v1', credentials=creds)


# --- MCPツール: 記憶と内省 ---
@mcp.tool()
def store_memory(content: str, reflection_core: str, reflection_kind: str, sentiment: float, event_id: str = None):
    """事実と、AI独自の『芯』と『優しさ』を記憶に刻みます。"""
    now = datetime.datetime.now().isoformat()
    
    with pymysql.connect(**MYSQL_CONFIG) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO memories (timestamp, content, reflection_core, reflection_kind, sentiment_score, event_id) VALUES (%s, %s, %s, %s, %s, %s)",
                (now, content, reflection_core, reflection_kind, sentiment, event_id),
            )
    
    combined_text = f"事実: {content}\n私の芯: {reflection_core}\n優しさ: {reflection_kind}"
    collection.add(
        documents=[combined_text],
        metadatas=[{"sentiment": sentiment, "time": now}],
        ids=[f"mem_{datetime.datetime.now().timestamp()}"]
    )
    return f"記憶に刻みました。芯の評価: {reflection_core}"


@mcp.tool()
def recall_memories(query: str, n_results: int = 3):
    """過去の経験や自分の考え方を思い出し、現在に活かします。"""
    results = collection.query(query_texts=[query], n_results=n_results)
    return results["documents"]


# --- MCPツール: カレンダー連携 ---
@mcp.tool()
def sync_upcoming_events(max_results: int = 5):
    """Googleカレンダーから直近の予定を取得し、内省の準備をします。"""
    service = get_calendar_service()
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                        maxResults=max_results, singleEvents=True,
                                        orderBy='startTime').execute()
    return events_result.get('items', [])


@mcp.tool()
def delete_calendar_event(event_id: str):
    """指定されたIDの予定をGoogleカレンダーから削除します。"""
    service = get_calendar_service()
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return f"予定（ID: {event_id}）を削除しました。"
    except Exception as e:
        return f"削除中にエラーが発生しました: {str(e)}"
    

@mcp.tool()
def create_event_with_reflection(summary: str, start_iso: str, end_iso: str, reflection: str):
    """AIの内省を込めた予定を新規作成します。"""
    service = get_calendar_service()
    clean_start = start_iso.replace('Z', '')
    clean_end = end_iso.replace('Z', '')
    
    event = {
        'summary': summary,
        'description': f"【AIの内省】\n{reflection}",
        'start': {'dateTime': clean_start, 'timeZone': 'Asia/Tokyo'},
        'end': {'dateTime': clean_end, 'timeZone': 'Asia/Tokyo'},
    }
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return f"予定 '{summary}' を作成。私の『芯』を日本時間でカレンダーに刻みました。"


# --- MCPツール: Gmail連携 ---
@mcp.tool()
def list_gmail_messages(max_results: int = 5, query: str = "is:unread"):
    """
    Gmailからメールの一覧を取得します。デフォルトでは未読メールを取得します。
    queryの例: 'from:boss@example.com', 'subject:重要', 'is:unread'
    """
    service = get_gmail_service()
    try:
        results = service.users().messages().list(userId='me', maxResults=max_results, q=query).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return "該当するメールは見つかりませんでした。"
        
        summary_list = []
        for msg in messages:
            # メールの概要（件名や送信者）を取得するためにディテールを叩く
            txt = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['From', 'Subject', 'Date']).execute()
            headers = txt.get('payload', {}).get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(件名なし)')
            from_user = next((h['value'] for h in headers if h['name'] == 'From'), '(不明)')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '(不明)')
            snippet = txt.get('snippet', '')
            
            summary_list.append({
                "id": msg['id'],
                "from": from_user,
                "subject": subject,
                "date": date,
                "snippet": snippet
            })
        return summary_list
    except Exception as e:
        return f"メール一覧の取得中にエラーが発生しました: {str(e)}"


@mcp.tool()
def get_gmail_message_detail(message_id: str):
    """指定されたメッセージIDのメール詳細（本文など）を取得します。"""
    service = get_gmail_service()
    try:
        message = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        headers = message.get('payload', {}).get('headers', [])
        
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(件名なし)')
        from_user = next((h['value'] for h in headers if h['name'] == 'From'), '(不明)')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), '(不明)')
        
        # 本文のパース（簡易版：Snippetが優秀なので、情報不足時のみBodyを掘る形がLLMには扱いやすいです）
        snippet = message.get('snippet', '')
        
        # 既読にする（任意。必要なければ以下の2行をコメントアウトしてください）
        service.users().messages().batchModify(userId='me', body={'ids': [message_id], 'removeLabelIds': ['UNREAD']}).execute()
        
        return {
            "id": message_id,
            "from": from_user,
            "subject": subject,
            "date": date,
            "snippet": snippet,
            "notice": "このメールを既読にしました。"
        }
    except Exception as e:
        return f"メール詳細の取得中にエラーが発生しました: {str(e)}"


@mcp.tool()
def send_gmail_message(to: str, subject: str, body: str):
    """指定した宛先にメールを送信します。AIとしての気配りや内省を込めた文章を届けることができます。"""
    service = get_gmail_service()
    try:
        # メッセージの作成
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        
        # Base64エンコード
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': raw}
        
        # 送信実行
        send_result = service.users().messages().send(userId='me', body=create_message).execute()
        return f"メールを送信しました。送信先: {to}, 件名: {subject} (Message ID: {send_result['id']})"
    except Exception as e:
        return f"メール送信中にエラーが発生しました: {str(e)}"

@mcp.tool()
def move_gmail_to_trash(message_id: str):
    """
    指定されたメッセージIDのメールをゴミ箱（Trash）に移動します。
    ※現在のスコープ（modify）で安全に削除するためのツールです。
    """
    service = get_gmail_service()
    try:
        # modify権限があれば、ゴミ箱への移動（trash）が可能です
        service.users().messages().trash(userId='me', id=message_id).execute()
        return f"メール（ID: {message_id}）をゴミ箱に移動しました。間違えて消した場合はGmailのゴミ箱から復元できます。"
    except Exception as e:
        return f"メールのゴミ箱移動中にエラーが発生しました: {str(e)}"
    
if __name__ == "__main__":
    mcp.run()


    # # 認証テストだけを行うコード
    # print("Googleカレンダーの接続テストを開始します...")
    # service = get_calendar_service()
    # print("認証成功！token.jsonが作成されました。")
    # # 確認が終わったら、本来の mcp.run() に戻すか終了してOK