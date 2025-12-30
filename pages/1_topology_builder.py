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
}

VENDORS = ["Cisco", "Juniper", "Fortinet", "Palo Alto", "Arista", "HPE", "Dell", "NetApp", "F5", "Other"]

# ==================== セッション状態 ====================
def init_session():
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    if "connections" not in st.session_state:
        st.session_state.connections = []
    if "connect_mode" not in st.session_state:
        st.session_state.connect_mode = None  # {"source": "dev_id", "mode": "uplink/peer"}

# ==================== レイヤー計算 ====================
def calculate_layers() -> Dict[str, int]:
    """接続関係からレイヤーを自動計算
    ルール: Uplink接続において、from=Child, to=Parent とみなす
    """
    devices = st.session_state.devices
    connections = st.session_state.connections
    
    if not devices:
        return {}
    
    # 親（Uplink先）を持つノードを特定
    # conn["type"] == "uplink" の場合、 conn["from"] -> conn["to"] (Child -> Parent)
    children = set()
    parent_map = {} # child -> [parents]
    
    for conn in connections:
        if conn.get("type") == "uplink":
            child, parent = conn["from"], conn["to"]
            children.add(child)
            if child not in parent_map:
                parent_map[child] = []
            parent_map[child].append(parent)
            
    # 親を持たないノードがルート（Layer 1）
    root_nodes = [d for d in devices.keys() if d not in children]
    
    # 循環参照などの場合、ルートが見つからない可能性があるため、その場合は適当なノードをルートにする
    if not root_nodes and devices:
        root_nodes = [list(devices.keys())[0]]
        
    layers = {}
    queue = [(node, 1) for node in root_nodes]
    visited = set()
    
    # 子ノードマップを作成（親 -> [子]）
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
        
        # 自分の子を次のレイヤーとして追加
        for child in children_map.get(node, []):
            queue.append((child, layer + 1))
            
    # 孤立ノードなどはLayer 1にする
    for d in devices.keys():
        if d not in layers:
            layers[d] = 1
            
    return layers

# ==================== vis.js HTML ====================
def generate_visjs_html() -> str:
    """vis.jsのHTML生成（自動配置・物理演算有効）"""
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
        style = DEVICE_TYPES.get(dev_type, {"color": "#6c757d", "icon": "⬜"})
        vendor = dev.get("metadata", {}).get("vendor") or ""
        layer = layers.get(dev_id, 1)
        
        label = f"{style['icon']} {dev_id}"
        if vendor:
            label += f"\\n{vendor}"
        
        nodes_data.append({
            "id": dev_id,
            "label": label,
            "color": {"background": style["color"], "border": "#333"},
            "font": {"color": "white", "size": 14, "face": "arial"},
            "shape": "box",
            "level": layer, # Hierarchical layout用
        })
    
    edges_data = []
    for conn in connections:
        conn_type = conn.get("type", "uplink")
        
        if conn_type == "uplink":
            # Uplink: Child(from) -> Parent(to). 
            # 描画上は Parent -> Child に矢印を向けたい場合が多いが、
            # ネットワーク図としては論理的に Child -> Parent がUplink。
            # ここでは階層構造を明確にするため、vis.jsの階層方向(UD)に合わせて
            # Parent(to) -> Child(from) にエッジを張り、矢印をつけることで「下位接続」を表現する
            edges_data.append({
                "from": conn["to"],   # Parent
                "to": conn["from"],   # Child
                "arrows": "to",
                "color": {"color": "#666"},
                "width": 2,
            })
        else:
            # Peer接続
            edges_data.append({
                "from": conn["from"],
                "to": conn["to"],
                "color": {"color": "#ff9800"},
                "dashes": True,
                "arrows": "", # 双方向的な意味合い
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
                        direction: 'UD', // Up-Down
                        sortMethod: 'directed',
                        levelSeparation: 100,
                        nodeSpacing: 150,
                        treeSpacing: 200,
                        blockShifting: true,
                        edgeMinimization: true,
                        parentCentralization: true
                    }}
                }},
                physics: {{
                    enabled: false // Hierarchicalの場合はPhysicsを切ったほうが安定する
                }},
                interaction: {{
                    dragNodes: false, // 自動配置を優先するためドラッグ無効（混乱防止）
                    dragView: true,
                    zoomView: true
                }}
            }};
            var network = new vis.Network(container, data, options);
            network.fit(); // 全体が収まるようにズーム調整
        </script>
    </body>
    </html>
    """

# ==================== コンポーネント関数 ====================

def render_add_device():
    """デバイス追加フォーム"""
    with st.expander("➕ デバイス追加", expanded=len(st.session_state.devices) == 0):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        with c1:
            new_id = st.text_input("デバイスID", placeholder="CORE-SW01", key="in_new_id").strip()
        with c2:
            new_type = st.selectbox("タイプ", list(DEVICE_TYPES.keys()), 
                                  format_func=lambda x: f"{DEVICE_TYPES[x]['icon']} {DEVICE_TYPES[x]['label']}")
        with c3:
            new_vendor = st.selectbox("ベンダー", [""] + VENDORS)
        with c4:
            st.write("")
            st.write("")
            if st.button("追加", type="primary", use_container_width=True):
                if new_id and new_id not in st.session_state.devices:
                    st.session_state.devices[new_id] = {
                        "type": new_type,
                        "metadata": {"vendor": new_vendor},
                        "modules": []
                    }
                    st.rerun()
                elif new_id in st.session_state.devices:
                    st.error("ID重複")
                else:
                    st.error("ID未入力")

def render_connect_mode():
    """接続モードのUI（セレクトボックス版）"""
    if not st.session_state.connect_mode:
        return

    mode = st.session_state.connect_mode
    source_dev = mode["source"]
    conn_mode = mode["mode"] # 'uplink' or 'peer'
    
    st.info(f"🔗 **接続モード中**: {source_dev} から {'下位(ダウンリンク)' if conn_mode == 'uplink' else 'ピア(対等)'} 接続を作成します")
    
    # 自分以外で、まだ接続されていない候補を探すのは複雑なので、
    # 単純に自分以外の全デバイスを候補に出し、ロジックで制御する
    candidates = [d for d in st.session_state.devices.keys() if d != source_dev]
    
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        target_dev = st.selectbox("接続先を選択", [""] + candidates, key="conn_target_select")
    
    with c2:
        st.write("")
        st.write("")
        # 接続ボタン
        if st.button("接続する", type="primary", use_container_width=True, disabled=not target_dev):
            # 既存接続チェック
            exists = any(
                (c["from"] == source_dev and c["to"] == target_dev) or
                (c["from"] == target_dev and c["to"] == source_dev)
                for c in st.session_state.connections
            )
            if exists:
                st.warning("既に接続が存在します")
            else:
                if conn_mode == "uplink":
                    # source(親) -> target(子) への接続操作
                    # データ構造上は Uplink: Child(from) -> Parent(to) なので
                    # from=target(子), to=source(親) として保存する
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
    """デバイス一覧と操作"""
    if not st.session_state.devices:
        return

    st.subheader("📋 デバイス操作")
    
    # レイヤー順にソートして表示したい
    layers = calculate_layers()
    sorted_devs = sorted(st.session_state.devices.keys(), key=lambda x: (layers.get(x, 99), x))
    
    for dev_id in sorted_devs:
        dev = st.session_state.devices[dev_id]
        layer = layers.get(dev_id, 1)
        style = DEVICE_TYPES.get(dev["type"], DEVICE_TYPES["SWITCH"])
        
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            with c1:
                st.markdown(f"**{style['icon']} {dev_id}** (L{layer})")
                if dev["metadata"].get("vendor"):
                    st.caption(dev["metadata"]["vendor"])
            
            # 操作ボタン類
            # 接続モード中は無効化
            is_disabled = st.session_state.connect_mode is not None
            
            with c2:
                if st.button("↓ 下位接続", key=f"btn_down_{dev_id}", 
                             disabled=is_disabled, use_container_width=True):
                    st.session_state.connect_mode = {"source": dev_id, "mode": "uplink"}
                    st.rerun()
            with c3:
                if st.button("→ ピア接続", key=f"btn_peer_{dev_id}", 
                             disabled=is_disabled, use_container_width=True):
                    st.session_state.connect_mode = {"source": dev_id, "mode": "peer"}
                    st.rerun()
            with c4:
                if st.button("🗑️", key=f"btn_del_{dev_id}", disabled=is_disabled):
                    del st.session_state.devices[dev_id]
                    # 関連する接続も削除
                    st.session_state.connections = [
                        c for c in st.session_state.connections
                        if c["from"] != dev_id and c["to"] != dev_id
                    ]
                    st.rerun()

def render_connection_list():
    """接続リスト削除"""
    if not st.session_state.connections:
        return
        
    with st.expander(f"🔗 接続リスト ({len(st.session_state.connections)})"):
        for i, conn in enumerate(st.session_state.connections):
            c1, c2 = st.columns([6, 1])
            with c1:
                if conn["type"] == "uplink":
                    # データ: from(子) -> to(親)
                    # 表示: 親 -> 子 (Downlink表現の方が直感的な場合が多いが、ここではデータ通り表示しつつ補足)
                    st.write(f"🔹 {conn['to']} (親) ← {conn['from']} (子)")
                else:
                    st.write(f"🔸 {conn['from']} ↔ {conn['to']}")
            with c2:
                if st.button("✕", key=f"del_conn_{i}"):
                    st.session_state.connections.pop(i)
                    st.rerun()

def render_data_io():
    """データ入出力"""
    st.divider()
    st.subheader("💾 データ管理")
    
    c1, c2 = st.columns(2)
    
    # Export
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
        st.caption("※ Streamlit Cloudではブラウザリロードでデータが消えるため、こまめにダウンロードしてください。")

    # Import
    with c2:
        uploaded = st.file_uploader("📤 JSONを読み込み (復元)", type=["json"])
        if uploaded:
            try:
                data = json.load(uploaded)
                if "devices" in data and "connections" in data:
                    if st.button("データを適用する", type="primary", use_container_width=True):
                        st.session_state.devices = data["devices"]
                        st.session_state.connections = data["connections"]
                        st.success("読み込み完了")
                        st.rerun()
            except Exception as e:
                st.error(f"読み込みエラー: {e}")

# ==================== メイン処理 ====================
def main():
    init_session()
    
    st.title("🔧 トポロジービルダー")
    
    # 1. ネットワーク図（常に上部に表示）
    components.html(generate_visjs_html(), height=460)
    
    # 2. 接続モード（アクティブ時のみ表示）
    render_connect_mode()
    
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        # 3. デバイス追加
        render_add_device()
        # 4. デバイス一覧・操作
        render_device_list()
        
    with col_right:
        # 5. 接続リスト
        render_connection_list()
        # 6. データIO
        render_data_io()

if __name__ == "__main__":
    main()
