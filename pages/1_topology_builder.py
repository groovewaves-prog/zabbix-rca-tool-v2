"""
Zabbix RCA Tool - トポロジービルダー
コネクタベースのノードマップ（上下=階層、左右=冗長）
"""

import streamlit as st
import json
import os
from datetime import datetime
from typing import Dict, List, Set, Tuple

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

# 標準モジュールタイプ
STANDARD_MODULES = {
    "PSU": {"label": "電源モジュール", "icon": "⚡", "desc": "電源ユニット"},
    "FAN": {"label": "ファンモジュール", "icon": "🌀", "desc": "冷却ファン"},
    "SUPERVISOR": {"label": "スーパバイザ", "icon": "🧠", "desc": "制御モジュール（SUP）"},
    "LINECARD": {"label": "ラインカード", "icon": "🔌", "desc": "インターフェースモジュール"},
    "CONTROLLER": {"label": "コントローラ", "icon": "🎛️", "desc": "ストレージ/WLCコントローラ"},
    "OPTICS": {"label": "光モジュール", "icon": "💡", "desc": "SFP/QSFP"},
}

# 接続タイプ
CONNECTION_TYPES = {
    "uplink": {"label": "上下接続（階層）", "color": "#666666", "dashes": False, "desc": "上位/下位デバイス間"},
    "peer": {"label": "左右接続（冗長）", "color": "#ff9800", "dashes": True, "desc": "同一レイヤーのピア/冗長"},
}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== セッション状態 ====================
def init_session():
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    if "connections" not in st.session_state:
        st.session_state.connections = []  # {"from": "", "to": "", "type": "uplink/peer"}
    if "custom_modules" not in st.session_state:
        st.session_state.custom_modules = {}
    if "selected_node" not in st.session_state:
        st.session_state.selected_node = None

# ==================== レイヤー自動計算 ====================
def calculate_layers() -> Dict[str, int]:
    """接続関係からレイヤーを自動計算（上下接続のみ考慮）"""
    
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return {}
    
    # 上位デバイスマップを構築（uplink接続のみ）
    # from -> to がuplink = fromがtoの下位
    children = {}  # parent -> [children]
    parents = {}   # child -> [parents]
    
    for conn in connections:
        if conn.get("type") == "uplink":
            child = conn["from"]
            parent = conn["to"]
            
            if parent not in children:
                children[parent] = []
            children[parent].append(child)
            
            if child not in parents:
                parents[child] = []
            parents[child].append(parent)
    
    # ルートノード（親がいないデバイス）を特定
    root_nodes = [d for d in devices.keys() if d not in parents]
    
    # レイヤー計算（BFS）
    layers = {}
    
    # ルートノードがない場合は全てLayer 1
    if not root_nodes:
        for d in devices.keys():
            layers[d] = 1
        return layers
    
    # BFSでレイヤー割り当て
    queue = [(r, 1) for r in root_nodes]
    visited = set()
    
    while queue:
        node, layer = queue.pop(0)
        
        if node in visited:
            continue
        visited.add(node)
        
        # 既存レイヤーより深い場合は更新
        if node not in layers or layer > layers[node]:
            layers[node] = layer
        
        # 子ノードをキューに追加
        for child in children.get(node, []):
            queue.append((child, layer + 1))
    
    # 未訪問ノード（孤立ノード）にレイヤー割り当て
    for d in devices.keys():
        if d not in layers:
            layers[d] = 1
    
    return layers

# ==================== ノードマップ描画 ====================
def render_node_map():
    """コネクタベースのノードマップ"""
    
    if not HAS_AGRAPH:
        st.error("❌ streamlit-agraph がインストールされていません")
        st.code("pip install streamlit-agraph", language="bash")
        return None
    
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        st.info("📍 デバイスがありません。サイドバーからデバイスを追加してください。")
        return None
    
    # レイヤー計算
    layers = calculate_layers()
    
    nodes = []
    edges = []
    
    # ノード生成
    for dev_id, dev in devices.items():
        dev_type = dev.get("type", "SWITCH")
        style = DEVICE_TYPES.get(dev_type, {"color": "#6c757d", "icon": "⬜"})
        layer = layers.get(dev_id, 1)
        
        # ピア接続を確認
        peers = []
        for conn in connections:
            if conn.get("type") == "peer":
                if conn["from"] == dev_id:
                    peers.append(conn["to"])
                elif conn["to"] == dev_id:
                    peers.append(conn["from"])
        
        # ラベル作成
        label = f"{style['icon']} {dev_id}"
        vendor = dev.get("metadata", {}).get("vendor")
        if vendor:
            label += f"\n{vendor}"
        
        # タイトル（ホバー時表示）
        title_parts = [
            f"ID: {dev_id}",
            f"タイプ: {dev_type}",
            f"レイヤー: {layer}（自動計算）",
        ]
        if peers:
            title_parts.append(f"ピア: {', '.join(peers)}")
        
        modules = dev.get("modules", [])
        if modules:
            mod_summary = {}
            for m in modules:
                t = m.get("type", "?")
                mod_summary[t] = mod_summary.get(t, 0) + 1
            title_parts.append(f"モジュール: {', '.join([f'{t}:{c}' for t,c in mod_summary.items()])}")
        
        nodes.append(Node(
            id=dev_id,
            label=label,
            size=35,
            color=style["color"],
            shape="box",
            font={"color": "white", "size": 12, "face": "arial"},
            level=layer,
            title="\n".join(title_parts),
            borderWidth=2,
            borderWidthSelected=4,
        ))
    
    # エッジ生成
    for conn in connections:
        conn_type = conn.get("type", "uplink")
        style = CONNECTION_TYPES.get(conn_type, CONNECTION_TYPES["uplink"])
        
        edges.append(Edge(
            source=conn["from"],
            target=conn["to"],
            color=style["color"],
            width=2 if conn_type == "uplink" else 1,
            dashes=style["dashes"],
            title=f"{style['label']}: {conn['from']} ↔ {conn['to']}",
            arrows="to" if conn_type == "uplink" else "",
        ))
    
    # 設定
    config = Config(
        width="100%",
        height=450,
        directed=True,
        physics=False,
        hierarchical=True,
        hierarchicalConfig={
            "enabled": True,
            "levelSeparation": 100,
            "nodeSpacing": 180,
            "direction": "UD",
            "sortMethod": "directed",
        },
        nodeHighlightBehavior=True,
        highlightColor="#ffc107",
    )
    
    # 凡例
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        st.caption("━━ 上下接続（階層）")
    with col2:
        st.caption("┅┅ 左右接続（冗長/ピア）")
    with col3:
        st.caption("※ノードクリックで選択")
    
    # グラフ描画
    selected = agraph(nodes=nodes, edges=edges, config=config)
    
    return selected

# ==================== サイドバー: デバイス追加 ====================
def render_sidebar_device():
    """サイドバー: デバイス追加"""
    
    st.sidebar.markdown("## ➕ デバイス追加")
    
    with st.sidebar.form("add_device", clear_on_submit=True):
        device_id = st.text_input("デバイスID *", placeholder="CORE_SW_01")
        
        device_type = st.selectbox(
            "タイプ *",
            list(DEVICE_TYPES.keys()),
            format_func=lambda x: f"{DEVICE_TYPES[x]['icon']} {DEVICE_TYPES[x]['label']}"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            vendor = st.selectbox("ベンダー", [""] + VENDORS)
        with col2:
            model = st.text_input("モデル", placeholder="C9500")
        
        # 標準モジュール
        st.markdown("**標準モジュール**")
        all_modules = {**STANDARD_MODULES, **st.session_state.custom_modules}
        
        module_counts = {}
        cols = st.columns(3)
        for idx, (mod_key, mod_info) in enumerate(all_modules.items()):
            with cols[idx % 3]:
                count = st.number_input(
                    f"{mod_info['icon']} {mod_key}",
                    min_value=0, max_value=16, value=0,
                    key=f"mod_{mod_key}",
                    help=mod_info.get("desc", "")
                )
                module_counts[mod_key] = count
        
        submitted = st.form_submit_button("追加", type="primary", use_container_width=True)
        
        if submitted:
            if not device_id:
                st.sidebar.error("IDを入力してください")
            elif not device_id.replace("_", "").replace("-", "").isalnum():
                st.sidebar.error("英数字と_-のみ使用可能")
            elif device_id in st.session_state.devices:
                st.sidebar.error("IDが重複しています")
            else:
                # モジュールリスト作成
                modules = []
                for mod_type, count in module_counts.items():
                    for i in range(count):
                        modules.append({"type": mod_type, "id": f"{mod_type}-{i+1}"})
                
                st.session_state.devices[device_id] = {
                    "type": device_type,
                    "metadata": {
                        "vendor": vendor if vendor else None,
                        "model": model if model else None,
                    },
                    "modules": modules,
                }
                st.sidebar.success(f"✅ {device_id} を追加")
                st.rerun()

# ==================== サイドバー: 接続追加 ====================
def render_sidebar_connection():
    """サイドバー: 接続追加"""
    
    st.sidebar.markdown("## 🔗 接続追加")
    
    device_list = list(st.session_state.devices.keys())
    
    if len(device_list) < 2:
        st.sidebar.caption("2台以上のデバイスが必要です")
        return
    
    with st.sidebar.form("add_connection"):
        conn_type = st.radio(
            "接続タイプ",
            ["uplink", "peer"],
            format_func=lambda x: f"{'↕️ 上下（階層）' if x == 'uplink' else '↔️ 左右（冗長）'}",
            horizontal=True,
            help="上下=上位/下位の関係、左右=同レイヤーの冗長/ピア"
        )
        
        if conn_type == "uplink":
            st.caption("接続元（下位） → 接続先（上位）")
            from_label = "下位デバイス"
            to_label = "上位デバイス"
        else:
            st.caption("同一レイヤーのピア/冗長関係")
            from_label = "デバイス1"
            to_label = "デバイス2"
        
        from_device = st.selectbox(from_label, device_list, key="conn_from")
        to_device = st.selectbox(to_label, device_list, key="conn_to")
        
        if st.form_submit_button("接続追加", use_container_width=True):
            if from_device == to_device:
                st.sidebar.error("同じデバイスは接続できません")
            else:
                # 重複チェック
                exists = any(
                    (c["from"] == from_device and c["to"] == to_device and c["type"] == conn_type) or
                    (c["from"] == to_device and c["to"] == from_device and c["type"] == conn_type)
                    for c in st.session_state.connections
                )
                if exists:
                    st.sidebar.warning("既に接続されています")
                else:
                    st.session_state.connections.append({
                        "from": from_device,
                        "to": to_device,
                        "type": conn_type,
                    })
                    st.sidebar.success(f"✅ 接続を追加")
                    st.rerun()

# ==================== カスタムモジュール管理 ====================
def render_custom_modules():
    """カスタムモジュール管理"""
    
    with st.expander("⚙️ カスタムモジュール追加"):
        st.caption("標準モジュール以外を追加")
        
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            new_key = st.text_input("キー", placeholder="NIC", key="new_mod_key")
        with col2:
            new_label = st.text_input("表示名", placeholder="ネットワークカード", key="new_mod_label")
        with col3:
            new_icon = st.text_input("アイコン", placeholder="🔌", max_chars=2, key="new_mod_icon")
        
        if st.button("追加", key="add_custom_mod"):
            if new_key and new_label:
                st.session_state.custom_modules[new_key.upper()] = {
                    "label": new_label,
                    "icon": new_icon or "📦",
                    "desc": f"カスタム: {new_label}",
                }
                st.success(f"✅ {new_key} を追加")
                st.rerun()
        
        # 一覧
        if st.session_state.custom_modules:
            st.markdown("**登録済みカスタムモジュール:**")
            for key, info in st.session_state.custom_modules.items():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.caption(f"{info['icon']} {key}: {info['label']}")
                with col2:
                    if st.button("✕", key=f"del_mod_{key}"):
                        del st.session_state.custom_modules[key]
                        st.rerun()

# ==================== デバイス詳細 ====================
def render_device_details(device_id: str):
    """選択デバイスの詳細表示"""
    
    if device_id not in st.session_state.devices:
        return
    
    dev = st.session_state.devices[device_id]
    style = DEVICE_TYPES.get(dev["type"], {"icon": "⬜", "label": "不明"})
    layers = calculate_layers()
    layer = layers.get(device_id, 1)
    
    st.markdown(f"### {style['icon']} {device_id}")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"**タイプ:** {style['label']}")
    with col2:
        st.markdown(f"**レイヤー:** {layer}（自動）")
    with col3:
        st.markdown(f"**ベンダー:** {dev.get('metadata', {}).get('vendor') or '-'}")
    with col4:
        st.markdown(f"**モデル:** {dev.get('metadata', {}).get('model') or '-'}")
    
    # モジュール
    modules = dev.get("modules", [])
    if modules:
        mod_summary = {}
        for m in modules:
            t = m["type"]
            mod_summary[t] = mod_summary.get(t, 0) + 1
        st.caption(f"モジュール: {', '.join([f'{t}:{c}' for t,c in mod_summary.items()])}")
    
    # 接続情報
    uplinks = []
    downlinks = []
    peers = []
    
    for conn in st.session_state.connections:
        if conn["type"] == "uplink":
            if conn["from"] == device_id:
                uplinks.append(conn["to"])
            elif conn["to"] == device_id:
                downlinks.append(conn["from"])
        elif conn["type"] == "peer":
            if conn["from"] == device_id:
                peers.append(conn["to"])
            elif conn["to"] == device_id:
                peers.append(conn["from"])
    
    conn_info = []
    if uplinks:
        conn_info.append(f"↑上位: {', '.join(uplinks)}")
    if downlinks:
        conn_info.append(f"↓下位: {', '.join(downlinks)}")
    if peers:
        conn_info.append(f"↔ピア: {', '.join(peers)}")
    
    if conn_info:
        st.caption(" | ".join(conn_info))
    
    # 削除ボタン
    if st.button("🗑️ このデバイスを削除", key=f"del_{device_id}"):
        del st.session_state.devices[device_id]
        # 関連接続も削除
        st.session_state.connections = [
            c for c in st.session_state.connections
            if c["from"] != device_id and c["to"] != device_id
        ]
        st.session_state.selected_node = None
        st.rerun()

# ==================== エクスポート ====================
def render_export():
    """エクスポートパネル"""
    
    if not st.session_state.devices:
        st.warning("デバイスがありません")
        return
    
    layers = calculate_layers()
    
    # トポロジーJSON生成
    topology = {}
    for dev_id, dev in st.session_state.devices.items():
        # 上位デバイス抽出（uplink接続のto側）
        parent_ids = [
            c["to"] for c in st.session_state.connections
            if c["from"] == dev_id and c["type"] == "uplink"
        ]
        
        # hw_inventory
        hw_inventory = {}
        for mod in dev.get("modules", []):
            key = f"{mod['type'].lower()}_count"
            hw_inventory[key] = hw_inventory.get(key, 0) + 1
        
        topology[dev_id] = {
            "type": dev["type"],
            "layer": layers.get(dev_id, 1),
            "parent_id": parent_ids[0] if parent_ids else None,
            "parent_ids": parent_ids,
            "metadata": {
                **dev.get("metadata", {}),
                "hw_inventory": hw_inventory,
            },
            "modules": dev.get("modules", []),
        }
    
    # 冗長グループを接続から自動生成
    redundancy_groups = {}
    peer_connections = [c for c in st.session_state.connections if c["type"] == "peer"]
    
    # 連結成分を見つける（簡易版）
    if peer_connections:
        visited = set()
        group_id = 1
        
        for conn in peer_connections:
            if conn["from"] not in visited and conn["to"] not in visited:
                # 新しいグループ
                members = {conn["from"], conn["to"]}
                
                # 他のピア接続も探す
                for other in peer_connections:
                    if other["from"] in members or other["to"] in members:
                        members.add(other["from"])
                        members.add(other["to"])
                
                visited.update(members)
                redundancy_groups[f"PEER_GROUP_{group_id}"] = {
                    "type": "peer",
                    "members": list(members),
                }
                group_id += 1
    
    # 完全データ
    full_data = {
        "topology": topology,
        "connections": st.session_state.connections,
        "redundancy_groups": redundancy_groups,
        "custom_modules": st.session_state.custom_modules,
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "device_count": len(topology),
            "version": "2.1",
        }
    }
    
    # サマリー
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("デバイス", len(topology))
    with col2:
        uplink_count = len([c for c in st.session_state.connections if c["type"] == "uplink"])
        peer_count = len([c for c in st.session_state.connections if c["type"] == "peer"])
        st.metric("接続", f"{uplink_count}↕ / {peer_count}↔")
    with col3:
        st.metric("冗長グループ", len(redundancy_groups))
    
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
            
            st.success("✅ 保存しました → サイドバーから「監視設定生成」へ")

# ==================== インポート ====================
def render_import():
    """データインポート"""
    
    with st.expander("📥 インポート"):
        uploaded = st.file_uploader("JSONファイル", type=["json"], key="import_file")
        
        if uploaded:
            try:
                data = json.load(uploaded)
                
                if "topology" in data:
                    topology = data["topology"]
                    connections = data.get("connections", [])
                    custom_mods = data.get("custom_modules", {})
                else:
                    topology = data
                    connections = []
                    custom_mods = {}
                
                st.json({"devices": len(topology), "connections": len(connections)})
                
                if st.button("インポート実行", key="exec_import"):
                    st.session_state.devices = {}
                    
                    for dev_id, dev in topology.items():
                        st.session_state.devices[dev_id] = {
                            "type": dev.get("type", "SWITCH"),
                            "metadata": dev.get("metadata", {}),
                            "modules": dev.get("modules", []),
                        }
                    
                    # 接続復元
                    if connections:
                        st.session_state.connections = connections
                    else:
                        # parent_idsから復元
                        st.session_state.connections = []
                        for dev_id, dev in topology.items():
                            for parent in dev.get("parent_ids", []):
                                st.session_state.connections.append({
                                    "from": dev_id,
                                    "to": parent,
                                    "type": "uplink",
                                })
                    
                    st.session_state.custom_modules = custom_mods
                    st.success(f"✅ {len(topology)}台をインポート")
                    st.rerun()
                    
            except Exception as e:
                st.error(f"エラー: {e}")

# ==================== メイン ====================
def main():
    init_session()
    
    # ヘッダー
    st.title("🔧 トポロジービルダー")
    st.caption("コネクタベース: ↕️上下接続=階層、↔️左右接続=冗長/ピア")
    
    # サイドバー
    render_sidebar_device()
    st.sidebar.divider()
    render_sidebar_connection()
    
    # メインエリア
    st.divider()
    
    # ノードマップ
    selected = render_node_map()
    
    if selected:
        st.session_state.selected_node = selected
    
    st.divider()
    
    # 選択デバイス詳細
    if st.session_state.selected_node and st.session_state.selected_node in st.session_state.devices:
        render_device_details(st.session_state.selected_node)
        st.divider()
    
    # 下部パネル
    col1, col2 = st.columns(2)
    
    with col1:
        render_custom_modules()
    
    with col2:
        render_export()
        render_import()

if __name__ == "__main__":
    main()
