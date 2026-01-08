"""
バリューブックス メール配信最適化システム
目標申込件数から、最適な顧客を抽出しパーソナライズメールを生成

使い方:
  python optimizer.py
"""

import pandas as pd
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Tuple
import os

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class ConversionRate:
    """ランク別のメール→申込 転換率"""
    platinum: float = 0.025   # 2.5% (プラチナ会員は反応しやすい)
    gold: float = 0.015       # 1.5%
    silver: float = 0.008     # 0.8%
    bronze: float = 0.003     # 0.3%
    
    def get_rate(self, rank: str) -> float:
        rates = {
            'プラチナ': self.platinum,
            'ゴールド': self.gold,
            'シルバー': self.silver,
            'ブロンズ': self.bronze
        }
        return rates.get(rank, 0.005)


def load_customers() -> pd.DataFrame:
    """顧客データを読み込む"""
    return pd.read_csv(os.path.join(DATA_DIR, 'customers_email.csv'))


def calculate_customer_score(row: pd.Series, today: datetime) -> float:
    """
    顧客スコアを計算（高いほどメール効果が期待できる）
    
    スコア要素:
    - 過去の反応率（高いほど良い）
    - 休眠日数（適度に休眠している人が狙い目）
    - 累計買取金額（高額顧客は再購入期待）
    - 最終メール送信からの日数（送りすぎは避ける）
    """
    score = 0
    
    # 過去の反応率（重み: 40%）
    score += row['過去反応率'] * 40
    
    # 休眠日数スコア（30〜90日が最適、重み: 25%）
    dormant_days = row['休眠日数']
    if 30 <= dormant_days <= 90:
        score += 25  # 最適ゾーン
    elif 15 <= dormant_days < 30:
        score += 15  # やや早い
    elif 90 < dormant_days <= 180:
        score += 18  # やや遅いが効果あり
    else:
        score += 5   # 効果薄い
    
    # 累計買取金額（重み: 20%）
    if row['累計買取金額'] >= 300000:
        score += 20
    elif row['累計買取金額'] >= 150000:
        score += 15
    elif row['累計買取金額'] >= 50000:
        score += 10
    else:
        score += 5
    
    # 最終メール送信からの日数（重み: 15%）
    # 21日以上経過していれば送信OK
    last_email = datetime.strptime(row['最終メール送信日'], '%Y-%m-%d')
    days_since_email = (today - last_email).days
    if days_since_email >= 30:
        score += 15
    elif days_since_email >= 21:
        score += 10
    elif days_since_email >= 14:
        score += 5
    else:
        score -= 10  # 送りすぎペナルティ
    
    return score


def extract_target_customers(
    df: pd.DataFrame,
    target_applications: int,
    conversion_rates: ConversionRate,
    today: datetime
) -> Tuple[pd.DataFrame, dict]:
    """
    目標申込件数を達成するために必要な顧客を抽出
    
    Returns:
        (抽出された顧客DF, 計算結果の詳細)
    """
    # 各顧客のスコアと期待転換率を計算
    df = df.copy()
    df['スコア'] = df.apply(lambda row: calculate_customer_score(row, today), axis=1)
    df['期待転換率'] = df['会員ランク'].apply(conversion_rates.get_rate)
    
    # スコアの高い順にソート
    df = df.sort_values('スコア', ascending=False)
    
    # 目標達成に必要な顧客数を計算
    cumulative_expected = 0
    selected_indices = []
    
    for idx, row in df.iterrows():
        if cumulative_expected >= target_applications:
            break
        cumulative_expected += row['期待転換率']
        selected_indices.append(idx)
    
    selected_df = df.loc[selected_indices]
    
    # 結果サマリー
    summary = {
        '目標申込件数': target_applications,
        '選定顧客数': len(selected_df),
        '期待申込件数': round(selected_df['期待転換率'].sum() * len(selected_df), 1),
        'ランク別内訳': selected_df['会員ランク'].value_counts().to_dict(),
        '平均スコア': round(selected_df['スコア'].mean(), 1)
    }
    
    return selected_df, summary


def generate_email_prompt(customer: pd.Series, campaign_type: str = "20%UP") -> str:
    """
    LLMに渡すプロンプトを生成
    
    顧客の過去データを基に、パーソナライズされたメール文面を作成するためのプロンプト
    """
    prompt = f"""
あなたはバリューブックスのメールライターです。
以下の顧客データを基に、買取促進メールを作成してください。

## 顧客情報
- 氏名: {customer['氏名']}
- 会員ランク: {customer['会員ランク']}
- 累計買取回数: {customer['累計買取回数']}回
- 累計買取金額: ¥{customer['累計買取金額']:,}
- 最終買取日: {customer['最終買取日']}
- 得意ジャンル: {customer['得意ジャンル']}
- 平均買取冊数: {customer['平均買取冊数']}冊
- 休眠日数: {customer['休眠日数']}日

## キャンペーン内容
- 買取金額{campaign_type}キャンペーン
- 本日限定

## 作成条件
1. 件名は20文字以内
2. 本文は200文字以内
3. 顧客の得意ジャンルに言及する
4. 過去の買取実績に感謝を示す
5. 休眠日数に応じたトーン調整:
   - 30日未満: 軽いトーン
   - 30-90日: 「お久しぶりです」トーン
   - 90日以上: 「ぜひまた」トーン

## 出力形式
件名: [件名]
本文:
[本文]
"""
    return prompt


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║     📧 バリューブックス メール配信最適化システム             ║
║     最小限のメールで最大の効果を                             ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # データ読み込み
    customers = load_customers()
    today = datetime.now()
    conversion_rates = ConversionRate()
    
    print(f"📊 顧客データ読み込み完了: {len(customers)}名")
    print(f"📅 本日: {today.strftime('%Y-%m-%d')}")
    print(f"\n{'='*60}")
    
    # 目標申込件数を入力
    print("\n【目標設定】")
    try:
        target = int(input("今日増加させたい申込件数を入力: "))
    except ValueError:
        target = 100
        print(f"  → デフォルト値 {target} 件を使用")
    
    # 顧客抽出
    print(f"\n{'='*60}")
    print("【顧客抽出中...】")
    
    selected, summary = extract_target_customers(
        customers, target, conversion_rates, today
    )
    
    print(f"\n✅ 抽出完了!")
    print(f"\n📋 抽出結果サマリー")
    print(f"{'='*60}")
    print(f"  目標申込件数: {summary['目標申込件数']} 件")
    print(f"  → 必要メール送信数: {summary['選定顧客数']} 通")
    print(f"  → 期待申込件数: {summary['期待申込件数']} 件")
    print(f"\n  ランク別内訳:")
    for rank, count in summary['ランク別内訳'].items():
        print(f"    {rank}: {count}名")
    print(f"\n  平均スコア: {summary['平均スコア']}")
    
    # 抽出された顧客一覧
    print(f"\n{'='*60}")
    print("【抽出顧客リスト（上位10名）】")
    print(f"{'='*60}")
    
    display_cols = ['顧客ID', '氏名', '会員ランク', '休眠日数', 'スコア', '期待転換率']
    print(selected[display_cols].head(10).to_string(index=False))
    
    # LLMプロンプト例
    print(f"\n{'='*60}")
    print("【LLM用プロンプト例（1名分）】")
    print(f"{'='*60}")
    
    sample_customer = selected.iloc[0]
    prompt = generate_email_prompt(sample_customer)
    print(prompt)
    
    # 抽出クエリの説明
    print(f"\n{'='*60}")
    print("【使用した抽出ロジック】")
    print(f"{'='*60}")
    print("""
    スコア計算式:
    ┌─────────────────────────────────────────────────────────┐
    │ スコア = 過去反応率 × 40                                │
    │        + 休眠日数スコア（30-90日が最適）× 25            │
    │        + 累計買取金額スコア × 20                        │
    │        + メール送信間隔スコア（21日以上推奨）× 15       │
    └─────────────────────────────────────────────────────────┘
    
    転換率（メール→申込）:
    ┌─────────────────────────────────────────────────────────┐
    │ プラチナ: 2.5%  ゴールド: 1.5%                          │
    │ シルバー: 0.8%  ブロンズ: 0.3%                          │
    └─────────────────────────────────────────────────────────┘
    """)
    
    # CSVに書き出し
    output_path = os.path.join(DATA_DIR, 'today_targets.csv')
    selected.to_csv(output_path, index=False)
    print(f"\n💾 抽出結果を保存しました: {output_path}")
    
    # 次のステップ
    print(f"\n{'='*60}")
    print("【次のステップ】")
    print(f"{'='*60}")
    print("""
    1. today_targets.csv を確認
    2. 各顧客のプロンプトをLLM（Claude/GPT）に渡す
    3. 生成されたメールを確認・送信
    
    💡 ヒント: 
    このスクリプトをCursorのAPIと連携すれば、
    メール生成まで自動化できます！
    """)


if __name__ == "__main__":
    main()

