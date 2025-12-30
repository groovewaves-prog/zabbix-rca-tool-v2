import streamlit as st
import streamlit.components.v1 as components
import json
from typing import Dict, List, Set

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="トポロジービルダー - Zabbix RCA Tool",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== 定数 ====================
DEVICE_TYPES = {
    "ROUTER": {"color": "#667eea", "label": "Router"},
    "SWITCH": {"color": "#11998e", "label": "Switch"},
    "FIREWALL": {"color": "#eb3349", "label": "Firewall"},
    "SERVER": {"color": "#2193b0", "label": "Server"},
    "ACCESS_POINT": {"color": "#f7971e", "label": "AP"},
    "LOAD_BALANCER": {"color": "#4776E6", "label": "LB"},
    "STORAGE": {"color": "#834d9b", "label": "Storage"},
    "CLOUD": {"color": "#74ebd5", "label": "Cloud"},
    "PC": {"color": "#333333", "label": "PC"},
}

VENDORS = ["Cisco", "Juniper", "Fortinet", "Palo Alto", "Arista", "HPE", "Dell", "NetApp", "F5", "AWS", "Azure", "Other"]

# ==================== セッション状態 ====================
def init_session():
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    if "connections" not in st.session_state:
        st.session_state.connections = []
    if "editing_device" not in st.session_state:
        st.session_state.editing_device = None

# ==================== ロジック・計算 ====================
def calculate_layers() -> Dict[str, int]:
    """接続関係からレイヤーを自動計算"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return {}
    
    children = set()
    for conn in connections:
        if conn.get("type") == "uplink":
            children.add(conn["from"])
            
    root_nodes = [d for d in devices.keys() if d not in children]
    if not root_nodes and devices:
        root_nodes = [list(devices.keys())[0]]
        
    layers = {}
    queue = [(node, 1) for node in root_nodes]
    visited = set()
    
    children_map = {}
    for conn in connections:
        if conn.get("type") == "uplink":
            parent, child = conn["to"], conn["from"]
            if parent not in children_map:
                children_map[parent] = []
            children_map[parent].append(child)
            
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

def check_lineage(dev_a: str, dev_b: str) -> bool:
    """親子関係チェック（循環参照・矛盾防止）"""
    connections = st.session_state.connections
    
    parent_map = {}
    for conn in connections:
        if conn["type"] == "uplink":
            child = conn["from"]
            parent = conn["to"]
            if child not in parent_map: parent_map[child] = []
            parent_map[child].append(parent)

    def get_ancestors(node):
        ancestors = set()
        queue = [node]
        visited = set()
        while queue:
            curr = queue.pop(0)
            if curr in visited: continue
            visited.add(curr)
            parents = parent_map.get(curr, [])
            for p in parents:
                ancestors.add(p)
                queue.append(p)
        return ancestors

    ancestors_a = get_ancestors(dev_a)
    ancestors_b = get_ancestors(dev_b)

    if dev_b in ancestors_a or dev_a in ancestors_b:
        return True
    return False

# ==================== vis.js HTML ====================
def generate_visjs_html() -> str:
    """vis.jsのHTML生成"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return """<div style='padding:40px;text-align:center;color:#888;
                   background:#f5f5f5;border-radius:8px;'>
                   📍 デバイスを追加してください</div>"""
    
    layers = calculate_layers()
    
    nodes_data = []
    for dev_id, dev in devices.items():
        dev_type = dev.get("type", "SWITCH")
        style = DEVICE_TYPES.get(dev_type, DEVICE_TYPES["SWITCH"])
        vendor = dev.get("metadata", {}).get("vendor") or ""
        layer = layers.get(dev_id, 1)
        
        label = f"{dev_id}"
        if vendor:
            label += f"\\n({vendor})"
        
        nodes_data.append({
            "id": dev_id,
            "label": label,
            "color": {
                "background": style["color"], 
                "border": "#222",
                "highlight": {"border": "#222", "background": "#ffdd00"}
            },
            "font": {"color": "white", "size": 14, "face": "arial", "vadjust": 0},
            "shape": "box",
            "level": layer,
            "margin": 10,
            "shadow": True
        })
    
    edges_data = []
    for conn in connections:
        conn_type = conn.get("type", "uplink")
        
        if conn_type == "uplink":
            edges_data.append({
                "from": conn["to"], # Parent
                "to": conn["from"], # Child
                "arrows": "to",
                "color": {"color": "#555"},
                "width": 2,
            })
        else:
            edges_data.append({
                "from": conn["from"],
                "to": conn["to"],
                "color": {"color": "#f1c40f"}, 
                "dashes": [8, 8],
                "arrows": "",
                "width": 3,
            })
    
    nodes_json = json.dumps(nodes_data)
    edges_json = json.dumps(edges_data)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <style>
            body {{ margin:0; font-family: sans-serif; }}
            #network {{ width:100%; height:450px; background:#ffffff; border:1px solid #ddd; border-radius:8px; }}
        </style>
    </head>
    <body>
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
                        levelSeparation: 120,
                        nodeSpacing: 250, 
                        treeSpacing: 300,
                        blockShifting: true,
                        edgeMinimization: true,
                        parentCentralization: true
                    }}
                }},
                physics: {{ enabled: false }},
                interaction: {{
                    dragNodes: false,
                    dragView: true,
                    zoomView: true,
                    hover: true
                }},
                nodes: {{ borderWidth: 2 }}
            }};
            var network = new vis.Network(container, data, options);
            network.fit();
        </script>
    </body>
    </html>
    """

# ==================== ダイアログ (Modal) ====================
@st.dialog("接続設定")
def connection_dialog(source_id: str, mode: str):
    label = "下位(ダウンリンク)" if mode == "uplink" else "ピア(対等)"
    st.write(f"**{source_id}** からの **{label}** 接続先を選択してください。")
    
    # 【改修箇所】既に接続済み（親、子、既存ピア）のデバイスをリストアップして除外する
    connected_targets = set()
    for c in st.session_state.connections:
        # source_id が「from」側にある場合、相手は「to」
        if c["from"] == source_id:
            connected_targets.add(c["to"])
        # source_id が「to」側にある場合、相手は「from」
        if c["to"] == source_id:
            connected_targets.add(c["from"])
            
    # 自分自身と、既に接続済みのデバイスを除外してリスト化
    candidates = [d for d in st.session_state.devices.keys() 
                  if d != source_id and d not in connected_targets]
    
    if not candidates:
        st.warning("接続可能なデバイスがありません（全て接続済みか、他にデバイスがありません）。")
        if st.button("閉じる"):
            st.rerun()
        return

    target_id = st.selectbox("接続先デバイス", candidates)
    
    # 接続ボタン
    if st.button("接続を作成", type="primary", use_container_width=True):
        # 1. 念のための既存接続チェック（リスト除外しているので本来は不要だが安全策）
        exists = any(
            (c["from"] == source_id and c["to"] == target_id) or
            (c["from"] == target_id and c["to"] == source_id)
            for c in st.session_state.connections
        )
        
        # 2. 矛盾チェック
        lineage_conflict = False
        if mode == "peer":
            if check_lineage(source_id, target_id):
                lineage_conflict = True
        
        if exists:
            st.error("既に接続されています")
        elif lineage_conflict:
            st.error("⚠️ 論理矛盾: 親子関係にあるノード同士をピア接続することはできません。")
        else:
            if mode == "uplink":
                # Uplink: Child(from) -> Parent(to)
                # 操作は Parent(source) -> Child(target) なので、保存時は Child=target, Parent=source
                st.session_state.connections.append({
                    "from": target_id,
                    "to": source_id,
                    "type": "uplink"
                })
            else:
                st.session_state.connections.append({
                    "from": source_id,
                    "to": target_id,
                    "type": "peer"
                })
            st.success("接続しました")
            st.rerun()

# ==================== UIコンポーネント ====================

def render_add_device():
    """デバイス追加"""
    with st.expander("➕ デバイス追加", expanded=len(st.session_state.devices) == 0):
        c1, c2 = st.columns([3, 1])
        with c1:
            new_id = st.text_input("デバイスID", placeholder="例: Core-SW01", key="in_new_id").strip()
        with c2:
            st.write("")
            st.write("")
            if st.button("追加", type="primary", use_container_width=True):
                if new_id and new_id not in st.session_state.devices:
                    st.session_state.devices[new_id] = {
