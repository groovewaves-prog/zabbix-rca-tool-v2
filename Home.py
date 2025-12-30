"""
Zabbix RCA Tool - Home
"""

import streamlit as st
import json
import os

st.set_page_config(
    page_title="Zabbix RCA Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def get_status():
    """データ状態を取得"""
    status = {
        "topology": {"exists": False, "count": 0, "file": None},
        "config": {"exists": False, "count": 0, "file": None},
        "alerts": {"exists": False, "count": 0, "file": None},
    }
    
    # トポロジー
    topo_path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(topo_path):
        try:
            with open(topo_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                status["topology"] = {
                    "exists": True,
                    "count": len(data),
                    "file": "topology.json"
                }
        except:
            pass
    
    # 監視設定
    config_path = os.path.join(DATA_DIR, "zabbix_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                status["config"] = {
                    "exists": True,
                    "count": data.get("summary", {}).get("host_count", 0),
                    "file": "zabbix_config.json"
                }
        except:
            pass
    
    # アラート
    alerts_path = os.path.join(DATA_DIR, "alerts.json")
    if os.path.exists(alerts_path):
        try:
            with open(alerts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                alerts = data.get("alerts", data) if isinstance(data, dict) else data
                status["alerts"] = {
                    "exists": True,
                    "count": len(alerts) if isinstance(alerts, list) else 0,
                    "file": "alerts.json"
                }
        except:
            pass
    
    return status

# ==================== メイン ====================
st.title("🔍 Zabbix RCA Tool")

st.divider()

# クイックアクセス
st.subheader("🚀 クイックアクセス")

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("🔧 トポロジービルダー", use_container_width=True, type="primary"):
        st.switch_page("pages/1_topology_builder.py")

with col2:
    if st.button("⚙️ 監視設定生成", use_container_width=True, type="primary"):
        st.switch_page("pages/2_config_generator.py")

with col3:
    if st.button("🎯 根本原因分析", use_container_width=True, type="primary"):
        st.switch_page("pages/3_rca_analyzer.py")

with col4:
    if st.button("📁 データ管理", use_container_width=True):
        st.switch_page("pages/4_data_manager.py")

st.divider()

# 現在の状態
st.subheader("📊 現在の状態")

status = get_status()

col1, col2, col3 = st.columns(3)

with col1:
    with st.container(border=True):
        st.markdown("**🗺️ トポロジー**")
        if status["topology"]["exists"]:
            st.success(f"✅ {status['topology']['count']}台")
            st.code(status["topology"]["file"], language=None)
        else:
            st.warning("⚠️ 未作成")

with col2:
    with st.container(border=True):
        st.markdown("**⚙️ 監視設定**")
        if status["config"]["exists"]:
            st.success(f"✅ {status['config']['count']}ホスト")
            st.code(status["config"]["file"], language=None)
        else:
            st.info("ℹ️ 未生成")

with col3:
    with st.container(border=True):
        st.markdown("**🎯 RCA**")
        if status["alerts"]["exists"]:
            st.info(f"📥 {status['alerts']['count']}件")
            st.code(status["alerts"]["file"], language=None)
        else:
            st.info("ℹ️ 待機中")
