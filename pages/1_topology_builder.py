import streamlit as st
import streamlit.components.v1 as components
import json
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
    "CLOUD": {"icon": "☁️", "color": "#74ebd5", "label": "クラウド"},
    "PC": {"icon": "💻", "color": "#333333", "label": "PC"},
}

VENDORS = ["Cisco", "Juniper", "Fortinet", "Palo Alto", "Arista", "HPE", "Dell", "NetApp", "F5", "AWS", "Azure", "Other"]

# ==================== セッション状態 ====================
def init_session():
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    if "connections" not in st.session_state:
        st.session_state.connections = []
    if "connect_mode" not in st.session_state:
        st.session_state.connect_mode = None  # {"source": "dev_id", "mode": "uplink/peer"}
    if "editing_device" not in st.session_state:
        st.session_state.editing_device = None # 編集中のデバイスID

# ==================== レイヤー計算 ====================
def calculate_layers() -> Dict[str, int]:
    """接続関係からレイヤーを自動計算"""
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return {}
    
    children = set()
    parent_map = {}
    
    for conn in connections:
        if conn.get("type") == "uplink":
            child, parent = conn["from"], conn["to"]
            children.add(child)
            if child not in parent_map:
                parent_map[child] = []
            parent_map[child].append(parent)
            
    root_nodes = [d for d in devices.keys() if d not in children]
    
    if not root_nodes and devices:
        root_nodes = [list(devices.keys())[0]]
        
    layers = {}
    queue = [(node, 1) for node in root_nodes]
    visited = set()
    
    children_map = {}
    for conn in connections:
        if conn.get("type") == "uplink":
            child, parent = conn["from"], conn["to"]
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
        
        label = f"{style['icon']} {dev_id}"
        if vendor:
            label += f"\\n{vendor}"
        
        nodes_data.append({
            "id": dev_id,
            "label": label,
            "color": {"background": style["color"], "border": "#333"},
            "font": {"color": "white", "size": 16, "face": "arial"}, # フォント少し大きく
            "shape": "box",
            "level": layer,
            "margin": 10,
        })
    
    edges_data = []
    for conn in connections:
        conn_type = conn.get("type", "uplink")
        
        if conn_type == "uplink":
            edges_data.append({
                "from": conn["to"],
                "to": conn["from"],
                "arrows": "to",
                "color": {"color": "#666"},
                "width": 2,
            })
        else:
            # Peer接続: 点線を太く、目立つ色に
            edges_data.append({
                "from": conn["from"],
                "to": conn["to"],
                "color": {"color": "#ffaa00"}, # 明るいオレンジ/黄色
                "dashes": [10, 10], # 点線の間隔を調整
                "arrows": "",
                "width": 3, # 線を太く
            })
    
    nodes_json = json.dumps(nodes_data)
    edges_json = json.dumps(edges_data)
    
    # nodeSpacing を 300 に拡大 (以前は150程度)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <style>
            body {{ margin:0; font-family: sans-serif; }}
            #network {{ width:100%; height:450px; background:#fafafa; border:1px solid #ddd; border-radius:8px; }}
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
                        levelSeparation: 120, // 階層間の距離も少し広げる
                        nodeSpacing: 300,    // ★ここを変更：ノード間の横幅を大きく広げる
                        treeSpacing: 320,
                        blockShifting: true,
                        edgeMinimization: true,
                        parentCentralization: true
                    }}
                }},
                physics: {{
                    enabled: false
                }},
                interaction: {{
                    dragNodes: false,
                    dragView: true,
                    zoomView: true
                }}
            }};
            var network = new vis.Network(container, data, options);
            network.fit();
        </script>
    </body>
    </html>
    """

# ==================== コンポーネント関数 ====================

def render_add_device():
    """デバイス追加フォーム（IDのみのシンプル版）"""
    with st.expander("➕ デバイス追加", expanded=len(st.session_state.devices) == 0):
        # シンプルにIDと追加ボタンのみ
        c1, c2 = st.columns([3, 1])
        with c1:
            new_id = st.text_input("デバイスID", placeholder="例: Router01", key="in_new_id").strip()
        with c2:
            st.write("") # スペーサー
            st.write("")
            if st.button("追加", type="primary", use_container_width=True):
                if new_id and new_id not in st.session_state.devices:
                    # デフォルト値で作成 (SWITCH, Vendorなし)
                    st.session_state.devices[new_id] = {
                        "type": "SWITCH", 
                        "metadata": {"vendor": ""},
                        "modules": []
                    }
                    st.success(f"{new_id} を追加しました。詳細はリストから編集してください。")
                    st.rerun()
                elif new_id in st.session_state.devices:
                    st.error("そのIDは既に存在します")
                else:
                    st.error("IDを入力してください")

def render_connect_mode():
    """接続モードUI"""
    if not st.session_state.connect_mode:
        return

    mode = st.session_state.connect_mode
    source_dev = mode["source"]
    conn_mode = mode["mode"]
    
    st.info(f"🔗 **接続モード中**: {source_dev} から {'下位(ダウンリンク)' if conn_mode == 'uplink' else 'ピア(対等)'} 接続を作成します")
    
    candidates = [d for d in st.session_state.devices.keys() if d != source_dev]
    
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        target_dev = st.selectbox("接続先を選択", [""] + candidates, key="conn_target_select")
    
    with c2:
        st.write("")
        st.write("")
        if st.button("接続する", type="primary", use_container_width=True, disabled=not target_dev):
            exists = any(
                (c["from"] == source_dev and c["to"] == target_dev) or
                (c["from"] == target_dev and c["to"] == source_dev)
                for c in st.session_state.connections
            )
            if exists:
                st.warning("既に接続が存在します")
            else:
                if conn_mode == "uplink":
                    st.session_state.connections.append({
                        "from": target_dev,
                        "to": source_dev,
                        "type": "uplink"
                    })
                else:
                    st.session_state.connections.append({
                        "from": source_dev,
                        "to": target_dev,
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
    """デバイス一覧と操作（詳細編集機能付き）"""
    if not st.session_state.devices:
        return

    st.subheader("📋 デバイス操作")
    
    layers = calculate_layers()
    # レイヤー順、ID順でソート
    sorted_devs = sorted(st.session_state.devices.keys(), key=lambda x: (layers.get(x, 99), x))
    
    for dev_id in sorted_devs:
        dev = st.session_state.devices[dev_id]
        layer = layers.get(dev_id, 1)
        style = DEVICE_TYPES.get(dev["type"], DEVICE_TYPES["SWITCH"])
        vendor_disp = dev["metadata"].get("vendor") or "Unknown"
        
        # カードデザイン
        with st.container(border=True):
            # 1行目: アイコン・ID・基本ボタン
            c1, c2, c3, c4, c5 = st.columns([3, 1.5, 1.5, 1.5, 0.8])
            
            with c1:
                st.markdown(f"**{style['icon']} {dev_id}** (L{layer})")
                st.caption(f"{style['label']} | {vendor_disp}")
            
            is_disabled = st.session_state.connect_mode is not None
            
            # 詳細（編集）ボタン
            with c2:
                # 編集モードのトグル
                is_editing = (st.session_state.editing_device == dev_id)
                btn_label = "📝 閉じる" if is_editing else "📝 詳細"
                btn_type = "secondary" if is_editing else "secondary"
                
                if st.button(btn_label, key=f"btn_edit_{dev_id}", 
                             disabled=is_disabled, use_container_width=True):
                    if is_editing:
                        st.session_state.editing_device = None
                    else:
                        st.session_state.editing_device = dev_id
                    st.rerun()

            with c3:
                if st.button("↓ 下位", key=f"btn_down_{dev_id}", 
                             disabled=is_disabled, use_container_width=True):
                    st.session_state.connect_mode = {"source": dev_id, "mode": "uplink"}
                    st.rerun()
            with c4:
                if st.button("→ ピア", key=f"btn_peer_{dev_id}", 
                             disabled=is_disabled, use_container_width=True):
                    st.session_state.connect_mode = {"source": dev_id, "mode": "peer"}
                    st.rerun()
            with c5:
                if st.button("🗑️", key=f"btn_del_{dev_id}", disabled=is_disabled):
                    del st.session_state.devices[dev_id]
                    st.session_state.connections = [
                        c for c in st.session_state.connections
                        if c["from"] != dev_id and c["to"] != dev_id
                    ]
                    if st.session_state.editing_device == dev_id:
                        st.session_state.editing_device = None
                    st.rerun()
            
            # 2行目: 編集フォーム（詳細ボタンが押されたときだけ表示）
            if st.session_state.editing_device == dev_id:
                st.markdown("---")
                st.markdown(f"**✏️ {dev_id} の詳細情報を編集**")
                
                ec1, ec2, ec3 = st.columns([2, 2, 1])
                
                # 現在の値を取得
                current_type = dev.get("type", "SWITCH")
                current_vendor = dev.get("metadata", {}).get("vendor", "")
                
                with ec1:
                    # タイプ選択
                    type_options = list(DEVICE_TYPES.keys())
                    new_type = st.selectbox(
                        "デバイスタイプ", 
                        type_options,
                        index=type_options.index(current_type) if current_type in type_options else 1,
                        format_func=lambda x: f"{DEVICE_TYPES[x]['icon']} {DEVICE_TYPES[x]['label']}",
                        key=f"edit_type_{dev_id}"
                    )
                
                with ec2:
                    # ベンダー選択
                    new_vendor = st.selectbox(
                        "ベンダー", 
                        [""] + VENDORS,
                        index=(VENDORS.index(current_vendor) + 1) if current_vendor in VENDORS else 0,
                        key=f"edit_vendor_{dev_id}"
                    )
                
                with ec3:
                    st.write("")
                    st.write("")
                    # 保存ボタン
                    if st.button("保存して閉じる", key=f"save_{dev_id}", type="primary", use_container_width=True):
                        st.session_state.devices[dev_id]["type"] = new_type
                        st.session_state.devices[dev_id]["metadata"]["vendor"] = new_vendor
                        st.session_state.editing_device = None # 編集終了
                        st.success("保存しました")
                        st.rerun()

def render_connection_list():
    """接続リスト"""
    if not st.session_state.connections:
        return
        
    with st.expander(f"🔗 接続リスト ({len(st.session_state.connections)})"):
        for i, conn in enumerate(st.session_state.connections):
            c1, c2 = st.columns([6, 1])
            with c1:
                if conn["type"] == "uplink":
                    st.write(f"🔹 {conn['to']} (親) ← {conn['from']} (子)")
                else:
                    st.write(f"🔸 {conn['from']} ↔ {conn['to']}")
            with c2:
                if st.button("✕", key=f"del_conn_{i}"):
                    st.session_state.connections.pop(i)
                    st.rerun()

def render_data_io():
    """データ保存・復元"""
    st.divider()
    st.subheader("💾 データ管理")
    
    c1, c2 = st.columns(2)
    with c1:
        full_data = {
            "devices": st.session_state.devices,
            "connections": st.session_state.connections
        }
        json_str = json.dumps(full_data, ensure_ascii=False, indent=2)
        st.download_button(
            "📥 JSONをダウンロード (保存)",
            data=json_str,
            file_name="topology_data.json",
            mime="application/json",
            type="primary",
            use_container_width=True
        )

    with c2:
        uploaded = st.file_uploader("📤 JSONを読み込み (復元)", type=["json"])
        if uploaded:
            try:
                data = json.load(uploaded)
                if "devices" in data and "connections" in data:
                    if st.button("データを適用する", type="primary", use_container_width=True):
                        st.session_state.devices = data["devices"]
                        st.session_state.connections = data["connections"]
                        st.session_state.editing_device = None
                        st.success("読み込み完了")
                        st.rerun()
            except Exception as e:
                st.error(f"読み込みエラー: {e}")

# ==================== メイン処理 ====================
def main():
    init_session()
    
    st.title("🔧 トポロジービルダー")
    
    # 1. ネットワーク図
    components.html(generate_visjs_html(), height=480)
    
    # 2. 接続モード（アクティブ時のみ）
    render_connect_mode()
    
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        # 3. デバイス追加（シンプル化）
        render_add_device()
        # 4. デバイス一覧（詳細ボタン追加）
        render_device_list()
        
    with col_right:
        # 5. 接続リスト
        render_connection_list()
        # 6. データIO
        render_data_io()

if __name__ == "__main__":
    main()
