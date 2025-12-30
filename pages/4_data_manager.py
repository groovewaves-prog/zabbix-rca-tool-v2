"""
Zabbix RCA Tool - データ管理
インポート・エクスポート・履歴管理
"""

import streamlit as st
import json
import os
from datetime import datetime
import pandas as pd

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="データ管理 - Zabbix RCA Tool",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== カスタムCSS ====================
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    .data-card {
        padding: 20px;
        border-radius: 10px;
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        margin: 10px 0;
    }
    .hint-box {
        padding: 15px;
        background: #e7f3ff;
        border-left: 4px solid #2196f3;
        border-radius: 0 8px 8px 0;
        margin: 15px 0;
    }
</style>
""", unsafe_allow_html=True)

# ==================== データディレクトリ ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def get_data_files():
    """データディレクトリ内のファイル一覧を取得"""
    if not os.path.exists(DATA_DIR):
        return []
    
    files = []
    for filename in os.listdir(DATA_DIR):
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.isfile(filepath):
            stat = os.stat(filepath)
            files.append({
                "filename": filename,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    
    return sorted(files, key=lambda x: x["modified"], reverse=True)

def load_json_file(filename: str):
    """JSONファイルを読み込む"""
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_json_file(filename: str, data: dict):
    """JSONファイルを保存"""
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def delete_file(filename: str):
    """ファイルを削除"""
    filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False

# ==================== メイン ====================
def main():
    # ヘッダー
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("📁 データ管理")
        st.caption("インポート・エクスポート・履歴管理")
    with col2:
        if st.button("🏠 ホームに戻る"):
            st.switch_page("Home.py")
    
    st.divider()
    
    # タブ
    tab1, tab2, tab3 = st.tabs(["📤 インポート", "📥 エクスポート", "🗂️ ファイル管理"])
    
    # ==================== インポート ====================
    with tab1:
        st.subheader("📤 データインポート")
        
        st.markdown("""
        <div class="hint-box">
            💡 <strong>ヒント:</strong> 既存のトポロジーデータやアラートデータをインポートできます。
        </div>
        """, unsafe_allow_html=True)
        
        import_type = st.selectbox(
            "インポートするデータタイプ",
            ["トポロジーデータ", "アラートデータ", "監視設定"]
        )
        
        uploaded_file = st.file_uploader(
            f"{import_type}のJSONファイル",
            type=["json"],
            key="import_file"
        )
        
        if uploaded_file:
            try:
                data = json.load(uploaded_file)
                
                # プレビュー
                st.subheader("📋 プレビュー")
                
                if import_type == "トポロジーデータ":
                    # トポロジー形式の判定
                    if "topology" in data:
                        # full_topology形式
                        topology = data["topology"]
                        redundancy_groups = data.get("redundancy_groups", {})
                        st.info(f"デバイス数: {len(topology)}台, 冗長グループ: {len(redundancy_groups)}件")
                    else:
                        # 単純なトポロジー形式
                        topology = data
                        st.info(f"デバイス数: {len(topology)}台")
                    
                    # デバイス一覧
                    with st.expander("デバイス一覧"):
                        for dev_id, dev in list(topology.items())[:10]:
                            st.markdown(f"- **{dev_id}**: {dev.get('type', '-')} (Layer {dev.get('layer', '-')})")
                        if len(topology) > 10:
                            st.caption(f"... 他 {len(topology) - 10}台")
                
                elif import_type == "アラートデータ":
                    alerts = data.get("alerts", data) if isinstance(data, dict) else data
                    if isinstance(alerts, list):
                        st.info(f"アラート数: {len(alerts)}件")
                        with st.expander("アラート一覧"):
                            for a in alerts[:10]:
                                st.markdown(f"- **{a.get('device_id', '-')}**: {a.get('message', '-')}")
                            if len(alerts) > 10:
                                st.caption(f"... 他 {len(alerts) - 10}件")
                    else:
                        st.warning("アラートデータの形式が不正です")
                
                elif import_type == "監視設定":
                    summary = data.get("summary", {})
                    st.info(f"ホスト: {summary.get('host_count', '-')}台, トリガー: {summary.get('trigger_count', '-')}個")
                
                # インポート実行
                st.divider()
                
                col1, col2 = st.columns(2)
                with col1:
                    filename_map = {
                        "トポロジーデータ": "topology.json",
                        "アラートデータ": "alerts.json",
                        "監視設定": "zabbix_config.json"
                    }
                    target_filename = st.text_input(
                        "保存ファイル名",
                        value=filename_map[import_type]
                    )
                
                with col2:
                    st.write("")  # スペーサー
                    st.write("")
                    if st.button("💾 インポート実行", type="primary", use_container_width=True):
                        save_json_file(target_filename, data)
                        st.success(f"✅ {target_filename} としてインポートしました")
                        st.rerun()
                
            except Exception as e:
                st.error(f"ファイル読み込みエラー: {e}")
    
    # ==================== エクスポート ====================
    with tab2:
        st.subheader("📥 データエクスポート")
        
        files = get_data_files()
        
        if not files:
            st.info("エクスポート可能なデータがありません")
        else:
            st.markdown("保存されているデータファイルをダウンロードできます。")
            
            for file_info in files:
                filename = file_info["filename"]
                if not filename.endswith(".json"):
                    continue
                
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    icon = "🗺️" if "topology" in filename else "⚠️" if "alert" in filename else "⚙️" if "config" in filename else "📄"
                    st.markdown(f"{icon} **{filename}**")
                    st.caption(f"サイズ: {file_info['size']:,} bytes | 更新: {file_info['modified']}")
                
                with col2:
                    # プレビュー
                    if st.button("👁️ プレビュー", key=f"preview_{filename}"):
                        st.session_state[f"show_preview_{filename}"] = not st.session_state.get(f"show_preview_{filename}", False)
                
                with col3:
                    # ダウンロード
                    data = load_json_file(filename)
                    if data:
                        st.download_button(
                            "📥 ダウンロード",
                            json.dumps(data, ensure_ascii=False, indent=2),
                            filename,
                            "application/json",
                            key=f"download_{filename}"
                        )
                
                # プレビュー表示
                if st.session_state.get(f"show_preview_{filename}", False):
                    data = load_json_file(filename)
                    if data:
                        with st.expander(f"{filename} の内容", expanded=True):
                            st.json(data)
                
                st.divider()
            
            # 一括エクスポート
            st.subheader("📦 一括エクスポート")
            
            if st.button("すべてのデータをまとめてダウンロード"):
                all_data = {}
                for file_info in files:
                    filename = file_info["filename"]
                    if filename.endswith(".json"):
                        data = load_json_file(filename)
                        if data:
                            all_data[filename] = data
                
                if all_data:
                    export_data = {
                        "exported_at": datetime.now().isoformat(),
                        "files": all_data
                    }
                    st.download_button(
                        "📥 全データをダウンロード",
                        json.dumps(export_data, ensure_ascii=False, indent=2),
                        "zabbix_rca_tool_export.json",
                        "application/json",
                        use_container_width=True
                    )
    
    # ==================== ファイル管理 ====================
    with tab3:
        st.subheader("🗂️ ファイル管理")
        
        files = get_data_files()
        
        if not files:
            st.info("データファイルがありません")
            
            # データディレクトリ作成
            if st.button("📁 データディレクトリを作成"):
                os.makedirs(DATA_DIR, exist_ok=True)
                st.success(f"✅ {DATA_DIR} を作成しました")
                st.rerun()
        else:
            # ファイル一覧テーブル
            df = pd.DataFrame(files)
            df.columns = ["ファイル名", "サイズ (bytes)", "更新日時"]
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            # ファイル削除
            st.subheader("🗑️ ファイル削除")
            
            st.warning("⚠️ 削除したファイルは復元できません")
            
            delete_target = st.selectbox(
                "削除するファイル",
                [""] + [f["filename"] for f in files]
            )
            
            if delete_target:
                col1, col2 = st.columns([3, 1])
                with col1:
                    confirm = st.checkbox(f"「{delete_target}」を削除することを確認しました")
                with col2:
                    if st.button("🗑️ 削除", disabled=not confirm, type="primary"):
                        if delete_file(delete_target):
                            st.success(f"✅ {delete_target} を削除しました")
                            st.rerun()
                        else:
                            st.error("削除に失敗しました")
            
            st.divider()
            
            # データリセット
            st.subheader("🔄 データリセット")
            
            st.error("⚠️ すべてのデータを削除します。この操作は取り消せません。")
            
            reset_confirm = st.text_input(
                "リセットするには「RESET」と入力してください",
                key="reset_confirm"
            )
            
            if st.button("🔄 全データをリセット", disabled=(reset_confirm != "RESET")):
                for file_info in files:
                    delete_file(file_info["filename"])
                st.success("✅ すべてのデータを削除しました")
                st.rerun()
    
    # サイドバー情報
    with st.sidebar:
        st.header("📊 データ統計")
        
        files = get_data_files()
        total_size = sum(f["size"] for f in files)
        
        st.metric("ファイル数", len(files))
        st.metric("合計サイズ", f"{total_size:,} bytes")
        
        st.divider()
        
        st.caption(f"データディレクトリ: {DATA_DIR}")

if __name__ == "__main__":
    main()
