# 🧠 バリューブックス インテリジェント・メールシステム V2

Emotional Balance（感情的貸借）の考え方に基づいた、スマートなメール配信システム

## 🎯 コンセプト

- **💸 負債 = 買取お願い**: ユーザーへのストレス
- **🎁 資産 = プレゼント・有益情報**: ユーザーへの喜び

ユーザーとの関係性を「貸借」として管理し、信頼関係を維持します。

## ✨ 機能

1. **📊 デイリーバジェット計算**: 倉庫の緊急度に応じて送信数を自動調整
2. **🎯 スマートターゲティング**: 関係性バランス×品質スコアで優先順位付け
3. **🤖 GPT-4メール生成**: パーソナライズされたメールを自動生成

## 🚀 デプロイ方法

### Streamlit Community Cloud

1. このリポジトリをフォーク
2. [Streamlit Cloud](https://share.streamlit.io) にログイン
3. "New app" → リポジトリを選択
4. Settings → Secrets に `OPENAI_API_KEY` を設定
5. Deploy!

### ローカル実行

```bash
# 依存関係インストール
pip install -r requirements.txt

# 環境変数設定
export OPENAI_API_KEY="sk-..."

# 起動
streamlit run dashboard_v2.py
```

## 📁 ファイル構成

```
08_email_optimizer/
├── dashboard_v2.py          # メインダッシュボード
├── smart_mailer_v2.py       # コアロジック
├── simulation_runner.py     # シミュレーター
├── customers_v2.csv         # 顧客データ
├── warehouse_status_v2.json # 倉庫状況
├── dummy_blog_data.json     # ブログ・キャンペーン情報
├── requirements.txt         # 依存関係
└── .streamlit/
    └── config.toml          # Streamlit設定
```

## 🔐 セキュリティ

- `OPENAI_API_KEY` は必ず Streamlit Secrets または環境変数で管理
- `.gitignore` で `secrets.toml` を除外済み

## 📝 ライセンス

Internal use only - バリューブックス

