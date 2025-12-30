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
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* ワークフローステップ */
    .workflow-container {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 15px;
        padding: 25px;
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 16px;
        margin: 10px 0;
    }
    .workflow-step {
        text-align: center;
        padding: 25px 35px;
        background: white;
        border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        min-width: 160px;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .workflow-step:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.12);
    }
    .step-icon {
        font-size: 2.2em;
        margin-bottom: 10px;
    }
    .step-number {
        font-weight: bold;
        font-size: 0.85em;
        margin-bottom: 5px;
    }
    .step-title {
        font-size: 1em;
        color: #333;
    }
    .step1 .step-number { color: #667eea; }
    .step2 .step-number { color: #11998e; }
    .step3 .step-number { color: #eb3349; }
    .workflow-arrow {
        font-size: 1.8em;
        color: #adb5bd;
    }
</style>
""", unsafe_allow_html=True)

# ==================== データディレクトリ ====================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def get_topology_status():
    """トポロジーデータの状態を取得"""
    topology_path = os.path.join(DATA_DIR, "topology.json")
    full_topology_path = os.path.join(DATA_DIR, "full_topology.json")
    
    result = {
        "exists": False, 
        "count": 0, 
        "data": {},
        "filename": None,
        "full_exists": False
    }
    
    if os.path.exists(topology_path):
        try:
            with open(topology_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                result["exists"] = True
                result["count"] = len(data)
                result["data"] = data
                result["filename"] = "topology.json"
        except:
            pass
    
    if os.path.exists(full_topology_path):
        result["full_exists"] = True
        result["full_filename"] = "full_topology.json"
    
    return result

def get_config_status():
    """監視設定の状態を取得"""
    config_path = os.path.join(DATA_DIR, "zabbix_config.json")
    
    result = {"exists": False, "data": {}, "filename": None}
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                result["exists"] = True
                result["data"] = data
                result["filename"] = "zabbix_config.json"
        except:
            pass
    
    return result

def get_alerts_status():
    """アラートデータの状態を取得"""
    alerts_path = os.path.join(DATA_DIR, "alerts.json")
    
    result = {"exists": False, "count": 0, "filename": None}
    
    if os.path.exists(alerts_path):
        try:
            with open(alerts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                alerts = data.get("alerts", data) if isinstance(data, dict) else data
                result["exists"] = True
                result["count"] = len(alerts) if isinstance(alerts, list) else 0
                result["filename"] = "alerts.json"
        except:
            pass
    
    return result

# ==================== メイン ====================
def main():
    # ヘッダー
    st.title("🔍 Zabbix RCA Tool")
    st.caption("トポロジーベースの根本原因分析ツール")
    
    st.divider()
    
    # ==================== ワークフロー ====================
    st.subheader("📋 ワークフロー")
    
    st.markdown("""
    <div class="workflow-container">
        <div class="workflow-step step1">
            <div class="step-icon">🔧</div>
            <div class="step-number">STEP 1</div>
            <div class="step-title">トポロジー作成</div>
        </div>
        <div class="workflow-arrow">→</div>
        <div class="workflow-step step2">
            <div class="step-icon">⚙️</div>
            <div class="step-number">STEP 2</div>
            <div class="step-title">監視設定生成</div>
        </div>
        <div class="workflow-arrow">→</div>
        <div class="workflow-step step3">
            <div class="step-icon">🎯</div>
            <div class="step-number">STEP 3</div>
            <div class="step-title">根本原因分析</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    # ==================== クイックアクセス ====================
    st.subheader("🚀 クイックアクセス")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🔧 トポロジービルダー\n\nデバイス・接続・冗長構成を\nウィザード形式で作成", 
                     key="btn_builder", use_container_width=True, type="primary"):
            st.switch_page("pages/1_topology_builder.py")
    
    with col2:
        if st.button("⚙️ 監視設定生成\n\nトポロジーから\nZabbix設定を自動生成", 
                     key="btn_config", use_container_width=True, type="primary"):
            st.switch_page("pages/2_config_generator.py")
    
    with col3:
        if st.button("🎯 根本原因分析\n\n大量アラートから\n真因を特定", 
                     key="btn_rca", use_container_width=True, type="primary"):
            st.switch_page("pages/3_rca_analyzer.py")
    
    with col4:
        if st.button("📁 データ管理\n\nインポート・エクスポート\n履歴管理", 
                     key="btn_data", use_container_width=True):
            st.switch_page("pages/4_data_manager.py")
    
    st.divider()
    
    # ==================== 現在の状態 ====================
    st.subheader("📊 現在の状態")
    
    topology_status = get_topology_status()
    config_status = get_config_status()
    alerts_status = get_alerts_status()
    
    col1, col2, col3 = st.columns(3)
    
    # トポロジーデータ
    with col1:
        with st.container(border=True):
            st.markdown("**🗺️ トポロジーデータ**")
            
            if topology_status["exists"]:
                st.success(f"✅ 読み込み済み")
                st.code(f"📄 {topology_status['filename']}", language=None)
                st.markdown(f"**デバイス数:** {topology_status['count']}台")
                
                # レイヤー別カウント
                layers = {}
                for device in topology_status["data"].values():
                    layer = device.get("layer", 0)
                    layers[layer] = layers.get(layer, 0) + 1
                
                layer_text = " / ".join([f"L{l}:{c}台" for l, c in sorted(layers.items())])
                st.caption(f"📍 {layer_text}")
                
                if topology_status.get("full_exists"):
                    st.caption(f"📄 {topology_status.get('full_filename', '')} (冗長グループ含む)")
            else:
                st.warning("⚠️ 未作成")
                st.caption("トポロジービルダーで作成してください")
    
    # 監視設定
    with col2:
        with st.container(border=True):
            st.markdown("**⚙️ 監視設定**")
            
            if config_status["exists"]:
                st.success("✅ 生成済み")
                st.code(f"📄 {config_status['filename']}", language=None)
                
                summary = config_status["data"].get("summary", {})
                st.markdown(f"**ホスト:** {summary.get('host_count', 0)}台")
                st.caption(f"トリガー: {summary.get('trigger_count', 0)}個 / 依存関係: {summary.get('dependency_count', 0)}件")
            else:
                st.warning("⚠️ 未生成")
                st.caption("トポロジー作成後に生成可能")
    
    # RCA分析
    with col3:
        with st.container(border=True):
            st.markdown("**🎯 RCA分析**")
            
            if alerts_status["exists"]:
                st.info(f"📥 アラートデータあり")
                st.code(f"📄 {alerts_status['filename']}", language=None)
                st.markdown(f"**アラート数:** {alerts_status['count']}件")
                st.caption("分析を実行できます")
            else:
                st.info("ℹ️ 待機中")
                st.caption("アラートデータをアップロードして分析")
    
    st.divider()
    
    # ==================== クイックスタートガイド ====================
    with st.expander("📖 クイックスタートガイド"):
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
