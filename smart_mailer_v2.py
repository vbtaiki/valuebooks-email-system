"""
バリューブックス インテリジェント・メールシステム V2
============================================================

🧠 コア・フィロソフィー（Emotional Balance）
- Solicitation = Debt（負債）: 買取お願いはユーザーへのストレス
- Giving = Credit（資産）: ポイント・有益情報・プレゼントは喜び
- 関係性バランスを維持しながら、倉庫状況に応じて最適なメールを送る

使い方:
  python smart_mailer_v2.py
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import os
import math

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# Enums & Data Classes
# ============================================================

class EmailType(Enum):
    """メールの種類（負債/資産の区分付き）"""
    # 負債系（Solicitation = Debt）
    URGENT_KAITORI = ("緊急買取促進", "debt", -15)
    NORMAL_KAITORI = ("通常買取促進", "debt", -8)
    
    # 資産系（Giving = Credit）
    GIFT_POINTS = ("ポイントプレゼント", "credit", +20)
    GIFT_INFO = ("有益情報・おすすめ", "credit", +10)
    NEWS_STORY = ("ニュース・ストーリー", "credit", +5)
    THANK_YOU = ("感謝メッセージ", "credit", +12)
    
    # 中立
    PURCHASE_PROMO = ("購入促進", "neutral", -3)
    SKIP = ("送信見送り", "neutral", 0)
    
    def __init__(self, label: str, category: str, balance_impact: int):
        self.label = label
        self.category = category
        self.balance_impact = balance_impact


class QualityTier(Enum):
    """ユーザー品質ティア"""
    A = ("A", "優良", 1.0)      # 常に送信OK
    B = ("B", "普通", 0.8)      # 通常送信OK
    C = ("C", "注意", 0.4)      # 緊急時のみ
    D = ("D", "送らない", 0.0)  # 超緊急時のみ
    
    def __init__(self, code: str, label: str, priority_weight: float):
        self.code = code
        self.tier_label = label
        self.priority_weight = priority_weight


@dataclass
class WarehouseContext:
    """倉庫の状況コンテキスト"""
    backlog_boxes: int
    backlog_books: int
    capacity_usage: float
    emergency_level: int  # 1-5
    slack_days: List[str]
    effective_capacity: int
    
    @property
    def is_emergency(self) -> bool:
        return self.emergency_level >= 4
    
    @property
    def is_critical(self) -> bool:
        return self.emergency_level == 5
    
    @property
    def is_relaxed(self) -> bool:
        return self.emergency_level <= 2


@dataclass
class CustomerProfile:
    """顧客プロファイル（V2拡張）"""
    customer_id: str
    name: str
    email: str
    rank: str
    
    # 取引履歴
    total_buyback_count: int
    total_buyback_amount: int
    total_purchase_count: int
    total_purchase_amount: int
    activity_type: str  # 買取メイン/購入メイン/両方活発
    genre: str
    
    # V2新規フィールド
    engagement_balance: int      # 関係性バランス（正=良好、負=送りすぎ）
    quality_tier: QualityTier    # 買取品質ティア
    last_solicitation: datetime  # 最後のお願い日
    last_gift: datetime          # 最後のプレゼント日
    rejection_rate: float        # 買取不可率
    
    # メール履歴
    days_since_last_email: int
    last_email_type: str
    open_rate: float
    response_rate: float


@dataclass
class EmailDecision:
    """メール送信決定"""
    customer: CustomerProfile
    email_type: EmailType
    priority_score: float
    reason: str
    content_elements: Dict
    balance_after: int


# ============================================================
# 1. Daily Volume Calculator
# ============================================================

class DailyVolumeCalculator:
    """
    その日の送信ボリュームを決定
    倉庫の空き具合 × 緊急度 → 送信バジェット
    """
    
    def __init__(self, warehouse: WarehouseContext, config: Dict):
        self.warehouse = warehouse
        self.config = config
    
    def calculate_budget(self) -> Dict:
        """送信バジェットを計算"""
        formula = self.config.get('email_budget_formula', {})
        base = formula.get('base_daily_emails', 500)
        multipliers = formula.get('emergency_multipliers', {})
        max_emails = formula.get('max_daily_emails', 2000)
        min_emails = formula.get('min_daily_emails', 0)
        
        # 基本計算: base × (1 - capacity_usage) × emergency_multiplier
        capacity_factor = 1 - self.warehouse.capacity_usage
        emergency_mult = multipliers.get(str(self.warehouse.emergency_level), 1.0)
        
        raw_budget = base * capacity_factor * emergency_mult
        
        # 丸めとクリッピング
        budget = int(min(max(raw_budget, min_emails), max_emails))
        
        # 内訳計算（負債系と資産系のバランス）
        if self.warehouse.is_critical:
            # 超緊急時: 負債系80%、資産系20%
            debt_ratio = 0.80
        elif self.warehouse.is_emergency:
            # 緊急時: 負債系60%、資産系40%
            debt_ratio = 0.60
        elif self.warehouse.is_relaxed:
            # 余裕時: 負債系20%、資産系80%
            debt_ratio = 0.20
        else:
            # 通常: 負債系40%、資産系60%
            debt_ratio = 0.40
        
        return {
            'total_budget': budget,
            'debt_budget': int(budget * debt_ratio),
            'credit_budget': int(budget * (1 - debt_ratio)),
            'capacity_factor': capacity_factor,
            'emergency_multiplier': emergency_mult,
            'emergency_level': self.warehouse.emergency_level,
            'calculation': f"{base} × {capacity_factor:.2f} × {emergency_mult} = {raw_budget:.0f}"
        }


# ============================================================
# 2. Smart Targeting Engine
# ============================================================

class SmartTargetingEngine:
    """
    関係性バランス × 品質スコア で優先順位付け
    """
    
    def __init__(self, warehouse: WarehouseContext, blog_data: Dict):
        self.warehouse = warehouse
        self.blog_data = blog_data
        self.today = datetime.now()
    
    def calculate_priority_score(self, customer: CustomerProfile) -> float:
        """
        優先度スコアを計算
        
        高スコア = 優先的に送信
        - 関係性バランスが高い（送りすぎていない）
        - 品質ティアが高い
        - 休眠期間が長い
        - 開封率が高い
        """
        score = 0.0
        
        # 1. 関係性バランス（-50〜+50 → 0〜100に正規化）
        balance_score = (customer.engagement_balance + 50) / 100 * 30
        score += max(0, min(30, balance_score))
        
        # 2. 品質ティア
        quality_score = customer.quality_tier.priority_weight * 25
        score += quality_score
        
        # 3. 休眠期間（長いほど優先）
        dormancy_score = min(customer.days_since_last_email / 60, 1.0) * 20
        score += dormancy_score
        
        # 4. 開封率・反応率
        engagement_score = (customer.open_rate * 0.5 + customer.response_rate * 0.5) * 15
        score += engagement_score
        
        # 5. 取引実績（LTV）
        ltv = customer.total_buyback_amount + customer.total_purchase_amount
        ltv_score = min(ltv / 500000, 1.0) * 10
        score += ltv_score
        
        return round(score, 2)
    
    def is_eligible_for_solicitation(self, customer: CustomerProfile) -> Tuple[bool, str]:
        """
        買取依頼（負債）を送ってよいか判定
        """
        # ティアDは超緊急時のみ
        if customer.quality_tier == QualityTier.D:
            if self.warehouse.is_critical:
                return True, "超緊急時のため例外的に送信対象"
            return False, "品質ティアD: 基本的に送信しない"
        
        # ティアCは緊急時のみ
        if customer.quality_tier == QualityTier.C:
            if self.warehouse.is_emergency:
                return True, "緊急時のため送信対象"
            return False, "品質ティアC: 緊急時以外は送信しない"
        
        # 関係性バランスがマイナス過ぎる場合
        if customer.engagement_balance < -20:
            return False, f"関係性バランス({customer.engagement_balance})が低すぎ"
        
        # 最終依頼から日が浅い
        days_since_solicitation = (self.today - customer.last_solicitation).days
        if days_since_solicitation < 14:
            if self.warehouse.is_critical:
                return True, "超緊急時のため間隔短くても送信"
            return False, f"最終依頼から{days_since_solicitation}日: 間隔が短い"
        
        return True, "送信可能"
    
    def needs_credit_first(self, customer: CustomerProfile) -> Tuple[bool, str]:
        """
        先に資産（プレゼント）を送るべきか判定
        """
        # バランスがマイナスなら資産を先に
        if customer.engagement_balance < 0:
            return True, f"バランス({customer.engagement_balance})がマイナス: 先にプレゼントを"
        
        # 最終プレゼントから長期間経過
        days_since_gift = (self.today - customer.last_gift).days
        if days_since_gift > 60:
            return True, f"最終プレゼントから{days_since_gift}日: 感謝を伝える時"
        
        return False, "バランス良好"
    
    def determine_email_type(self, customer: CustomerProfile) -> Tuple[EmailType, str]:
        """
        最適なメールタイプを決定
        """
        # 1. 送信間隔チェック（7日未満はスキップ）
        if customer.days_since_last_email < 7:
            return EmailType.SKIP, f"最終送信から{customer.days_since_last_email}日: 間隔が短い"
        
        # 2. 資産を先に送るべきか？
        needs_credit, credit_reason = self.needs_credit_first(customer)
        
        if needs_credit and not self.warehouse.is_critical:
            # 資産系メールを選択
            return self._select_credit_email(customer), credit_reason
        
        # 3. 買取依頼を送ってよいか？
        can_solicit, solicit_reason = self.is_eligible_for_solicitation(customer)
        
        if self.warehouse.is_emergency and customer.activity_type in ['買取メイン', '両方活発']:
            if can_solicit:
                if self.warehouse.is_critical:
                    return EmailType.URGENT_KAITORI, f"超緊急 + {solicit_reason}"
                return EmailType.URGENT_KAITORI, f"緊急 + {solicit_reason}"
        
        # 4. 顧客傾向に応じた通常選択
        if customer.activity_type == '購入メイン':
            return EmailType.PURCHASE_PROMO, "購入傾向の顧客"
        
        if can_solicit and len(self.warehouse.slack_days) > 0:
            return EmailType.NORMAL_KAITORI, f"閑散期のため買取促進"
        
        # 5. デフォルトは情報提供
        return self._select_credit_email(customer), "関係性維持のため情報提供"
    
    def _select_credit_email(self, customer: CustomerProfile) -> EmailType:
        """資産系メールを選択"""
        # バランスが大きくマイナスならポイントプレゼント
        if customer.engagement_balance < -15:
            return EmailType.GIFT_POINTS
        
        # 長期間感謝を伝えていないなら感謝メール
        days_since_gift = (self.today - customer.last_gift).days
        if days_since_gift > 90:
            return EmailType.THANK_YOU
        
        # それ以外は情報提供
        if customer.activity_type == '購入メイン':
            return EmailType.GIFT_INFO
        
        return EmailType.NEWS_STORY
    
    def build_priority_queue(self, customers: List[CustomerProfile], budget: Dict) -> List[EmailDecision]:
        """
        優先順位付きの送信リストを作成
        """
        decisions = []
        
        for customer in customers:
            email_type, reason = self.determine_email_type(customer)
            
            if email_type == EmailType.SKIP:
                decisions.append(EmailDecision(
                    customer=customer,
                    email_type=email_type,
                    priority_score=0,
                    reason=reason,
                    content_elements={},
                    balance_after=customer.engagement_balance
                ))
                continue
            
            priority = self.calculate_priority_score(customer)
            
            # 品質ティアによる重み付け
            priority *= customer.quality_tier.priority_weight
            
            # 緊急時は買取系を優先
            if self.warehouse.is_emergency and email_type.category == 'debt':
                priority *= 1.3
            
            balance_after = customer.engagement_balance + email_type.balance_impact
            
            decisions.append(EmailDecision(
                customer=customer,
                email_type=email_type,
                priority_score=priority,
                reason=reason,
                content_elements=self._build_content_elements(customer, email_type),
                balance_after=balance_after
            ))
        
        # 優先度でソート
        decisions.sort(key=lambda x: x.priority_score, reverse=True)
        
        # バジェットに応じてフィルタリング
        debt_count = 0
        credit_count = 0
        filtered = []
        
        for decision in decisions:
            if decision.email_type == EmailType.SKIP:
                filtered.append(decision)
                continue
            
            if decision.email_type.category == 'debt':
                if debt_count < budget['debt_budget']:
                    filtered.append(decision)
                    debt_count += 1
                else:
                    decision.email_type = EmailType.SKIP
                    decision.reason = "バジェット超過（負債系）"
                    filtered.append(decision)
            elif decision.email_type.category == 'credit':
                if credit_count < budget['credit_budget']:
                    filtered.append(decision)
                    credit_count += 1
                else:
                    decision.email_type = EmailType.SKIP
                    decision.reason = "バジェット超過（資産系）"
                    filtered.append(decision)
            else:
                # 中立系は通常通り
                if debt_count + credit_count < budget['total_budget']:
                    filtered.append(decision)
        
        return filtered
    
    def _build_content_elements(self, customer: CustomerProfile, email_type: EmailType) -> Dict:
        """コンテンツ要素を構築"""
        elements = {
            'personalization': {
                'name': customer.name,
                'rank': customer.rank,
                'genre': customer.genre
            },
            'relationship_context': self._get_relationship_context(customer),
            'offers': self._get_matching_offers(email_type),
            'stories': self._get_matching_stories(customer)
        }
        return elements
    
    def _get_relationship_context(self, customer: CustomerProfile) -> str:
        """関係性に応じたコンテキスト文"""
        balance = customer.engagement_balance
        days_since = customer.days_since_last_email
        
        if balance < -10:
            return "いつもご利用いただきありがとうございます。久しぶりのご連絡となり恐縮です。"
        elif days_since > 60:
            return f"大変ご無沙汰しております。{customer.name}様のことを思い出し、ご連絡いたしました。"
        elif balance > 20:
            return "いつも温かいご支援をいただき、心より感謝申し上げます。"
        else:
            return ""
    
    def _get_matching_offers(self, email_type: EmailType) -> List[Dict]:
        """現在のキャンペーンから適切なオファーを取得"""
        campaigns = self.blog_data.get('current_campaigns', [])
        offers = []
        
        for campaign in campaigns:
            # 負債系メールには買取キャンペーン
            if email_type.category == 'debt' and campaign.get('is_solicitation'):
                offers.append(campaign)
            # 資産系メールにはポイントキャンペーン
            elif email_type.category == 'credit' and not campaign.get('is_solicitation'):
                offers.append(campaign)
        
        return offers
    
    def _get_matching_stories(self, customer: CustomerProfile) -> List[Dict]:
        """ブログ記事から適切なストーリーを取得"""
        posts = self.blog_data.get('blog_posts', [])
        stories = []
        
        for post in posts:
            if post.get('use_in_email') and post.get('sentiment') == 'positive':
                stories.append({
                    'title': post['title'],
                    'summary': post['summary'],
                    'tone': post.get('tone', '')
                })
        
        return stories[:2]  # 最大2件


# ============================================================
# 3. Contextual Content Generator
# ============================================================

class ContextualContentGenerator:
    """
    メール本文を動的に生成
    ユーザーコンテキスト × オファー × ストーリー
    """
    
    def __init__(self, blog_data: Dict):
        self.blog_data = blog_data
    
    def generate_prompt(self, decision: EmailDecision) -> str:
        """LLMに渡すプロンプトを生成"""
        customer = decision.customer
        elements = decision.content_elements
        
        # 関係性に基づくトーン指示
        if customer.engagement_balance < -10:
            tone_instruction = "控えめで誠実なトーン。お願いの押し売り感を出さない。"
        elif customer.engagement_balance > 20:
            tone_instruction = "感謝と親しみを込めたトーン。信頼関係を大切に。"
        else:
            tone_instruction = "自然で温かみのあるトーン。"
        
        # オファー情報
        offers_text = ""
        if elements['offers']:
            offers_text = "\n## 現在のキャンペーン\n"
            for offer in elements['offers']:
                offers_text += f"- {offer['name']}: {offer['description']}\n"
        
        # ストーリー情報
        stories_text = ""
        if elements['stories']:
            stories_text = "\n## 最近のニュース（人間味を足すために活用可）\n"
            for story in elements['stories']:
                stories_text += f"- {story['title']}: {story['summary']}\n"
        
        # ギフト情報（資産系メールの場合）
        gift_text = ""
        if decision.email_type.category == 'credit':
            gifts = self.blog_data.get('gift_options', [])
            if gifts:
                gift_text = "\n## プレゼント候補\n"
                for gift in gifts[:2]:
                    gift_text += f"- {gift['name']}: {gift['description']}\n"
        
        prompt = f"""
あなたはバリューブックスのメールライターです。
「感情的貸借（Emotional Balance）」の考え方に基づき、ユーザーとの関係性を大切にしたメールを作成してください。

## メールタイプ
- 種別: {decision.email_type.label}
- カテゴリ: {decision.email_type.category}（{'負債=お願い' if decision.email_type.category == 'debt' else '資産=贈り物'}）
- 判断理由: {decision.reason}

## 顧客情報
- 氏名: {customer.name}
- 会員ランク: {customer.rank}
- 傾向: {customer.activity_type}
- 得意ジャンル: {customer.genre}
- 累計買取: {customer.total_buyback_count}回 / ¥{customer.total_buyback_amount:,}
- 累計購入: {customer.total_purchase_count}回 / ¥{customer.total_purchase_amount:,}

## 関係性の状態
- 現在のバランス: {customer.engagement_balance}（{'良好' if customer.engagement_balance > 0 else '要注意'}）
- 送信後のバランス: {decision.balance_after}
- 品質ティア: {customer.quality_tier.tier_label}

## 関係性コンテキスト
{elements['relationship_context']}
{offers_text}{stories_text}{gift_text}
## トーン指示
{tone_instruction}

## 作成条件
1. 件名は20文字以内
2. 本文は150〜200文字
3. {customer.name}様の名前を使う
4. 得意ジャンル（{customer.genre}）に自然に言及
5. 押し売り感を出さない

## 出力形式
件名: [件名]

本文:
[本文]
"""
        return prompt


# ============================================================
# Data Loaders
# ============================================================

def load_warehouse_v2() -> Tuple[WarehouseContext, Dict]:
    """V2倉庫データを読み込み"""
    path = os.path.join(DATA_DIR, 'warehouse_status_v2.json')
    if not os.path.exists(path):
        path = os.path.join(DATA_DIR, 'warehouse_status.json')
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    backlog = data.get('backlog', {})
    forecast = data.get('weekly_forecast', [])
    thresholds = data.get('thresholds', {})
    
    # 閑散期の日を特定
    slack_days = []
    for day in forecast:
        if day['capacity_usage'] < thresholds.get('閑散期_capacity_under', 0.35):
            slack_days.append(day['date'])
    
    today_forecast = forecast[0] if forecast else {}
    
    context = WarehouseContext(
        backlog_boxes=backlog.get('未査定_箱数', 0),
        backlog_books=backlog.get('未査定_推定冊数', 0),
        capacity_usage=today_forecast.get('capacity_usage', 0.5),
        emergency_level=data.get('emergency_level', 3),
        slack_days=slack_days,
        effective_capacity=data.get('warehouse_capacity', {}).get('effective_capacity', 360)
    )
    
    return context, data


def load_customers_v2() -> List[CustomerProfile]:
    """V2顧客データを読み込み"""
    path = os.path.join(DATA_DIR, 'customers_v2.csv')
    if not os.path.exists(path):
        path = os.path.join(DATA_DIR, 'customers_full.csv')
    
    df = pd.read_csv(path)
    customers = []
    
    for _, row in df.iterrows():
        # 品質ティアをEnumに変換
        tier_code = row.get('buyback_quality_tier', 'B')
        quality_tier = {
            'A': QualityTier.A,
            'B': QualityTier.B,
            'C': QualityTier.C,
            'D': QualityTier.D
        }.get(tier_code, QualityTier.B)
        
        # 日付のパース
        last_solicitation = datetime.strptime(
            row.get('last_solicitation_date', '2025-01-01'), '%Y-%m-%d'
        )
        last_gift = datetime.strptime(
            row.get('last_gift_date', '2025-01-01'), '%Y-%m-%d'
        )
        last_email = datetime.strptime(row['最終メール送信日'], '%Y-%m-%d')
        days_since = (datetime.now() - last_email).days
        
        customers.append(CustomerProfile(
            customer_id=row['顧客ID'],
            name=row['氏名'],
            email=row['メールアドレス'],
            rank=row['会員ランク'],
            total_buyback_count=row['累計買取回数'],
            total_buyback_amount=row['累計買取金額'],
            total_purchase_count=row['累計購入回数'],
            total_purchase_amount=row['累計購入金額'],
            activity_type=row['購入傾向'],
            genre=row['得意ジャンル'],
            engagement_balance=row.get('engagement_balance', 0),
            quality_tier=quality_tier,
            last_solicitation=last_solicitation,
            last_gift=last_gift,
            rejection_rate=row.get('rejection_rate', 0.1),
            days_since_last_email=days_since,
            last_email_type=row['最終メール種別'],
            open_rate=row['メール開封率'],
            response_rate=row['過去反応率']
        ))
    
    return customers


def load_blog_data() -> Dict:
    """ブログデータを読み込み"""
    path = os.path.join(DATA_DIR, 'dummy_blog_data.json')
    if not os.path.exists(path):
        return {'blog_posts': [], 'current_campaigns': [], 'gift_options': []}
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# Main Execution
# ============================================================

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  📚 バリューブックス インテリジェント・メールシステム V2              ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║  🧠 Emotional Balance: 関係性の貸借を管理                             ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    # データ読み込み
    print("📊 データ読み込み中...")
    warehouse, warehouse_config = load_warehouse_v2()
    customers = load_customers_v2()
    blog_data = load_blog_data()
    
    print(f"   顧客数: {len(customers)}名")
    print(f"   ブログ記事: {len(blog_data.get('blog_posts', []))}件")
    print(f"   キャンペーン: {len(blog_data.get('current_campaigns', []))}件")
    
    # ========== Phase 1: 倉庫状況 & バジェット計算 ==========
    print(f"\n{'='*70}")
    print("【Phase 1: 倉庫状況 & デイリーバジェット】")
    print(f"{'='*70}")
    
    volume_calc = DailyVolumeCalculator(warehouse, warehouse_config)
    budget = volume_calc.calculate_budget()
    
    emergency_emoji = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "🚨"}
    
    print(f"  📦 未査定バックログ: {warehouse.backlog_boxes}箱 ({warehouse.backlog_books}冊)")
    print(f"  ⚡ キャパシティ使用率: {warehouse.capacity_usage:.0%}")
    print(f"  🚨 緊急度: {emergency_emoji.get(warehouse.emergency_level, '')} Lv.{warehouse.emergency_level}")
    
    if warehouse.slack_days:
        print(f"  📅 閑散期: {len(warehouse.slack_days)}日間 ({', '.join(warehouse.slack_days[:3])}...)")
    
    print(f"\n  📧 本日の送信バジェット:")
    print(f"     計算式: {budget['calculation']}")
    print(f"     総数: {budget['total_budget']}通")
    print(f"     ├─ 負債系（買取依頼）: {budget['debt_budget']}通")
    print(f"     └─ 資産系（プレゼント）: {budget['credit_budget']}通")
    
    # ========== Phase 2: ターゲット抽出 ==========
    print(f"\n{'='*70}")
    print("【Phase 2: スマートターゲティング】")
    print(f"{'='*70}")
    
    targeting = SmartTargetingEngine(warehouse, blog_data)
    decisions = targeting.build_priority_queue(customers, budget)
    
    # 統計
    by_type = {}
    for d in decisions:
        key = d.email_type.label
        if key not in by_type:
            by_type[key] = []
        by_type[key].append(d)
    
    print("\n  📊 メールタイプ別 振り分け結果:")
    type_order = [
        EmailType.URGENT_KAITORI, EmailType.NORMAL_KAITORI,
        EmailType.GIFT_POINTS, EmailType.GIFT_INFO, EmailType.NEWS_STORY, EmailType.THANK_YOU,
        EmailType.PURCHASE_PROMO, EmailType.SKIP
    ]
    
    for et in type_order:
        count = len(by_type.get(et.label, []))
        if count > 0:
            category_icon = {"debt": "💸", "credit": "🎁", "neutral": "📝"}
            icon = category_icon.get(et.category, "")
            print(f"     {icon} {et.label}: {count}名")
    
    # ========== Phase 3: 詳細ログ ==========
    print(f"\n{'='*70}")
    print("【Phase 3: 送信対象詳細】")
    print(f"{'='*70}")
    
    send_targets = [d for d in decisions if d.email_type != EmailType.SKIP]
    
    for i, d in enumerate(send_targets[:10], 1):
        c = d.customer
        balance_change = d.email_type.balance_impact
        balance_arrow = "↗" if balance_change > 0 else "↘" if balance_change < 0 else "→"
        
        print(f"\n  [{i}] {c.name}（{c.rank}）")
        print(f"      メールタイプ: {d.email_type.label}")
        print(f"      理由: {d.reason}")
        print(f"      優先度スコア: {d.priority_score:.1f}")
        print(f"      品質ティア: {c.quality_tier.tier_label}")
        print(f"      バランス: {c.engagement_balance} {balance_arrow} {d.balance_after}")
    
    # ========== Phase 4: LLMプロンプト例 ==========
    if send_targets:
        print(f"\n{'='*70}")
        print("【Phase 4: LLMプロンプト例】")
        print(f"{'='*70}")
        
        content_gen = ContextualContentGenerator(blog_data)
        sample = send_targets[0]
        prompt = content_gen.generate_prompt(sample)
        
        print(f"\n  対象: {sample.customer.name}様（{sample.email_type.label}）")
        print("-" * 60)
        print(prompt[:1500] + "..." if len(prompt) > 1500 else prompt)
    
    # ========== サマリー ==========
    print(f"\n{'='*70}")
    print("【本日のサマリー】")
    print(f"{'='*70}")
    
    total_send = len(send_targets)
    skip_count = len([d for d in decisions if d.email_type == EmailType.SKIP])
    debt_send = len([d for d in send_targets if d.email_type.category == 'debt'])
    credit_send = len([d for d in send_targets if d.email_type.category == 'credit'])
    
    print(f"  📧 送信予定: {total_send}通")
    print(f"     ├─ 負債系: {debt_send}通（買取依頼）")
    print(f"     └─ 資産系: {credit_send}通（プレゼント・情報）")
    print(f"  🚫 見送り: {skip_count}名")
    print(f"  ⚖️ 平均バランス変動: {sum(d.email_type.balance_impact for d in send_targets) / max(len(send_targets), 1):.1f}")


if __name__ == "__main__":
    main()

