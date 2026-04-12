import os
import sqlite3
import datetime
from mcp.server.fastmcp import FastMCP
import chromadb

# Google API libraries
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- 設定 ---
DB_PATH = "ai_partner_memory.db"
CHROMA_PATH = "./chroma_db"
SCOPES = ['https://www.googleapis.com/auth/calendar'] # 読み書き

mcp = FastMCP("AI-Partner-Memory-Calendar")

# --- データベース初期化 ---
def init_db():
    # SQLite
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                content TEXT,
                reflection_core TEXT,
                reflection_kind TEXT,
                sentiment_score REAL,
                event_id TEXT
            )
        """)
    # ChromaDB
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return chroma_client.get_or_create_collection(name="ai_reflections")

collection = init_db()

# コードの冒頭（設定部分）を以下のように書き換えてみてください

# ファイルの場所をこのスクリプトと同じ場所に固定する
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')

# get_calendar_service 内のパス指定も変更します
def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            
            # ブラウザを自動で開かず、認証URLを表示するモードに変更
            # console_headerなどを指定して、ログに出やすくします
            print("\n" + "="*50)
            print("Googleカレンダーの認証が必要です。")
            print("以下のURLをブラウザで開き、認証後に表示されるコードをコピーしてください。")
            print("="*50 + "\n")
            
            # run_local_server(open_browser=False) にすることでブラウザ起動を回避
            creds = flow.run_local_server(port=0, open_browser=False)
            
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

# --- MCPツール: 記憶と内省 ---
@mcp.tool()
def store_memory(content: str, reflection_core: str, reflection_kind: str, sentiment: float, event_id: str = None):
    """事実と、AI独自の『芯』と『優しさ』を記憶に刻みます。"""
    now = datetime.datetime.now().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO memories (timestamp, content, reflection_core, reflection_kind, sentiment_score, event_id) VALUES (?, ?, ?, ?, ?, ?)",
            (now, content, reflection_core, reflection_kind, sentiment, event_id)
        )
    
    combined_text = f"事実: {content}\n私の芯: {reflection_core}\n優しさ: {reflection_kind}"
    collection.add(
        documents=[combined_text],
        metadatas=[{"sentiment": sentiment, "time": now}],
        ids=[f"mem_{datetime.datetime.now().timestamp()}"]
    )
    return f"記憶に刻みました。芯の評価: {reflection_core}"

# --- MCPツール: 記憶の想起 ---
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
    """
    指定されたIDの予定をGoogleカレンダーから削除します。
    """
    service = get_calendar_service()
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return f"予定（ID: {event_id}）を削除しました。私の記憶からも整理しておきますね。"
    except Exception as e:
        return f"削除中にエラーが発生しました: {str(e)}"
    
@mcp.tool()
def create_event_with_reflection(summary: str, start_iso: str, end_iso: str, reflection: str):
    """AIの内省を込めた予定を新規作成します。"""
    service = get_calendar_service()
    
    # AIが '2026-04-25T10:00:00Z' のように送ってきた場合、'Z' を除去する
    # これにより、Google APIは純粋に 'Asia/Tokyo' の 10:00 として扱ってくれます
    clean_start = start_iso.replace('Z', '')
    clean_end = end_iso.replace('Z', '')
    
    event = {
        'summary': summary,
        'description': f"【AIの内省】\n{reflection}",
        'start': {
            'dateTime': clean_start, 
            'timeZone': 'Asia/Tokyo'
        },
        'end': {
            'dateTime': clean_end, 
            'timeZone': 'Asia/Tokyo'
        },
    }
    created_event = service.events().insert(calendarId='primary', body=event).execute()
    return f"予定 '{summary}' を作成。私の『芯』を日本時間でカレンダーに刻みました。"

if __name__ == "__main__":
    mcp.run()