import streamlit as st
import streamlit.components.v1 as components
import json
import statistics
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
    
    # 【追加】モジュール種別のマスタ定義 (初期値)
    if "module_master_list" not in st.session_state:
        st.session_state.module_master_list = ["LineCard", "Supervisor", "SFP+"]

# ==================== ロジック・計算 ====================
def calculate_layers() -> Dict[str, int]:
    """レイヤー計算（最長パス法）"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return {}
    
    layers = {d: 1 for d in devices}
    connected_nodes = set()
    
    uplinks = []
    peers = []
    
    for c in connections:
        connected_nodes.add(c['from'])
        connected_nodes.add(c['to'])
        if c['type'] == 'uplink':
            uplinks.append(c)
        else:
            peers.append(c)

    for _ in range(len(devices) + 2):
        changed = False
        for c in uplinks:
            parent = c['to']
            child = c['from']
            if parent in layers and child in layers:
                if layers[child] < layers[parent] + 1:
                    layers[child] = layers[parent] + 1
                    changed = True
        
        for c in peers:
            p1 = c['from']
            p2 = c['to']
            if p1 in layers and p2 in layers:
                max_layer = max(layers[p1], layers[p2])
                if layers[p1] != max_layer:
                    layers[p1] = max_layer
                    changed = True
                if layers[p2] != max_layer:
                    layers[p2] = max_layer
                    changed = True
        if not changed:
            break
            
    for d in devices:
        if d not in connected_nodes:
            layers[d] = 0
            
    return layers

def calculate_positions(layers: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    """重心法を用いた座標計算"""
    positions = {}
    connections = st.session_state.connections
    
    max_layer = max(layers.values()) if layers else 0
    
    child_to_parents = {}
    for c in connections:
        if c['type'] == 'uplink':
            child = c['from']
            parent = c['to']
            if child not in child_to_parents:
                child_to_parents[child] = []
            child_to_parents[child].append(parent)

    nodes_by_layer = {}
    for node, layer in layers.items():
        if layer not in nodes_by_layer:
            nodes_by_layer[layer] = []
        nodes_by_layer[layer].append(node)

    Y_SPACING = 150
    X_SPACING = 220

    for layer in range(max_layer + 1):
        if layer not in nodes_by_layer:
            continue
            
        nodes = nodes_by_layer[layer]
        
        if layer <= 1:
            nodes.sort()
        else:
            node_weights = []
            for node in nodes:
                parents = child_to_parents.get(node, [])
                parent_x_sum = 0
                valid_parents = 0
                for p in parents:
                    if p in positions:
                        parent_x_sum += positions[p]["x"]
                        valid_parents += 1
                
                if valid_parents > 0:
                    weight = parent_x_sum / valid_parents
                else:
                    weight = 0 
                node_weights.append((weight, node))
            
            node_weights.sort(key=lambda x: (x[0], x[1]))
            nodes = [n[1] for n in node_weights]

        count = len(nodes)
        total_width = (count - 1) * X_SPACING
        start_x = -total_width / 2
        
        for i, node in enumerate(nodes):
            x = int(start_x + (i * X_SPACING))
            y = int(layer * Y_SPACING)
            positions[node] = {"x": x, "y": y}
            
    return positions

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
    positions = calculate_positions(layers)
    
    nodes_data = []
    for dev_id, dev in devices.items():
        dev_type = dev.get("type", "SWITCH")
        style = DEVICE_TYPES.get(dev_type, DEVICE_TYPES["SWITCH"])
        vendor = dev.get("metadata", {}).get("vendor") or ""
        
        pos = positions.get(dev_id, {"x": 0, "y": 0})
        
        label = f"{dev_id}"
        if vendor:
            label += f"\\n({vendor})"
        
        nodes_data.append({
            "id": dev_id,
            "label": label,
            "x": pos["x"],
            "y": pos["y"],
            "color": {
                "background": style["color"], 
                "border": "#222",
                "highlight": {"border": "#222", "background": "#ffdd00"}
            },
            "font": {"color": "white", "size": 14, "face": "arial", "vadjust": 0},
            "shape": "box",
            "margin": 10,
            "shadow": True,
            "physics": False 
        })
    
    edges_data = []
    for conn in connections:
        conn_meta = conn.get("metadata", {})
        is_lag = conn_meta.get("lag_enabled", False)
        vlans = conn_meta.get("vlans", "")
        
        # 【機能追加】LAGの場合は線を太く青くする
        edge_color = "#3498db" if is_lag else "#555" # LAG=Blue, Normal=Gray
        edge_width = 5 if is_lag else 2
        
        # 【機能追加】VLAN情報があればラベル表示
        edge_label = f"VLAN: {vlans}" if vlans else ""
        
        base_edge = {
            "from": conn["from"],
            "to": conn["to"],
            "label": edge_label,
            "font": {"size": 10, "align": "middle", "background": "white"},
            "color": {"color": edge_color},
            "width": edge_width,
            "smooth": False
        }

        if conn["type"] == "uplink":
            # 親 -> 子 の矢印 (データ構造は from=子, to=親 なので to -> from)
            base_edge["from"] = conn["to"]
            base_edge["to"] = conn["from"]
            base_edge["arrows"] = "to"
        else:
            # ピア接続
            base_edge["color"]["color"] = "#f1c40f" if not is_lag else "#f39c12" # LAGの場合は濃いオレンジ
            base_edge["dashes"] = [8, 8] if not is_lag else False # LAGなら実線にするなどの変化も可能だが、ピアなので点線のまま色を変える
            base_edge["arrows"] = ""
            base_edge["width"] = 3 if not is_lag else 5
            
        edges_data.append(base_edge)
    
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
                layout: {{ hierarchical: {{ enabled: false }} }},
                physics: {{ enabled: false }},
                interaction: {{
                    dragNodes: true,
                    dragView: true,
                    zoomView: true,
                    hover: true
                }},
                nodes: {{ borderWidth: 2 }},
                edges: {{ smooth: false }}
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
            # 接続データの作成（metadata初期化）
            new_conn = {
                "from": target_id if mode == "uplink" else source_id,
                "to": source_id if mode == "uplink" else target_id,
                "type": mode,
                "metadata": {"lag_enabled": False, "vlans": ""}
            }
            if mode == "uplink":
                new_conn["from"] = target_id
                new_conn["to"] = source_id
            else:
                new_conn["from"] = source_id
                new_conn["to"] = target_id
                
            st.session_state.connections.append(new_conn)
            st.session_state.selected_devices = set()
            st.rerun()

@st.dialog("モジュール定義の管理")
def manage_modules_dialog():
    st.write("デバイスに追加可能なモジュールの種類を定義します。")
    
    # 現在のリスト表示と削除
    if st.session_state.module_master_list:
        st.markdown("##### 現在の定義済みモジュール")
        for i, mod_name in enumerate(st.session_state.module_master_list):
            c1, c2 = st.columns([4, 1])
            c1.text(f"・ {mod_name}")
            if c2.button("削除", key=f"del_mod_{i}"):
                st.session_state.module_master_list.pop(i)
                st.rerun()
    else:
        st.info("定義されているモジュールはありません。")

    st.markdown("---")
    st.markdown("##### 新規追加")
    new_mod = st.text_input("モジュール名称", placeholder="例: LineCard-10G")
    if st.button("追加", type="primary"):
        if new_mod and new_mod not in st.session_state.module_master_list:
            st.session_state.module_master_list.append(new_mod)
            st.success(f"{new_mod} を追加しました")
            st.rerun()
        elif new_mod in st.session_state.module_master_list:
            st.error("既に存在します")

@st.dialog("全データ削除")
def clear_data_dialog():
    st.warning("⚠️ **本当にすべてのデータを削除しますか？**\n\n作成したデバイスや接続設定はすべて失われます。この操作は元に戻せません。")
    if st.button("削除実行", type="primary", use_container_width=True):
        st.session_state.devices = {}
        st.session_state.connections = []
        st.session_state.editing_device = None
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
                            "hw_inventory": {"psu_count": 1, "fan_count": 0, "custom_modules": {}},
                        }
                    }
                    st.success(f"追加: {new_id}")
                    st.rerun()
                elif new_id in st.session_state.devices:
                    st.error("ID重複")

def render_device_list():
    """デバイス一覧・操作"""
    if not st.session_state.devices:
        return

    st.subheader("📋 デバイス操作")

    search_query = st.text_input("🔍 デバイス検索", placeholder="名前でフィルタ...", label_visibility="collapsed")

    connected_ids = set()
    for c in st.session_state.connections:
        connected_ids.add(c["from"])
        connected_ids.add(c["to"])

    layers = calculate_layers()
    all_devs = sorted(st.session_state.devices.keys(), key=lambda x: (layers.get(x, 1), x))
    
    if search_query:
        sorted_devs = [d for d in all_devs if search_query.lower() in d.lower()]
    else:
        sorted_devs = all_devs

    current_selected = []
    for dev_id in st.session_state.devices.keys():
        if st.session_state.get(f"chk_{dev_id}", False):
            current_selected.append(dev_id)
    
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

    with st.container(height=500):
        if not sorted_devs:
            st.write("該当するデバイスはありません。")

        for dev_id in sorted_devs:
            dev = st.session_state.devices[dev_id]
            meta = dev.get("metadata", {})
            hw = meta.get("hw_inventory", {})
            
            is_isolated = dev_id not in connected_ids
            
            c_check, c_card = st.columns([0.5, 6])
            
            with c_check:
                st.write("") 
                st.checkbox("", key=f"chk_{dev_id}")
            
            with c_card:
                with st.container(border=True):
                    st.markdown(f"**{dev_id}** (L{layers.get(dev_id,1)})")
                    info_badges = []
                    
                    if is_isolated:
                        info_badges.append("⚠️ 未接続")

                    if meta.get("vendor"): info_badges.append(meta["vendor"])
                    if meta.get("model"): info_badges.append(meta["model"])
                    
                    psu = hw.get("psu_count", 0)
                    if psu > 0: info_badges.append(f"⚡PSU:{psu}")
                    
                    # モジュール情報のバッジ表示
                    custom_mods = hw.get("custom_modules", {})
                    for m_name, m_count in custom_mods.items():
                        if m_count > 0:
                            info_badges.append(f"📦{m_name}:{m_count}")
                    
                    if info_badges:
                        st.caption(" | ".join(info_badges))
                    else:
                        st.caption("No details")

            if st.session_state.editing_device == dev_id:
                with st.container(border=True):
                    st.info(f"📝 **{dev_id}** を設定中...")
                    
                    with st.form(key=f"form_{dev_id}"):
                        tab1, tab2, tab3 = st.tabs(["基本情報", "ハードウェア/モジュール", "論理/ネットワーク"])
                        
                        # --- Tab 1: 基本情報 ---
                        with tab1:
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

                        # --- Tab 2: ハードウェア/モジュール (改修) ---
                        with tab2:
                            # 基本HW
                            h1, h2 = st.columns(2)
                            with h1:
                                new_psu = st.number_input("PSU数", min_value=0, value=hw.get("psu_count", 1))
                            with h2:
                                new_fan = st.number_input("FAN数", min_value=0, value=hw.get("fan_count", 0))
                            
                            st.divider()
                            # モジュール管理ボタン
                            c_m_head, c_m_btn = st.columns([3, 2])
                            c_m_head.markdown("##### 追加モジュール構成")
                            if c_m_btn.form_submit_button("🛠️ モジュール定義を追加/編集"):
                                manage_modules_dialog()
                            
                            # 動的入力フィールドの生成
                            current_custom_mods = hw.get("custom_modules", {})
                            new_custom_mods = {}
                            
                            if st.session_state.module_master_list:
                                cols = st.columns(2)
                                for i, mod_name in enumerate(st.session_state.module_master_list):
                                    with cols[i % 2]:
                                        val = st.number_input(f"{mod_name} 数", min_value=0, 
                                                              value=current_custom_mods.get(mod_name, 0),
                                                              key=f"num_{dev_id}_{mod_name}")
                                        if val > 0:
                                            new_custom_mods[mod_name] = int(val)
                            else:
                                st.caption("※ 定義されたモジュールがありません。上のボタンから定義を追加してください。")

                        # --- Tab 3: 論理/ネットワーク (改修) ---
                        with tab3:
                            st.markdown("##### 接続ごとの論理設定")
                            st.caption("このデバイスに関連する接続（リンク）の設定を行います。")
                            
                            # このデバイスに関連する接続を抽出
                            related_conns = []
                            for idx, c in enumerate(st.session_state.connections):
                                if c['from'] == dev_id or c['to'] == dev_id:
                                    related_conns.append((idx, c))
                            
                            if not related_conns:
                                st.info("接続されているリンクがありません。")
                            
                            # 接続ごとの設定UI
                            updated_conns_meta = {} # { index: metadata }
                            
                            for idx, c in related_conns:
                                target = c['to'] if c['from'] == dev_id else c['from']
                                link_type = "Uplink" if c['type'] == "uplink" else "Peer"
                                label = f"🔗 対 {target} ({link_type})"
                                
                                with st.expander(label, expanded=False):
                                    c_meta = c.get("metadata", {})
                                    
                                    # LAG設定
                                    is_lag = st.checkbox("LAG (Link Aggregation) 構成", 
                                                         value=c_meta.get("lag_enabled", False),
                                                         key=f"lag_{dev_id}_{idx}")
                                    
                                    # VLAN設定
                                    vlans = st.text_input("VLAN ID (カンマ区切り)", 
                                                          value=c_meta.get("vlans", ""),
                                                          placeholder="例: 10, 20, 100-105",
                                                          key=f"vlan_{dev_id}_{idx}")
                                    
                                    updated_conns_meta[idx] = {
                                        "lag_enabled": is_lag,
                                        "vlans": vlans
                                    }

                        st.markdown("---")
                        c_save, c_cancel = st.columns([1, 1])
                        with c_save:
                            if st.form_submit_button("💾 保存", type="primary", use_container_width=True):
                                # デバイス情報の更新
                                st.session_state.devices[dev_id]["type"] = new_type
                                st.session_state.devices[dev_id]["metadata"] = {
                                    "vendor": new_vend,
                                    "model": new_model,
                                    "location": new_loc,
                                    "hw_inventory": {
                                        "psu_count": int(new_psu),
                                        "fan_count": int(new_fan),
                                        "custom_modules": new_custom_mods
                                    }
                                }
                                
                                # 接続情報の更新 (Tab3での変更を反映)
                                for idx, meta in updated_conns_meta.items():
                                    st.session_state.connections[idx]["metadata"] = meta
                                
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
        filename_input = st.text_input("保存ファイル名", value="topology.json")
        if not filename_input.endswith(".json"):
            filename_input += ".json"

        export_data = {
            "topology": {},
            "connections": st.session_state.connections, 
            "module_master_list": st.session_state.module_master_list, # マスタも保存
            "metadata": {"version": "2.3"}
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
        st.download_button(
            label="📥 JSONダウンロード",
            data=json_str,
            file_name=filename_input,
            mime="application/json",
            type="primary"
        )

    with c2:
        st.write("") 
        st.write("")
        uploaded = st.file_uploader("📤 JSON読み込み", type=["json"])
        if uploaded:
            if st.button("適用", type="primary"):
                try:
                    data = json.load(uploaded)
                    topo = data.get("topology", {})
                    new_devs = {}
                    
                    # モジュールマスタの復元
                    if "module_master_list" in data:
                        st.session_state.module_master_list = data["module_master_list"]
                    
                    for d_id, d_val in topo.items():
                        new_devs[d_id] = {
                            "type": d_val.get("type", "SWITCH"),
                            "metadata": d_val.get("metadata", {})
                        }
                    
                    if "connections" in data:
                        st.session_state.connections = data["connections"]
                    else:
                        st.session_state.connections = [] # 旧形式ならここでよしなに変換が必要だが割愛
                            
                    st.session_state.devices = new_devs
                    st.success("読み込み完了")
                    st.rerun()
                except Exception as e:
                    st.error(f"エラー: {e}")
    
    st.markdown("---")
    if st.button("🗑️ 全データをクリア (初期化)", type="primary", use_container_width=True):
        clear_data_dialog()

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
        # 接続リストのフィルタリング
        layers = calculate_layers()
        all_devs = sorted(st.session_state.devices.keys(), key=lambda x: (layers.get(x, 1), x))
        current_selected = []
        for dev_id in all_devs:
            if st.session_state.get(f"chk_{dev_id}", False):
                current_selected.append(dev_id)
        
        all_conns = st.session_state.connections
        
        if current_selected:
            display_conns = [
                (i, c) for i, c in enumerate(all_conns)
                if c["from"] in current_selected or c["to"] in current_selected
            ]
            header_text = f"🔗 関連する接続 ({len(display_conns)})"
            is_expanded = True
        else:
            display_conns = [(i, c) for i, c in enumerate(all_conns)]
            header_text = f"🔗 全接続リスト ({len(display_conns)})"
            is_expanded = False

        if display_conns:
            with st.expander(header_text, expanded=is_expanded):
                if not current_selected and display_conns:
                     st.caption("※ 左側でデバイスを選択すると、関連する接続のみに絞り込まれます。")
                
                for i, c in display_conns:
                    col_c1, col_c2 = st.columns([6,1])
                    with col_c1:
                        # LAG状態などの表示
                        meta = c.get("metadata", {})
                        tags = ""
                        if meta.get("lag_enabled"): tags += " [LAG]"
                        if meta.get("vlans"): tags += f" [VLAN:{meta['vlans']}]"
                        
                        if c["type"] == "uplink":
                            st.markdown(f"**⬇️ 下位接続:** {c['to']} → {c['from']} {tags}")
                        else:
                            st.markdown(f"**↔️ ピア接続:** {c['from']} ↔ {c['to']} {tags}")
                    with col_c2:
                        if st.button("🗑️", key=f"del_conn_{i}"):
                            st.session_state.connections.pop(i)
                            st.rerun()
        else:
            if all_conns and current_selected:
                 st.info("選択されたデバイスに関連する接続はありません。")
        
        render_data_io()

if __name__ == "__main__":
    main()
