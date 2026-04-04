1. 仮想環境の作成と同期
uv は pyproject.toml や requirements.txt がなくても、直接パッケージを指定して同期できます。

# 仮想環境をカレントディレクトリに作成 (.venv)
uv venv --python 3.11

# 依存関係を一括インストール
# ※ StreamableHttpTransport を含む最新の mcp[cli] を指定
uv  pip install --no-cache-dir --upgrade -r requirements.txt

2. プロキシの起動
仮想環境内の uvicorn を使って起動します。

# Linux / macOS の場合
source .venv/bin/activate