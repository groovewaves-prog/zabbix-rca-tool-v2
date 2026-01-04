"""
Zabbix RCA Tool - 根本原因分析 & AI復旧支援 (Standalone Mock Edition)
外部ファイルやNetworkXに依存せず、単体で動作確認可能なバージョン
"""

import streamlit as st
import streamlit.components.v1 as components
import json
import os
import time
from typing import Dict, List, Any, Tuple

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


# ==================== モック関数 (AI Ops & API) ====================

def mock_stream_text(text: str):
    """AIのストリーミング生成を演出するモック"""
    chunk_size = 5
    for i in range(0, len(text), chunk_size):
        time.sleep(0.05)  # 生成速度の演出
        yield text[i:i+chunk_size]


def generate_remediation_mock(device_name: str, error: str):
    """network_ops.py の代わりとなるモック生成"""
    return f"""
**推奨される復旧手順 ({device_name})**

1. **接続状態の確認**
   対象機器へのSSH接続を試行します... `Success`
   
2. **ログの確認**
   エラーログ: `{error}` を検出しました。
   インターフェースカウンタにCRCエラーが多数見られます。

3. **推奨コマンドの実行**
   以下のコマンド投入を推奨します:
   ```bash
   conf t
   interface GigabitEthernet1/0/1
    shutdown
    no shutdown
   end
   write memory
   ```

4. **再起動 (オプション)**
   復旧しない場合、再起動が必要です。
"""


def generate_report_mock(device_name: str):
    """レポート生成のモック"""
    return f"""
# 障害分析レポート: {device_name}

## 概要
- **発生日時**: {time.strftime("%Y-%m-%d %H:%M:%S")}
- **対象**: {device_name}
- **影響範囲**: 下流のデバイス数台に波及

## 分析結果
トポロジー分析の結果、{device_name} が根本原因（Root Cause）であると特定されました。
上位ネットワークからの切断、またはハードウェア障害の可能性があります。

## 対応履歴
AIアシスタントにより復旧コマンドが生成され、オペレーターにより適用されました。
"""


class MockZabbixAPI:
    def call(self, method: str, params: Any = None):
        time.sleep(0.5)
        # モックシナリオ: Router01がダウンし、配下も全滅
        if method == "problem.get":
            return [
                {"eventid": "1001", "objectid": "tr_r1", "name": "Router01 is unavailable (ICMP Ping)", "severity": "5", "hosts": [{"host": "Router01"}]},
                {"eventid": "1002", "objectid": "tr_sw1", "name": "Switch01 is unavailable", "severity": "4", "hosts": [{"host": "Switch01"}]},
                {"eventid": "1003", "objectid": "tr_sw2", "name": "Switch02 is unavailable", "severity": "4", "hosts": [{"host": "Switch02"}]}
            ]
        return []


# ==================== RCAロジック (簡易版 - NetworkX不使用) ====================

def load_topology():
    path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def perform_rca_simple(problems: List[Dict], topology: Dict) -> Tuple[List[Dict], List[Dict]]:
    """NetworkXを使わずに辞書操作だけでRCAを行う簡易ロジック"""
    problem_hosts = set()
    host_problem_map = {}

    # 障害ホストのリスト化
    for p in problems:
        if not p.get("hosts"):
            continue
        h = p["hosts"][0]["host"]
        problem_hosts.add(h)
        host_problem_map[h] = p

    # 親子関係マップの作成 (Child -> Parents)
    child_to_parents = {}
    connections = topology.get("connections", [])
    for conn in connections:
        if conn["type"] == "uplink":
            child = conn["from"]
            parent = conn["to"]
            if child not in child_to_parents:
                child_to_parents[child] = []
            child_to_parents[child].append(parent)

    root_causes = []
    symptoms = []

    for h in problem_hosts:
        prob = host_problem_map[h]

        # 親を探す
        parents = child_to_parents.get(h, [])

        # 親のいずれかが障害状態か？
        is_symptom = False
        for p in parents:
            if p in problem_hosts:
                is_symptom = True
                break

        if is_symptom:
            symptoms.append({"host": h, "data": prob})
        else:
            # 影響範囲（Impacts）の特定（簡易的に直下のみ探索）
            impacts = []
            for c_host, p_list in child_to_parents.items():
                if h in p_list and c_host in problem_hosts:
                    impacts.append(c_host)

            root_causes.append({"host": h, "data": prob, "impacts": impacts})

    # 深刻度順にソート
    root_causes.sort(key=lambda x: int(x["data"]["severity"]), reverse=True)
    return root_causes, symptoms


# ==================== UIコンポーネント ====================

def render_visjs(topology, rc_list, sym_list):
    rc_hosts = set([r["host"] for r in rc_list])
    sym_hosts = set([s["host"] for s in sym_list])
    nodes = []
    for did, d in topology.get("topology", {}).items():
        color, shape, size = "#66BB6A", "box", 25
        if did in rc_hosts:
            color, shape, size = "#EF5350", "ellipse", 40
        elif did in sym_hosts:
            color = "#FFA726"

        meta = d.get("metadata", {})
        label = f"{did}\\n({meta.get('vendor', '')})"
        nodes.append({
            "id": did,
            "label": label,
            "color": color,
            "shape": shape,
            "size": size,
            "font": {"color": "white" if did in rc_hosts else "black"}
        })

    edges = [
        {"from": c["from"], "to": c["to"], "arrows": "to" if c["type"] == "uplink" else ""}
        for c in topology.get("connections", [])
    ]

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


def render_ai_ops_panel(target_rc: Dict):
    """モック版 AI Ops パネル"""
    host = target_rc['host']
    error = target_rc['data']['name']

    tab_fix, tab_report, tab_chat = st.tabs(["🛠️ 修復コマンド", "📝 レポート", "💬 Chat"])

    with tab_fix:
        if st.button("🚀 修復案を生成", key="btn_fix"):
            st.write("--- AI Response ---")
            ph = st.empty()
            full_text = ""
            mock_text = generate_remediation_mock(host, error)
            for chunk in mock_stream_text(mock_text):
                full_text += chunk
                ph.markdown(full_text + "▌")
            ph.markdown(full_text)

    with tab_report:
        if st.button("📄 レポート生成", key="btn_rep"):
            ph = st.empty()
            full_text = ""
            mock_text = generate_report_mock(host)
            for chunk in mock_stream_text(mock_text):
                full_text += chunk
                ph.markdown(full_text + "▌")
            ph.markdown(full_text)

    with tab_chat:
        st.write("AIチャット機能（モック）")
        q = st.text_input("質問を入力")
        if st.button("送信") and q:
            st.write(f"🤖 AI: '{q}' についての回答です...（本来はここにGeminiの回答が入ります）")


# ==================== メイン処理 ====================

def main():
    if "rca_data" not in st.session_state:
        st.session_state.rca_data = None
    if "selected_rc_host" not in st.session_state:
        st.session_state.selected_rc_host = None

    with st.sidebar:
        st.header("⚙️ RCA Config")
        st.checkbox("🧪 Mock Mode", value=True, disabled=True, help="この環境ではMockのみ動作します")

        st.divider()
        if st.button("🔄 Refresh Data", type="primary"):
            st.session_state.rca_data = None
            st.session_state.selected_rc_host = None
            st.rerun()

    st.title("🔍 根本原因分析 & AI復旧支援 (Demo)")

    # データロード
    topo = load_topology()
    if not topo:
        st.error("⚠️ トポロジーデータがありません。先に 'Topology Builder' でデータを作成・保存してください。")
        return

    # APIコール (Mock)
    if not st.session_state.rca_data:
        api = MockZabbixAPI()
        st.session_state.rca_data = api.call("problem.get")

    # RCA実行 (Simple Logic)
    root_causes, symptoms = perform_rca_simple(st.session_state.rca_data, topo)

    # レイアウト
    c_map, c_list = st.columns([5, 4])

    with c_map:
        st.subheader("🗺️ 障害トポロジー")
        render_visjs(topo, root_causes, symptoms)

        if st.session_state.selected_rc_host:
            st.divider()
            target = next((r for r in root_causes if r["host"] == st.session_state.selected_rc_host), None)
            if target:
                render_ai_ops_panel(target)
            else:
                st.info("選択解除されました。")

    with c_list:
        st.subheader("🚨 対応チケット (Root Causes)")
        if not root_causes:
            st.success("No active root causes.")

        for i, rc in enumerate(root_causes):
            sev = SEVERITY_MAP.get(rc["data"]["severity"], {})
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{rc['host']}**")
                c2.caption(sev.get("label", "Unknown"))
                st.error(rc["data"]["name"])

                if st.button(f"🤖 AIアシスタント起動", key=f"ai_btn_{i}", use_container_width=True):
                    st.session_state.selected_rc_host = rc["host"]
                    st.rerun()


if __name__ == "__main__":
    main()
