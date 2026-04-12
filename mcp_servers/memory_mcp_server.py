import sqlite3
import datetime
from mcp.server.fastmcp import FastMCP
import chromadb

# MCPサーバーの初期化
mcp = FastMCP("Personalized-Memory-Server")

# DBのセットアップ（SQLite & ChromaDB）
DB_PATH = "ai_personality_memory.db"
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="ai_reflections")

def init_sqlite():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                content TEXT,
                reflection_core TEXT,
                reflection_kind TEXT,
                sentiment_score REAL
            )
        """)

init_sqlite()

@mcp.tool()
def store_memory(content: str, reflection_core: str, reflection_kind: str, sentiment: float):
    """
    情報をAIの個性（芯と優しさ）と共に記憶します。
    
    Args:
        content: 客観的な事実や要約
        reflection_core: 「芯の強さ」に基づく独自の評価・こだわり
        reflection_kind: 「優しさ」に基づく配慮やmaruさんへのメッセージ
        sentiment: 感情スコア (-1.0から1.0)
    """
    now = datetime.datetime.now().isoformat()
    
    # 1. SQLiteに保存（事実と詳細な内省）
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO memories (timestamp, content, reflection_core, reflection_kind, sentiment_score) VALUES (?, ?, ?, ?, ?)",
            (now, content, reflection_core, reflection_kind, sentiment)
        )
    
    # 2. ChromaDBに保存（概念検索用）
    # 事実と内省を混ぜてベクトル化することで、後で「考え方」を検索可能にする
    combined_text = f"Fact: {content}\nMy Core: {reflection_core}"
    collection.add(
        documents=[combined_text],
        metadatas=[{"kind": reflection_kind, "time": now}],
        ids=[f"mem_{datetime.datetime.now().timestamp()}"]
    )
    
    return f"記憶に刻みました。私の芯において、この件は '{reflection_core}' と整理しました。"

@mcp.tool()
def recall_memories(query: str, n_results: int = 3):
    """
    過去の記憶や自分の考え方を、現在の状況に合わせて思い出します。
    """
    results = collection.query(query_texts=[query], n_results=n_results)
    return results["documents"]

if __name__ == "__main__":
    mcp.run()