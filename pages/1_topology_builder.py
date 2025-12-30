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
# アイコンは削除し、色とラベルのみ定義
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
    if "connect_mode" not in st.session_state:
        st.session_state.connect_mode = None 
    if "editing_device" not in st.session_state:
        st.session_state.editing_device = None

# ==================== ロジック・計算 ====================
def calculate_layers() -> Dict[str, int]:
    """接続関係からレイヤーを自動計算"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return {}
    
    # 子ノードを特定
    children = set()
    for conn in connections:
        if conn.get("type") == "uplink":
            # Uplink: Child(from) -> Parent(to)
            children.add(conn["from"])
            
    # 親を持たないノードがルート
    root_nodes = [d for d in devices.keys() if d not in children]
    if not root_nodes and devices:
        root_nodes = [list(devices.keys())[0]] # 循環回避用
        
    layers = {}
    queue = [(node, 1) for node in root_nodes]
    visited = set()
    
    # 親 -> 子のマッピング
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
    """
    dev_a と dev_b の間に親子（祖先・子孫）関係があるかチェックする。
    ピア接続を作成する際の矛盾防止用。
    Returns: True if related (connection forbidden), False if safe.
    """
    connections = st.session_state.connections
    
    # 親マップ構築: child -> [parents]
    parent_map = {}
    for conn in connections:
        if conn["type"] == "uplink":
            child = conn["from"]
            parent = conn["to"]
            if child not in parent_map: parent_map[child] = []
            parent_map[child].append(parent)

    # 特定のノードの全祖先を取得する関数
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

    # AがBの祖先、またはBがAの祖先である場合
    if dev_b in ancestors_a or dev_a in ancestors_b:
        return True
        
    return False

# ==================== vis.js HTML ====================
def generate_visjs_html() -> str:
    """vis.jsのHTML生成（アイコンなし、テキストのみ）"""
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
        
        # ラベル: アイコン削除、IDとベンダーのみ
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
            # Peer接続: 黄色い点線
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

# ==================== UIコンポーネント ====================

def render_add_device():
    """デバイス追加（ID入力のみ）"""
    with st.expander("➕ デバイス追加", expanded=len(st.session_state.devices) == 0):
        c1, c2 = st.columns([3, 1])
        with c1:
            new_id = st.text_input("デバイスID", placeholder="例: Core-SW01", key="in_new_id").strip()
        with c2:
            st.write("")
            st.write("")
            if st.button("追加", type="primary", use_container_width=True):
                if new_id and new_id not in st.session_state.devices:
                    # 初期データ構造（JSON準拠）
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
                else:
                    st.error("IDを入力してください")

def render_connect_mode():
    """接続モード管理"""
    if not st.session_state.connect_mode:
        return

    mode = st.session_state.connect_mode
    src = mode["source"]
    conn_type = mode["mode"]
    
    label = "下位(ダウンリンク)" if conn_type == "uplink" else "ピア(対等)"
    st.info(f"🔗 **接続作成中**: {src} から {label} 接続")
    
    candidates = [d for d in st.session_state.devices.keys() if d != src]
    
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        dst = st.selectbox("接続先を選択", [""] + candidates, key="conn_dst")
    
    with c2:
        st.write("")
        st.write("")
        if st.button("接続", type="primary", disabled=not dst, use_container_width=True):
            # 1. 既存接続チェック
            exists = any(
                (c["from"] == src and c["to"] == dst) or
                (c["from"] == dst and c["to"] == src)
                for c in st.session_state.connections
            )
            
            # 2. 矛盾チェック（ピア接続しようとしているのに上下関係があるなど）
            lineage_conflict = False
            if conn_type == "peer":
                if check_lineage(src, dst):
                    lineage_conflict = True
            
            if exists:
                st.warning("既に接続されています")
            elif lineage_conflict:
                st.error("⚠️ 論理矛盾: 親子(上下)関係にあるノード同士をピア接続することはできません。")
            else:
                if conn_type == "uplink":
                    # Uplink: Child(from) -> Parent(to)
                    # 操作は Parent(src) -> Child(dst) なので、保存時は逆にする
                    st.session_state.connections.append({
                        "from": dst,
                        "to": src,
                        "type": "uplink"
                    })
                else:
                    st.session_state.connections.append({
                        "from": src,
                        "to": dst,
                        "type": "peer"
                    })
                st.session_state.connect_mode = None
                st.rerun()

    with c3:
        st.write("")
        st.write("")
        if st.button("キャンセル", use_container_width=True):
            st.session_state.connect_mode = None
            st.rerun()

def render_device_list():
    """デバイス一覧・詳細編集"""
    if not st.session_state.devices:
        return

    st.subheader("📋 デバイス操作")
    
    layers = calculate_layers()
    sorted_devs = sorted(st.session_state.devices.keys(), key=lambda x: (layers.get(x, 99), x))
    
    for dev_id in sorted_devs:
        dev = st.session_state.devices[dev_id]
        meta = dev.get("metadata", {})
        hw = meta.get("hw_inventory", {})
        
        # カードコンテナ
        with st.container(border=True):
            # --- ヘッダー行: ID, スペック要約, アクションボタン ---
            c1, c2, c3, c4, c5 = st.columns([3, 1.5, 1.5, 1.5, 0.8])
            
            with c1:
                st.markdown(f"**{dev_id}** (L{layers.get(dev_id,1)})")
                # サマリー情報の表示（ハードウェア冗長性など）
                info_badges = []
                if meta.get("vendor"): info_badges.append(meta["vendor"])
                if meta.get("model"): info_badges.append(meta["model"])
                # 冗長性情報のバッジ化
                psu = hw.get("psu_count", 0)
                fan = hw.get("fan_count", 0)
                if psu > 0: info_badges.append(f"⚡PSU:{psu}")
                if fan > 0: info_badges.append(f"💨FAN:{fan}")
                
                if info_badges:
                    st.caption(" | ".join(info_badges))
                else:
                    st.caption("No details")

            is_disabled = st.session_state.connect_mode is not None
            is_editing = (st.session_state.editing_device == dev_id)
            
            with c2:
                btn_label = "📝 閉じる" if is_editing else "📝 詳細"
                if st.button(btn_label, key=f"edit_{dev_id}", disabled=is_disabled, use_container_width=True):
                    st.session_state.editing_device = None if is_editing else dev_id
                    st.rerun()
            with c3:
                if st.button("↓ 下位", key=f"down_{dev_id}", disabled=is_disabled, use_container_width=True):
                    st.session_state.connect_mode = {"source": dev_id, "mode": "uplink"}
                    st.rerun()
            with c4:
                if st.button("→ ピア", key=f"peer_{dev_id}", disabled=is_disabled, use_container_width=True):
                    st.session_state.connect_mode = {"source": dev_id, "mode": "peer"}
                    st.rerun()
            with c5:
                if st.button("🗑️", key=f"del_{dev_id}", disabled=is_disabled):
                    del st.session_state.devices[dev_id]
                    st.session_state.connections = [c for c in st.session_state.connections 
                                                  if c["from"] != dev_id and c["to"] != dev_id]
                    if is_editing: st.session_state.editing_device = None
                    st.rerun()

            # --- 詳細編集フォーム ---
            if is_editing:
                st.markdown("---")
                with st.form(key=f"form_{dev_id}"):
                    st.caption("基本情報")
                    f1, f2, f3, f4 = st.columns(4)
                    with f1:
                        # タイプ
                        curr_type = dev.get("type", "SWITCH")
                        new_type = st.selectbox("Type", list(DEVICE_TYPES.keys()), 
                                              index=list(DEVICE_TYPES.keys()).index(curr_type) if curr_type in DEVICE_TYPES else 0)
                    with f2:
                        # ベンダー
                        curr_vend = meta.get("vendor", "")
                        new_vend = st.selectbox("Vendor", [""] + VENDORS, 
                                              index=(VENDORS.index(curr_vend)+1) if curr_vend in VENDORS else 0)
                    with f3:
                        # モデル名 (JSON: model)
                        new_model = st.text_input("Model", value=meta.get("model", ""))
                    with f4:
                        # 設置場所 (JSON: location)
                        new_loc = st.text_input("Location", value=meta.get("location", ""))

                    st.caption("ハードウェア冗長・インベントリ")
                    h1, h2, h3 = st.columns([1, 1, 2])
                    with h1:
                        # PSU数 (JSON: hw_inventory.psu_count)
                        new_psu = st.number_input("電源ユニット(PSU)数", min_value=0, value=hw.get("psu_count", 1))
                    with h2:
                        # FAN数 (JSON: hw_inventory.fan_count)
                        new_fan = st.number_input("ファンモジュール数", min_value=0, value=hw.get("fan_count", 0))
                    with h3:
                        st.info("💡 PSUやFANの数は、RCA分析時のハードウェア障害判定に使用されます。")

                    # 保存
                    if st.form_submit_button("💾 変更を保存", type="primary"):
                        st.session_state.devices[dev_id]["type"] = new_type
                        st.session_state.devices[dev_id]["metadata"] = {
                            "vendor": new_vend,
                            "model": new_model,
                            "location": new_loc,
                            "hw_inventory": {
                                "psu_count": int(new_psu),
                                "fan_count": int(new_fan)
                            }
                        }
                        st.session_state.editing_device = None
                        st.rerun()

def render_data_io():
    """JSON Import/Export"""
    st.divider()
    st.subheader("💾 データ管理")
    
    c1, c2 = st.columns(2)
    with c1:
        # Export用データ生成
        export_data = {
            "topology": {},
            "redundancy_groups": {}, # 今回は簡易実装のため空または自動生成の余地あり
            "metadata": {"version": "2.0"}
        }
        
        # JSON構造に合わせて変換
        layers = calculate_layers()
        for d_id, d_data in st.session_state.devices.items():
            # 親IDリストの抽出
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
                    # full_topology.json形式に対応
                    topo = data.get("topology", {})
                    
                    new_devs = {}
                    new_conns = []
                    
                    for d_id, d_val in topo.items():
                        new_devs[d_id] = {
                            "type": d_val.get("type", "SWITCH"),
                            "metadata": d_val.get("metadata", {})
                        }
                        # Uplink復元
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
    
    render_connect_mode()
    
    col_left, col_right = st.columns([1, 1])
    with col_left:
        render_add_device()
        render_device_list()
        
    with col_right:
        # 簡易接続リスト表示
        if st.session_state.connections:
            with st.expander(f"🔗 接続リスト ({len(st.session_state.connections)})"):
                for i, c in enumerate(st.session_state.connections):
                    col_c1, col_c2 = st.columns([5,1])
                    with col_c1:
                        if c["type"] == "uplink":
                            st.write(f"🔹 {c['to']} ← {c['from']}")
                        else:
                            st.write(f"🔸 {c['from']} ↔ {c['to']}")
                    with col_c2:
                        if st.button("✕", key=f"del_conn_{i}"):
                            st.session_state.connections.pop(i)
                            st.rerun()
        
        render_data_io()

if __name__ == "__main__":
    main()
