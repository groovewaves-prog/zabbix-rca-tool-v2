"""
Zabbix RCA Tool v2 - ホーム
マルチページ構成のエントリーポイント
"""

import streamlit as st
import json
import os
from datetime import datetime

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="Zabbix RCA Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== カスタムCSS ====================
st.markdown("""
<style>
    /* ヘッダー・フッター非表示 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* ワークフローカード */
    .workflow-card {
        padding: 25px;
        border-radius: 12px;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
        cursor: pointer;
        height: 200px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .workflow-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    }
    .card-builder {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    .card-config {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        color: white;
    }
    .card-rca {
        background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
        color: white;
    }
    .card-data {
        background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%);
        color: white;
    }
    .card-icon {
        font-size: 3em;
        margin-bottom: 15px;
    }
    .card-title {
        font-size: 1.3em;
        font-weight: bold;
        margin-bottom: 8px;
    }
    .card-desc {
        font-size: 0.9em;
        opacity: 0.9;
    }
    
    /* ステータスバッジ */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85em;
        margin: 2px;
    }
    .badge-ok { background: #d4edda; color: #155724; }
    .badge-warn { background: #fff3cd; color: #856404; }
    .badge-error { background: #f8d7da; color: #721c24; }
    .badge-info { background: #cce5ff; color: #004085; }
</style>
""", unsafe_allow_html=True)

# ==================== データディレクトリ ====================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def get_topology_status():
    """トポロジーデータの状態を取得"""
    topology_path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(topology_path):
        try:
            with open(topology_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"exists": True, "count": len(data), "data": data}
        except:
            pass
    return {"exists": False, "count": 0, "data": {}}

def get_config_status():
    """監視設定の状態を取得"""
    config_path = os.path.join(DATA_DIR, "zabbix_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {"exists": True, "data": data}
        except:
            pass
    return {"exists": False, "data": {}}

# ==================== メイン ====================
def main():
    # ヘッダー
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🔍 Zabbix RCA Tool")
        st.caption("トポロジーベースの根本原因分析ツール")
    with col2:
        st.markdown(f"""
        <div style="text-align: right; padding: 10px;">
            🟢 Online<br>
            <small>{datetime.now().strftime('%Y-%m-%d %H:%M')}</small>
        </div>
        """, unsafe_allow_html=True)
    
    st.divider()
    
    # ==================== ワークフロー概要 ====================
    st.subheader("📋 ワークフロー")
    
    st.markdown("""
    ```
    ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
    │  STEP 1     │      │  STEP 2     │      │  STEP 3     │
    │ トポロジー   │ ──▶  │ 監視設定    │ ──▶  │ 根本原因    │
    │ 作成        │      │ 生成        │      │ 分析        │
    └─────────────┘      └─────────────┘      └─────────────┘
    ```
    """)
    
    st.divider()
    
    # ==================== 機能カード ====================
    st.subheader("🚀 クイックアクセス")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="workflow-card card-builder">
            <div class="card-icon">🔧</div>
            <div class="card-title">トポロジービルダー</div>
            <div class="card-desc">デバイス・接続・冗長構成を<br>ウィザード形式で作成</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("開く", key="btn_builder", use_container_width=True):
            st.switch_page("pages/1_topology_builder.py")
    
    with col2:
        st.markdown("""
        <div class="workflow-card card-config">
            <div class="card-icon">⚙️</div>
            <div class="card-title">監視設定生成</div>
            <div class="card-desc">トポロジーから<br>Zabbix設定を自動生成</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("開く", key="btn_config", use_container_width=True):
            st.switch_page("pages/2_config_generator.py")
    
    with col3:
        st.markdown("""
        <div class="workflow-card card-rca">
            <div class="card-icon">🎯</div>
            <div class="card-title">根本原因分析</div>
            <div class="card-desc">大量アラートから<br>真因を特定</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("開く", key="btn_rca", use_container_width=True):
            st.switch_page("pages/3_rca_analyzer.py")
    
    with col4:
        st.markdown("""
        <div class="workflow-card card-data">
            <div class="card-icon">📁</div>
            <div class="card-title">データ管理</div>
            <div class="card-desc">インポート・エクスポート<br>履歴管理</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("開く", key="btn_data", use_container_width=True):
            st.switch_page("pages/4_data_manager.py")
    
    st.divider()
    
    # ==================== 現在の状態 ====================
    st.subheader("📊 現在の状態")
    
    topology_status = get_topology_status()
    config_status = get_config_status()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**🗺️ トポロジーデータ**")
        if topology_status["exists"]:
            st.markdown(f'<span class="status-badge badge-ok">✅ {topology_status["count"]}台のデバイス</span>', unsafe_allow_html=True)
            
            # レイヤー別カウント
            layers = {}
            for device in topology_status["data"].values():
                layer = device.get("layer", 0)
                layers[layer] = layers.get(layer, 0) + 1
            
            for layer in sorted(layers.keys()):
                st.caption(f"  └ Layer {layer}: {layers[layer]}台")
        else:
            st.markdown('<span class="status-badge badge-warn">⚠️ 未作成</span>', unsafe_allow_html=True)
            st.caption("トポロジービルダーで作成してください")
    
    with col2:
        st.markdown("**⚙️ 監視設定**")
        if config_status["exists"]:
            data = config_status["data"]
            summary = data.get("summary", {})
            st.markdown(f'<span class="status-badge badge-ok">✅ 生成済み</span>', unsafe_allow_html=True)
            st.caption(f"  └ ホスト: {summary.get('host_count', 0)}台")
            st.caption(f"  └ トリガー: {summary.get('trigger_count', 0)}個")
        else:
            st.markdown('<span class="status-badge badge-warn">⚠️ 未生成</span>', unsafe_allow_html=True)
            st.caption("トポロジー作成後に生成可能")
    
    with col3:
        st.markdown("**🎯 RCA分析**")
        st.markdown('<span class="status-badge badge-info">ℹ️ 待機中</span>', unsafe_allow_html=True)
        st.caption("アラートデータで分析可能")
    
    st.divider()
    
    # ==================== クイックスタートガイド ====================
    with st.expander("📖 クイックスタートガイド", expanded=False):
        st.markdown("""
        ### 🔧 Step 1: トポロジー作成
        
        1. **トポロジービルダー**を開く
        2. ウィザードに従ってデバイスを定義
           - デバイスID、タイプ、ベンダー、モデル
           - 電源モジュールなどの内部冗長構成
        3. 階層（Layer）を設定
        4. 接続関係（親子関係・マルチパス）を設定
        5. 冗長グループ（HA Pair、Stack等）を設定
        6. JSONをエクスポート
        
        ---
        
        ### ⚙️ Step 2: 監視設定生成
        
        1. **監視設定生成**を開く
        2. トポロジーを確認
        3. 「監視設定を生成」をクリック
        4. 生成された設定をプレビュー
           - ホストグループ
           - ホスト設定（テンプレート、タグ、マクロ）
           - トリガー
           - 依存関係
        5. JSONをダウンロードしてZabbixにインポート
        
        ---
        
        ### 🎯 Step 3: 根本原因分析
        
        1. **根本原因分析**を開く
        2. アラートデータを入力
           - サンプルデータ使用
           - JSONアップロード
           - 手動入力
        3. 「分析実行」をクリック
        4. 結果を確認
           - KPIカード（ノイズ削減率等）
           - Tier 1: 真因候補（要対応）
           - Tier 2: 要注意
           - Tier 3: 症状/波及（抑制済み）
        """)

if __name__ == "__main__":
    main()
