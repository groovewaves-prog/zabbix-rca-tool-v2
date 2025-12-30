"""
Zabbix RCA Tool - トポロジービルダー
ノードマップベースのインタラクティブなトポロジー構築
"""

import streamlit as st
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

# ノードマップライブラリ
try:
    from streamlit_agraph import agraph, Node, Edge, Config
    HAS_AGRAPH = True
except ImportError:
    HAS_AGRAPH = False

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="トポロジービルダー - Zabbix RCA Tool",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 定数 ====================
DEVICE_TYPES = {
    "ROUTER": {"icon": "🔵", "color": "#667eea", "label": "ルーター"},
    "SWITCH": {"icon": "🟢", "color": "#11998e", "label": "スイッチ"},
    "FIREWALL": {"icon": "🔴", "color": "#eb3349", "label": "ファイアウォール"},
    "SERVER": {"icon": "🔷", "color": "#2193b0", "label": "サーバー"},
    "ACCESS_POINT": {"icon": "📡", "color": "#f7971e", "label": "アクセスポイント"},
    "LOAD_BALANCER": {"icon": "⚖️", "color": "#4776E6", "label": "ロードバランサー"},
    "STORAGE": {"icon": "💾", "color": "#834d9b", "label": "ストレージ"},
}

VENDORS = ["Cisco", "Juniper", "Fortinet", "Palo Alto", "Arista", "HPE", "Dell", "NetApp", "F5", "Other"]

MODULE_TYPES = {
    "PSU": "電源",
    "FAN": "ファン", 
    "SUPERVISOR": "スーパバイザ",
    "LINECARD": "ラインカード",
    "CONTROLLER": "コントローラ",
}

REDUNDANCY_TYPES = {
    "Active-Standby": "1台アクティブ、他スタンバイ",
    "Active-Active": "全台アクティブ",
    "Stack": "スタック構成",
    "VRRP/HSRP": "仮想IP冗長",
    "Cluster": "クラスタ",
}

LAYER_NAMES = {
    1: "WAN Edge",
    2: "Core", 
    3: "Distribution",
    4: "Access",
    5: "Endpoint",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== セッション状態 ====================
def init_session():
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    if "connections" not in st.session_state:
        st.session_state.connections = []
    if "redundancy_groups" not in st.session_state:
        st.session_state.redundancy_groups = {}
    if "selected_node" not in st.session_state:
        st.session_state.selected_node = None
    if "add_connection_mode" not in st.session_state:
        st.session_state.add_connection_mode = False
    if "connection_source" not in st.session_state:
        st.session_state.connection_source = None

# ==================== ノードマップ描画 ====================
def render_node_map():
    """インタラクティブなノードマップを描画"""
    
    if not HAS_AGRAPH:
        st.error("❌ streamlit-agraph がインストールされていません")
        st.code("pip install streamlit-agraph", language="bash")
        return None
    
    nodes = []
    edges = []
    
    # デバイスからノードを生成
    for dev_id, dev in st.session_state.devices.items():
        dev_type = dev.get("type", "SWITCH")
        style = DEVICE_TYPES.get(dev_type, {"color": "#6c757d", "icon": "⬜"})
        layer = dev.get("layer", 3)
        
        # 冗長グループに属しているか確認
        in_group = None
        for rg_id, rg in st.session_state.redundancy_groups.items():
            if dev_id in rg.get("members", []):
                in_group = rg_id
                break
        
        # ラベル作成
        label = f"{style['icon']} {dev_id}"
        if dev.get("metadata", {}).get("vendor"):
            label += f"\n({dev['metadata']['vendor']})"
        
        nodes.append(Node(
            id=dev_id,
            label=label,
            size=30,
            color=style["color"],
            shape="box",
            font={"color": "white", "size": 14},
            level=layer,  # 階層配置用
            title=f"Layer {layer} | {dev_type}\nクリックして選択",
        ))
    
    # 接続からエッジを生成
    for conn in st.session_state.connections:
        edges.append(Edge(
            source=conn["from"],
            target=conn["to"],
            color="#888888",
            width=2,
        ))
    
    # 冗長グループの視覚化（同グループを破線で接続）
    for rg_id, rg in st.session_state.redundancy_groups.items():
        members = rg.get("members", [])
        for i in range(len(members) - 1):
            edges.append(Edge(
                source=members[i],
                target=members[i + 1],
                color="#ff9800",
                width=1,
                dashes=True,
                title=f"冗長グループ: {rg_id}",
            ))
    
    # 設定
    config = Config(
        width="100%",
        height=500,
        directed=True,
        physics=False,  # 物理シミュレーションOFF（手動配置可能に）
        hierarchical=True,
        hierarchicalConfig={
            "enabled": True,
            "levelSeparation": 120,
            "nodeSpacing": 150,
            "direction": "UD",  # 上から下
            "sortMethod": "directed",
        },
        nodeHighlightBehavior=True,
        highlightColor="#ffc107",
        collapsible=False,
    )
    
    # ノードがない場合
    if not nodes:
        st.info("📍 デバイスがありません。サイドバーからデバイスを追加してください。")
        return None
    
    # グラフ描画
    selected = agraph(nodes=nodes, edges=edges, config=config)
    
    return selected

# ==================== サイドバー: デバイス追加 ====================
def render_sidebar_add_device():
    """サイドバー: デバイス追加フォーム"""
    
    st.sidebar.markdown("### ➕ デバイス追加")
    
    with st.sidebar.form("add_device", clear_on_submit=True):
        device_id = st.text_input("デバイスID", placeholder="CORE_SW_01")
        
        device_type = st.selectbox(
            "タイプ",
            list(DEVICE_TYPES.keys()),
            format_func=lambda x: f"{DEVICE_TYPES[x]['icon']} {DEVICE_TYPES[x]['label']}"
        )
        
        layer = st.select_slider(
            "レイヤー",
            options=[1, 2, 3, 4, 5],
            value=2,
            format_func=lambda x: f"L{x}: {LAYER_NAMES[x]}"
        )
        
        vendor = st.selectbox("ベンダー", [""] + VENDORS)
        model = st.text_input("モデル", placeholder="C9500")
        
        # モジュール
        st.markdown("**モジュール数**")
        col1, col2 = st.columns(2)
        with col1:
            psu = st.number_input("電源", 0, 8, 0, key="psu")
            fan = st.number_input("ファン", 0, 8, 0, key="fan")
        with col2:
            sup = st.number_input("SUP", 0, 4, 0, key="sup")
            lc = st.number_input("LC", 0, 16, 0, key="lc")
        
        if st.form_submit_button("追加", type="primary", use_container_width=True):
            if not device_id:
                st.sidebar.error("IDを入力してください")
            elif device_id in st.session_state.devices:
                st.sidebar.error("IDが重複しています")
            else:
                # モジュールリスト作成
                modules = []
                for i in range(psu):
                    modules.append({"type": "PSU", "id": f"PSU-{i+1}"})
                for i in range(fan):
                    modules.append({"type": "FAN", "id": f"FAN-{i+1}"})
                for i in range(sup):
                    modules.append({"type": "SUPERVISOR", "id": f"SUP-{i+1}"})
                for i in range(lc):
                    modules.append({"type": "LINECARD", "id": f"LC-{i+1}"})
                
                st.session_state.devices[device_id] = {
                    "type": device_type,
                    "layer": layer,
                    "metadata": {
                        "vendor": vendor if vendor else None,
                        "model": model if model else None,
                    },
                    "modules": modules,
                }
                st.sidebar.success(f"✅ {device_id} を追加")
                st.rerun()

# ==================== サイドバー: 接続追加 ====================
def render_sidebar_connections():
    """サイドバー: 接続管理"""
    
    st.sidebar.markdown("### 🔗 接続追加")
    
    device_list = list(st.session_state.devices.keys())
    
    if len(device_list) < 2:
        st.sidebar.caption("2台以上のデバイスが必要です")
        return
    
    with st.sidebar.form("add_connection"):
        from_device = st.selectbox("接続元", device_list, key="conn_from")
        to_device = st.selectbox("接続先", device_list, key="conn_to")
        
        if st.form_submit_button("接続追加", use_container_width=True):
            if from_device == to_device:
                st.sidebar.error("同じデバイス間は接続できません")
            else:
                # 既存接続チェック
                exists = any(
                    (c["from"] == from_device and c["to"] == to_device) or
                    (c["from"] == to_device and c["to"] == from_device)
                    for c in st.session_state.connections
                )
                if exists:
                    st.sidebar.warning("既に接続されています")
                else:
                    st.session_state.connections.append({
                        "from": from_device,
                        "to": to_device,
                    })
                    st.sidebar.success(f"✅ {from_device} → {to_device}")
                    st.rerun()
    
    # 接続一覧
    if st.session_state.connections:
        st.sidebar.markdown("**接続一覧:**")
        for i, conn in enumerate(st.session_state.connections):
            col1, col2 = st.sidebar.columns([4, 1])
            with col1:
                st.caption(f"{conn['from']} → {conn['to']}")
            with col2:
                if st.button("✕", key=f"del_conn_{i}"):
                    st.session_state.connections.pop(i)
                    st.rerun()

# ==================== 選択デバイスの詳細 ====================
def render_device_details(device_id: str):
    """選択されたデバイスの詳細表示・編集"""
    
    if device_id not in st.session_state.devices:
        return
    
    dev = st.session_state.devices[device_id]
    style = DEVICE_TYPES.get(dev["type"], {"icon": "⬜", "label": "不明"})
    
    st.markdown(f"### {style['icon']} {device_id}")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"**タイプ:** {dev['type']}")
        st.markdown(f"**レイヤー:** {dev.get('layer', '-')}")
    
    with col2:
        st.markdown(f"**ベンダー:** {dev.get('metadata', {}).get('vendor') or '-'}")
        st.markdown(f"**モデル:** {dev.get('metadata', {}).get('model') or '-'}")
    
    with col3:
        modules = dev.get("modules", [])
        if modules:
            mod_summary = {}
            for m in modules:
                t = m["type"]
                mod_summary[t] = mod_summary.get(t, 0) + 1
            st.markdown(f"**モジュール:** {', '.join([f'{t}:{c}' for t,c in mod_summary.items()])}")
        else:
            st.markdown("**モジュール:** なし")
    
    # 編集・削除ボタン
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        new_layer = st.selectbox(
            "レイヤー変更",
            [1, 2, 3, 4, 5],
            index=dev.get("layer", 3) - 1,
            key=f"edit_layer_{device_id}"
        )
        if new_layer != dev.get("layer"):
            st.session_state.devices[device_id]["layer"] = new_layer
            st.rerun()
    
    with col2:
        if st.button("🗑️ 削除", key=f"del_{device_id}", type="secondary"):
            # デバイス削除
            del st.session_state.devices[device_id]
            # 関連する接続も削除
            st.session_state.connections = [
                c for c in st.session_state.connections
                if c["from"] != device_id and c["to"] != device_id
            ]
            # 冗長グループからも削除
            for rg_id in list(st.session_state.redundancy_groups.keys()):
                rg = st.session_state.redundancy_groups[rg_id]
                if device_id in rg.get("members", []):
                    rg["members"].remove(device_id)
                    if len(rg["members"]) < 2:
                        del st.session_state.redundancy_groups[rg_id]
            st.session_state.selected_node = None
            st.rerun()

# ==================== 冗長グループ管理 ====================
def render_redundancy_panel():
    """冗長グループ管理パネル"""
    
    st.markdown("### 🔷 冗長グループ")
    
    # 登録済みグループ
    if st.session_state.redundancy_groups:
        for rg_id, rg in st.session_state.redundancy_groups.items():
            col1, col2, col3 = st.columns([2, 3, 1])
            with col1:
                st.markdown(f"**{rg_id}**")
            with col2:
                st.caption(f"{rg['type']}: {', '.join(rg['members'])}")
            with col3:
                if st.button("✕", key=f"del_rg_{rg_id}"):
                    del st.session_state.redundancy_groups[rg_id]
                    st.rerun()
    
    # 新規追加
    with st.expander("➕ 冗長グループ追加"):
        col1, col2 = st.columns(2)
        
        with col1:
            rg_name = st.text_input("グループ名", placeholder="CORE_HA", key="rg_name")
            rg_type = st.selectbox("タイプ", list(REDUNDANCY_TYPES.keys()), key="rg_type")
        
        with col2:
            members = st.multiselect(
                "メンバー（2台以上）",
                list(st.session_state.devices.keys()),
                key="rg_members"
            )
        
        if st.button("追加", key="add_rg"):
            if not rg_name:
                st.error("グループ名を入力してください")
            elif rg_name in st.session_state.redundancy_groups:
                st.error("グループ名が重複しています")
            elif len(members) < 2:
                st.error("2台以上を選択してください")
            else:
                st.session_state.redundancy_groups[rg_name] = {
                    "type": rg_type,
                    "members": members,
                }
                st.success(f"✅ {rg_name} を追加")
                st.rerun()

# ==================== エクスポート ====================
def render_export_panel():
    """エクスポートパネル"""
    
    st.markdown("### 📤 エクスポート")
    
    if not st.session_state.devices:
        st.warning("デバイスがありません")
        return
    
    # トポロジーJSON生成
    topology = {}
    for dev_id, dev in st.session_state.devices.items():
        # 接続から親デバイスを抽出
        parent_ids = [
            c["to"] for c in st.session_state.connections if c["from"] == dev_id
        ] + [
            c["from"] for c in st.session_state.connections if c["to"] == dev_id
        ]
        # 上位レイヤーのみを親とする
        parent_ids = [
            p for p in parent_ids
            if st.session_state.devices.get(p, {}).get("layer", 99) < dev.get("layer", 0)
        ]
        
        # hw_inventory
        hw_inventory = {}
        for mod in dev.get("modules", []):
            key = f"{mod['type'].lower()}_count"
            hw_inventory[key] = hw_inventory.get(key, 0) + 1
        
        topology[dev_id] = {
            "type": dev["type"],
            "layer": dev.get("layer", 3),
            "parent_id": parent_ids[0] if parent_ids else None,
            "parent_ids": parent_ids,
            "metadata": {
                **dev.get("metadata", {}),
                "hw_inventory": hw_inventory,
            },
            "modules": dev.get("modules", []),
        }
    
    # 完全データ
    full_data = {
        "topology": topology,
        "connections": st.session_state.connections,
        "redundancy_groups": st.session_state.redundancy_groups,
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "device_count": len(topology),
            "version": "2.0",
        }
    }
    
    # サマリー
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("デバイス", len(topology))
    with col2:
        st.metric("接続", len(st.session_state.connections))
    with col3:
        st.metric("冗長グループ", len(st.session_state.redundancy_groups))
    
    # プレビュー
    with st.expander("📄 JSONプレビュー"):
        st.json(full_data)
    
    # ボタン
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            "📥 ダウンロード",
            json.dumps(full_data, ensure_ascii=False, indent=2),
            "topology.json",
            "application/json",
            use_container_width=True
        )
    
    with col2:
        if st.button("💾 保存して次へ", type="primary", use_container_width=True):
            os.makedirs(DATA_DIR, exist_ok=True)
            
            with open(os.path.join(DATA_DIR, "topology.json"), "w", encoding="utf-8") as f:
                json.dump(topology, f, ensure_ascii=False, indent=2)
            
            with open(os.path.join(DATA_DIR, "full_topology.json"), "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
            
            st.success("✅ 保存しました")
            st.info("👉 監視設定生成ページへ進んでください")

# ==================== インポート ====================
def render_import_panel():
    """既存データのインポート"""
    
    with st.expander("📥 データインポート"):
        uploaded = st.file_uploader("JSONファイル", type=["json"])
        
        if uploaded:
            try:
                data = json.load(uploaded)
                
                # full_topology形式
                if "topology" in data:
                    topology = data["topology"]
                    connections = data.get("connections", [])
                    rg = data.get("redundancy_groups", {})
                else:
                    # 単純なtopology形式
                    topology = data
                    connections = []
                    rg = {}
                
                if st.button("インポート実行"):
                    st.session_state.devices = {}
                    
                    for dev_id, dev in topology.items():
                        st.session_state.devices[dev_id] = {
                            "type": dev.get("type", "SWITCH"),
                            "layer": dev.get("layer", 3),
                            "metadata": dev.get("metadata", {}),
                            "modules": dev.get("modules", []),
                        }
                    
                    # 接続を復元（parent_idsから）
                    if not connections:
                        for dev_id, dev in topology.items():
                            for parent in dev.get("parent_ids", []):
                                connections.append({"from": dev_id, "to": parent})
                    
                    st.session_state.connections = connections
                    st.session_state.redundancy_groups = rg
                    
                    st.success(f"✅ {len(topology)}台をインポート")
                    st.rerun()
                    
            except Exception as e:
                st.error(f"読み込みエラー: {e}")

# ==================== メイン ====================
def main():
    init_session()
    
    # ヘッダー
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🔧 トポロジービルダー")
    with col2:
        if st.button("🏠 ホーム"):
            st.switch_page("Home.py")
    
    # サイドバー
    render_sidebar_add_device()
    st.sidebar.divider()
    render_sidebar_connections()
    
    # メインエリア
    st.divider()
    
    # ノードマップ
    st.markdown("### 🗺️ ネットワークトポロジー")
    st.caption("ノードをクリックして選択・編集できます")
    
    selected = render_node_map()
    
    # 選択されたノードを更新
    if selected:
        st.session_state.selected_node = selected
    
    st.divider()
    
    # 選択デバイスの詳細
    if st.session_state.selected_node and st.session_state.selected_node in st.session_state.devices:
        render_device_details(st.session_state.selected_node)
        st.divider()
    
    # 下部パネル
    col1, col2 = st.columns(2)
    
    with col1:
        render_redundancy_panel()
    
    with col2:
        render_export_panel()
        render_import_panel()

if __name__ == "__main__":
    main()
