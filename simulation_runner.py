"""
バリューブックス メールシステム V2 シミュレーター
============================================================

様々な倉庫状況・顧客状況をシミュレートし、
システムの挙動を検証する

使い方:
  python simulation_runner.py
  python simulation_runner.py --scenario critical
  python simulation_runner.py --scenario relaxed
"""

import json
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict
import copy

# smart_mailer_v2からインポート
from smart_mailer_v2 import (
    WarehouseContext, CustomerProfile, EmailType, QualityTier,
    DailyVolumeCalculator, SmartTargetingEngine, ContextualContentGenerator,
    load_customers_v2, load_blog_data
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# シナリオ定義
# ============================================================

SCENARIOS = {
    "critical": {
        "name": "🚨 超緊急シナリオ（倉庫ガラガラ）",
        "description": "倉庫がほぼ空っぽ。誰でもいいから買取依頼を送りたい状況",
        "warehouse": {
            "backlog_boxes": 30,
            "backlog_books": 600,
            "capacity_usage": 0.12,
            "emergency_level": 5,
            "slack_days": ["2026-01-08", "2026-01-09", "2026-01-10", "2026-01-11", "2026-01-12", "2026-01-13", "2026-01-14"],
            "effective_capacity": 360
        },
        "config": {
            "email_budget_formula": {
                "base_daily_emails": 500,
                "emergency_multipliers": {"1": 0.5, "2": 0.8, "3": 1.0, "4": 1.5, "5": 2.5},
                "max_daily_emails": 2000,
                "min_daily_emails": 0
            }
        }
    },
    "emergency": {
        "name": "🔴 緊急シナリオ（やや空き）",
        "description": "倉庫にやや余裕。品質の良いユーザーに積極的に送信",
        "warehouse": {
            "backlog_boxes": 85,
            "backlog_books": 1700,
            "capacity_usage": 0.28,
            "emergency_level": 4,
            "slack_days": ["2026-01-08", "2026-01-09", "2026-01-10", "2026-01-11"],
            "effective_capacity": 360
        },
        "config": {
            "email_budget_formula": {
                "base_daily_emails": 500,
                "emergency_multipliers": {"1": 0.5, "2": 0.8, "3": 1.0, "4": 1.5, "5": 2.5},
                "max_daily_emails": 2000,
                "min_daily_emails": 0
            }
        }
    },
    "normal": {
        "name": "🟠 通常シナリオ（バランス運営）",
        "description": "標準的な倉庫状況。バランスを重視した送信",
        "warehouse": {
            "backlog_boxes": 150,
            "backlog_books": 3000,
            "capacity_usage": 0.50,
            "emergency_level": 3,
            "slack_days": ["2026-01-11", "2026-01-12"],
            "effective_capacity": 360
        },
        "config": {
            "email_budget_formula": {
                "base_daily_emails": 500,
                "emergency_multipliers": {"1": 0.5, "2": 0.8, "3": 1.0, "4": 1.5, "5": 2.5},
                "max_daily_emails": 2000,
                "min_daily_emails": 0
            }
        }
    },
    "relaxed": {
        "name": "🟢 余裕シナリオ（繁忙期）",
        "description": "倉庫が埋まっている。資産系メール中心で関係性構築",
        "warehouse": {
            "backlog_boxes": 220,
            "backlog_books": 4400,
            "capacity_usage": 0.75,
            "emergency_level": 2,
            "slack_days": [],
            "effective_capacity": 360
        },
        "config": {
            "email_budget_formula": {
                "base_daily_emails": 500,
                "emergency_multipliers": {"1": 0.5, "2": 0.8, "3": 1.0, "4": 1.5, "5": 2.5},
                "max_daily_emails": 2000,
                "min_daily_emails": 0
            }
        }
    },
    "packed": {
        "name": "🔵 満杯シナリオ（買取停止レベル）",
        "description": "倉庫パンク寸前。買取依頼は送らず購入促進のみ",
        "warehouse": {
            "backlog_boxes": 280,
            "backlog_books": 5600,
            "capacity_usage": 0.92,
            "emergency_level": 1,
            "slack_days": [],
            "effective_capacity": 360
        },
        "config": {
            "email_budget_formula": {
                "base_daily_emails": 500,
                "emergency_multipliers": {"1": 0.5, "2": 0.8, "3": 1.0, "4": 1.5, "5": 2.5},
                "max_daily_emails": 2000,
                "min_daily_emails": 0
            }
        }
    }
}


# ============================================================
# シミュレーション実行
# ============================================================

def run_simulation(scenario_key: str) -> Dict:
    """特定のシナリオでシミュレーションを実行"""
    
    if scenario_key not in SCENARIOS:
        print(f"❌ 不明なシナリオ: {scenario_key}")
        print(f"   利用可能: {', '.join(SCENARIOS.keys())}")
        return {}
    
    scenario = SCENARIOS[scenario_key]
    
    print(f"\n{'='*70}")
    print(f"  {scenario['name']}")
    print(f"  {scenario['description']}")
    print(f"{'='*70}\n")
    
    # 倉庫コンテキスト作成
    wh = scenario['warehouse']
    warehouse = WarehouseContext(
        backlog_boxes=wh['backlog_boxes'],
        backlog_books=wh['backlog_books'],
        capacity_usage=wh['capacity_usage'],
        emergency_level=wh['emergency_level'],
        slack_days=wh['slack_days'],
        effective_capacity=wh['effective_capacity']
    )
    
    # データ読み込み
    customers = load_customers_v2()
    blog_data = load_blog_data()
    
    # Phase 1: バジェット計算
    volume_calc = DailyVolumeCalculator(warehouse, scenario['config'])
    budget = volume_calc.calculate_budget()
    
    print("【倉庫状況】")
    emergency_emoji = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "🚨"}
    print(f"  📦 バックログ: {warehouse.backlog_boxes}箱")
    print(f"  ⚡ 使用率: {warehouse.capacity_usage:.0%}")
    print(f"  {emergency_emoji.get(warehouse.emergency_level, '')} 緊急度: Lv.{warehouse.emergency_level}")
    if warehouse.slack_days:
        print(f"  📅 閑散期: {len(warehouse.slack_days)}日間")
    
    print("\n【送信バジェット】")
    print(f"  計算: {budget['calculation']}")
    print(f"  総数: {budget['total_budget']}通")
    print(f"  ├─ 負債系: {budget['debt_budget']}通")
    print(f"  └─ 資産系: {budget['credit_budget']}通")
    
    # Phase 2: ターゲティング
    targeting = SmartTargetingEngine(warehouse, blog_data)
    decisions = targeting.build_priority_queue(customers, budget)
    
    # 統計集計
    stats = {
        'total_customers': len(customers),
        'total_budget': budget['total_budget'],
        'debt_budget': budget['debt_budget'],
        'credit_budget': budget['credit_budget'],
        'by_type': {},
        'by_tier': {},
        'by_balance': {'positive': 0, 'negative': 0, 'neutral': 0},
        'decisions': []
    }
    
    for d in decisions:
        # タイプ別集計
        type_label = d.email_type.label
        if type_label not in stats['by_type']:
            stats['by_type'][type_label] = {'count': 0, 'customers': []}
        stats['by_type'][type_label]['count'] += 1
        stats['by_type'][type_label]['customers'].append({
            'name': d.customer.name,
            'reason': d.reason,
            'priority': d.priority_score,
            'balance_before': d.customer.engagement_balance,
            'balance_after': d.balance_after
        })
        
        # ティア別集計
        tier = d.customer.quality_tier.code
        if tier not in stats['by_tier']:
            stats['by_tier'][tier] = 0
        if d.email_type != EmailType.SKIP:
            stats['by_tier'][tier] += 1
        
        # バランス変動集計
        if d.email_type != EmailType.SKIP:
            impact = d.email_type.balance_impact
            if impact > 0:
                stats['by_balance']['positive'] += 1
            elif impact < 0:
                stats['by_balance']['negative'] += 1
            else:
                stats['by_balance']['neutral'] += 1
        
        stats['decisions'].append({
            'customer_id': d.customer.customer_id,
            'name': d.customer.name,
            'email_type': d.email_type.label,
            'category': d.email_type.category,
            'priority': d.priority_score,
            'reason': d.reason,
            'quality_tier': d.customer.quality_tier.code,
            'balance_before': d.customer.engagement_balance,
            'balance_after': d.balance_after
        })
    
    # 結果表示
    print("\n【メールタイプ別 振り分け】")
    type_order = ['緊急買取促進', '通常買取促進', 'ポイントプレゼント', '有益情報・おすすめ', 
                  'ニュース・ストーリー', '感謝メッセージ', '購入促進', '送信見送り']
    
    for type_name in type_order:
        if type_name in stats['by_type']:
            count = stats['by_type'][type_name]['count']
            icon = "💸" if "買取" in type_name else "🎁" if type_name in ['ポイントプレゼント', '感謝メッセージ'] else "📝"
            print(f"  {icon} {type_name}: {count}名")
    
    print("\n【品質ティア別 送信数】")
    for tier in ['A', 'B', 'C', 'D']:
        count = stats['by_tier'].get(tier, 0)
        tier_info = {'A': '優良', 'B': '普通', 'C': '注意', 'D': '送らない'}
        bar = "█" * min(count, 20)
        print(f"  Tier {tier}（{tier_info[tier]}）: {bar} {count}名")
    
    print("\n【バランス変動】")
    print(f"  ↗ 資産系（バランス+）: {stats['by_balance']['positive']}名")
    print(f"  ↘ 負債系（バランス-）: {stats['by_balance']['negative']}名")
    print(f"  → 中立: {stats['by_balance']['neutral']}名")
    
    # 特筆すべきケース
    print("\n【注目ケース】")
    
    # ティアC/Dで送信対象になったケース
    cd_sends = [d for d in decisions 
                if d.email_type != EmailType.SKIP 
                and d.customer.quality_tier in [QualityTier.C, QualityTier.D]]
    if cd_sends:
        print("  ⚠️ 品質ティアC/Dへの送信（緊急時対応）:")
        for d in cd_sends[:3]:
            print(f"     • {d.customer.name}（ティア{d.customer.quality_tier.code}）→ {d.email_type.label}")
            print(f"       理由: {d.reason}")
    
    # バランスがマイナスで負債メールを送るケース
    neg_debt = [d for d in decisions 
                if d.email_type.category == 'debt' 
                and d.customer.engagement_balance < 0]
    if neg_debt:
        print("  ⚠️ バランスマイナスへの負債メール（要注意）:")
        for d in neg_debt[:3]:
            print(f"     • {d.customer.name}（バランス{d.customer.engagement_balance}）→ {d.email_type.label}")
            print(f"       理由: {d.reason}")
    
    # 高優先度の資産メール
    high_credit = [d for d in decisions 
                   if d.email_type.category == 'credit' 
                   and d.priority_score > 50]
    if high_credit:
        print("  🎁 高優先度の資産メール:")
        for d in high_credit[:3]:
            print(f"     • {d.customer.name}（スコア{d.priority_score:.1f}）→ {d.email_type.label}")
    
    return stats


def run_comparison():
    """全シナリオを比較"""
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  📊 シナリオ比較シミュレーション                                      ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║  各倉庫状況でシステムがどう振る舞うかを検証                           ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    results = {}
    
    for key in SCENARIOS.keys():
        print(f"\n{'#'*70}")
        results[key] = run_simulation(key)
    
    # 比較サマリー
    print(f"\n{'='*70}")
    print("【シナリオ比較サマリー】")
    print(f"{'='*70}\n")
    
    print(f"{'シナリオ':<12} {'バジェット':>10} {'負債系':>8} {'資産系':>8} {'見送り':>8}")
    print("-" * 50)
    
    for key, stats in results.items():
        scenario_name = key
        total = stats.get('total_budget', 0)
        debt = stats.get('debt_budget', 0)
        credit = stats.get('credit_budget', 0)
        skip = stats.get('by_type', {}).get('送信見送り', {}).get('count', 0)
        print(f"{scenario_name:<12} {total:>10}通 {debt:>8}通 {credit:>8}通 {skip:>8}名")
    
    print("\n📌 ポイント:")
    print("  • 緊急度が上がるほど、負債系（買取依頼）の比率が上昇")
    print("  • 余裕時は資産系（プレゼント）で関係性を構築")
    print("  • 品質ティアC/Dは緊急時のみ送信対象")


def run_single_customer_trace(customer_name: str = None):
    """特定顧客の判断プロセスを詳細トレース"""
    
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  🔍 顧客別 判断プロセス トレース                                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)
    
    customers = load_customers_v2()
    blog_data = load_blog_data()
    
    # 対象顧客を選択
    if customer_name:
        target = next((c for c in customers if customer_name in c.name), None)
        if not target:
            print(f"❌ 顧客が見つかりません: {customer_name}")
            return
    else:
        # ランダムに3名選択
        targets = customers[:3]
    
    for scenario_key in ['critical', 'normal', 'packed']:
        scenario = SCENARIOS[scenario_key]
        wh = scenario['warehouse']
        warehouse = WarehouseContext(**wh)
        
        print(f"\n{'='*70}")
        print(f"  {scenario['name']}")
        print(f"{'='*70}")
        
        targeting = SmartTargetingEngine(warehouse, blog_data)
        
        for customer in (targets if not customer_name else [target]):
            print(f"\n  👤 {customer.name}（{customer.rank}）")
            print(f"     品質ティア: {customer.quality_tier.tier_label}")
            print(f"     バランス: {customer.engagement_balance}")
            print(f"     傾向: {customer.activity_type}")
            
            # 判定プロセス
            can_solicit, reason = targeting.is_eligible_for_solicitation(customer)
            print(f"     📋 買取依頼可否: {'✅' if can_solicit else '❌'} {reason}")
            
            needs_credit, credit_reason = targeting.needs_credit_first(customer)
            print(f"     🎁 資産優先: {'はい' if needs_credit else 'いいえ'} - {credit_reason}")
            
            email_type, final_reason = targeting.determine_email_type(customer)
            print(f"     📧 最終判定: {email_type.label}")
            print(f"        └ {final_reason}")


# ============================================================
# メイン実行
# ============================================================

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  🧪 バリューブックス メールシステム V2 シミュレーター                 ║
╚══════════════════════════════════════════════════════════════════════╝

使い方:
  python simulation_runner.py                    # 全シナリオ比較
  python simulation_runner.py --scenario critical # 特定シナリオ
  python simulation_runner.py --trace            # 顧客別トレース
    """)
    
    args = sys.argv[1:]
    
    if '--scenario' in args:
        idx = args.index('--scenario')
        if idx + 1 < len(args):
            run_simulation(args[idx + 1])
        else:
            print("❌ シナリオ名を指定してください")
            print(f"   利用可能: {', '.join(SCENARIOS.keys())}")
    elif '--trace' in args:
        customer_name = None
        if len(args) > 1:
            idx = args.index('--trace')
            if idx + 1 < len(args):
                customer_name = args[idx + 1]
        run_single_customer_trace(customer_name)
    else:
        run_comparison()


if __name__ == "__main__":
    main()

