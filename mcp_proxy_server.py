import yaml
import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI, Request
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.client.sse import sse_client

# ==========================================
# 1. 設定とグローバル変数の初期化
# ==========================================

# MCPサーバーの設定ファイルを読み込み
with open("mcp_config.yaml", "r") as f:
    config = yaml.safe_load(f)
    CONFIG_SERVERS = config.get("mcp_servers", {})

# プロキシ内部で管理する状態
REGISTRY = {"tools": {}}  # ツール名とバックエンドの紐付け情報を格納
SERVER_SESSIONS = {}      # 各サーバーとのアクティブなセッションを保持
SERVER_STACKS = {}        # リソース解放のための ExitStack を保持

# ==========================================
# 2. バックエンド接続ロジック
# ==========================================

async def connect_and_register(server_id, conf):
    """
    http と stdio の両方のトランスポートに対応して接続・登録を行う
    """
    transport_type = conf.get("transport", "http")
    print(f"[*] Connecting to '{server_id}' via {transport_type}...")
    stack = AsyncExitStack()
    
    try:
        if transport_type == "http":
            # 1. 従来の HTTP ストリーミング (streamable-http)
            transport_cm = streamable_http_client(conf["url"])
            read, write, _ = await stack.enter_async_context(transport_cm)
            
        elif transport_type == "sse":
            # 2. SSE (Server-Sent Events)
            # url は通常 'http://host:port/sse' のようになります
            transport_cm = sse_client(conf["url"])
            read, write = await stack.enter_async_context(transport_cm)
            
        elif transport_type == "stdio":
            # 3. ローカルプロセス (stdio)
            server_params = StdioServerParameters(
                command=conf["command"],
                args=conf.get("args", []),
                env={**os.environ, **conf.get("env", {})}
            )
            read, write = await stack.enter_async_context(stdio_client(server_params))
        
        # --- 以下、セッション初期化と登録処理は共通 ---
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        
        # ツール取得と登録
        tools_result = await session.list_tools()
        for tool in tools_result.tools:
            p_name = f"{server_id}_{tool.name}"
            REGISTRY["tools"][p_name] = {
                "server_id": server_id,
                "original_name": tool.name,
                "full_data": {
                    "name": p_name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema
                }
            }
            print(f"  [OK] Registered tool: {p_name}")
        
        SERVER_SESSIONS[server_id] = session
        SERVER_STACKS[server_id] = stack
        return True

    except Exception as e:
        print(f"  [Failed] {server_id}: {e}")
        await stack.aclose()
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--- MCP Proxy Server Starting (Multi-Transport) ---")
    for server_id, conf in CONFIG_SERVERS.items():
        # 設定オブジェクト全体を渡すように変更
        asyncio.create_task(connect_and_register(server_id, conf))
    yield
    
    # 終了処理：全ての ExitStack を閉じて接続を安全に終了
    print("--- Shutting down connections ---")
    for stack in SERVER_STACKS.values():
        await stack.aclose()

app = FastAPI(lifespan=lifespan)

# ==========================================
# 4. MCP JSON-RPC ハンドラ
# ==========================================

@app.post("/mcp")
async def unified_mcp_handler(request: Request):
    """
    全ての MCP JSON-RPC リクエストを処理し、適切なバックエンドへ振り分ける。
    """
    payload = await request.json()
    method = payload.get("method")
    params = payload.get("params", {})
    request_id = payload.get("id")

    # A. 初期化リクエスト (プロトコルの握手)
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "experimental": {}
                },
                "serverInfo": {
                    "name": "mcp-proxy-stable",
                    "version": "1.0.0"
                }
            }
        }

    # B. ツール一覧リクエスト
    if method == "tools/list":
        tool_list = [v["full_data"] for v in REGISTRY["tools"].values()]
        print(f">>> Reporting {len(tool_list)} combined tools to client")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": tool_list}
        }

    # C. ツール実行リクエスト
    if method == "tools/call":
        tool_name = params.get("name")
        target = REGISTRY["tools"].get(tool_name)
        
        if target:
            session = SERVER_SESSIONS.get(target["server_id"])
            if session:
                try:
                    # 本物のツール名と引数でバックエンドを呼び出す
                    result = await session.call_tool(
                        target["original_name"], 
                        params.get("arguments", {})
                    )
                    
                    # 結果をクライアントが理解できる形式に整形して返却
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": c.text} if hasattr(c, 'text') else {"type": "text", "text": str(c)} 
                                for c in result.content
                            ],
                            "isError": result.isError
                        }
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0", 
                        "id": request_id, 
                        "error": {"code": -32603, "message": f"Backend error: {str(e)}"}
                    }

    # D. 未知のメソッドや未登録のツール
    return {
        "jsonrpc": "2.0", 
        "id": request_id, 
        "result": {"tools": [], "content": [{"type": "text", "text": "Method not handled or tool not found."}]}
    }

# ==========================================
# 5. サーバー起動
# ==========================================

if __name__ == "__main__":
    import uvicorn
    # 外部接続を許可するため 0.0.0.0 で起動
    uvicorn.run(app, host="0.0.0.0", port=8010)