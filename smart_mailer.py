"""
バリューブックス スマートメーラー
倉庫状況・顧客履歴・ニュースを総合判断してメールを最適化

使い方:
  python smart_mailer.py
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum
import os

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


class EmailType(Enum):
    """メールの種類"""
    URGENT_KAITORI = "緊急買取促進"      # 閑散期で倉庫が空いている
    NORMAL_KAITORI = "通常買取促進"      # 通常の買取促進
    PURCHASE = "購入促進"                 # 購入履歴ベースの購入促進
    NEWS = "ニュースお知らせ"            # 関係構築目的
    SKIP = "送信見送り"                   # 送りすぎ防止


@dataclass
class WarehouseStatus:
    """倉庫の状況"""
    backlog_boxes: int           # 未査定の箱数
    backlog_books: int           # 未査定の推定冊数
    today_predicted: int         # 今日の予想到着数
    capacity_usage: float        # キャパシティ使用率
    is_slack_period: bool        # 閑散期かどうか
    slack_days: List[str]        # 閑散期の日付リスト
    urgency_level: str           # 緊急度（低/中/高）


@dataclass
class CustomerContext:
    """顧客のコンテキスト"""
    customer_id: str
    name: str
    rank: str
    days_since_last_email: int
    last_email_type: str
    email_frequency_ok: bool     # メール頻度が適切か
    primary_activity: str        # 買取メイン/購入メイン/両方
    matching_news: List[Dict]    # マッチするニュース
    recommended_type: EmailType  # 推奨メールタイプ
    recommendation_reason: str   # 推奨理由


def load_warehouse_status() -> WarehouseStatus:
    """倉庫状況を読み込み、分析する"""
    with open(os.path.join(DATA_DIR, 'warehouse_status.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    backlog = data['backlog']
    forecast = data['weekly_forecast']
    thresholds = data['thresholds']
    
    # 閑散期の日を特定
    slack_days = []
    for day in forecast:
        if day['capacity_usage'] < thresholds['閑散期_capacity_under']:
            slack_days.append(day['date'])
    
    # 今日のキャパシティ使用率
    today_forecast = forecast[0] if forecast else {}
    capacity_usage = today_forecast.get('capacity_usage', 0.5)
    
    # 緊急度を判定
    if backlog['未査定_箱数'] < 100 and len(slack_days) >= 3:
        urgency = "高"
    elif backlog['未査定_箱数'] < 150 and len(slack_days) >= 1:
        urgency = "中"
    else:
        urgency = "低"
    
    return WarehouseStatus(
        backlog_boxes=backlog['未査定_箱数'],
        backlog_books=backlog['未査定_推定冊数'],
        today_predicted=today_forecast.get('predicted_arrivals', 0),
        capacity_usage=capacity_usage,
        is_slack_period=len(slack_days) > 0,
        slack_days=slack_days,
        urgency_level=urgency
    )


def load_news() -> List[Dict]:
    """最新ニュースを読み込む"""
    with open(os.path.join(DATA_DIR, 'recent_news.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['news_items']


def analyze_customer(
    customer: pd.Series,
    warehouse: WarehouseStatus,
    news: List[Dict],
    today: datetime
) -> CustomerContext:
    """
    顧客を総合分析し、最適なメールタイプを決定
    
    判断基準:
    1. メール頻度（21日以上空いているか）
    2. 倉庫の緊急度（閑散期なら買取促進を優先）
    3. 顧客の傾向（買取メイン/購入メイン）
    4. マッチするニュースがあるか
    5. 最後に送ったメールの種類（同じ種類は避ける）
    """
    # メール送信からの日数
    last_email = datetime.strptime(customer['最終メール送信日'], '%Y-%m-%d')
    days_since_email = (today - last_email).days
    
    # メール頻度チェック（14日以内は送りすぎ）
    email_frequency_ok = days_since_email >= 14
    
    # マッチするニュースを検索
    customer_genre = customer['得意ジャンル']
    matching_news = [
        n for n in news 
        if any(g in customer_genre for g in n.get('related_genres', []))
        or '全ジャンル' in n.get('related_genres', [])
    ]
    
    # メールタイプの決定ロジック
    recommended_type = EmailType.SKIP
    reason = ""
    
    # Step 1: 頻度チェック
    if not email_frequency_ok:
        if days_since_email < 7:
            recommended_type = EmailType.SKIP
            reason = f"最終送信から{days_since_email}日。送りすぎ防止のため見送り。"
        elif days_since_email < 14:
            # 7-14日は緊急時のみ送信
            if warehouse.urgency_level == "高":
                recommended_type = EmailType.URGENT_KAITORI
                reason = f"送信間隔短いが、倉庫緊急度「高」のため買取促進を優先。"
            else:
                recommended_type = EmailType.SKIP
                reason = f"最終送信から{days_since_email}日。もう少し間隔を空けたい。"
    else:
        # Step 2: 倉庫状況と顧客傾向で判断
        activity = customer['購入傾向']
        last_type = customer['最終メール種別']
        
        if warehouse.urgency_level == "高" and activity in ['買取メイン', '両方活発']:
            # 緊急かつ買取傾向の顧客 → 買取促進
            recommended_type = EmailType.URGENT_KAITORI
            reason = f"閑散期{len(warehouse.slack_days)}日連続。買取傾向の顧客に緊急買取促進。"
        
        elif warehouse.urgency_level == "中" and activity == '買取メイン':
            # 中程度の緊急性
            if last_type != '買取促進':
                recommended_type = EmailType.NORMAL_KAITORI
                reason = f"閑散期あり。前回は{last_type}だったので買取促進へ切替。"
            else:
                # 前回も買取促進なら、ニュースかスキップ
                if matching_news:
                    recommended_type = EmailType.NEWS
                    reason = f"前回買取促進のため、今回はニュース（{matching_news[0]['title'][:20]}...）"
                else:
                    recommended_type = EmailType.NORMAL_KAITORI
                    reason = "前回も買取促進だが、マッチするニュースがないため継続。"
        
        elif activity == '購入メイン':
            # 購入メインの顧客
            if matching_news and any(n['action_type'] == '購入促進' for n in matching_news):
                recommended_type = EmailType.PURCHASE
                reason = f"購入傾向の顧客。{matching_news[0]['title'][:20]}に関連した購入促進。"
            elif matching_news:
                recommended_type = EmailType.NEWS
                reason = f"購入傾向の顧客にニュースでアプローチ。"
            else:
                recommended_type = EmailType.PURCHASE
                reason = "購入傾向の顧客に購入促進。"
        
        elif activity == '両方活発':
            # 両方活発な顧客 → バランスを取る
            if last_type == '買取促進' and matching_news:
                recommended_type = EmailType.NEWS
                reason = f"アクティブ顧客。前回買取促進のため、今回はニュース。"
            elif warehouse.is_slack_period:
                recommended_type = EmailType.NORMAL_KAITORI
                reason = f"アクティブ顧客。閑散期のため買取促進。"
            else:
                recommended_type = EmailType.PURCHASE
                reason = "アクティブ顧客。購入も促進。"
        
        else:
            # デフォルト
            if matching_news:
                recommended_type = EmailType.NEWS
                reason = "マッチするニュースあり。関係構築目的で送信。"
            elif warehouse.is_slack_period:
                recommended_type = EmailType.NORMAL_KAITORI
                reason = "閑散期のため買取促進。"
            else:
                recommended_type = EmailType.SKIP
                reason = "特に送信する理由がないため見送り。"
    
    return CustomerContext(
        customer_id=customer['顧客ID'],
        name=customer['氏名'],
        rank=customer['会員ランク'],
        days_since_last_email=days_since_email,
        last_email_type=customer['最終メール種別'],
        email_frequency_ok=email_frequency_ok,
        primary_activity=customer['購入傾向'],
        matching_news=matching_news,
        recommended_type=recommended_type,
        recommendation_reason=reason
    )


def generate_llm_prompt(
    context: CustomerContext,
    customer: pd.Series,
    warehouse: WarehouseStatus
) -> str:
    """
    LLMに渡すプロンプトを生成
    コンテキストを全て渡して、最適なメールを生成してもらう
    """
    
    news_section = ""
    if context.matching_news:
        news_section = "\n## 関連ニュース\n"
        for n in context.matching_news[:2]:
            news_section += f"- {n['title']}: {n['summary']}\n"
    
    prompt = f"""
あなたはバリューブックスのメールライターです。
以下の状況を総合的に判断し、最適なメールを作成してください。

## 送信判断
- 推奨メールタイプ: {context.recommended_type.value}
- 判断理由: {context.recommendation_reason}

## 顧客情報
- 氏名: {customer['氏名']}
- 会員ランク: {customer['会員ランク']}
- 傾向: {customer['購入傾向']}
- 得意ジャンル: {customer['得意ジャンル']}
- 累計買取: {customer['累計買取回数']}回 / ¥{customer['累計買取金額']:,}
- 累計購入: {customer['累計購入回数']}回 / ¥{customer['累計購入金額']:,}
- 最終メール送信: {context.days_since_last_email}日前（{context.last_email_type}）

## 倉庫状況
- 緊急度: {warehouse.urgency_level}
- 閑散期: {len(warehouse.slack_days)}日間（{', '.join(warehouse.slack_days[:3])}...）
- 未査定バックログ: {warehouse.backlog_boxes}箱
- 20%UPキャンペーン: {'実施中' if warehouse.is_slack_period else '未実施'}
{news_section}
## メール種別ごとのトーン
- 緊急買取促進: 「本日限定！」「見逃せない！」など緊急感を出す
- 通常買取促進: 「そろそろ本の整理はいかがですか？」など自然なトーン
- 購入促進: 過去の購入傾向を踏まえ、おすすめ本を提案
- ニュース: 情報提供メイン、押し売り感なし

## 作成条件
1. 件名は20文字以内
2. 本文は200文字以内
3. 顧客の傾向に合わせたパーソナライズ
4. 送りすぎ感を出さない自然なトーン

## 出力形式
件名: [件名]
本文:
[本文]
"""
    return prompt


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║     🧠 バリューブックス スマートメーラー                     ║
║     倉庫状況×顧客履歴×ニュースを総合判断                    ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    today = datetime.now()
    
    # データ読み込み
    print("📊 データ読み込み中...")
    warehouse = load_warehouse_status()
    news = load_news()
    customers = pd.read_csv(os.path.join(DATA_DIR, 'customers_full.csv'))
    
    print(f"   顧客数: {len(customers)}名")
    print(f"   ニュース: {len(news)}件")
    
    # 倉庫状況サマリー
    print(f"\n{'='*60}")
    print("【倉庫状況】")
    print(f"{'='*60}")
    print(f"  📦 未査定バックログ: {warehouse.backlog_boxes}箱 ({warehouse.backlog_books}冊)")
    print(f"  📈 今日の予想到着: {warehouse.today_predicted}件")
    print(f"  ⚡ キャパシティ使用率: {warehouse.capacity_usage:.0%}")
    print(f"  🚨 緊急度: {warehouse.urgency_level}")
    
    if warehouse.is_slack_period:
        print(f"\n  ⚠️ 閑散期検出！")
        print(f"     該当日: {', '.join(warehouse.slack_days)}")
        print(f"     → 20%UPキャンペーン推奨")
    
    # 各顧客を分析
    print(f"\n{'='*60}")
    print("【顧客分析・メール判断】")
    print(f"{'='*60}")
    
    results = {
        EmailType.URGENT_KAITORI: [],
        EmailType.NORMAL_KAITORI: [],
        EmailType.PURCHASE: [],
        EmailType.NEWS: [],
        EmailType.SKIP: []
    }
    
    for _, customer in customers.iterrows():
        context = analyze_customer(customer, warehouse, news, today)
        results[context.recommended_type].append(context)
    
    # 結果サマリー
    print("\n📊 メールタイプ別 振り分け結果:")
    for email_type, contexts in results.items():
        emoji = {
            EmailType.URGENT_KAITORI: "🔴",
            EmailType.NORMAL_KAITORI: "🟡",
            EmailType.PURCHASE: "🟢",
            EmailType.NEWS: "🔵",
            EmailType.SKIP: "⚫"
        }.get(email_type, "")
        print(f"   {emoji} {email_type.value}: {len(contexts)}名")
    
    # 詳細表示
    print(f"\n{'='*60}")
    print("【詳細判断ログ】")
    print(f"{'='*60}")
    
    for email_type in [EmailType.URGENT_KAITORI, EmailType.NORMAL_KAITORI, EmailType.PURCHASE, EmailType.NEWS]:
        if results[email_type]:
            print(f"\n■ {email_type.value}")
            for ctx in results[email_type][:3]:  # 各タイプ3名まで表示
                print(f"   • {ctx.name}（{ctx.rank}）")
                print(f"     └ {ctx.recommendation_reason}")
    
    print(f"\n■ {EmailType.SKIP.value}")
    for ctx in results[EmailType.SKIP]:
        print(f"   • {ctx.name}: {ctx.recommendation_reason}")
    
    # LLMプロンプト例
    if results[EmailType.URGENT_KAITORI]:
        print(f"\n{'='*60}")
        print("【LLMプロンプト例（緊急買取促進）】")
        print(f"{'='*60}")
        
        sample_ctx = results[EmailType.URGENT_KAITORI][0]
        sample_customer = customers[customers['顧客ID'] == sample_ctx.customer_id].iloc[0]
        prompt = generate_llm_prompt(sample_ctx, sample_customer, warehouse)
        print(prompt)
    
    # 送信計画
    total_send = sum(len(v) for k, v in results.items() if k != EmailType.SKIP)
    
    print(f"\n{'='*60}")
    print("【本日の送信計画】")
    print(f"{'='*60}")
    print(f"   📧 送信予定: {total_send}通")
    print(f"   🚫 見送り: {len(results[EmailType.SKIP])}名")
    print(f"\n   20%UPキャンペーン対象日: {', '.join(warehouse.slack_days)}")


if __name__ == "__main__":
    main()

