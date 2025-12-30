import streamlit as st

st.set_page_config(
    page_title="Zabbix RCA Tool",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== データ状態取得 ====================
def get_session_status():
    """
    Session Stateからデータの状態を取得する。
    Streamlit Cloudなどディスク永続化が保証されない環境向け。
    """
    status = {
        "topology": {"count": 0, "status": "⚠️ 未作成"},
        "config": {"count": 0, "status": "ℹ️ 未生成"}, # 今回のスコープ外だが枠組みだけ用意
        "alerts": {"count": 0, "status": "ℹ️ 待機中"},
    }
    
    # トポロジーデータのチェック (1_topology_builder.py で管理)
    if "devices" in st.session_state and st.session_state.devices:
        count = len(st.session_state.devices)
        status["topology"] = {
            "count": count,
            "status": f"✅ {count}台 (メモリ内)"
        }
    
    # ※ ConfigやAlertsも同様に session_state に保存する設計にするのが望ましい
    # 必要に応じて追加実装してください
    
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
    if st.button("⚙️ 監視設定生成", use_container_width=True):
        st.info("構築中...") # st.switch_page("pages/2_config_generator.py")

with col3:
    if st.button("🎯 根本原因分析", use_container_width=True):
         st.info("構築中...") # st.switch_page("pages/3_rca_analyzer.py")

with col4:
    # データ管理ページへのリンク（必要であれば）
    st.empty()

st.divider()

# 現在の状態
st.subheader("📊 現在のセッション状態")
st.caption("※ ブラウザを閉じるとデータはリセットされます。トポロジー画面でJSONを保存してください。")

status = get_session_status()

col1, col2, col3 = st.columns(3)

with col1:
    with st.container(border=True):
        st.markdown("**🗺️ トポロジー**")
        st.markdown(status["topology"]["status"])

with col2:
    with st.container(border=True):
        st.markdown("**⚙️ 監視設定**")
        st.markdown(status["config"]["status"])

with col3:
    with st.container(border=True):
        st.markdown("**🎯 RCA**")
        st.markdown(status["alerts"]["status"])
