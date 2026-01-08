"""
バリューブックス スマートメール ダッシュボード
倉庫状況・閑散期予測・顧客分析・LLMプロンプトを一画面で確認

使い方:
  streamlit run 08_email_optimizer/smart_dashboard.py
"""

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime, timedelta

# ページ設定
st.set_page_config(
    page_title="スマートメーラー",
    page_icon="🧠",
    layout="wide"
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# カスタムCSS
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 1rem;
    }
    .status-card {
        padding: 1rem;
        border-radius: 0.75rem;
        margin-bottom: 1rem;
    }
    .email-type-box {
        padding: 0.75rem;
        border-radius: 0.5rem;
        margin: 0.25rem 0;
    }
    .type-urgent { background: #fef2f2; border-left: 4px solid #ef4444; }
    .type-normal { background: #fffbeb; border-left: 4px solid #f59e0b; }
    .type-purchase { background: #f0fdf4; border-left: 4px solid #22c55e; }
    .type-news { background: #eff6ff; border-left: 4px solid #3b82f6; }
    .type-skip { background: #f3f4f6; border-left: 4px solid #9ca3af; }
    .prompt-box {
        background: #1e1e1e;
        color: #d4d4d4;
        padding: 1rem;
        border-radius: 0.5rem;
        font-family: 'Monaco', 'Consolas', monospace;
        font-size: 0.85rem;
        white-space: pre-wrap;
        max-height: 500px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

def load_all_data():
    """全データを読み込む"""
    data = {}
    
    warehouse_path = os.path.join(DATA_DIR, 'warehouse_status.json')
    if os.path.exists(warehouse_path):
        with open(warehouse_path, 'r', encoding='utf-8') as f:
            data['warehouse'] = json.load(f)
    
    customers_path = os.path.join(DATA_DIR, 'customers_full.csv')
    if os.path.exists(customers_path):
        data['customers'] = pd.read_csv(customers_path)
    else:
        customers_path = os.path.join(DATA_DIR, 'customers_email.csv')
        if os.path.exists(customers_path):
            data['customers'] = pd.read_csv(customers_path)
    
    news_path = os.path.join(DATA_DIR, 'recent_news.json')
    if os.path.exists(news_path):
        with open(news_path, 'r', encoding='utf-8') as f:
            data['news'] = json.load(f)
    
    return data

def analyze_slack_periods(warehouse_data):
    """閑散期を分析"""
    forecast = warehouse_data.get('weekly_forecast', [])
    threshold = warehouse_data.get('thresholds', {}).get('閑散期_capacity_under', 0.45)
    
    slack_days = []
    for day in forecast:
        if day['capacity_usage'] < threshold:
            slack_days.append({
                'date': day['date'],
                'usage': day['capacity_usage'],
                'predicted': day['predicted_arrivals']
            })
    
    return slack_days

def determine_urgency(warehouse_data):
    """緊急度を判定"""
    backlog = warehouse_data.get('backlog', {}).get('未査定_箱数', 0)
    slack_days = analyze_slack_periods(warehouse_data)
    
    if backlog < 100 and len(slack_days) >= 3:
        return "高", "🔴"
    elif backlog < 150 and len(slack_days) >= 1:
        return "中", "🟡"
    else:
        return "低", "🟢"

def analyze_customer_email_type(customer, warehouse_data, news_items, today):
    """顧客のメールタイプを判定"""
    last_email = datetime.strptime(customer['最終メール送信日'], '%Y-%m-%d')
    days_since = (today - last_email).days
    
    slack_days = analyze_slack_periods(warehouse_data)
    urgency, _ = determine_urgency(warehouse_data)
    activity = customer.get('購入傾向', '買取メイン')
    last_type = customer.get('最終メール種別', '')
    genre = customer.get('得意ジャンル', '')
    
    # マッチするニュースを検索
    matching_news = []
    for n in news_items:
        if any(g in genre for g in n.get('related_genres', [])) or '全ジャンル' in n.get('related_genres', []):
            matching_news.append(n)
    
    if days_since < 7:
        return "見送り", "送信間隔が短すぎる（7日未満）", matching_news
    elif days_since < 14 and urgency != "高":
        return "見送り", "もう少し間隔を空けたい（14日未満）", matching_news
    elif urgency == "高" and activity in ['買取メイン', '両方活発']:
        return "緊急買取促進", f"閑散期{len(slack_days)}日間・緊急度高・買取傾向", matching_news
    elif len(slack_days) > 0 and activity == '買取メイン':
        if last_type != '買取促進':
            return "通常買取促進", f"閑散期あり・前回は{last_type}→買取促進に切替", matching_news
        else:
            return "通常買取促進", "閑散期のため買取促進を継続", matching_news
    elif activity == '購入メイン':
        return "購入促進", "購入傾向の顧客に購入促進", matching_news
    elif activity == '両方活発':
        if matching_news:
            return "ニュース", f"アクティブ顧客にニュース（{matching_news[0]['title'][:15]}...）", matching_news
        else:
            return "通常買取促進", "アクティブ顧客・閑散期のため買取促進", matching_news
    else:
        return "通常買取促進", "デフォルト", matching_news

def generate_llm_prompt(customer, email_type, reason, warehouse_data, matching_news):
    """LLMプロンプトを生成"""
    slack_days = analyze_slack_periods(warehouse_data)
    urgency, _ = determine_urgency(warehouse_data)
    backlog = warehouse_data.get('backlog', {})
    
    news_section = ""
    if matching_news:
        news_section = "\n## 関連ニュース\n"
        for n in matching_news[:2]:
            news_section += f"- {n['title']}: {n['summary']}\n"
    
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
- 最終メール: {customer['最終メール送信日']}（{customer.get('最終メール種別', 'N/A')}）

## 倉庫状況
- 緊急度: {urgency}
- 閑散期: {len(slack_days)}日間
- 未査定バックログ: {backlog.get('未査定_箱数', 0)}箱
- 20%UPキャンペーン: {'実施中' if len(slack_days) > 0 else '未実施'}
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
[本文]"""
    
    return prompt

def main():
    st.markdown('<p class="main-header">🧠 スマートメーラー ダッシュボード</p>', unsafe_allow_html=True)
    
    data = load_all_data()
    today = datetime.now()
    
    if 'warehouse' not in data:
        st.error("倉庫データがありません")
        return
    
    warehouse = data['warehouse']
    customers = data.get('customers', pd.DataFrame())
    news_items = data.get('news', {}).get('news_items', [])
    
    # ========== 上部: 倉庫状況 ==========
    st.markdown("## 📦 倉庫状況")
    
    col1, col2, col3, col4 = st.columns(4)
    
    backlog = warehouse.get('backlog', {})
    with col1:
        st.metric("未査定", f"{backlog.get('未査定_箱数', 0)}箱", 
                  delta=f"{backlog.get('未査定_推定冊数', 0)}冊")
    
    with col2:
        today_pred = warehouse.get('weekly_forecast', [{}])[0].get('predicted_arrivals', 0)
        st.metric("今日の予想到着", f"{today_pred}件")
    
    with col3:
        capacity = warehouse.get('weekly_forecast', [{}])[0].get('capacity_usage', 0)
        st.metric("キャパシティ使用率", f"{capacity:.0%}")
    
    with col4:
        urgency, emoji = determine_urgency(warehouse)
        st.metric("緊急度", f"{emoji} {urgency}")
    
    # ========== 閑散期カレンダー ==========
    st.markdown("---")
    st.markdown("## 📅 向こう1週間の予測 & 20%UPキャンペーン推奨日")
    
    slack_days = analyze_slack_periods(warehouse)
    forecast = warehouse.get('weekly_forecast', [])
    
    cols = st.columns(7)
    for i, day in enumerate(forecast):
        with cols[i]:
            date_obj = datetime.strptime(day['date'], '%Y-%m-%d')
            is_slack = day['capacity_usage'] < warehouse.get('thresholds', {}).get('閑散期_capacity_under', 0.45)
            
            if is_slack:
                st.markdown(f"""
                <div style="background: #fef3c7; padding: 0.75rem; border-radius: 0.5rem; text-align: center; border: 2px solid #f59e0b;">
                    <div style="font-weight: bold; color: #92400e;">{date_obj.strftime('%m/%d')}</div>
                    <div style="font-size: 0.8rem; color: #b45309;">({date_obj.strftime('%a')})</div>
                    <div style="font-size: 1.2rem; margin: 0.5rem 0;">⚠️</div>
                    <div style="font-size: 0.75rem; color: #92400e;">閑散期</div>
                    <div style="font-size: 0.7rem; color: #92400e;">20%UP推奨</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: #f0fdf4; padding: 0.75rem; border-radius: 0.5rem; text-align: center;">
                    <div style="font-weight: bold; color: #166534;">{date_obj.strftime('%m/%d')}</div>
                    <div style="font-size: 0.8rem; color: #15803d;">({date_obj.strftime('%a')})</div>
                    <div style="font-size: 1.2rem; margin: 0.5rem 0;">✅</div>
                    <div style="font-size: 0.75rem; color: #166534;">通常</div>
                    <div style="font-size: 0.7rem; color: #166534;">{day['capacity_usage']:.0%}</div>
                </div>
                """, unsafe_allow_html=True)
    
    if slack_days:
        st.warning(f"⚠️ **{len(slack_days)}日間の閑散期を検出！** 20%UPキャンペーンの実施を推奨します。")
    
    # ========== メール判断結果 ==========
    st.markdown("---")
    st.markdown("## 📧 メール送信判断")
    
    if not customers.empty:
        results = {"緊急買取促進": [], "通常買取促進": [], "購入促進": [], "ニュース": [], "見送り": []}
        
        for _, customer in customers.iterrows():
            email_type, reason, matching_news = analyze_customer_email_type(customer, warehouse, news_items, today)
            results[email_type].append({
                'customer': customer,
                'reason': reason,
                'matching_news': matching_news
            })
        
        # サマリー
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.markdown(f"""
            <div class="email-type-box type-urgent">
                <strong>🔴 緊急買取</strong><br>
                <span style="font-size: 1.5rem;">{len(results['緊急買取促進'])}名</span>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="email-type-box type-normal">
                <strong>🟡 通常買取</strong><br>
                <span style="font-size: 1.5rem;">{len(results['通常買取促進'])}名</span>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="email-type-box type-purchase">
                <strong>🟢 購入促進</strong><br>
                <span style="font-size: 1.5rem;">{len(results['購入促進'])}名</span>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
            <div class="email-type-box type-news">
                <strong>🔵 ニュース</strong><br>
                <span style="font-size: 1.5rem;">{len(results['ニュース'])}名</span>
            </div>
            """, unsafe_allow_html=True)
        
        with col5:
            st.markdown(f"""
            <div class="email-type-box type-skip">
                <strong>⚫ 見送り</strong><br>
                <span style="font-size: 1.5rem;">{len(results['見送り'])}名</span>
            </div>
            """, unsafe_allow_html=True)
        
        # タブ
        tab1, tab2, tab3, tab4 = st.tabs(["📋 送信対象リスト", "🤖 LLMプロンプト確認", "📰 最新ニュース", "🔍 顧客検索"])
        
        with tab1:
            for email_type in ["緊急買取促進", "通常買取促進", "購入促進", "ニュース"]:
                if results[email_type]:
                    st.markdown(f"### {email_type}")
                    for item in results[email_type]:
                        c = item['customer']
                        st.markdown(f"- **{c['氏名']}**（{c['会員ランク']}）: {item['reason']}")
        
        with tab2:
            st.markdown("### 🤖 LLMに渡すプロンプトを確認")
            st.markdown("顧客を選択すると、その顧客用に生成されるLLMプロンプトが表示されます。")
            
            # 送信対象の顧客リストを作成
            send_targets = []
            for email_type in ["緊急買取促進", "通常買取促進", "購入促進", "ニュース"]:
                for item in results[email_type]:
                    send_targets.append({
                        'customer': item['customer'],
                        'email_type': email_type,
                        'reason': item['reason'],
                        'matching_news': item['matching_news']
                    })
            
            if send_targets:
                # 顧客選択
                customer_options = [f"{t['customer']['氏名']}（{t['customer']['会員ランク']}）- {t['email_type']}" for t in send_targets]
                selected_idx = st.selectbox("顧客を選択", range(len(send_targets)), format_func=lambda x: customer_options[x])
                
                selected = send_targets[selected_idx]
                c = selected['customer']
                
                st.markdown("---")
                
                # 顧客情報サマリー
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.markdown("#### 顧客情報")
                    st.markdown(f"**{c['氏名']}**")
                    st.markdown(f"ランク: {c['会員ランク']}")
                    st.markdown(f"傾向: {c.get('購入傾向', 'N/A')}")
                    st.markdown(f"ジャンル: {c.get('得意ジャンル', 'N/A')}")
                    
                    st.markdown("#### 判断結果")
                    st.info(f"📧 **{selected['email_type']}**")
                    st.markdown(f"理由: {selected['reason']}")
                
                with col2:
                    st.markdown("#### LLMプロンプト")
                    prompt = generate_llm_prompt(
                        c, 
                        selected['email_type'], 
                        selected['reason'], 
                        warehouse, 
                        selected['matching_news']
                    )
                    st.markdown(f'<div class="prompt-box">{prompt}</div>', unsafe_allow_html=True)
                    
                    # コピーボタン
                    st.code(prompt, language="markdown")
            else:
                st.info("送信対象の顧客がいません")
        
        with tab3:
            st.markdown("### 最新ニュース")
            for n in news_items:
                st.markdown(f"""
                <div style="background: #f8fafc; padding: 1rem; border-radius: 0.5rem; margin: 0.5rem 0;">
                    <strong>{n['title']}</strong><br>
                    <small style="color: #64748b;">{n['date']} | {n['category']} | {n['action_type']}</small><br>
                    {n['summary']}<br>
                    <small>関連ジャンル: {', '.join(n['related_genres'])}</small>
                </div>
                """, unsafe_allow_html=True)
        
        with tab4:
            search_name = st.text_input("顧客名で検索")
            if search_name:
                matched = customers[customers['氏名'].str.contains(search_name, na=False)]
                if not matched.empty:
                    for _, c in matched.iterrows():
                        email_type, reason, matching_news = analyze_customer_email_type(c, warehouse, news_items, today)
                        
                        st.markdown(f"### {c['氏名']}（{c['会員ランク']}）")
                        st.markdown(f"**判断: {email_type}** - {reason}")
                        
                        with st.expander("🤖 LLMプロンプトを表示"):
                            prompt = generate_llm_prompt(c, email_type, reason, warehouse, matching_news)
                            st.code(prompt, language="markdown")
    
    # フッター
    st.markdown("---")
    total_send = sum(len(v) for k, v in results.items() if k != "見送り") if not customers.empty else 0
    st.success(f"📧 本日の送信予定: **{total_send}通** | 🚫 見送り: **{len(results.get('見送り', []))}名**")

if __name__ == "__main__":
    main()
