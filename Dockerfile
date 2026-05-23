# ビルドステージ
FROM python:3.13-slim 

WORKDIR /app

# 依存関係のコピーとインストール
# ※ requirements.txt または pyproject.toml がある場合
COPY requirements.txt .
RUN pip install -r requirements.txt

# ソースコードと設定ファイルのコピー
COPY mcp_proxy_server.py .
COPY mcp_pipe.py .
COPY mcp_config.yaml .
COPY mcp_config.json .

# ポートの開放 (プロキシサーバー用)
EXPOSE 8010

# サーバーの起動
CMD ["sh", "-c", "python mcp_pipe.py & python mcp_proxy_server.py"]