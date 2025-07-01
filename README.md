# GCP-Slack-bot（GCPを用いたSlackボットアプリケーションの開発手順）

## 立教大学人工知能科学研究科　自己推薦　活動報告用　2025年7月1日

作成者：高山一樹（たかやま　かずき）

## Compute Engineを使ったデプロイ手順
※GCPの完成イメージ
![image](https://github.com/user-attachments/assets/d888b825-14a9-48a1-a5f2-d0ec68578258)

※Slackのイメージ図（問題発言を検出）
![image](https://github.com/user-attachments/assets/bf99d04f-397c-4c35-99f3-1496e1c79fff)


### ステップ1: プロジェクトの準備
まず、Google Cloud Consoleにアクセスして、プロジェクトを準備。
<br>

ブラウザで https://console.cloud.google.com にアクセスしてください。Googleアカウントでログインすると、Google Cloud Consoleのダッシュボードが表示されます。
画面上部にあるプロジェクト名を確認。「gen-lang-client-0822699629」と表示されている。
<br>

Compute Engine APIの有効化
次に、仮想マシンを作成するためのサービス（Compute Engine）を有効にする必要がある。
左側のナビゲーションメニューから「APIとサービス」をクリックし、その中の「ライブラリ」を選択。検索ボックスに「Compute Engine」と入力すると、「Compute Engine API」が表示される。これをクリックして、青い「有効にする」ボタンをクリック。
有効化には1〜2分かかることがある。「APIが有効です」と表示されたら、次のステップ。

### ステップ2: VMインスタンスの作成
---

Compute Engine VM の作成手順

1. Compute Engine に移動する
   左側のナビゲーションメニューから **「Compute Engine」** を選択してクリックする。見つからない場合は、メニュー上部の検索ボックスに **「Compute Engine」** と入力して検索する。

2. VM インスタンスを作成する
   「VM インスタンス」ページが開いたら **「インスタンスを作成」** ボタンをクリックする。ここから専用の仮想コンピュータの設定を開始する。

3. 基本設定

   名前
     「名前」フィールドに **slack-bot-monitor** と入力する。
   リージョンとゾーン
     リージョンは **asia-northeast1（東京）** を選択する。ゾーンは既定の **asia-northeast1-a** のままで問題ない。
   マシンタイプ**
     「マシンタイプ」 を開き、**E2** タブから **e2-micro** を選択する。コストを抑えつつ Slack ボットには十分な性能で、月額約 1,000 円程度で運用可能である。

4. ブートディスクの設定
   「ブートディスク」 セクションで 「変更」をクリックし、表示されたウィンドウで次を設定する。

   OS: Ubuntu
   バージョン: Ubuntu 22.04 LTS
   サイズ: 10 GB（既定値）
   タイプ: 標準永続ディスク
   設定後、「選択」をクリックしてウィンドウを閉じる。

5. ネットワークタグの追加
   ページを下へスクロールし、**「管理、セキュリティ、ディスク、ネットワーク、単一テナンシー」** を展開する。**「ネットワーキング」** タブを選択し、**「ネットワークタグ」** に **slack-bot** と入力する（後のファイアウォール設定で使用）。

6. インスタンスの作成**
   すべての設定が完了したら、ページ下部の **「作成」** ボタンをクリックする。VM の作成には通常 1〜2 分を要する。


### ステップ3: VM への接続と初期設定

1. インスタンスを確認する
   「VM インスタンス」の一覧に **slack-bot-monitor** が表示され、緑色のチェックマークが付いていることを確認する。これで VM の準備は完了である。

2. SSH で接続する
   インスタンス名の右側にある 「SSH」 ボタンをクリックする。すると新しいブラウザウィンドウが開き、黒背景のターミナルが表示される。これが仮想コンピュータへのコンソールである。

3. 初期設定を実施する
   ターミナルが開いたら、以下のコマンドを順番に実行する（コピー＆ペースト後に Enter キーを押下）。

   ```bash
    sudo apt update
    sudo apt upgrade -y
   ```

   以降の設定コマンドがある場合も、同様に一つずつ実行していく。
   
　　　次に、Pythonと必要なツールをインストール：

   ```bash
    sudo apt install -y python3-pip python3-venv git
   ```



### ステップ4: ボットのセットアップ


   ```bash
    sudo mkdir -p /opt/slack-bot
    cd /opt/slack-bot
   ```

   ```bash
    sudo python3 -m venv venv
    sudo chown -R $USER:$USER /opt/slack-bot
    source venv/bin/activate
   ```

   ```bash
    pip install --upgrade pip
    pip install slack_bolt google-generativeai pyyaml
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```

### ステップ5 : ボットコードの転送

※ファイルアップロード手順.mdを確認ください

### ステップ6：ボットを24時間動かすための設定

   ```bash
   sudo nano /etc/systemd/system/slack-bot.service
   ```
nanoエディタが開いたら、以下の内容をコピー＆ペースト

```
  [Unit]
  Description=Slack Guideline Monitor Bot
  After=network.target
  
  [Service]
  Type=simple
  User=root
  WorkingDirectory=/opt/slack-bot
  Environment="PATH=/opt/slack-bot/venv/bin"
  ExecStart=/opt/slack-bot/venv/bin/python /opt/slack-bot/slack_bot.py
  Restart=always
  RestartSec=10
  StandardOutput=journal
  StandardError=journal
  
  [Install]
  WantedBy=multi-user.target
```
ファイルを保存（Ctrl+O、Enter、Ctrl+X）したら、サービスを有効化して起動

```bash
  sudo systemctl daemon-reload
  sudo systemctl enable slack-bot.service
  sudo systemctl start slack-bot.service
```

ボットが正しく動いているか確認

```bash
  sudo systemctl status slack-bot.service
```
