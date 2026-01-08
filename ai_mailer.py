"""
バリューブックス AIメール生成システム
OpenAI GPT-4を使って顧客ごとにパーソナライズされたメールを生成

使い方:
  export OPENAI_API_KEY="sk-..."
  python ai_mailer.py
"""

import os
import json
import pandas as pd
from datetime import datetime
from openai import OpenAI

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def load_warehouse_status():
    """倉庫状況を読み込む"""
    with open(os.path.join(DATA_DIR, 'warehouse_status.json'), 'r', encoding='utf-8') as f:
        return json.load(f)


def load_customers():
    """顧客データを読み込む"""
    path = os.path.join(DATA_DIR, 'customers_full.csv')
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.read_csv(os.path.join(DATA_DIR, 'customers_email.csv'))


def load_news():
    """ニュースを読み込む"""
    path = os.path.join(DATA_DIR, 'recent_news.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f).get('news_items', [])
    return []


def analyze_slack_periods(warehouse):
    """閑散期を分析"""
    forecast = warehouse.get('weekly_forecast', [])
    threshold = warehouse.get('thresholds', {}).get('閑散期_capacity_under', 0.45)
    return [d['date'] for d in forecast if d['capacity_usage'] < threshold]


def determine_email_type(customer, warehouse, today):
    """メールタイプを判定"""
    last_email = datetime.strptime(customer['最終メール送信日'], '%Y-%m-%d')
    days_since = (today - last_email).days
    
    slack_days = analyze_slack_periods(warehouse)
    backlog = warehouse.get('backlog', {}).get('未査定_箱数', 150)
    activity = customer.get('購入傾向', '買取メイン')
    
    # 緊急度判定
    urgency = "高" if backlog < 100 and len(slack_days) >= 3 else "中" if len(slack_days) >= 1 else "低"
    
    if days_since < 7:
        return None, "送信間隔が短すぎる"
    elif days_since < 14 and urgency != "高":
        return None, "もう少し間隔を空ける"
    elif urgency == "高" and activity in ['買取メイン', '両方活発']:
        return "緊急買取促進", f"閑散期{len(slack_days)}日間・緊急"
    elif len(slack_days) > 0 and activity == '買取メイン':
        return "通常買取促進", "閑散期のため買取促進"
    elif activity == '購入メイン':
        return "購入促進", "購入傾向の顧客"
    else:
        return "ニュース", "関係構築"


def build_prompt(customer, email_type, reason, warehouse, news):
    """LLMプロンプトを構築"""
    slack_days = analyze_slack_periods(warehouse)
    backlog = warehouse.get('backlog', {})
    
    # マッチするニュースを検索
    genre = customer.get('得意ジャンル', '')
    matching_news = [n for n in news if any(g in genre for g in n.get('related_genres', [])) or '全ジャンル' in n.get('related_genres', [])]
    
    news_text = ""
    if matching_news:
        news_text = "\n## 関連ニュース\n" + "\n".join([f"- {n['title']}: {n['summary']}" for n in matching_news[:2]])
    
    prompt = f"""あなたはバリューブックスのメールライターです。
以下の状況を総合的に判断し、最適なメールを作成してください。

## 送信判断
- 推奨メールタイプ: {email_type}
- 判断理由: {reason}

## 顧客情報
- 氏名: {customer['氏名']}
- 会員ランク: {customer['会員ランク']}
- 傾向: {customer.get('購入傾向', 'N/A')}
- 得意ジャンル: {customer.get('得意ジャンル', 'N/A')}
- 累計買取: {customer.get('累計買取回数', 0)}回 / ¥{customer.get('累計買取金額', 0):,}
- 累計購入: {customer.get('累計購入回数', 0)}回 / ¥{customer.get('累計購入金額', 0):,}

## 倉庫状況
- 閑散期: {len(slack_days)}日間（20%UPキャンペーン実施中）
- 未査定バックログ: {backlog.get('未査定_箱数', 0)}箱
{news_text}

## メール種別ごとのトーン
- 緊急買取促進: 「本日限定！」など緊急感を出す
- 通常買取促進: 「そろそろ本の整理はいかがですか？」など自然なトーン
- 購入促進: おすすめ本を提案
- ニュース: 情報提供メイン

## 作成条件
1. 件名は20文字以内
2. 本文は150〜200文字
3. 顧客の名前を使ってパーソナライズ
4. 得意ジャンルに言及する
5. 押し売り感を出さない

## 出力形式（これに従ってください）
件名: [件名をここに]

本文:
[本文をここに]"""
    
    return prompt


def generate_email_with_gpt(client, prompt):
    """GPT-4でメールを生成"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # コスト効率の良いモデル
            messages=[
                {"role": "system", "content": "あなたは古書店バリューブックスのプロのメールライターです。顧客に寄り添った、温かみのあるメールを書きます。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"エラー: {str(e)}"


def parse_email_response(response):
    """GPTの出力をパース"""
    lines = response.strip().split('\n')
    subject = ""
    body_lines = []
    in_body = False
    
    for line in lines:
        if line.startswith('件名:') or line.startswith('件名：'):
            subject = line.replace('件名:', '').replace('件名：', '').strip()
        elif line.startswith('本文:') or line.startswith('本文：'):
            in_body = True
        elif in_body:
            body_lines.append(line)
    
    return subject, '\n'.join(body_lines).strip()


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║     🤖 バリューブックス AIメール生成システム                 ║
║     OpenAI GPT-4でパーソナライズメールを自動生成             ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # APIキー確認
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("❌ エラー: OPENAI_API_KEY が設定されていません")
        print("   export OPENAI_API_KEY='sk-...' を実行してください")
        return
    
    print(f"✅ APIキー確認OK: {api_key[:20]}...")
    
    # OpenAIクライアント初期化
    client = OpenAI()
    
    # データ読み込み
    print("\n📊 データ読み込み中...")
    warehouse = load_warehouse_status()
    customers = load_customers()
    news = load_news()
    today = datetime.now()
    
    print(f"   顧客数: {len(customers)}名")
    print(f"   ニュース: {len(news)}件")
    
    slack_days = analyze_slack_periods(warehouse)
    print(f"   閑散期: {len(slack_days)}日間")
    
    # 送信対象を選定
    print(f"\n{'='*60}")
    print("【送信対象の選定】")
    print(f"{'='*60}")
    
    targets = []
    skipped = []
    
    for _, customer in customers.iterrows():
        email_type, reason = determine_email_type(customer, warehouse, today)
        if email_type:
            targets.append({'customer': customer, 'type': email_type, 'reason': reason})
        else:
            skipped.append({'customer': customer, 'reason': reason})
    
    print(f"   送信対象: {len(targets)}名")
    print(f"   見送り: {len(skipped)}名")
    
    if not targets:
        print("\n送信対象がいません。")
        return
    
    # 生成する件数を確認
    print(f"\n{'='*60}")
    print("【メール生成】")
    print(f"{'='*60}")
    
    try:
        num_generate = int(input(f"何通生成しますか？ (1-{len(targets)}): "))
        num_generate = min(num_generate, len(targets))
    except ValueError:
        num_generate = min(3, len(targets))
        print(f"   → デフォルト {num_generate}通を生成")
    
    generated_emails = []
    
    for i, target in enumerate(targets[:num_generate]):
        customer = target['customer']
        email_type = target['type']
        reason = target['reason']
        
        print(f"\n📧 [{i+1}/{num_generate}] {customer['氏名']}（{customer['会員ランク']}）")
        print(f"   タイプ: {email_type}")
        print(f"   理由: {reason}")
        
        # プロンプト構築
        prompt = build_prompt(customer, email_type, reason, warehouse, news)
        
        # GPT-4で生成
        print("   🤖 GPT-4で生成中...")
        response = generate_email_with_gpt(client, prompt)
        
        # パース
        subject, body = parse_email_response(response)
        
        print(f"\n   📬 件名: {subject}")
        print(f"   ────────────────────────────────")
        print(f"   {body[:100]}..." if len(body) > 100 else f"   {body}")
        
        generated_emails.append({
            'customer_id': customer['顧客ID'],
            'name': customer['氏名'],
            'email': customer['メールアドレス'],
            'rank': customer['会員ランク'],
            'type': email_type,
            'subject': subject,
            'body': body,
            'generated_at': datetime.now().isoformat()
        })
    
    # 結果を保存
    output_path = os.path.join(DATA_DIR, 'ai_generated_emails.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(generated_emails, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ {len(generated_emails)}通のメールを生成しました！")
    print(f"💾 保存先: {output_path}")
    print(f"{'='*60}")
    
    # サンプル表示
    if generated_emails:
        print("\n【生成サンプル（1通目の全文）】")
        print(f"{'='*60}")
        sample = generated_emails[0]
        print(f"To: {sample['email']}")
        print(f"Subject: {sample['subject']}")
        print(f"\n{sample['body']}")


if __name__ == "__main__":
    main()

