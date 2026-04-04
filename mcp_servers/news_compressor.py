import asyncio
from mcp.server.fastmcp import FastMCP

# MCPサーバーの初期化
# 名前にスペースを入れないのがコツです
mcp = FastMCP("NewsCompressor")

@mcp.tool()
async def compress_news(text: str) -> str:
    """
    長いニュース記事を短く要約します。
    
    Args:
        text: 要約したいニュースの全文
    """
    # ここではテスト用に、単純な文字列操作で要約をシミュレートします
    # 実際にはここでLLMを呼び出したり、BeautifulSoupでパースしたりします
    lines = text.strip().split('\n')
    summary = lines[:3]  # 最初の3行だけ抽出
    
    result = "【要約結果】\n" + "\n".join([f"・{l}" for l in summary])
    if len(lines) > 3:
        result += "\n...（以下略）"
        
    return result

if __name__ == "__main__":
    # stdioモードでサーバーを起動
    mcp.run(transport="stdio")