"""
Zabbix RCA Tool - トポロジービルダー
コネクタボタン式（↓→）のインタラクティブ接続
"""

import streamlit as st
import streamlit.components.v1 as components
import json
import os
from datetime import datetime
from typing import Dict, List

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="トポロジービルダー - Zabbix RCA Tool",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== 定数 ====================
DEVICE_TYPES = {
    "ROUTER": {"icon": "🔵", "color": "#667eea", "label": "ルーター"},
    "SWITCH": {"icon": "🟢", "color": "#11998e", "label": "スイッチ"},
    "FIREWALL": {"icon": "🔴", "color": "#eb3349", "label": "ファイアウォール"},
    "SERVER": {"icon": "🔷", "color": "#2193b0", "label": "サーバー"},
    "ACCESS_POINT": {"icon": "📡", "color": "#f7971e", "label": "AP"},
    "LOAD_BALANCER": {"icon": "⚖️", "color": "#4776E6", "label": "LB"},
    "STORAGE": {"icon": "💾", "color": "#834d9b", "label": "ストレージ"},
}

VENDORS = ["Cisco", "Juniper", "Fortinet", "Palo Alto", "Arista", "HPE", "Dell", "NetApp", "F5", "Other"]

STANDARD_MODULES = {
    "PSU": "電源", "FAN": "ファン", "SUP": "スーパバイザ", 
    "LC": "ラインカード", "CTRL": "コントローラ",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== セッション状態 ====================
def init_session():
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    if "connections" not in st.session_state:
        st.session_state.connections = []
    if "connect_mode" not in st.session_state:
        st.session_state.connect_mode = None  # {"from": "dev_id", "type": "uplink/peer"}

# ==================== レイヤー計算 ====================
def calculate_layers() -> Dict[str, int]:
    """接続関係からレイヤーを自動計算"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return {}
    
    parents = {}
    for conn in connections:
        if conn.get("type") == "uplink":
            child, parent = conn["from"], conn["to"]
            if child not in parents:
                parents[child] = []
            parents[child].append(parent)
    
    root_nodes = [d for d in devices.keys() if d not in parents]
    if not root_nodes:
        return {d: 1 for d in devices.keys()}
    
    children_map = {}
    for conn in connections:
        if conn.get("type") == "uplink":
            parent, child = conn["to"], conn["from"]
            if parent not in children_map:
                children_map[parent] = []
            children_map[parent].append(child)
    
    layers = {}
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
    
    for d in devices.keys():
        if d not in layers:
            layers[d] = 1
    
    return layers

# ==================== vis.js HTML ====================
def generate_visjs_html() -> str:
    """vis.jsのHTML生成（自由配置可能）"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return """<div style='padding:40px;text-align:center;color:#888;
                   background:#f5f5f5;border-radius:8px;'>
                   📍 デバイスを追加してください</div>"""
    
    layers = calculate_layers()
    
    # ノードデータ
    nodes_data = []
    for dev_id, dev in devices.items():
        dev_type = dev.get("type", "SWITCH")
        style = DEVICE_TYPES.get(dev_type, {"color": "#6c757d", "icon": "⬜"})
        vendor = dev.get("metadata", {}).get("vendor") or ""
        layer = layers.get(dev_id, 1)
        
        label = dev_id
        if vendor:
            label += f"\\n{vendor}"
        
        nodes_data.append({
            "id": dev_id,
            "label": label,
            "color": {"background": style["color"], "border": "#333"},
            "font": {"color": "white", "size": 12},
            "shape": "box",
            "margin": {"top": 10, "bottom": 10, "left": 15, "right": 15},
            "level": layer,
        })
    
    # エッジデータ
    edges_data = []
    for i, conn in enumerate(connections):
        conn_type = conn.get("type", "uplink")
        
        if conn_type == "uplink":
            edges_data.append({
                "from": conn["to"],
                "to": conn["from"],
                "arrows": "to",
                "color": "#555",
                "width": 2,
            })
        else:
            edges_data.append({
                "from": conn["from"],
                "to": conn["to"],
                "color": "#ff9800",
                "dashes": True,
                "width": 2,
            })
    
    nodes_json = json.dumps(nodes_data)
    edges_json = json.dumps(edges_data)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <style>
            body {{ margin:0; font-family: Arial, sans-serif; }}
            #network {{ width:100%; height:350px; background:#fafafa; border:1px solid #ddd; border-radius:8px; }}
            .legend {{ padding:8px; font-size:11px; color:#666; display:flex; gap:20px; }}
        </style>
    </head>
    <body>
        <div class="legend">
            <span>━ 上下接続（階層）</span>
            <span style="color:#ff9800;">┅ 左右接続（冗長）</span>
            <span style="color:#999;">ドラッグで移動可能</span>
        </div>
        <div id="network"></div>
        <script>
            var nodes = new vis.DataSet({nodes_json});
            var edges = new vis.DataSet({edges_json});
            
            var container = document.getElementById('network');
            var data = {{ nodes: nodes, edges: edges }};
            var options = {{
                layout: {{
                    hierarchical: {{
                        enabled: true,
                        direction: 'UD',
                        sortMethod: 'directed',
                        levelSeparation: 80,
                        nodeSpacing: 120,
                    }}
                }},
                physics: {{ enabled: false }},
                interaction: {{
                    dragNodes: true,
                    dragView: true,
                    zoomView: true,
                }},
                nodes: {{ borderWidth: 2, shadow: true }},
                edges: {{ smooth: {{ type: 'cubicBezier' }} }}
            }};
            
            var network = new vis.Network(container, data, options);
        </script>
    </body>
    </html>
    """

# ==================== ノードマップ ====================
def render_node_map():
    """ノードマップ表示"""
    html = generate_visjs_html()
    components.html(html, height=400)

# ==================== デバイス追加ダイアログ ====================
def render_add_device():
    """デバイス追加"""
    
    with st.expander("➕ デバイス追加", expanded=len(st.session_state.devices) == 0):
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        
        with col1:
            new_id = st.text_input("デバイスID", placeholder="CORE_SW_01", key="new_dev_id")
        
        with col2:
            new_type = st.selectbox(
                "タイプ",
                list(DEVICE_TYPES.keys()),
                format_func=lambda x: f"{DEVICE_TYPES[x]['icon']} {DEVICE_TYPES[x]['label']}",
                key="new_dev_type"
            )
        
        with col3:
            new_vendor = st.selectbox("ベンダー", [""] + VENDORS, key="new_dev_vendor")
        
        with col4:
            st.write("")  # スペーサー
            st.write("")
            if st.button("追加", type="primary", key="add_dev_btn"):
                if not new_id:
                    st.error("IDを入力")
                elif new_id in st.session_state.devices:
                    st.error("ID重複")
                else:
                    st.session_state.devices[new_id] = {
                        "type": new_type,
                        "metadata": {"vendor": new_vendor or None},
                        "modules": [],
                    }
                    st.rerun()

# ==================== 接続モード表示 ====================
def render_connect_mode():
    """接続モード中の表示"""
    
    if st.session_state.connect_mode:
        mode = st.session_state.connect_mode
        from_dev = mode["from"]
        conn_type = mode["type"]
        
        type_label = "↓ 下位へ接続" if conn_type == "uplink" else "→ ピア接続"
        type_color = "#2196f3" if conn_type == "uplink" else "#ff9800"
        
        st.markdown(f"""
        <div style="background:{type_color}; color:white; padding:12px 20px; 
                    border-radius:8px; margin:10px 0; display:flex; 
                    align-items:center; justify-content:space-between;">
            <span><strong>🔗 接続モード:</strong> {from_dev} から {type_label}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # 接続先候補
        other_devices = [d for d in st.session_state.devices.keys() if d != from_dev]
        
        if other_devices:
            cols = st.columns(len(other_devices) + 1)
            
            for i, dev_id in enumerate(other_devices):
                # 既存接続チェック
                already_connected = any(
                    (c["from"] == from_dev and c["to"] == dev_id) or
                    (c["from"] == dev_id and c["to"] == from_dev)
                    for c in st.session_state.connections
                )
                
                with cols[i]:
                    style = DEVICE_TYPES.get(
                        st.session_state.devices[dev_id]["type"], 
                        {"icon": "⬜"}
                    )
                    
                    btn_label = f"{style['icon']} {dev_id}"
                    if already_connected:
                        btn_label += " ✓"
                    
                    if st.button(btn_label, key=f"target_{dev_id}", 
                                disabled=already_connected,
                                use_container_width=True):
                        # 接続作成
                        if conn_type == "uplink":
                            # from_devが下位、選択したdev_idが上位
                            st.session_state.connections.append({
                                "from": from_dev,
                                "to": dev_id,
                                "type": "uplink",
                            })
                        else:
                            st.session_state.connections.append({
                                "from": from_dev,
                                "to": dev_id,
                                "type": "peer",
                            })
                        
                        st.session_state.connect_mode = None
                        st.rerun()
            
            with cols[-1]:
                if st.button("❌ キャンセル", key="cancel_connect", use_container_width=True):
                    st.session_state.connect_mode = None
                    st.rerun()
        else:
            st.warning("接続先のデバイスがありません")
            if st.button("キャンセル"):
                st.session_state.connect_mode = None
                st.rerun()

# ==================== デバイスカード ====================
def render_device_cards():
    """デバイスカード一覧（コネクタボタン付き）"""
    
    if not st.session_state.devices:
        return
    
    st.markdown("### 📋 デバイス一覧")
    st.caption("↓ = 下位デバイスへ接続（階層）、→ = ピア接続（冗長）")
    
    layers = calculate_layers()
    
    # レイヤーごとにグループ化
    layer_groups = {}
    for dev_id in st.session_state.devices.keys():
        layer = layers.get(dev_id, 1)
        if layer not in layer_groups:
            layer_groups[layer] = []
        layer_groups[layer].append(dev_id)
    
    # レイヤーごとに表示
    for layer in sorted(layer_groups.keys()):
        st.markdown(f"**Layer {layer}**")
        
        devices_in_layer = layer_groups[layer]
        cols = st.columns(min(len(devices_in_layer), 4))
        
        for i, dev_id in enumerate(devices_in_layer):
            dev = st.session_state.devices[dev_id]
            style = DEVICE_TYPES.get(dev["type"], {"icon": "⬜", "color": "#6c757d", "label": "?"})
            vendor = dev.get("metadata", {}).get("vendor") or ""
            
            with cols[i % 4]:
                # カードコンテナ
                with st.container(border=True):
                    # ヘッダー行
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.markdown(f"**{style['icon']} {dev_id}**")
                        if vendor:
                            st.caption(vendor)
                    with c2:
                        if st.button("🗑️", key=f"del_{dev_id}"):
                            del st.session_state.devices[dev_id]
                            st.session_state.connections = [
                                c for c in st.session_state.connections
                                if c["from"] != dev_id and c["to"] != dev_id
                            ]
                            st.rerun()
                    
                    # コネクタボタン行
                    b1, b2 = st.columns(2)
                    
                    with b1:
                        # 下位接続ボタン（↓）
                        disabled = st.session_state.connect_mode is not None
                        if st.button("↓ 下位へ", key=f"down_{dev_id}", 
                                    disabled=disabled,
                                    use_container_width=True):
                            st.session_state.connect_mode = {
                                "from": dev_id,
                                "type": "uplink",
                            }
                            st.rerun()
                    
                    with b2:
                        # ピア接続ボタン（→）
                        if st.button("→ ピア", key=f"peer_{dev_id}",
                                    disabled=disabled,
                                    use_container_width=True):
                            st.session_state.connect_mode = {
                                "from": dev_id,
                                "type": "peer",
                            }
                            st.rerun()
                    
                    # 接続情報表示
                    uplinks = [c["to"] for c in st.session_state.connections 
                              if c["from"] == dev_id and c["type"] == "uplink"]
                    downlinks = [c["from"] for c in st.session_state.connections 
                                if c["to"] == dev_id and c["type"] == "uplink"]
                    peers = [c["to"] if c["from"] == dev_id else c["from"] 
                            for c in st.session_state.connections 
                            if c["type"] == "peer" and (c["from"] == dev_id or c["to"] == dev_id)]
                    
                    conn_parts = []
                    if uplinks:
                        conn_parts.append(f"↑{','.join(uplinks)}")
                    if downlinks:
                        conn_parts.append(f"↓{','.join(downlinks)}")
                    if peers:
                        conn_parts.append(f"↔{','.join(peers)}")
                    
                    if conn_parts:
                        st.caption(" ".join(conn_parts))

# ==================== 接続管理 ====================
def render_connection_manager():
    """接続削除"""
    
    if not st.session_state.connections:
        return
    
    with st.expander(f"🔗 接続一覧 ({len(st.session_state.connections)}件)"):
        for i, conn in enumerate(st.session_state.connections):
            icon = "↓" if conn["type"] == "uplink" else "↔"
            col1, col2 = st.columns([5, 1])
            
            with col1:
                if conn["type"] == "uplink":
                    st.caption(f"{icon} {conn['to']} → {conn['from']}")
                else:
                    st.caption(f"{icon} {conn['from']} ↔ {conn['to']}")
            
            with col2:
                if st.button("✕", key=f"del_conn_{i}"):
                    st.session_state.connections.pop(i)
                    st.rerun()

# ==================== エクスポート ====================
def render_export():
    """エクスポート"""
    
    if not st.session_state.devices:
        return
    
    with st.expander("📤 保存/エクスポート"):
        layers = calculate_layers()
        
        topology = {}
        for dev_id, dev in st.session_state.devices.items():
            parent_ids = [c["to"] for c in st.session_state.connections
                         if c["from"] == dev_id and c["type"] == "uplink"]
            
            topology[dev_id] = {
                "type": dev["type"],
                "layer": layers.get(dev_id, 1),
                "parent_id": parent_ids[0] if parent_ids else None,
                "parent_ids": parent_ids,
                "metadata": dev.get("metadata", {}),
                "modules": dev.get("modules", []),
            }
        
        # 冗長グループ
        redundancy_groups = {}
        peer_conns = [c for c in st.session_state.connections if c["type"] == "peer"]
        if peer_conns:
            visited = set()
            gid = 1
            for conn in peer_conns:
                members = {conn["from"], conn["to"]}
                for other in peer_conns:
                    if other["from"] in members or other["to"] in members:
                        members.update([other["from"], other["to"]])
                if not members.issubset(visited):
                    redundancy_groups[f"PEER_{gid}"] = {"type": "peer", "members": list(members)}
                    visited.update(members)
                    gid += 1
        
        full_data = {
            "topology": topology,
            "connections": st.session_state.connections,
            "redundancy_groups": redundancy_groups,
            "metadata": {"created_at": datetime.now().isoformat()},
        }
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("デバイス", len(topology))
        with col2:
            st.metric("接続", len(st.session_state.connections))
        with col3:
            st.metric("冗長G", len(redundancy_groups))
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📥 JSON", json.dumps(full_data, ensure_ascii=False, indent=2),
                              "topology.json", use_container_width=True)
        with col2:
            if st.button("💾 保存", type="primary", use_container_width=True):
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(os.path.join(DATA_DIR, "topology.json"), "w", encoding="utf-8") as f:
                    json.dump(topology, f, ensure_ascii=False, indent=2)
                with open(os.path.join(DATA_DIR, "full_topology.json"), "w", encoding="utf-8") as f:
                    json.dump(full_data, f, ensure_ascii=False, indent=2)
                st.success("✅ 保存完了")

# ==================== インポート ====================
def render_import():
    """インポート"""
    
    with st.expander("📥 インポート"):
        uploaded = st.file_uploader("JSON", type=["json"], key="import")
        
        if uploaded:
            try:
                data = json.load(uploaded)
                topology = data.get("topology", data)
                connections = data.get("connections", [])
                
                if st.button(f"インポート ({len(topology)}台)"):
                    st.session_state.devices = {
                        dev_id: {
                            "type": dev.get("type", "SWITCH"),
                            "metadata": dev.get("metadata", {}),
                            "modules": dev.get("modules", []),
                        }
                        for dev_id, dev in topology.items()
                    }
                    
                    if connections:
                        st.session_state.connections = connections
                    else:
                        st.session_state.connections = []
                        for dev_id, dev in topology.items():
                            for parent in dev.get("parent_ids", []):
                                st.session_state.connections.append({
                                    "from": dev_id, "to": parent, "type": "uplink"
                                })
                    st.rerun()
            except Exception as e:
                st.error(str(e))

# ==================== メイン ====================
def main():
    init_session()
    
    st.title("🔧 トポロジービルダー")
    
    # デバイス追加
    render_add_device()
    
    # ノードマップ
    render_node_map()
    
    # 接続モード中
    render_connect_mode()
    
    # デバイスカード
    render_device_cards()
    
    st.divider()
    
    # 下部パネル
    col1, col2 = st.columns(2)
    with col1:
        render_connection_manager()
    with col2:
        render_export()
        render_import()

if __name__ == "__main__":
    main()
