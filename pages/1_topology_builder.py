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

# ==================== 定数・設定 ====================
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
    if "selected_devices" not in st.session_state:
        st.session_state.selected_devices = set()

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
    """親子関係チェック"""
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

def check_cycle_for_uplink(parent: str, child: str) -> bool:
    """循環参照チェック"""
    connections = st.session_state.connections
    parent_map = {}
    for conn in connections:
        if conn["type"] == "uplink":
            c = conn["from"]
            p = conn["to"]
            if c not in parent_map: parent_map[c] = []
            parent_map[c].append(p)

    queue = [parent]
    visited = set()
    while queue:
        curr = queue.pop(0)
        if curr == child:
            return True
        if curr in visited:
            continue
        visited.add(curr)
        for p in parent_map.get(curr, []):
            queue.append(p)
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
                "constraint": False
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
                        levelSeparation: 150,
                        nodeSpacing: 200, 
                        treeSpacing: 250,
                        blockShifting: true,
                        edgeMinimization: true,
                        parentCentralization: true,
                        shakeTowards: 'roots'
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
    
    connected_targets = set()
    for c in st.session_state.connections:
        if c["from"] == source_id:
            connected_targets.add(c["to"])
        if c["to"] == source_id:
            connected_targets.add(c["from"])
    
    layers = calculate_layers()
    source_layer = layers.get(source_id, 1)
    
    candidates = []
    for d in st.session_state.devices.keys():
        if d == source_id or d in connected_targets:
            continue
        
        if mode == "peer":
            if check_lineage(source_id, d):
                continue
            if layers.get(d, 1) != source_layer:
                continue
        
        if mode == "uplink":
            if check_cycle_for_uplink(source_id, d):
                continue

        candidates.append(d)
    
    if not candidates:
        st.warning("接続可能な候補デバイスがありません。")
        if st.button("閉じる"):
            st.rerun()
        return

    target_id = st.selectbox("接続先デバイス", candidates)
    
    if st.button("接続を作成", type="primary", use_container_width=True):
        exists = any(
            (c["from"] == source_id and c["to"] == target_id) or
            (c["from"] == target_id and c["to"] == source_id)
            for c in st.session_state.connections
        )
        
        error_msg = None
        if exists:
            error_msg = "既に接続されています"
        elif mode == "peer" and check_lineage(source_id, target_id):
            error_msg = "親子関係にあるノード同士をピア接続することはできません。"
        elif mode == "uplink" and check_cycle_for_uplink(source_id, target_id):
            error_msg = "循環参照（ループ）が発生するため接続できません。"
            
        if error_msg:
            st.error(error_msg)
        else:
            if mode == "uplink":
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
            # 操作完了時は選択状態を解除
            st.session_state.selected_devices = set()
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
                        "type": "SWITCH", 
                        "metadata": {
                            "vendor": "",
                            "model": "",
                            "location": "",
                            "hw_inventory": {"psu_count": 1, "fan_count": 0}
                        }
                    }
                    st.success(f"追加: {new_id}")
                    st.rerun()
                elif new_id in st.session_state.devices:
                    st.error("ID重複")

def render_device_list():
    """デバイス一覧・操作 (チェックボックス式 + Action Panel)"""
    if not st.session_state.devices:
        return

    # 【改修箇所】ソート順を「レイヤー(小->大) > 名前」のみに変更
    layers = calculate_layers()
    sorted_devs = sorted(st.session_state.devices.keys(), key=lambda x: (
        layers.get(x, 1), 
        x
    ))

    # チェックボックスの状態収集
    current_selected = []
    for dev_id in sorted_devs:
        if st.session_state.get(f"chk_{dev_id}", False):
            current_selected.append(dev_id)
    
    # --- Action Panel (画面上部に固定的に配置される操作エリア) ---
    st.markdown("### 📋 デバイス操作")
    
    with st.container(border=True):
        if not current_selected:
            st.info("👇 下のリストから操作したいデバイスにチェックを入れてください")
        else:
            sel_str = ", ".join(current_selected)
            st.markdown(f"**選択中:** `{sel_str}`")
            
            ac1, ac2, ac3, ac4 = st.columns(4)
            is_single = (len(current_selected) == 1)
            target_id = current_selected[0] if is_single else None
            
            with ac1:
                if st.button("📝 詳細・編集", disabled=not is_single, use_container_width=True):
                    st.session_state.editing_device = target_id
                    st.rerun()
            with ac2:
                if st.button("⬇️ 下位接続", disabled=not is_single, use_container_width=True):
                    connection_dialog(target_id, "uplink")
            with ac3:
                if st.button("↔️ ピア接続", disabled=not is_single, use_container_width=True):
                    connection_dialog(target_id, "peer")
            with ac4:
                if st.button("🗑️ 削除", type="primary", use_container_width=True):
                    for d_id in current_selected:
                        if d_id in st.session_state.devices:
                            del st.session_state.devices[d_id]
                            st.session_state.connections = [c for c in st.session_state.connections 
                                                          if c["from"] != d_id and c["to"] != d_id]
                    st.session_state.editing_device = None
                    st.rerun()
            
            if not is_single:
                st.caption("※「接続」や「編集」は、1つのデバイスのみ選択している場合に有効になります。")

    # --- デバイスリスト (スクロール可能) ---
    with st.container(height=500):
        for dev_id in sorted_devs:
            dev = st.session_state.devices[dev_id]
            meta = dev.get("metadata", {})
            hw = meta.get("hw_inventory", {})
            
            c_check, c_card = st.columns([0.5, 6])
            
            with c_check:
                st.write("") 
                st.checkbox("", key=f"chk_{dev_id}")
            
            with c_card:
                with st.container(border=True):
                    st.markdown(f"**{dev_id}** (L{layers.get(dev_id,1)})")
                    info_badges = []
                    if meta.get("vendor"): info_badges.append(meta["vendor"])
                    if meta.get("model"): info_badges.append(meta["model"])
                    psu = hw.get("psu_count", 0)
                    fan = hw.get("fan_count", 0)
                    if psu > 0: info_badges.append(f"⚡PSU:{psu}")
                    if fan > 0: info_badges.append(f"💨FAN:{fan}")
                    
                    if info_badges:
                        st.caption(" | ".join(info_badges))
                    else:
                        st.caption("No details")

            # 編集パネル
            if st.session_state.editing_device == dev_id:
                with st.container(border=True):
                    st.info(f"📝 **{dev_id}** を編集中...")
                    with st.form(key=f"form_{dev_id}"):
                        row1_c1, row1_c2 = st.columns(2)
                        with row1_c1:
                            curr_type = dev.get("type", "SWITCH")
                            new_type = st.selectbox("Type", list(DEVICE_TYPES.keys()), 
                                                    index=list(DEVICE_TYPES.keys()).index(curr_type) if curr_type in DEVICE_TYPES else 0)
                        with row1_c2:
                            curr_vend = meta.get("vendor", "")
                            new_vend = st.selectbox("Vendor", [""] + VENDORS, 
                                                    index=(VENDORS.index(curr_vend)+1) if curr_vend in VENDORS else 0)

                        row2_c1, row2_c2 = st.columns(2)
                        with row2_c1:
                            new_model = st.text_input("Model", value=meta.get("model", ""))
                        with row2_c2:
                            new_loc = st.text_input("Location", value=meta.get("location", ""))

                        h1, h2 = st.columns(2)
                        with h1:
                            new_psu = st.number_input("PSU数", min_value=0, value=hw.get("psu_count", 1))
                        with h2:
                            new_fan = st.number_input("FAN数", min_value=0, value=hw.get("fan_count", 0))

                        c_save, c_cancel = st.columns([1, 1])
                        with c_save:
                            if st.form_submit_button("💾 保存", type="primary", use_container_width=True):
                                st.session_state.devices[dev_id]["type"] = new_type
                                st.session_state.devices[dev_id]["metadata"] = {
                                    "vendor": new_vend,
                                    "model": new_model,
                                    "location": new_loc,
                                    "hw_inventory": {"psu_count": int(new_psu), "fan_count": int(new_fan)}
                                }
                                st.session_state.editing_device = None
                                st.rerun()
                        with c_cancel:
                            if st.form_submit_button("キャンセル", use_container_width=True):
                                st.session_state.editing_device = None
                                st.rerun()

def render_data_io():
    """JSON Import/Export"""
    st.divider()
    st.subheader("💾 データ管理")
    
    c1, c2 = st.columns(2)
    with c1:
        export_data = {
            "topology": {},
            "redundancy_groups": {},
            "metadata": {"version": "2.0"}
        }
        layers = calculate_layers()
        for d_id, d_data in st.session_state.devices.items():
            parents = [c["to"] for c in st.session_state.connections 
                      if c["from"] == d_id and c["type"] == "uplink"]
            
            export_data["topology"][d_id] = {
                "type": d_data["type"],
                "layer": layers.get(d_id, 1),
                "parent_id": parents[0] if parents else None,
                "parent_ids": parents,
                "metadata": d_data["metadata"]
            }
        
        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
        st.download_button("📥 JSONダウンロード", json_str, "full_topology.json", "application/json", type="primary")

    with c2:
        uploaded = st.file_uploader("📤 JSON読み込み", type=["json"])
        if uploaded:
            if st.button("適用", type="primary"):
                try:
                    data = json.load(uploaded)
                    topo = data.get("topology", {})
                    new_devs = {}
                    new_conns = []
                    
                    for d_id, d_val in topo.items():
                        new_devs[d_id] = {
                            "type": d_val.get("type", "SWITCH"),
                            "metadata": d_val.get("metadata", {})
                        }
                        p_ids = d_val.get("parent_ids", [])
                        if not p_ids and d_val.get("parent_id"):
                            p_ids = [d_val.get("parent_id")]
                        for p_id in p_ids:
                            new_conns.append({"from": d_id, "to": p_id, "type": "uplink"})
                            
                    st.session_state.devices = new_devs
                    st.session_state.connections = new_conns
                    st.success("読み込み完了")
                    st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")

# ==================== メイン ====================
def main():
    init_session()
    
    st.title("🔧 トポロジービルダー")
    
    components.html(generate_visjs_html(), height=480)
    
    col_left, col_right = st.columns([1, 1])
    with col_left:
        render_add_device()
        render_device_list()
        
    with col_right:
        if st.session_state.connections:
            with st.expander(f"🔗 接続リスト ({len(st.session_state.connections)})"):
                for i, c in enumerate(st.session_state.connections):
                    col_c1, col_c2 = st.columns([6,1])
                    with col_c1:
                        if c["type"] == "uplink":
                            st.markdown(f"**⬇️ 下位接続:** {c['to']} ← {c['from']}")
                        else:
                            st.markdown(f"**↔️ ピア接続:** {c['from']} ↔ {c['to']}")
                    with col_c2:
                        if st.button("🗑️", key=f"del_conn_{i}"):
                            st.session_state.connections.pop(i)
                            st.rerun()
        
        render_data_io()

if __name__ == "__main__":
    main()
