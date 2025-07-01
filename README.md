# GCP-Slack-bot（GCPを用いたSlackボットの開発手順）

## Compute Engineを使ったデプロイ手順

### ステップ1: プロジェクトの準備
まず、Google Cloud Consoleにアクセスして、プロジェクトを準備します。

<p align="center">
# プロジェクトIDを設定（あなたの場合）
gcloud config set project gen-lang-client-0822699629

# 必要なAPIを有効化
gcloud services enable compute.googleapis.com
</p>
