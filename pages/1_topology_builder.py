"""
Zabbix RCA Tool - トポロジービルダー
Graphvizベースのノードマップ（Streamlit標準機能のみ使用）
"""

import streamlit as st
import json
import os
from datetime import datetime
from typing import Dict, List, Set

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
    "PSU": {"label": "電源", "icon": "⚡"},
    "FAN": {"label": "ファン", "icon": "🌀"},
    "SUPERVISOR": {"label": "スーパバイザ", "icon": "🧠"},
    "LINECARD": {"label": "ラインカード", "icon": "🔌"},
    "CONTROLLER": {"label": "コントローラ", "icon": "🎛️"},
    "OPTICS": {"label": "光モジュール", "icon": "💡"},
}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== セッション状態 ====================
def init_session():
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    if "connections" not in st.session_state:
        st.session_state.connections = []
    if "custom_modules" not in st.session_state:
        st.session_state.custom_modules = {}
    if "selected_device" not in st.session_state:
        st.session_state.selected_device = None

# ==================== レイヤー自動計算 ====================
def calculate_layers() -> Dict[str, int]:
    """接続関係からレイヤーを自動計算"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return {}
    
    # 親子関係マップ構築（uplinkのみ）
    parents = {}
    for conn in connections:
        if conn.get("type") == "uplink":
            child = conn["from"]
            parent = conn["to"]
            if child not in parents:
                parents[child] = []
            parents[child].append(parent)
    
    # ルートノード特定
    root_nodes = [d for d in devices.keys() if d not in parents]
    
    if not root_nodes:
        return {d: 1 for d in devices.keys()}
    
    # BFSでレイヤー割り当て
    layers = {}
    children_map = {}
    for conn in connections:
        if conn.get("type") == "uplink":
            parent = conn["to"]
            child = conn["from"]
            if parent not in children_map:
                children_map[parent] = []
            children_map[parent].append(child)
    
    queue = [(r, 1) for r in root_nodes]
    visited = set()
    
    while queue:
        node, layer = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        layers[node] = layer
        for child in children_map.get(node, []):
            queue.append((child, layer + 1))
    
    # 未訪問ノード
    for d in devices.keys():
        if d not in layers:
            layers[d] = 1
    
    return layers

# ==================== Graphviz DOT生成 ====================
def generate_dot() -> str:
    """GraphvizのDOT言語でグラフを生成"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return ""
    
    layers = calculate_layers()
    
    # レイヤーごとにグループ化
    layer_groups = {}
    for dev_id, layer in layers.items():
        if layer not in layer_groups:
            layer_groups[layer] = []
        layer_groups[layer].append(dev_id)
    
    dot_lines = [
        "digraph topology {",
        "    rankdir=TB;",
        "    node [shape=box, style=\"rounded,filled\", fontname=\"Arial\", fontsize=11];",
        "    edge [fontname=\"Arial\", fontsize=9];",
        "    splines=ortho;",
        "    nodesep=0.8;",
        "    ranksep=1.0;",
        "",
    ]
    
    # ノード定義
    for dev_id, dev in devices.items():
        dev_type = dev.get("type", "SWITCH")
        style = DEVICE_TYPES.get(dev_type, {"color": "#6c757d"})
        vendor = dev.get("metadata", {}).get("vendor") or ""
        label = f"{dev_id}"
        if vendor:
            label += f"\\n({vendor})"
        
        # 選択中のノードはハイライト
        penwidth = "3" if st.session_state.selected_device == dev_id else "1"
        
        dot_lines.append(f'    "{dev_id}" [label="{label}", fillcolor="{style["color"]}", fontcolor="white", penwidth={penwidth}];')
    
    dot_lines.append("")
    
    # 同一レイヤーをサブグラフで配置
    for layer in sorted(layer_groups.keys()):
        devs = layer_groups[layer]
        dot_lines.append(f"    {{ rank=same; {' '.join([f'\"{d}\"' for d in devs])} }}")
    
    dot_lines.append("")
    
    # エッジ定義
    for conn in connections:
        conn_type = conn.get("type", "uplink")
        
        if conn_type == "uplink":
            # 上下接続（実線、矢印）
            dot_lines.append(f'    "{conn["to"]}" -> "{conn["from"]}" [color="#666666", arrowhead=normal];')
        else:
            # 左右接続（破線、矢印なし）
            dot_lines.append(f'    "{conn["from"]}" -> "{conn["to"]}" [color="#ff9800", style=dashed, arrowhead=none, constraint=false];')
    
    dot_lines.append("}")
    
    return "\n".join(dot_lines)

# ==================== ノードマップ描画 ====================
def render_node_map():
    """Graphvizベースのノードマップ"""
    
    devices = st.session_state.devices
    
    if not devices:
        st.info("📍 デバイスがありません。サイドバーからデバイスを追加してください。")
        return
    
    # 凡例
    col1, col2 = st.columns(2)
    with col1:
        st.caption("━━ 上下接続（階層関係）")
    with col2:
        st.caption("┅┅ 左右接続（冗長/ピア）")
    
    # Graphviz描画
    dot = generate_dot()
    if dot:
        st.graphviz_chart(dot, use_container_width=True)
    
    # デバイス選択（selectbox）
    st.markdown("---")
    device_list = list(devices.keys())
    
    col1, col2 = st.columns([2, 3])
    with col1:
        selected = st.selectbox(
            "📍 デバイスを選択",
            [""] + device_list,
            index=0 if st.session_state.selected_device is None else device_list.index(st.session_state.selected_device) + 1 if st.session_state.selected_device in device_list else 0,
            key="device_selector"
        )
        if selected:
            st.session_state.selected_device = selected
        elif selected == "":
            st.session_state.selected_device = None

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
        st.markdown("**モジュール**")
        all_modules = {**STANDARD_MODULES, **st.session_state.custom_modules}
        
        module_counts = {}
        cols = st.columns(3)
        for idx, (mod_key, mod_info) in enumerate(all_modules.items()):
            with cols[idx % 3]:
                count = st.number_input(
                    f"{mod_info['icon']} {mod_key}",
                    min_value=0, max_value=16, value=0,
                    key=f"mod_{mod_key}"
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
            horizontal=True
        )
        
        if conn_type == "uplink":
            st.caption("下位 → 上位")
            from_label = "下位デバイス"
            to_label = "上位デバイス"
        else:
            st.caption("同一レイヤーのピア")
            from_label = "デバイス1"
            to_label = "デバイス2"
        
        from_device = st.selectbox(from_label, device_list, key="conn_from")
        to_device = st.selectbox(to_label, device_list, key="conn_to")
        
        if st.form_submit_button("接続追加", use_container_width=True):
            if from_device == to_device:
                st.sidebar.error("同じデバイスは接続できません")
            else:
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

# ==================== デバイス詳細 ====================
def render_device_details():
    """選択デバイスの詳細"""
    
    device_id = st.session_state.selected_device
    
    if not device_id or device_id not in st.session_state.devices:
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
    
    # 操作ボタン
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("🗑️ 削除", key="del_device"):
            del st.session_state.devices[device_id]
            st.session_state.connections = [
                c for c in st.session_state.connections
                if c["from"] != device_id and c["to"] != device_id
            ]
            st.session_state.selected_device = None
            st.rerun()
    
    with col2:
        # 接続削除
        device_connections = [
            c for c in st.session_state.connections
            if c["from"] == device_id or c["to"] == device_id
        ]
        if device_connections:
            if st.button("🔗 接続をクリア", key="clear_conn"):
                st.session_state.connections = [
                    c for c in st.session_state.connections
                    if c["from"] != device_id and c["to"] != device_id
                ]
                st.rerun()

# ==================== カスタムモジュール ====================
def render_custom_modules():
    """カスタムモジュール管理"""
    
    with st.expander("⚙️ カスタムモジュール"):
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
                }
                st.success(f"✅ {new_key} を追加")
                st.rerun()
        
        if st.session_state.custom_modules:
            for key, info in st.session_state.custom_modules.items():
                st.caption(f"{info['icon']} {key}: {info['label']}")

# ==================== エクスポート ====================
def render_export():
    """エクスポート"""
    
    if not st.session_state.devices:
        st.warning("デバイスがありません")
        return
    
    layers = calculate_layers()
    
    # トポロジーJSON生成
    topology = {}
    for dev_id, dev in st.session_state.devices.items():
        parent_ids = [
            c["to"] for c in st.session_state.connections
            if c["from"] == dev_id and c["type"] == "uplink"
        ]
        
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
    
    # 冗長グループ自動生成
    redundancy_groups = {}
    peer_connections = [c for c in st.session_state.connections if c["type"] == "peer"]
    
    if peer_connections:
        visited = set()
        group_id = 1
        
        for conn in peer_connections:
            if conn["from"] not in visited or conn["to"] not in visited:
                members = {conn["from"], conn["to"]}
                for other in peer_connections:
                    if other["from"] in members or other["to"] in members:
                        members.add(other["from"])
                        members.add(other["to"])
                
                if not members.issubset(visited):
                    redundancy_groups[f"PEER_GROUP_{group_id}"] = {
                        "type": "peer",
                        "members": list(members),
                    }
                    visited.update(members)
                    group_id += 1
    
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
        st.metric("接続", f"{uplink_count}↕ {peer_count}↔")
    with col3:
        st.metric("冗長グループ", len(redundancy_groups))
    
    with st.expander("📄 JSON"):
        st.json(full_data)
    
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
        if st.button("💾 保存", type="primary", use_container_width=True):
            os.makedirs(DATA_DIR, exist_ok=True)
            
            with open(os.path.join(DATA_DIR, "topology.json"), "w", encoding="utf-8") as f:
                json.dump(topology, f, ensure_ascii=False, indent=2)
            
            with open(os.path.join(DATA_DIR, "full_topology.json"), "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
            
            st.success("✅ 保存しました")

# ==================== インポート ====================
def render_import():
    """インポート"""
    
    with st.expander("📥 インポート"):
        uploaded = st.file_uploader("JSON", type=["json"], key="import_file")
        
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
                
                st.caption(f"デバイス: {len(topology)}台, 接続: {len(connections)}件")
                
                if st.button("インポート", key="exec_import"):
                    st.session_state.devices = {}
                    
                    for dev_id, dev in topology.items():
                        st.session_state.devices[dev_id] = {
                            "type": dev.get("type", "SWITCH"),
                            "metadata": dev.get("metadata", {}),
                            "modules": dev.get("modules", []),
                        }
                    
                    if connections:
                        st.session_state.connections = connections
                    else:
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
    
    st.title("🔧 トポロジービルダー")
    st.caption("↕️上下接続=階層、↔️左右接続=冗長/ピア")
    
    # サイドバー
    render_sidebar_device()
    st.sidebar.divider()
    render_sidebar_connection()
    
    # メイン
    st.divider()
    
    # ノードマップ
    render_node_map()
    
    # 選択デバイス詳細
    if st.session_state.selected_device:
        st.divider()
        render_device_details()
    
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
