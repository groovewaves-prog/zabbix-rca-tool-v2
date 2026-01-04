import streamlit as st
import streamlit.components.v1 as components
import json
from typing import Dict, List, Set

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="トポロジービルダー - Zabbix RCA Tool",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 初期定数 (デフォルト値) ====================
DEFAULT_DEVICE_TYPES = [
    "ROUTER", "SWITCH", "FIREWALL", "SERVER", "ACCESS_POINT", 
    "LOAD_BALANCER", "STORAGE", "CLOUD", "PC"
]

TYPE_COLORS = {
    "ROUTER": "#667eea", "SWITCH": "#11998e", "FIREWALL": "#eb3349",
    "SERVER": "#2193b0", "ACCESS_POINT": "#f7971e", "LOAD_BALANCER": "#4776E6",
    "STORAGE": "#834d9b", "CLOUD": "#74ebd5", "PC": "#333333"
}

DEFAULT_VENDORS = [
    "Cisco", "Juniper", "Fortinet", "Palo Alto", "Arista", 
    "HPE", "Dell", "NetApp", "F5", "AWS", "Azure", "Linux", "Windows", "Other"
]

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
    
    if "master_device_types" not in st.session_state:
        st.session_state.master_device_types = DEFAULT_DEVICE_TYPES.copy()
    if "master_vendors" not in st.session_state:
        st.session_state.master_vendors = DEFAULT_VENDORS.copy()
    if "module_master_list" not in st.session_state:
        st.session_state.module_master_list = ["LineCard", "Supervisor", "SFP+"]
        
    if "site_name" not in st.session_state:
        st.session_state.site_name = "Tokyo-HQ"
    
    # 【修正】ダイアログ制御用フラグを追加
    if "pending_dialog" not in st.session_state:
        st.session_state.pending_dialog = None
    if "pending_dialog_device" not in st.session_state:
        st.session_state.pending_dialog_device = None

# ==================== ロジック・計算 ====================
def calculate_layers() -> Dict[str, int]:
    devices = st.session_state.devices
    connections = st.session_state.connections
    if not devices: return {}
    
    layers = {d: 1 for d in devices}
    connected_nodes = set()
    uplinks = [c for c in connections if c['type'] == 'uplink']
    peers = [c for c in connections if c['type'] == 'peer']
    
    for c in connections:
        connected_nodes.add(c['from'])
        connected_nodes.add(c['to'])

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
        if not changed: break
            
    for d in devices:
        if d not in connected_nodes: layers[d] = 0
    return layers

def calculate_positions(layers: Dict[str, int]) -> Dict[str, Dict[str, int]]:
    positions = {}
    connections = st.session_state.connections
    max_layer = max(layers.values()) if layers else 0
    
    child_to_parents = {}
    for c in connections:
        if c['type'] == 'uplink':
            child = c['from']
            parent = c['to']
            if child not in child_to_parents: child_to_parents[child] = []
            child_to_parents[child].append(parent)

    nodes_by_layer = {}
    for node, layer in layers.items():
        if layer not in nodes_by_layer: nodes_by_layer[layer] = []
        nodes_by_layer[layer].append(node)

    Y_SPACING = 150
    X_SPACING = 220

    for layer in range(max_layer + 1):
        if layer not in nodes_by_layer: continue
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
                weight = (parent_x_sum / valid_parents) if valid_parents > 0 else 0
                node_weights.append((weight, node))
            
            node_weights.sort(key=lambda x: (x[0], x[1]))
            nodes = [n[1] for n in node_weights]

        count = len(nodes)
        total_width = (count - 1) * X_SPACING
        start_x = -total_width / 2
        
        for i, node in enumerate(nodes):
            positions[node] = {"x": int(start_x + (i * X_SPACING)), "y": int(layer * Y_SPACING)}
            
    return positions

def check_lineage(dev_a: str, dev_b: str) -> bool:
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
    return dev_b in ancestors_a or dev_a in ancestors_b

def check_cycle_for_uplink(parent: str, child: str) -> bool:
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
        if curr == child: return True
        if curr in visited: continue
        visited.add(curr)
        for p in parent_map.get(curr, []): queue.append(p)
    return False

# ==================== vis.js HTML ====================
def generate_visjs_html() -> str:
    devices = st.session_state.devices
    connections = st.session_state.connections
    if not devices:
        return "<div style='padding:40px;text-align:center;color:#888;background:#f5f5f5;border-radius:8px;'>📍 デバイスを追加してください</div>"
    
    layers = calculate_layers()
    positions = calculate_positions(layers)
    
    nodes_data = []
    for dev_id, dev in devices.items():
        dev_type = dev.get("type", "SWITCH")
        color = TYPE_COLORS.get(dev_type, "#999999")
        vendor = dev.get("metadata", {}).get("vendor") or ""
        
        pos = positions.get(dev_id, {"x": 0, "y": 0})
        label = f"{dev_id}"
        if vendor: label += f"\\n({vendor})"
        
        nodes_data.append({
            "id": dev_id, "label": label, "x": pos["x"], "y": pos["y"],
            "color": {"background": color, "border": "#222", "highlight": {"border": "#222", "background": "#ffdd00"}},
            "font": {"color": "white", "size": 14, "face": "arial", "vadjust": 0},
            "shape": "box", "margin": 10, "shadow": True, "physics": False 
        })
    
    edges_data = []
    for conn in connections:
        conn_meta = conn.get("metadata", {})
        is_lag = conn_meta.get("lag_enabled", False)
        vlans = conn_meta.get("vlans", "")
        edge_color = "#3498db" if is_lag else "#555"
        edge_width = 5 if is_lag else 2
        edge_label = f"VLAN: {vlans}" if vlans else ""
        
        base_edge = {
            "from": conn["from"], "to": conn["to"], "label": edge_label,
            "font": {"size": 10, "align": "middle", "background": "white"},
            "color": {"color": edge_color}, "width": edge_width, "smooth": False
        }
        if conn["type"] == "uplink":
            base_edge["from"] = conn["to"]; base_edge["to"] = conn["from"]; base_edge["arrows"] = "to"
        else:
            base_edge["color"]["color"] = "#f1c40f" if not is_lag else "#f39c12"
            base_edge["dashes"] = [8, 8] if not is_lag else False
            base_edge["arrows"] = ""
            base_edge["width"] = 3 if not is_lag else 5
        edges_data.append(base_edge)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <style>body {{ margin:0; }} #network {{ width:100%; height:450px; background:#ffffff; border:1px solid #ddd; border-radius:8px; }}</style>
    </head>
    <body>
        <div id="network"></div>
        <script>
            var nodes = new vis.DataSet({json.dumps(nodes_data)});
            var edges = new vis.DataSet({json.dumps(edges_data)});
            var container = document.getElementById('network');
            var data = {{ nodes: nodes, edges: edges }};
            var options = {{
                layout: {{ hierarchical: {{ enabled: false }} }},
                physics: {{ enabled: false }},
                interaction: {{ dragNodes: true, zoomView: true, hover: true }},
                nodes: {{ borderWidth: 2 }},
                edges: {{ smooth: false }}
            }};
            var network = new vis.Network(container, data, options);
            network.fit();
        </script>
    </body>
    </html>
    """

# ==================== ダイアログ ====================
@st.dialog("接続設定")
def connection_dialog(source_id: str, mode: str):
    label = "下位(ダウンリンク)" if mode == "uplink" else "ピア(対等)"
    st.write(f"**{source_id}** からの **{label}** 接続先を選択してください。")
    
    connected_targets = set()
    for c in st.session_state.connections:
        if c["from"] == source_id: connected_targets.add(c["to"])
        if c["to"] == source_id: connected_targets.add(c["from"])
    
    layers = calculate_layers()
    source_layer = layers.get(source_id, 1)
    
    candidates = []
    for d in st.session_state.devices.keys():
        if d == source_id or d in connected_targets: continue
        if mode == "peer":
            if check_lineage(source_id, d): continue
            if layers.get(d, 1) != source_layer: continue
        if mode == "uplink":
            if check_cycle_for_uplink(source_id, d): continue
        candidates.append(d)
    
    if not candidates:
        st.warning("接続可能な候補デバイスがありません。")
        if st.button("閉じる"): st.rerun()
        return

    target_id = st.selectbox("接続先デバイス", candidates)
    
    if st.button("接続を作成", type="primary", use_container_width=True):
        # uplink: target(親) → source(子) の関係で保存
        # peer: 順序を維持
        new_conn = {
            "from": target_id if mode == "uplink" else source_id,
            "to": source_id if mode == "uplink" else target_id,
            "type": mode,
            "metadata": {"lag_enabled": False, "vlans": ""}
        }
        st.session_state.connections.append(new_conn)
        st.rerun()

@st.dialog("モジュール定義の管理")
def manage_modules_dialog():
    st.write("デバイスに追加可能なモジュールの種類を定義します。")
    if st.session_state.module_master_list:
        for i, mod_name in enumerate(st.session_state.module_master_list):
            c1, c2 = st.columns([4, 1])
            c1.text(f"・ {mod_name}")
            if c2.button("削除", key=f"del_mod_{i}"):
                st.session_state.module_master_list.pop(i)
                st.rerun()
    else:
        st.info("定義なし")
    st.divider()
    new_mod = st.text_input("新規モジュール名", placeholder="例: LineCard-10G")
    if st.button("追加", key="add_mod"):
        if new_mod and new_mod not in st.session_state.module_master_list:
            st.session_state.module_master_list.append(new_mod)
            st.rerun()

@st.dialog("マスタデータ管理 (Type/Vendor)")
def manage_master_data_dialog():
    tab1, tab2 = st.tabs(["デバイスType", "Vendor"])
    with tab1:
        st.write("デバイスの種別（Type）を定義します。")
        for i, t in enumerate(st.session_state.master_device_types):
            c1, c2 = st.columns([4,1])
            c1.text(t)
            if c2.button("削除", key=f"del_type_{i}"):
                st.session_state.master_device_types.pop(i)
                st.rerun()
        new_t = st.text_input("新規Type名", placeholder="例: FIREWALL", key="new_type_in")
        if st.button("Type追加", key="add_type_btn"):
            if new_t and new_t not in st.session_state.master_device_types:
                st.session_state.master_device_types.append(new_t)
                st.rerun()
    with tab2:
        st.write("ベンダー（Vendor）を定義します。")
        for i, v in enumerate(st.session_state.master_vendors):
            c1, c2 = st.columns([4,1])
            c1.text(v)
            if c2.button("削除", key=f"del_vend_{i}"):
                st.session_state.master_vendors.pop(i)
                st.rerun()
        new_v = st.text_input("新規Vendor名", placeholder="例: Cisco", key="new_vend_in")
        if st.button("Vendor追加", key="add_vend_btn"):
            if new_v and new_v not in st.session_state.master_vendors:
                st.session_state.master_vendors.append(new_v)
                st.rerun()

@st.dialog("全データ削除")
def clear_data_dialog():
    st.warning("⚠️ **本当に削除しますか？**")
    if st.button("削除実行", type="primary"):
        st.session_state.devices = {}
        st.session_state.connections = []
        st.session_state.editing_device = None
        st.rerun()

# ==================== UIコンポーネント ====================
def render_sidebar():
    with st.sidebar:
        st.header("🏢 トポロジー全体設定")
        st.session_state.site_name = st.text_input("拠点名 (Site Name)", value=st.session_state.site_name, help="例: Tokyo-HQ, Osaka-Branch")

def render_add_device():
    with st.expander("➕ デバイス追加", expanded=len(st.session_state.devices) == 0):
        c1, c2 = st.columns([3, 1])
        new_id = c1.text_input("デバイスID", placeholder="例: Core-SW01").strip()
        c2.write("")
        c2.write("")
        if c2.button("追加", type="primary", use_container_width=True):
            if new_id and new_id not in st.session_state.devices:
                st.session_state.devices[new_id] = {
                    "type": "SWITCH", 
                    "metadata": {
                        "vendor": "", "model": "", "rack_info": "", 
                        "hw_inventory": {"psu_count": 1, "fan_count": 0, "custom_modules": {}}
                    }
                }
                st.rerun()
            elif new_id: st.error("ID重複")

def render_device_list():
    if not st.session_state.devices: return
    st.subheader("📋 デバイス操作")
    
    search = st.text_input("🔍 検索", label_visibility="collapsed")
    layers = calculate_layers()
    all_devs = sorted(st.session_state.devices.keys(), key=lambda x: (layers.get(x, 1), x))
    if search: all_devs = [d for d in all_devs if search.lower() in d.lower()]

    current_selected = [d for d in st.session_state.devices if st.session_state.get(f"chk_{d}")]
    
    with st.container(border=True):
        if not current_selected:
            st.info("👇 デバイスを選択してください")
        else:
            st.markdown(f"**選択中:** `{', '.join(current_selected)}`")
            ac1, ac2, ac3, ac4 = st.columns(4)
            is_single = len(current_selected) == 1
            tgt = current_selected[0] if is_single else None
            
            if ac1.button("📝 詳細・編集", disabled=not is_single, use_container_width=True):
                st.session_state.editing_device = tgt
                st.rerun()
            if ac2.button("⬇️ 下位接続", disabled=not is_single, use_container_width=True):
                connection_dialog(tgt, "uplink")
            if ac3.button("↔️ ピア接続", disabled=not is_single, use_container_width=True):
                connection_dialog(tgt, "peer")
            if ac4.button("🗑️ 削除", type="primary", use_container_width=True):
                for d in current_selected:
                    del st.session_state.devices[d]
                    st.session_state.connections = [c for c in st.session_state.connections if c["from"] != d and c["to"] != d]
                st.session_state.editing_device = None
                st.rerun()

    with st.container(height=500):
        for dev_id in all_devs:
            dev = st.session_state.devices[dev_id]
            meta = dev.get("metadata", {})
            
            # 必須項目チェック（設置場所を除外）
            missing_items = []
            if not meta.get("vendor"): missing_items.append("Vendor")
            if not meta.get("model"): missing_items.append("Model")
            
            c_chk, c_card = st.columns([0.5, 6])
            c_chk.write(""); c_chk.checkbox("", key=f"chk_{dev_id}")
            
            with c_card.container(border=True):
                st.markdown(f"**{dev_id}** (L{layers.get(dev_id,1)})")
                badges = []
                if meta.get("vendor"): badges.append(meta["vendor"])
                if meta.get("model"): badges.append(meta["model"])
                if meta.get("rack_info"): badges.append(f"📍{meta['rack_info']}")
                if badges: st.caption(" | ".join(badges))
                
                if missing_items:
                    st.warning(f"⚠️ 未設定: {', '.join(missing_items)}")

            if st.session_state.editing_device == dev_id:
                with st.container(border=True):
                    st.info(f"📝 **{dev_id}** を設定中...")
                    with st.form(key=f"form_{dev_id}"):
                        t1, t2, t3 = st.tabs(["基本情報", "HW/モジュール", "論理/NW"])
                        with t1:
                            tv_head, tv_btn = st.columns([3, 2])
                            tv_head.markdown("##### デバイス種別・ベンダー")
                            # 【修正】フォーム内ではフラグを立てるだけにする
                            if tv_btn.form_submit_button("🛠️ Type/Vendor 管理"):
                                st.session_state.pending_dialog = "master_data"
                                st.session_state.pending_dialog_device = dev_id

                            r1c1, r1c2 = st.columns(2)
                            curr_type = dev.get("type", "SWITCH")
                            type_opts = st.session_state.master_device_types
                            idx_t = type_opts.index(curr_type) if curr_type in type_opts else 0
                            new_type = r1c1.selectbox("Type", type_opts, index=idx_t)
                            
                            curr_vend = meta.get("vendor", "")
                            vend_opts = [""] + st.session_state.master_vendors
                            idx_v = vend_opts.index(curr_vend) if curr_vend in vend_opts else 0
                            new_vend = r1c2.selectbox("Vendor", vend_opts, index=idx_v, help="⚠️ AI推論のために必須です")

                            r2c1, r2c2 = st.columns(2)
                            new_model = r2c1.text_input("Model", value=meta.get("model", ""), help="⚠️ AI推論のために必須です")
                            new_rack = r2c2.text_input("設置場所 (ラック情報など)", value=meta.get("rack_info", meta.get("location", "")), help="任意")

                        with t2:
                            h1, h2 = st.columns(2)
                            new_psu = h1.number_input("PSU数", min_value=0, value=meta.get("hw_inventory", {}).get("psu_count", 1))
                            new_fan = h2.number_input("FAN数", min_value=0, value=meta.get("hw_inventory", {}).get("fan_count", 0))
                            st.divider()
                            cm1, cm2 = st.columns([3,2])
                            cm1.markdown("##### 追加モジュール構成")
                            # 【修正】フォーム内ではフラグを立てるだけにする
                            if cm2.form_submit_button("🛠️ モジュール定義編集"):
                                st.session_state.pending_dialog = "modules"
                                st.session_state.pending_dialog_device = dev_id
                            curr_mods = meta.get("hw_inventory", {}).get("custom_modules", {})
                            new_mods = {}
                            if st.session_state.module_master_list:
                                cols = st.columns(2)
                                for i, mname in enumerate(st.session_state.module_master_list):
                                    val = cols[i%2].number_input(f"{mname} 数", min_value=0, value=curr_mods.get(mname, 0), key=f"mnum_{dev_id}_{mname}")
                                    if val > 0: new_mods[mname] = int(val)

                        with t3:
                            st.markdown("##### 接続ごとの論理設定")
                            related = [(i,c) for i,c in enumerate(st.session_state.connections) if c['from']==dev_id or c['to']==dev_id]
                            if not related: st.caption("接続なし")
                            updated_conns = {}
                            for idx, c in related:
                                target = c['to'] if c['from']==dev_id else c['from']
                                ltype = "Uplink" if c['type']=='uplink' else "Peer"
                                with st.expander(f"🔗 対 {target} ({ltype})"):
                                    cmeta = c.get("metadata", {})
                                    islag = st.checkbox("LAG構成", value=cmeta.get("lag_enabled", False), key=f"lag_{dev_id}_{idx}")
                                    ivlans = st.text_input("VLAN ID", value=cmeta.get("vlans", ""), key=f"vlan_{dev_id}_{idx}")
                                    updated_conns[idx] = {"lag_enabled": islag, "vlans": ivlans}

                        st.divider()
                        c_save, c_cancel = st.columns([1, 1])
                        with c_save:
                            if st.form_submit_button("💾 保存", type="primary", use_container_width=True):
                                if not new_vend or not new_model:
                                    st.warning("⚠️ VendorまたはModelが未入力です。後工程のために設定を推奨します。")
                                
                                st.session_state.devices[dev_id]["type"] = new_type
                                st.session_state.devices[dev_id]["metadata"].update({
                                    "vendor": new_vend,
                                    "model": new_model,
                                    "rack_info": new_rack, 
                                    "hw_inventory": {"psu_count": int(new_psu), "fan_count": int(new_fan), "custom_modules": new_mods}
                                })
                                for idx, cmeta in updated_conns.items():
                                    st.session_state.connections[idx]["metadata"] = cmeta
                                st.session_state.editing_device = None
                                st.rerun()
                        with c_cancel:
                            if st.form_submit_button("キャンセル", use_container_width=True):
                                st.session_state.editing_device = None
                                st.rerun()

def render_data_io():
    st.divider()
    st.subheader("💾 データ管理")
    c1, c2 = st.columns(2)
    with c1:
        fname = st.text_input("保存ファイル名", value="topology.json")
        # 【修正】注意書きを追加
        st.caption("⚠️ **注意:** 入力後は必ず **Enterキー** を押して確定してください。")
        
        if not fname.endswith(".json"): fname += ".json"
        
        # エクスポートチェック（設置場所を除外）
        incomplete_count = 0
        for d in st.session_state.devices.values():
            m = d.get("metadata", {})
            if not all([m.get("vendor"), m.get("model")]):
                incomplete_count += 1
        
        if incomplete_count > 0:
            st.warning(f"⚠️ {incomplete_count} 台のデバイスでVendorまたはModelが未入力です。AIによる設定生成の精度が下がる可能性があります。")

        export_data = {
            "site_name": st.session_state.site_name,
            "topology": {},
            "connections": st.session_state.connections,
            "master_data": {
                "device_types": st.session_state.master_device_types,
                "vendors": st.session_state.master_vendors,
                "modules": st.session_state.module_master_list
            },
            "metadata": {"version": "2.4"}
        }
        layers = calculate_layers()
        for did, ddata in st.session_state.devices.items():
            parents = [c["to"] for c in st.session_state.connections if c["from"] == did and c["type"] == "uplink"]
            meta = ddata["metadata"].copy()
            meta["location"] = meta.get("rack_info", "")
            export_data["topology"][did] = {
                "type": ddata["type"], "layer": layers.get(did, 1), "parent_ids": parents, "metadata": meta
            }
            
        st.download_button("📥 JSONダウンロード", json.dumps(export_data, indent=2, ensure_ascii=False), fname, "application/json", type="primary")

    with c2:
        st.write("")
        st.write("")
        uploaded = st.file_uploader("📤 JSON読み込み", type=["json"])
        if uploaded and st.button("適用", type="primary"):
            try:
                data = json.load(uploaded)
                if "site_name" in data: st.session_state.site_name = data["site_name"]
                mdata = data.get("master_data", {})
                if "device_types" in mdata: st.session_state.master_device_types = mdata["device_types"]
                if "vendors" in mdata: st.session_state.master_vendors = mdata["vendors"]
                if "modules" in mdata: st.session_state.module_master_list = mdata["modules"]
                elif "module_master_list" in data: st.session_state.module_master_list = data["module_master_list"]
                
                topo = data.get("topology", {})
                new_devs = {}
                for did, val in topo.items():
                    meta = val.get("metadata", {})
                    if "rack_info" not in meta and "location" in meta: meta["rack_info"] = meta["location"]
                    new_devs[did] = {"type": val.get("type", "SWITCH"), "metadata": meta}
                st.session_state.devices = new_devs
                if "connections" in data: st.session_state.connections = data["connections"]
                st.success("読み込み完了")
                st.rerun()
            except Exception as e: st.error(f"エラー: {e}")
                
    st.divider()
    if st.button("🗑️ 全データをクリア", type="primary", use_container_width=True):
        clear_data_dialog()


# 【修正】接続オブジェクトの一意識別用ヘルパー関数
def _connection_matches(conn: dict, target_conn: dict) -> bool:
    """2つの接続オブジェクトが同一かどうかを判定"""
    return (conn["from"] == target_conn["from"] and 
            conn["to"] == target_conn["to"] and 
            conn["type"] == target_conn["type"])


# ==================== メイン ====================
def main():
    init_session()
    render_sidebar()
    st.title("🔧 トポロジービルダー")
    components.html(generate_visjs_html(), height=480)
    c_left, c_right = st.columns([1, 1])
    with c_left:
        render_add_device()
        render_device_list()
    with c_right:
        all_conns = st.session_state.connections
        sel_devs = [d for d in st.session_state.devices if st.session_state.get(f"chk_{d}")]
        display_conns = []
        if sel_devs:
            display_conns = [(i,c) for i,c in enumerate(all_conns) if c["from"] in sel_devs or c["to"] in sel_devs]
            head = f"🔗 関連接続 ({len(display_conns)})"
            expanded = True
        else:
            display_conns = [(i,c) for i,c in enumerate(all_conns)]
            head = f"🔗 全接続 ({len(display_conns)})"
            expanded = False
        with st.expander(head, expanded=expanded):
            for i, c in display_conns:
                c1, c2 = st.columns([6,1])
                meta = c.get("metadata", {})
                tags = ""
                if meta.get("lag_enabled"): tags += " [LAG]"
                if meta.get("vlans"): tags += f" [VLAN:{meta['vlans']}]"
                label = f"**⬇️** {c['to']} → {c['from']}" if c['type'] == 'uplink' else f"**↔️** {c['from']} ↔ {c['to']}"
                c1.markdown(f"{label} {tags}")
                if c2.button("🗑️", key=f"del_conn_{i}"):
                    # 【修正】インデックスではなく接続オブジェクト自体を使って削除
                    st.session_state.connections = [
                        conn for conn in st.session_state.connections 
                        if not _connection_matches(conn, c)
                    ]
                    st.rerun()
        render_data_io()
    
    # 【修正】フォーム外でダイアログを処理（フォーム内でのダイアログ呼び出し問題を回避）
    if st.session_state.pending_dialog == "master_data":
        st.session_state.pending_dialog = None
        manage_master_data_dialog()
    elif st.session_state.pending_dialog == "modules":
        st.session_state.pending_dialog = None
        manage_modules_dialog()

if __name__ == "__main__":
    main()
