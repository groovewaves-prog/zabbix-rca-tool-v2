"""
Zabbix RCA Tool - 根本原因分析 & AI復旧支援 (Hybrid Edition)
確実なトポロジー分析で真因を特定し、Generative AIで復旧を支援する
"""

import streamlit as st
import streamlit.components.v1 as components
import json
import os
import requests
import time
import networkx as nx
from typing import Dict, List, Any, Tuple

# === 既存AIモジュールの統合 ===
try:
    from network_ops import (
        generate_remediation_commands_streaming,
        generate_analyst_report_streaming,
        sanitize_output
    )
    HAS_AI_OPS = True
except ImportError:
    HAS_AI_OPS = False

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="RCA & AI Ops - Zabbix Tool",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 定数・設定 ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

SEVERITY_MAP = {
    "5": {"label": "Disaster", "color": "#E45959"},
    "4": {"label": "High", "color": "#E97659"},
    "3": {"label": "Average", "color": "#FFA059"},
    "2": {"label": "Warning", "color": "#FFC859"},
    "1": {"label": "Information", "color": "#7499FF"},
    "0": {"label": "Not classified", "color": "#97AAB3"}
}

# ==================== クラス定義 (API) ====================
class ZabbixAPI:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip('/') + '/api_jsonrpc.php'
        self.headers = {'Content-Type': 'application/json'}
        self.auth = token
        self.id_counter = 1

    def call(self, method: str, params: Any = None):
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "auth": self.auth, "id": self.id_counter}
        self.id_counter += 1
        try:
            res = requests.post(self.url, headers=self.headers, json=payload, timeout=5)
            res.raise_for_status()
            result = res.json()
            if 'error' in result: raise Exception(result['error']['data'])
            return result.get('result')
        except Exception as e: raise Exception(f"Connection Failed: {str(e)}")

class MockZabbixAPI:
    def __init__(self): pass
    def call(self, method: str, params: Any = None):
        time.sleep(0.5)
        if method == "problem.get":
            return [
                {"eventid": "1001", "objectid": "tr_r1", "name": "Router01 is unavailable (ICMP Ping)", "severity": "5", "hosts": [{"host": "Router01"}]},
                {"eventid": "1002", "objectid": "tr_sw1", "name": "Switch01 is unavailable", "severity": "4", "hosts": [{"host": "Switch01"}]},
                {"eventid": "1003", "objectid": "tr_sw2", "name": "Switch02 is unavailable", "severity": "4", "hosts": [{"host": "Switch02"}]}
            ]
        return []

# ==================== RCAロジック (Deterministic) ====================
def load_topology():
    path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    return {}

def build_dependency_graph(topology: Dict) -> nx.DiGraph:
    G = nx.DiGraph()
    for dev_id in topology.get("topology", {}).keys(): G.add_node(dev_id)
    for conn in topology.get("connections", []):
        if conn["type"] == "uplink":
            G.add_edge(conn["to"], conn["from"]) # Parent -> Child
    return G

def perform_rca(problems: List[Dict], G: nx.DiGraph) -> Tuple[List[Dict], List[Dict]]:
    problem_hosts = set()
    host_problem_map = {}
    for p in problems:
        if not p.get("hosts"): continue
        h = p["hosts"][0]["host"]
        problem_hosts.add(h)
        host_problem_map[h] = p

    root_causes = []
    symptoms = []

    for h in problem_hosts:
        prob = host_problem_map[h]
        if h not in G:
            root_causes.append({"host": h, "data": prob, "impacts": []})
            continue

        parents = list(G.predecessors(h))
        is_symptom = False
        for p in parents:
            if p in problem_hosts: is_symptom = True; break
        
        if is_symptom:
            symptoms.append({"host": h, "data": prob})
        else:
            root_causes.append({"host": h, "data": prob, "impacts": []})

    for rc in root_causes:
        if rc["host"] in G:
            desc = nx.descendants(G, rc["host"])
            rc["impacts"] = [d for d in desc if d in problem_hosts]
    
    root_causes.sort(key=lambda x: int(x["data"]["severity"]), reverse=True)
    return root_causes, symptoms

# ==================== UIコンポーネント ====================
def render_visjs(topology, rc_list, sym_list):
    rc_hosts = set([r["host"] for r in rc_list])
    sym_hosts = set([s["host"] for s in sym_list])
    nodes = []
    for did, d in topology.get("topology", {}).items():
        color, shape, size = "#66BB6A", "box", 25
        if did in rc_hosts: color, shape, size = "#EF5350", "ellipse", 40
        elif did in sym_hosts: color = "#FFA726"
        
        meta = d.get("metadata", {})
        label = f"{did}\n({meta.get('vendor','')})"
        nodes.append({"id": did, "label": label, "color": color, "shape": shape, "size": size, "font": {"color": "black"}})
    
    edges = [{"from": c["from"], "to": c["to"], "arrows": "to" if c["type"]=="uplink" else ""} for c in topology.get("connections", [])]
    
    html = f"""
    <html><head><script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script></head>
    <body><div id="mynetwork" style="height:400px;border:1px solid lightgray;"></div>
    <script>
    var data = {{nodes: new vis.DataSet({json.dumps(nodes)}), edges: new vis.DataSet({json.dumps(edges)})}};
    var options = {{layout:{{hierarchical:{{enabled:true, direction:"UD", sortMethod:"directed"}}}}, physics:{{enabled:false}}}};
    new vis.Network(document.getElementById('mynetwork'), data, options);
    </script></body></html>
    """
    components.html(html, height=420)

# ==================== AI Ops パネル (Uploaded Logic) ====================
def render_ai_ops_panel(target_rc: Dict, topology: Dict):
    """
    選択された真因に対して、app.py/network_ops.py の機能を適用するパネル
    """
    st.markdown(f"### 🤖 AI Ops Support: {target_rc['host']}")
    
    # コンテキスト情報の抽出
    h_data = topology.get("topology", {}).get(target_rc['host'], {})
    meta = h_data.get("metadata", {})
    vendor = meta.get("vendor", "Unknown")
    model = meta.get("model", "Unknown")
    error_msg = target_rc['data']['name']
    
    st.info(f"**Target:** {vendor} {model} | **Error:** {error_msg}")

    # タブによる機能切り替え
    tab_fix, tab_report, tab_chat = st.tabs(["🛠️ 修復コマンド生成", "📝 障害レポート作成", "💬 AIチャット"])

    # 1. 修復コマンド (network_ops.py)
    with tab_fix:
        st.write("この障害に対する推奨復旧手順とコマンドを生成します。")
        if st.button("🚀 修復案を生成 (Streaming)", key="btn_fix"):
            if not HAS_AI_OPS:
                st.error("network_ops.py が見つかりません。")
            else:
                st.write("--- AI Response ---")
                placeholder = st.empty()
                full_text = ""
                # シナリオを合成して渡す
                scenario_desc = f"Device {target_rc['host']} ({vendor} {model}) is down. Error: {error_msg}."
                
                # network_opsの関数を呼び出し
                # ※実運用ではデバイス定義(SANDBOX_DEVICE等)を動的に書き換える等の調整が必要
                try:
                    # device_infoのモック作成
                    dev_info = {"device_type": "cisco_ios", "host": target_rc['host']} 
                    
                    stream = generate_remediation_commands_streaming(
                        device_id=target_rc['host'],
                        device_info=dev_info,
                        scenario=scenario_desc
                    )
                    for chunk in stream:
                        full_text += chunk
                        placeholder.markdown(full_text + "▌")
                    placeholder.markdown(full_text)
                except Exception as e:
                    st.error(f"AI Error: {e}")

    # 2. レポート作成 (network_ops.py)
    with tab_report:
        if st.button("📄 レポート生成", key="btn_rep"):
            if HAS_AI_OPS:
                st.write("--- Analysis Report ---")
                ph = st.empty()
                txt = ""
                try:
                    stream = generate_analyst_report_streaming(
                        incident_data={"host": target_rc['host'], "error": error_msg, "impact": len(target_rc['impacts'])},
                        topology_context=f"Parent of {len(target_rc['impacts'])} devices"
                    )
                    for chunk in stream:
                        txt += chunk
                        ph.markdown(txt + "▌")
                    ph.markdown(txt)
                except Exception as e:
                    st.error(f"Generate Error: {e}")

    # 3. 簡易チャット (app.pyのロジックを簡易移植)
    with tab_chat:
        user_input = st.text_input("AIに質問する (例: このルーターの再起動コマンドは？)", key="chat_in")
        if st.button("送信", key="chat_send") and user_input:
            # ここではシンプルにGeminiを呼ぶ（本来はConversation Chain推奨）
            import google.generativeai as genai
            model = genai.GenerativeModel("gemma-3-12b-it")
            prompt = f"あなたはネットワークエンジニアのアシスタントです。\n対象機器: {vendor} {model}\n状況: {error_msg}\n\nユーザーの質問: {user_input}"
            try:
                with st.spinner("考え中..."):
                    res = model.generate_content(prompt)
                    st.markdown(res.text)
            except Exception as e:
                st.error(f"Chat Error: {e}")

# ==================== メイン処理 ====================
def main():
    if "rca_data" not in st.session_state: st.session_state.rca_data = None
    if "selected_rc_host" not in st.session_state: st.session_state.selected_rc_host = None

    # サイドバー設定
    with st.sidebar:
        st.header("⚙️ RCA Config")
        use_mock = st.checkbox("🧪 Mock Mode", value=True)
        # API Keyは network_ops.py でも使われるため、環境変数かsecrets推奨だがここでも入力可
        api_key = st.text_input("Google API Key (Gemini)", type="password")
        if api_key: os.environ["GOOGLE_API_KEY"] = api_key
        
        st.divider()
        if st.button("🔄 Refresh Data", type="primary"):
            st.session_state.rca_data = None
            st.session_state.selected_rc_host = None
            st.rerun()

    st.title("🔍 根本原因分析 & AI復旧支援")

    # データロード & 取得
    topo = load_topology()
    if not topo: st.error("No Topology Data"); return

    if not st.session_state.rca_data:
        try:
            api = MockZabbixAPI() if use_mock else ZabbixAPI("http://url", "token") # URL/Tokenは適宜
            st.session_state.rca_data = api.call("problem.get")
        except: st.error("Data Fetch Error"); return

    # RCA実行
    G = build_dependency_graph(topo)
    root_causes, symptoms = perform_rca(st.session_state.rca_data, G)

    # レイアウト
    c_map, c_list = st.columns([5, 4])
    
    with c_map:
        st.subheader("🗺️ 障害トポロジー")
        render_visjs(topo, root_causes, symptoms)
        # AIパネルの表示（真因が選択されている場合）
        if st.session_state.selected_rc_host:
            st.divider()
            # 選択された真因データを特定
            target = next((r for r in root_causes if r["host"] == st.session_state.selected_rc_host), None)
            if target:
                render_ai_ops_panel(target, topo)
            else:
                st.info("選択された障害は解消しました。")

    with c_list:
        st.subheader("🚨 対応チケット (Root Causes)")
        if not root_causes: st.success("No active root causes.")
        
        for i, rc in enumerate(root_causes):
            sev = SEVERITY_MAP.get(rc["data"]["severity"], {})
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{rc['host']}**")
                c2.caption(sev.get("label", "Unknown"))
                st.error(rc["data"]["name"])
                
                # AIアシスタント起動ボタン
                if st.button(f"🤖 AIアシスタント起動", key=f"ai_btn_{i}", use_container_width=True):
                    st.session_state.selected_rc_host = rc["host"]
                    st.rerun()

if __name__ == "__main__":
    main()
