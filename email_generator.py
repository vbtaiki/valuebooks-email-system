"""
バリューブックス LLMメール生成システム
顧客データからパーソナライズメールを自動生成

使い方:
  python email_generator.py

※ 実際にLLMを使う場合は OPENAI_API_KEY または ANTHROPIC_API_KEY を設定
"""

import pandas as pd
import json
import os
from datetime import datetime
from typing import Optional

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


# ========================================
# デモ用: LLMなしでもテンプレートで生成
# ========================================

EMAIL_TEMPLATES = {
    'プラチナ': {
        'subject': '【VIP限定】本日限り買取20%UP',
        'template': """
{name}様

いつもバリューブックスをご愛顧いただき、誠にありがとうございます。

{name}様の累計{total_count}回のお取引、心より感謝申し上げます。

本日限定で、買取金額20%UPキャンペーンを実施しております。
{genre}の本がございましたら、ぜひこの機会にお送りください。

▼ 今すぐ申し込む
https://www.valuebooks.jp/sell

バリューブックス
"""
    },
    'ゴールド': {
        'subject': '【期間限定】買取金額20%UPのご案内',
        'template': """
{name}様

いつもありがとうございます。バリューブックスです。

{dormant_message}

本日、買取金額20%UPキャンペーンを実施中です！
{genre}などの本をお持ちでしたら、ぜひお送りください。

前回は約{avg_books}冊をお送りいただきました。
同程度の冊数でも、今日なら20%お得です。

▼ 申し込みはこちら
https://www.valuebooks.jp/sell

バリューブックス
"""
    },
    'シルバー': {
        'subject': '買取20%UP！本の整理にぴったり',
        'template': """
{name}様

こんにちは、バリューブックスです。

{dormant_message}

本日限定で買取金額が20%アップします！
{genre}の本が眠っていませんか？

この機会にぜひお試しください。
5冊以上で送料無料、集荷もお任せ。

▼ 詳しくはこちら
https://www.valuebooks.jp/sell

バリューブックス
"""
    },
    'ブロンズ': {
        'subject': '【初回歓迎】買取20%UPキャンペーン',
        'template': """
{name}様

バリューブックスです。

読み終わった本、そのままになっていませんか？

本日限定、買取金額20%UPキャンペーン実施中！
ダンボールに詰めて送るだけ。集荷もお任せください。

▼ 今すぐチェック
https://www.valuebooks.jp/sell

バリューブックス
"""
    }
}


def get_dormant_message(dormant_days: int) -> str:
    """休眠日数に応じたメッセージを生成"""
    if dormant_days < 30:
        return "いつもご利用いただきありがとうございます。"
    elif dormant_days < 90:
        return "お久しぶりです。その後いかがお過ごしでしょうか。"
    else:
        return "ご無沙汰しております。またお会いできる日を楽しみにしております。"


def generate_email_from_template(customer: pd.Series) -> dict:
    """テンプレートからメールを生成（LLMなし）"""
    rank = customer['会員ランク']
    template_data = EMAIL_TEMPLATES.get(rank, EMAIL_TEMPLATES['シルバー'])
    
    dormant_message = get_dormant_message(customer['休眠日数'])
    
    body = template_data['template'].format(
        name=customer['氏名'].split()[0] if ' ' in customer['氏名'] else customer['氏名'],
        total_count=customer['累計買取回数'],
        genre=customer['得意ジャンル'],
        avg_books=customer['平均買取冊数'],
        dormant_message=dormant_message
    )
    
    return {
        'to': customer['メールアドレス'],
        'subject': template_data['subject'],
        'body': body.strip(),
        'customer_id': customer['顧客ID'],
        'rank': rank
    }


def generate_email_with_llm(customer: pd.Series, api_key: Optional[str] = None) -> dict:
    """
    LLMを使ってパーソナライズメールを生成
    
    ※ 実際に使う場合は以下のようにAPI連携:
    
    # OpenAI の場合
    import openai
    openai.api_key = api_key
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Anthropic(Claude) の場合
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-3-opus-20240229",
        messages=[{"role": "user", "content": prompt}]
    )
    """
    
    # デモ用: プロンプトだけ生成してテンプレートで返す
    prompt = f"""
以下の顧客情報を基に、買取促進メールを作成してください。

【顧客情報】
- 氏名: {customer['氏名']}
- 会員ランク: {customer['会員ランク']}
- 累計買取回数: {customer['累計買取回数']}回
- 得意ジャンル: {customer['得意ジャンル']}
- 休眠日数: {customer['休眠日数']}日

【キャンペーン】
買取金額20%UP（本日限定）

【条件】
- 件名: 20文字以内
- 本文: 200文字以内
- 顧客の得意ジャンルに言及
- 押し付けがましくない自然なトーン
"""
    
    # 実際のLLM呼び出しの代わりにテンプレート生成
    # (APIキーがあれば本物のLLMを呼び出す処理をここに追加)
    
    if api_key:
        print(f"  📡 LLM API呼び出し中... (実装時はここでAPI通信)")
    
    return generate_email_from_template(customer)


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║     ✉️  バリューブックス LLMメール生成システム               ║
║     顧客データからパーソナライズメールを自動生成             ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # 抽出済み顧客データを読み込み
    targets_path = os.path.join(DATA_DIR, 'today_targets.csv')
    
    if os.path.exists(targets_path):
        customers = pd.read_csv(targets_path)
        print(f"📊 抽出済み顧客データを読み込み: {len(customers)}名")
    else:
        # 元データから読み込み
        customers = pd.read_csv(os.path.join(DATA_DIR, 'customers_email.csv'))
        customers = customers.head(5)  # デモ用に5名
        print(f"📊 デモデータを使用: {len(customers)}名")
    
    print(f"\n{'='*60}")
    print("【メール生成開始】")
    print(f"{'='*60}")
    
    generated_emails = []
    
    for idx, customer in customers.iterrows():
        print(f"\n📧 {customer['氏名']} ({customer['会員ランク']})...")
        
        email = generate_email_with_llm(customer)
        generated_emails.append(email)
        
        print(f"   ✅ 件名: {email['subject']}")
    
    # 生成結果をJSON保存
    output_path = os.path.join(DATA_DIR, 'generated_emails.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(generated_emails, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"💾 {len(generated_emails)}通のメールを生成しました")
    print(f"   保存先: {output_path}")
    
    # サンプル表示
    print(f"\n{'='*60}")
    print("【生成サンプル（1通目）】")
    print(f"{'='*60}")
    
    sample = generated_emails[0]
    print(f"\nTo: {sample['to']}")
    print(f"Subject: {sample['subject']}")
    print(f"\n{sample['body']}")
    
    print(f"\n{'='*60}")
    print("【LLM連携のヒント】")
    print(f"{'='*60}")
    print("""
    このスクリプトを本番環境で使うには:
    
    1. OpenAI APIの場合:
       export OPENAI_API_KEY="sk-..."
       
    2. Claude APIの場合:
       export ANTHROPIC_API_KEY="sk-ant-..."
    
    3. generate_email_with_llm() 関数内で
       実際のAPI呼び出しを有効化
    
    💡 Cursorなら「LLM連携を実装して」と言うだけ！
    """)


if __name__ == "__main__":
    main()

