"""
バリューブックス 統合メールシステム
倉庫状況 → 閑散期検出 → LLM総合判断 → GPT-4メール生成

使い方:
  export OPENAI_API_KEY="sk-..."
  streamlit run 08_email_optimizer/full_dashboard.py
"""

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from openai import OpenAI

# ページ設定
st.set_page_config(
    page_title="バリューブックス メールシステム",
    page_icon="📚",
    layout="wide"
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# カスタムCSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap');
    
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1e3a5f;
        margin-bottom: 0.5rem;
        font-family: 'Noto Sans JP', sans-serif;
    }
    .sub-header {
        color: #64748b;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: 600;
        color: #334155;
        margin: 1.5rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #e2e8f0;
    }
    .warehouse-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
    }
    .calendar-day {
        padding: 0.75rem;
        border-radius: 0.5rem;
        text-align: center;
        margin: 0.25rem;
    }
    .calendar-slack {
        background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
        color: white;
        border: 2px solid #d97706;
    }
    .calendar-normal {
        background: #f0fdf4;
        color: #166534;
        border: 1px solid #86efac;
    }
    .flow-box {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .flow-arrow {
        text-align: center;
        font-size: 1.5rem;
        color: #94a3b8;
        margin: 0.5rem 0;
    }
    .customer-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.25rem;
        border-radius: 1rem;
        color: white;
    }
    .email-preview {
        background: #ffffff;
        border: 2px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 1.5rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .email-subject {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e3a5f;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 0.75rem;
        margin-bottom: 1rem;
    }
    .email-body {
        font-size: 0.95rem;
        line-height: 1.8;
        color: #334155;
        white-space: pre-wrap;
    }
    .type-badge {
        display: inline-block;
        padding: 0.3rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 0.25rem;
    }
    .type-urgent { background: #fef2f2; color: #dc2626; border: 1px solid #fca5a5; }
    .type-normal { background: #fffbeb; color: #d97706; border: 1px solid #fcd34d; }
    .type-purchase { background: #f0fdf4; color: #16a34a; border: 1px solid #86efac; }
    .type-news { background: #eff6ff; color: #2563eb; border: 1px solid #93c5fd; }
    .type-skip { background: #f3f4f6; color: #6b7280; border: 1px solid #d1d5db; }
    .urgency-high { color: #dc2626; }
    .urgency-mid { color: #d97706; }
    .urgency-low { color: #16a34a; }
    .prompt-box {
        background: #1e1e1e;
        color: #d4d4d4;
        padding: 1rem;
        border-radius: 0.5rem;
        font-family: 'Monaco', 'Consolas', monospace;
        font-size: 0.8rem;
        white-space: pre-wrap;
        max-height: 400px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

# セッション状態
if 'generated_email' not in st.session_state:
    st.session_state.generated_email = None

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
            data['news'] = json.load(f).get('news_items', [])
    
    return data

def analyze_slack_periods(warehouse):
    """閑散期を分析"""
    forecast = warehouse.get('weekly_forecast', [])
    threshold = warehouse.get('thresholds', {}).get('閑散期_capacity_under', 0.45)
    return [d for d in forecast if d['capacity_usage'] < threshold]

def determine_urgency(warehouse):
    """緊急度を判定"""
    backlog = warehouse.get('backlog', {}).get('未査定_箱数', 150)
    slack_days = analyze_slack_periods(warehouse)
    
    if backlog < 100 and len(slack_days) >= 3:
        return "高", "urgency-high", "🔴"
    elif backlog < 150 and len(slack_days) >= 1:
        return "中", "urgency-mid", "🟡"
    else:
        return "低", "urgency-low", "🟢"

def determine_email_type(customer, warehouse, news, today):
    """メールタイプを判定"""
    last_email = datetime.strptime(customer['最終メール送信日'], '%Y-%m-%d')
    days_since = (today - last_email).days
    
    slack_days = analyze_slack_periods(warehouse)
    urgency, _, _ = determine_urgency(warehouse)
    activity = customer.get('購入傾向', '買取メイン')
    genre = customer.get('得意ジャンル', '')
    
    # マッチするニュース
    matching_news = [n for n in news if any(g in genre for g in n.get('related_genres', [])) or '全ジャンル' in n.get('related_genres', [])]
    
    if days_since < 7:
        return None, "送信間隔が短すぎる（7日未満）", "skip", matching_news
    elif days_since < 14 and urgency != "高":
        return None, f"もう少し間隔を空ける（{days_since}日経過）", "skip", matching_news
    elif urgency == "高" and activity in ['買取メイン', '両方活発']:
        return "緊急買取促進", f"閑散期{len(slack_days)}日間・緊急度高・買取傾向", "urgent", matching_news
    elif len(slack_days) > 0 and activity == '買取メイン':
        return "通常買取促進", "閑散期のため買取促進", "normal", matching_news
    elif activity == '購入メイン':
        if matching_news:
            return "購入促進", f"購入傾向・{matching_news[0]['title'][:15]}...", "purchase", matching_news
        return "購入促進", "購入傾向の顧客", "purchase", matching_news
    elif activity == '両方活発':
        if matching_news:
            return "ニュース", f"アクティブ顧客・ニュースあり", "news", matching_news
        return "通常買取促進", "アクティブ顧客", "normal", matching_news
    else:
        return "通常買取促進", "デフォルト", "normal", matching_news

def build_prompt(customer, email_type, reason, warehouse, matching_news):
    """LLMプロンプトを構築"""
    slack_days = analyze_slack_periods(warehouse)
    urgency, _, _ = determine_urgency(warehouse)
    backlog = warehouse.get('backlog', {})
    
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
- 緊急度: {urgency}
- 閑散期: {len(slack_days)}日間
- 未査定バックログ: {backlog.get('未査定_箱数', 0)}箱
- 20%UPキャンペーン: {'実施中' if len(slack_days) > 0 else '未実施'}
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

## 出力形式
件名: [件名]

本文:
[本文]"""
    
    return prompt

def generate_email_with_gpt(prompt):
    """GPT-4でメールを生成"""
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは古書店バリューブックスのプロのメールライターです。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content, None
    except Exception as e:
        return None, str(e)

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
    st.markdown('<p class="main-header">📚 バリューブックス 統合メールシステム</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">倉庫状況 → 閑散期検出 → LLM総合判断 → GPT-4メール生成</p>', unsafe_allow_html=True)
    
    # APIキー確認
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        st.error("⚠️ OPENAI_API_KEY が設定されていません")
        st.code("export OPENAI_API_KEY='sk-...'")
        return
    
    data = load_all_data()
    today = datetime.now()
    
    if 'warehouse' not in data:
        st.error("倉庫データがありません")
        return
    
    warehouse = data['warehouse']
    customers = data.get('customers', pd.DataFrame())
    news = data.get('news', [])
    
    # ========== Phase 1: 倉庫状況 ==========
    st.markdown('<p class="section-header">📦 Phase 1: 倉庫状況</p>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    backlog = warehouse.get('backlog', {})
    urgency, urgency_class, urgency_emoji = determine_urgency(warehouse)
    
    with col1:
        st.metric("未査定バックログ", f"{backlog.get('未査定_箱数', 0)}箱", f"{backlog.get('未査定_推定冊数', 0)}冊")
    with col2:
        st.metric("今日の予想到着", f"{warehouse.get('weekly_forecast', [{}])[0].get('predicted_arrivals', 0)}件")
    with col3:
        st.metric("キャパシティ使用率", f"{warehouse.get('weekly_forecast', [{}])[0].get('capacity_usage', 0):.0%}")
    with col4:
        st.metric("緊急度", f"{urgency_emoji} {urgency}")
    
    # ========== Phase 2: 閑散期検出 ==========
    st.markdown('<div class="flow-arrow">↓</div>', unsafe_allow_html=True)
    st.markdown('<p class="section-header">📅 Phase 2: 閑散期検出（向こう1週間）</p>', unsafe_allow_html=True)
    
    slack_days = analyze_slack_periods(warehouse)
    forecast = warehouse.get('weekly_forecast', [])
    
    cols = st.columns(7)
    for i, day in enumerate(forecast):
        with cols[i]:
            date_obj = datetime.strptime(day['date'], '%Y-%m-%d')
            is_slack = day['capacity_usage'] < warehouse.get('thresholds', {}).get('閑散期_capacity_under', 0.45)
            
            if is_slack:
                st.markdown(f"""
                <div class="calendar-day calendar-slack">
                    <div style="font-weight:bold;">{date_obj.strftime('%m/%d')}</div>
                    <div style="font-size:0.8rem;">{date_obj.strftime('%a')}</div>
                    <div style="font-size:1.2rem;">⚠️</div>
                    <div style="font-size:0.7rem;">20%UP推奨</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="calendar-day calendar-normal">
                    <div style="font-weight:bold;">{date_obj.strftime('%m/%d')}</div>
                    <div style="font-size:0.8rem;">{date_obj.strftime('%a')}</div>
                    <div style="font-size:1.2rem;">✅</div>
                    <div style="font-size:0.7rem;">{day['capacity_usage']:.0%}</div>
                </div>
                """, unsafe_allow_html=True)
    
    if slack_days:
        st.warning(f"⚠️ **{len(slack_days)}日間の閑散期を検出！** → 20%UPキャンペーン実施推奨")
    
    # ========== Phase 3: LLM総合判断 ==========
    st.markdown('<div class="flow-arrow">↓</div>', unsafe_allow_html=True)
    st.markdown('<p class="section-header">🧠 Phase 3: LLM総合判断</p>', unsafe_allow_html=True)
    
    # 顧客を分析
    results = {"urgent": [], "normal": [], "purchase": [], "news": [], "skip": []}
    
    for _, customer in customers.iterrows():
        email_type, reason, type_class, matching_news = determine_email_type(customer, warehouse, news, today)
        results[type_class].append({
            'customer': customer,
            'email_type': email_type if email_type else "見送り",
            'reason': reason,
            'type_class': type_class,
            'matching_news': matching_news
        })
    
    # サマリー
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f'<div class="type-badge type-urgent">🔴 緊急買取 {len(results["urgent"])}名</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="type-badge type-normal">🟡 通常買取 {len(results["normal"])}名</div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="type-badge type-purchase">🟢 購入促進 {len(results["purchase"])}名</div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="type-badge type-news">🔵 ニュース {len(results["news"])}名</div>', unsafe_allow_html=True)
    with col5:
        st.markdown(f'<div class="type-badge type-skip">⚫ 見送り {len(results["skip"])}名</div>', unsafe_allow_html=True)
    
    # ========== Phase 4: GPT-4メール生成 ==========
    st.markdown('<div class="flow-arrow">↓</div>', unsafe_allow_html=True)
    st.markdown('<p class="section-header">🤖 Phase 4: GPT-4メール生成</p>', unsafe_allow_html=True)
    
    # 送信対象リスト作成
    send_targets = []
    for type_class in ["urgent", "normal", "purchase", "news"]:
        send_targets.extend(results[type_class])
    
    if not send_targets:
        st.info("送信対象の顧客がいません")
        return
    
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.markdown("#### 👤 顧客を選択")
        
        customer_options = [f"{t['customer']['氏名']}（{t['customer']['会員ランク']}）- {t['email_type']}" for t in send_targets]
        selected_idx = st.selectbox("顧客", range(len(send_targets)), format_func=lambda x: customer_options[x], label_visibility="collapsed")
        
        selected = send_targets[selected_idx]
        c = selected['customer']
        
        # 顧客カード
        st.markdown(f"""
        <div class="customer-card">
            <h3 style="margin:0;color:white;">{c['氏名']}</h3>
            <p style="margin:0.25rem 0;opacity:0.9;">{c['会員ランク']}会員</p>
            <p style="margin:0;font-size:0.85rem;">📚 {c.get('得意ジャンル', 'N/A')}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"**傾向:** {c.get('購入傾向', 'N/A')}")
        st.markdown(f"**累計買取:** {c.get('累計買取回数', 0)}回 / ¥{c.get('累計買取金額', 0):,}")
        st.markdown(f"**累計購入:** {c.get('累計購入回数', 0)}回 / ¥{c.get('累計購入金額', 0):,}")
        
        st.markdown("---")
        
        type_badge = f"type-{selected['type_class']}"
        st.markdown(f'<span class="type-badge {type_badge}">{selected["email_type"]}</span>', unsafe_allow_html=True)
        st.markdown(f"<small style='color:#64748b;'>{selected['reason']}</small>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 生成ボタン
        if st.button("🤖 GPT-4でメール生成", type="primary", use_container_width=True):
            prompt = build_prompt(c, selected['email_type'], selected['reason'], warehouse, selected['matching_news'])
            
            with st.spinner("GPT-4で生成中..."):
                response, error = generate_email_with_gpt(prompt)
            
            if error:
                st.error(f"エラー: {error}")
            else:
                subject, body = parse_email_response(response)
                st.session_state.generated_email = {
                    'to': c['メールアドレス'],
                    'subject': subject,
                    'body': body,
                    'name': c['氏名'],
                    'type': selected['email_type']
                }
                st.rerun()
    
    with col_right:
        st.markdown("#### ✉️ 生成されたメール")
        
        if st.session_state.generated_email:
            email = st.session_state.generated_email
            
            st.markdown(f"""
            <div class="email-preview">
                <div style="color:#64748b;font-size:0.85rem;margin-bottom:0.5rem;">
                    To: {email['to']}
                </div>
                <div class="email-subject">
                    📧 {email['subject']}
                </div>
                <div class="email-body">{email['body']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("🔄 再生成", use_container_width=True):
                    st.session_state.generated_email = None
                    st.rerun()
            with col_b:
                if st.button("✅ 送信済みにする", use_container_width=True):
                    st.success(f"✅ {email['name']}様へのメールを送信済みにしました")
            
            # コピー用
            with st.expander("📋 テキストをコピー"):
                st.code(f"件名: {email['subject']}\n\n{email['body']}")
        
        else:
            st.markdown("""
            <div style="background:#f8fafc;padding:3rem;border-radius:1rem;text-align:center;color:#94a3b8;">
                <div style="font-size:3rem;margin-bottom:1rem;">📧</div>
                <p>顧客を選択して</p>
                <p><strong>「🤖 GPT-4でメール生成」</strong>を押してください</p>
            </div>
            """, unsafe_allow_html=True)
        
        # プロンプト確認
        with st.expander("🔍 LLMプロンプトを確認"):
            prompt = build_prompt(c, selected['email_type'], selected['reason'], warehouse, selected['matching_news'])
            st.markdown(f'<div class="prompt-box">{prompt}</div>', unsafe_allow_html=True)
    
    # フッター
    st.markdown("---")
    total = len(send_targets)
    st.success(f"📧 本日の送信予定: **{total}通** | 🚫 見送り: **{len(results['skip'])}名**")

if __name__ == "__main__":
    main()

