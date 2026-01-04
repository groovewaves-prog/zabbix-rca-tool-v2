import streamlit as st
import os

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
        "config": {"count": 0, "status": "ℹ️ 未生成"},
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
def main():
    st.title("🔍 Zabbix RCA Tool")
    
    # ステータス表示
    current_status = get_session_status()
    
    st.divider()

    # クイックアクセス
    st.subheader("🚀 クイックアクセス")
    
    # 【改修】4列から3列に変更し、Data Managerへのリンクを削除
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("##### 1. 構成管理")
        if st.button("🔧 トポロジービルダー", use_container_width=True, type="primary"):
            st.switch_page("pages/1_topology_builder.py")
        st.caption(f"現在の状態: {current_status['topology']['status']}")

    with col2:
        st.markdown("##### 2. 設定生成")
        # 【改修】リンクを有効化
        if st.button("⚙️ 監視設定生成", use_container_width=True):
            st.switch_page("pages/2_config_generator.py")
        st.caption("AIによるテンプレート推奨と設定出力")

    with col3:
        st.markdown("##### 3. 分析・復旧")
        # 【改修】リンクを有効化 (ファイル名を 3_rca_analysis.py に修正)
        if st.button("🎯 根本原因分析 & AI Ops", use_container_width=True):
            st.switch_page("pages/3_rca_analysis.py")
        st.caption("トポロジー分析による真因特定と復旧")

    st.divider()

    # 現在の状態詳細
    st.subheader("📊 現在のセッション状態")
    st.info("※ ブラウザを閉じるとメモリ内のデータ（作成中のトポロジー等）はリセットされます。各画面でJSONをダウンロードして保存することをお勧めします。")

if __name__ == "__main__":
    main()
