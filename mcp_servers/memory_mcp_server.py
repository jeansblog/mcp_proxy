import os
import pymysql
import datetime
import yaml
from mcp.server.fastmcp import FastMCP
import chromadb

# MCPサーバーの初期化
mcp = FastMCP("Personalized-Memory-Server")

# DBのセットアップ（MySQL & ChromaDB）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "db_config.yaml")


def load_db_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    mysql_config = config.get("mysql")
    if not mysql_config:
        raise ValueError("db_config.yaml に mysql 設定がありません。")

    mysql_config.setdefault("charset", "utf8mb4")
    # コンテナ実行時に環境変数で上書き可能にする
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

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name="ai_reflections")

def init_mysql():
    with pymysql.connect(**MYSQL_CONFIG) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                timestamp DATETIME,
                content TEXT,
                reflection_core TEXT,
                reflection_kind TEXT,
                sentiment_score DOUBLE
            )
        """)

init_mysql()

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
    
    # 1. MySQLに保存（事実と詳細な内省）
    with pymysql.connect(**MYSQL_CONFIG) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO memories (timestamp, content, reflection_core, reflection_kind, sentiment_score) VALUES (%s, %s, %s, %s, %s)",
                (now, content, reflection_core, reflection_kind, sentiment),
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