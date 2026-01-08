"""
バリューブックス インテリジェント・メールシステム V2 ダッシュボード
============================================================

🧠 Emotional Balance（感情的貸借）の可視化と操作

使い方:
  export OPENAI_API_KEY="sk-..."
  streamlit run 08_email_optimizer/dashboard_v2.py
"""

import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from openai import OpenAI

# ページ設定
st.set_page_config(
    page_title="メールシステム V2",
    page_icon="🧠",
    layout="wide"
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# カスタムCSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap');
    
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #1e3a5f 0%, #4a90a4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .philosophy-box {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        border-left: 4px solid #4a90a4;
        padding: 1.5rem;
        border-radius: 0 1rem 1rem 0;
        margin: 1rem 0;
    }
    .debt-badge {
        background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
        color: #dc2626;
        padding: 0.5rem 1rem;
        border-radius: 2rem;
        font-weight: 600;
        display: inline-block;
        margin: 0.25rem;
    }
    .credit-badge {
        background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
        color: #16a34a;
        padding: 0.5rem 1rem;
        border-radius: 2rem;
        font-weight: 600;
        display: inline-block;
        margin: 0.25rem;
    }
    .emergency-card {
        padding: 1.5rem;
        border-radius: 1rem;
        text-align: center;
        color: white;
        font-weight: 600;
    }
    .emergency-5 { background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); }
    .emergency-4 { background: linear-gradient(135deg, #ea580c 0%, #c2410c 100%); }
    .emergency-3 { background: linear-gradient(135deg, #d97706 0%, #b45309 100%); }
    .emergency-2 { background: linear-gradient(135deg, #65a30d 0%, #4d7c0f 100%); }
    .emergency-1 { background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%); }
    .budget-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
    }
    .customer-card {
        background: white;
        border: 2px solid #e2e8f0;
        border-radius: 1rem;
        padding: 1.25rem;
        margin: 0.5rem 0;
        transition: all 0.2s;
    }
    .customer-card:hover {
        border-color: #4a90a4;
        box-shadow: 0 4px 12px rgba(74, 144, 164, 0.15);
    }
    .balance-positive { color: #16a34a; font-weight: 600; }
    .balance-negative { color: #dc2626; font-weight: 600; }
    .tier-a { background: #dcfce7; color: #166534; padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.85rem; }
    .tier-b { background: #dbeafe; color: #1e40af; padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.85rem; }
    .tier-c { background: #fef3c7; color: #92400e; padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.85rem; }
    .tier-d { background: #fee2e2; color: #991b1b; padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.85rem; }
    .email-preview {
        background: white;
        border: 2px solid #e2e8f0;
        border-radius: 1rem;
        padding: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .prompt-box {
        background: #1e1e1e;
        color: #d4d4d4;
        padding: 1rem;
        border-radius: 0.75rem;
        font-family: 'Monaco', 'Consolas', monospace;
        font-size: 0.8rem;
        white-space: pre-wrap;
        max-height: 400px;
        overflow-y: auto;
    }
    .flow-step {
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
</style>
""", unsafe_allow_html=True)

# セッション状態
if 'generated_email' not in st.session_state:
    st.session_state.generated_email = None
if 'emergency_level' not in st.session_state:
    st.session_state.emergency_level = 4

def load_data():
    """データ読み込み"""
    data = {}
    
    # V2倉庫データ
    wh_path = os.path.join(DATA_DIR, 'warehouse_status_v2.json')
    if not os.path.exists(wh_path):
        wh_path = os.path.join(DATA_DIR, 'warehouse_status.json')
    with open(wh_path, 'r', encoding='utf-8') as f:
        data['warehouse'] = json.load(f)
    
    # V2顧客データ
    cust_path = os.path.join(DATA_DIR, 'customers_v2.csv')
    if not os.path.exists(cust_path):
        cust_path = os.path.join(DATA_DIR, 'customers_full.csv')
    data['customers'] = pd.read_csv(cust_path)
    
    # ブログデータ
    blog_path = os.path.join(DATA_DIR, 'dummy_blog_data.json')
    if os.path.exists(blog_path):
        with open(blog_path, 'r', encoding='utf-8') as f:
            data['blog'] = json.load(f)
    else:
        data['blog'] = {'blog_posts': [], 'current_campaigns': [], 'gift_options': []}
    
    return data

def calculate_budget(emergency_level: int, capacity_usage: float) -> dict:
    """バジェット計算"""
    base = 500
    multipliers = {1: 0.5, 2: 0.8, 3: 1.0, 4: 1.5, 5: 2.5}
    
    capacity_factor = 1 - capacity_usage
    emergency_mult = multipliers.get(emergency_level, 1.0)
    
    raw_budget = base * capacity_factor * emergency_mult
    budget = int(min(max(raw_budget, 0), 2000))
    
    # 負債/資産比率
    debt_ratios = {1: 0.20, 2: 0.20, 3: 0.40, 4: 0.60, 5: 0.80}
    debt_ratio = debt_ratios.get(emergency_level, 0.40)
    
    return {
        'total': budget,
        'debt': int(budget * debt_ratio),
        'credit': int(budget * (1 - debt_ratio)),
        'formula': f"{base} × {capacity_factor:.2f} × {emergency_mult} = {raw_budget:.0f}"
    }

def analyze_customer(row, emergency_level):
    """顧客分析"""
    today = datetime.now()
    last_email = datetime.strptime(row['最終メール送信日'], '%Y-%m-%d')
    days_since = (today - last_email).days
    
    balance = row.get('engagement_balance', 0)
    tier = row.get('buyback_quality_tier', 'B')
    activity = row.get('購入傾向', '買取メイン')
    
    # メールタイプ決定
    if days_since < 7:
        return None, "間隔が短い", "skip"
    
    # ティアによるフィルタリング
    if tier == 'D' and emergency_level < 5:
        return None, "ティアD: 超緊急時のみ", "skip"
    if tier == 'C' and emergency_level < 4:
        return None, "ティアC: 緊急時のみ", "skip"
    
    # バランスがマイナスなら資産優先
    if balance < -10 and emergency_level < 5:
        return "🎁 ポイントプレゼント", f"バランス({balance})がマイナス", "credit"
    
    # 緊急時は買取優先
    if emergency_level >= 4 and activity in ['買取メイン', '両方活発']:
        if emergency_level == 5:
            return "🚨 緊急買取促進", "超緊急モード", "debt"
        return "💸 買取促進", f"緊急度{emergency_level}", "debt"
    
    # 購入傾向
    if activity == '購入メイン':
        return "🛒 購入促進", "購入傾向の顧客", "neutral"
    
    # デフォルトは情報提供
    return "📰 ニュース", "関係性維持", "credit"

def generate_email_prompt(customer, email_type, reason, warehouse, blog):
    """プロンプト生成"""
    balance = customer.get('engagement_balance', 0)
    
    campaigns = blog.get('current_campaigns', [])
    campaigns_text = "\n".join([f"- {c['name']}: {c['description']}" for c in campaigns[:2]]) if campaigns else "なし"
    
    stories = [p for p in blog.get('blog_posts', []) if p.get('use_in_email')]
    stories_text = "\n".join([f"- {s['title']}: {s['summary'][:50]}..." for s in stories[:2]]) if stories else "なし"
    
    # トーン指示
    if balance < -10:
        tone = "控えめで誠実なトーン。お願いの押し売り感を出さない。"
    elif balance > 20:
        tone = "感謝と親しみを込めたトーン。"
    else:
        tone = "自然で温かみのあるトーン。"
    
    prompt = f"""あなたはバリューブックスのメールライターです。
「感情的貸借（Emotional Balance）」の考え方を重視してください。

## メールタイプ
- 種別: {email_type}
- 判断理由: {reason}

## 顧客情報
- 氏名: {customer['氏名']}
- 会員ランク: {customer['会員ランク']}
- 傾向: {customer.get('購入傾向', 'N/A')}
- 得意ジャンル: {customer.get('得意ジャンル', 'N/A')}
- 累計買取: {customer.get('累計買取回数', 0)}回 / ¥{customer.get('累計買取金額', 0):,}

## 関係性の状態
- 現在のバランス: {balance}（{'良好' if balance > 0 else '要注意'}）
- 品質ティア: {customer.get('buyback_quality_tier', 'B')}

## 現在のキャンペーン
{campaigns_text}

## 最近のニュース
{stories_text}

## トーン指示
{tone}

## 作成条件
1. 件名は20文字以内
2. 本文は150〜200文字
3. 顧客名を使う
4. 得意ジャンルに自然に言及

## 出力形式
件名: [件名]

本文:
[本文]"""
    
    return prompt

def generate_with_gpt(prompt, api_key=None):
    """GPT-4でメール生成"""
    try:
        client = OpenAI(api_key=api_key) if api_key else OpenAI()
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

def parse_email(response):
    """メールをパース"""
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
    st.markdown('<p class="main-header">🧠 インテリジェント・メールシステム V2</p>', unsafe_allow_html=True)
    
    # 哲学の説明
    st.markdown("""
    <div class="philosophy-box">
        <strong>Emotional Balance（感情的貸借）の考え方</strong><br>
        <span class="debt-badge">💸 負債 = 買取お願い</span>
        <span class="credit-badge">🎁 資産 = プレゼント・有益情報</span>
        <br><br>
        ユーザーとの関係性を「貸借」として管理。負債が溜まったら資産で返済し、信頼関係を維持します。
    </div>
    """, unsafe_allow_html=True)
    
    # APIキー確認（環境変数 or Streamlit secrets）
    api_key = None
    
    # 1. 環境変数から取得
    api_key = os.environ.get('OPENAI_API_KEY')
    
    # 2. Streamlit secretsから取得
    if not api_key:
        try:
            if 'OPENAI_API_KEY' in st.secrets:
                api_key = st.secrets['OPENAI_API_KEY']
        except Exception:
            pass
    
    if not api_key:
        st.warning("⚠️ OPENAI_API_KEY が設定されていません。メール生成機能は使用できません。")
    
    data = load_data()
    warehouse = data['warehouse']
    customers = data['customers']
    blog = data['blog']
    
    # ========== サイドバー: 緊急度コントロール ==========
    st.sidebar.markdown("## ⚡ 緊急度コントロール")
    
    emergency_level = st.sidebar.slider(
        "倉庫の緊急度",
        min_value=1, max_value=5,
        value=st.session_state.emergency_level,
        help="1=余裕あり → 5=超緊急"
    )
    st.session_state.emergency_level = emergency_level
    
    emergency_labels = {
        1: "🟢 余裕あり",
        2: "🟡 やや余裕",
        3: "🟠 標準",
        4: "🔴 緊急",
        5: "🚨 超緊急"
    }
    
    st.sidebar.markdown(f"### {emergency_labels[emergency_level]}")
    
    emergency_desc = {
        1: "倉庫満杯。買取依頼は送らず、関係性構築を優先。",
        2: "やや余裕。資産系メール中心。",
        3: "標準運営。バランスを重視。",
        4: "やや緊急。買取依頼を増やす。",
        5: "超緊急！誰でもいいから送る。"
    }
    st.sidebar.info(emergency_desc[emergency_level])
    
    # キャパシティ使用率
    capacity_usage = warehouse.get('weekly_forecast', [{}])[0].get('capacity_usage', 0.5)
    
    # ========== メインコンテンツ ==========
    
    # Phase 1: バジェット計算
    st.markdown("### 📊 Phase 1: 本日の送信バジェット")
    
    budget = calculate_budget(emergency_level, capacity_usage)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="emergency-card emergency-{emergency_level}">
            <div style="font-size:2rem;">Lv.{emergency_level}</div>
            <div>緊急度</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="budget-card">
            <div style="font-size:2rem;">{budget['total']}</div>
            <div>送信バジェット</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.metric("💸 負債系（買取依頼）", f"{budget['debt']}通")
    
    with col4:
        st.metric("🎁 資産系（プレゼント）", f"{budget['credit']}通")
    
    st.caption(f"計算式: {budget['formula']}")
    
    st.markdown('<div class="flow-arrow">↓</div>', unsafe_allow_html=True)
    
    # Phase 2: ターゲティング
    st.markdown("### 🎯 Phase 2: スマートターゲティング")
    
    # 顧客を分析
    results = []
    for _, row in customers.iterrows():
        email_type, reason, category = analyze_customer(row, emergency_level)
        results.append({
            'customer': row,
            'email_type': email_type if email_type else "⚫ 見送り",
            'reason': reason,
            'category': category
        })
    
    # 統計表示
    send_targets = [r for r in results if r['category'] != 'skip']
    debt_targets = [r for r in results if r['category'] == 'debt']
    credit_targets = [r for r in results if r['category'] == 'credit']
    skip_targets = [r for r in results if r['category'] == 'skip']
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📧 送信対象", f"{len(send_targets)}名")
    col2.metric("💸 負債系", f"{len(debt_targets)}名")
    col3.metric("🎁 資産系", f"{len(credit_targets)}名")
    col4.metric("⚫ 見送り", f"{len(skip_targets)}名")
    
    st.markdown('<div class="flow-arrow">↓</div>', unsafe_allow_html=True)
    
    # Phase 3: 顧客選択 & メール生成
    st.markdown("### ✉️ Phase 3: メール生成")
    
    if not send_targets:
        st.info("送信対象の顧客がいません。緊急度を上げてみてください。")
        return
    
    col_left, col_right = st.columns([1, 2])
    
    with col_left:
        st.markdown("#### 👤 顧客を選択")
        
        customer_options = [
            f"{r['customer']['氏名']}（{r['customer']['会員ランク']}）- {r['email_type']}"
            for r in send_targets
        ]
        
        selected_idx = st.selectbox(
            "送信対象",
            range(len(send_targets)),
            format_func=lambda x: customer_options[x],
            label_visibility="collapsed"
        )
        
        selected = send_targets[selected_idx]
        c = selected['customer']
        
        # 顧客詳細
        balance = c.get('engagement_balance', 0)
        tier = c.get('buyback_quality_tier', 'B')
        
        balance_class = "balance-positive" if balance >= 0 else "balance-negative"
        tier_class = f"tier-{tier.lower()}"
        
        st.markdown(f"""
        <div class="customer-card">
            <h3 style="margin:0;">{c['氏名']}</h3>
            <p style="color:#64748b;margin:0.5rem 0;">{c['会員ランク']}会員</p>
            <p><span class="{tier_class}">ティア{tier}</span></p>
            <p>バランス: <span class="{balance_class}">{balance:+d}</span></p>
            <p style="font-size:0.85rem;color:#64748b;">
                📚 {c.get('得意ジャンル', 'N/A')}<br>
                傾向: {c.get('購入傾向', 'N/A')}
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"**判定:** {selected['email_type']}")
        st.caption(f"理由: {selected['reason']}")
        
        st.markdown("---")
        
        # 生成ボタン
        if api_key:
            if st.button("🤖 GPT-4でメール生成", type="primary", use_container_width=True):
                prompt = generate_email_prompt(c, selected['email_type'], selected['reason'], warehouse, blog)
                
                with st.spinner("生成中..."):
                    response, error = generate_with_gpt(prompt, api_key)
                    
                    if error:
                        st.error(f"エラー: {error}")
                    else:
                        subject, body = parse_email(response)
                        st.session_state.generated_email = {
                            'to': c['メールアドレス'],
                            'name': c['氏名'],
                            'subject': subject,
                            'body': body,
                            'type': selected['email_type'],
                            'prompt': prompt
                        }
                        st.rerun()
        else:
            st.button("🤖 GPT-4でメール生成", disabled=True, use_container_width=True)
            st.caption("APIキーを設定してください")
    
    with col_right:
        st.markdown("#### ✉️ 生成されたメール")
        
        if st.session_state.generated_email:
            email = st.session_state.generated_email
            
            st.markdown(f"""
            <div class="email-preview">
                <div style="color:#64748b;font-size:0.85rem;margin-bottom:0.75rem;">
                    To: {email['to']} | タイプ: {email['type']}
                </div>
                <div style="font-size:1.1rem;font-weight:600;color:#1e3a5f;border-bottom:1px solid #e2e8f0;padding-bottom:0.75rem;margin-bottom:1rem;">
                    📧 {email['subject']}
                </div>
                <div style="font-size:0.95rem;line-height:1.8;color:#334155;white-space:pre-wrap;">
{email['body']}
                </div>
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
            
            # プロンプト確認
            with st.expander("🔍 LLMプロンプトを確認"):
                st.markdown(f'<div class="prompt-box">{email["prompt"]}</div>', unsafe_allow_html=True)
            
            # コピー用
            with st.expander("📋 テキストをコピー"):
                st.code(f"件名: {email['subject']}\n\n{email['body']}")
        
        else:
            st.markdown("""
            <div style="background:#f8fafc;padding:3rem;border-radius:1rem;text-align:center;color:#94a3b8;">
                <div style="font-size:3rem;margin-bottom:1rem;">✉️</div>
                <p>顧客を選択して</p>
                <p><strong>「🤖 GPT-4でメール生成」</strong>を押してください</p>
            </div>
            """, unsafe_allow_html=True)
    
    # ========== 全顧客一覧 ==========
    st.markdown("---")
    st.markdown("### 📋 全顧客の判定結果")
    
    with st.expander("一覧を表示"):
        for r in results:
            c = r['customer']
            balance = c.get('engagement_balance', 0)
            tier = c.get('buyback_quality_tier', 'B')
            
            icon = "💸" if r['category'] == 'debt' else "🎁" if r['category'] == 'credit' else "⚫"
            balance_color = "#16a34a" if balance >= 0 else "#dc2626"
            
            st.markdown(f"""
            <div style="display:flex;align-items:center;padding:0.5rem;border-bottom:1px solid #e2e8f0;">
                <div style="width:40px;font-size:1.2rem;">{icon}</div>
                <div style="flex:1;">
                    <strong>{c['氏名']}</strong>
                    <span style="color:#64748b;font-size:0.85rem;margin-left:0.5rem;">
                        {c['会員ランク']} | ティア{tier}
                    </span>
                </div>
                <div style="width:100px;text-align:right;color:{balance_color};font-weight:600;">
                    {balance:+d}
                </div>
                <div style="width:200px;text-align:right;color:#64748b;font-size:0.85rem;">
                    {r['reason']}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # フッター
    st.markdown("---")
    st.caption("🧠 Emotional Balance System V2 | バリューブックス")

if __name__ == "__main__":
    main()

