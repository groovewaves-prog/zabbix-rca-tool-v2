"""
Zabbix RCA Tool - 根本原因分析 & AI復旧支援 (Enhanced Demo Edition)
大量アラームから真因特定・優先順位付けをデモできるバージョン
"""

import streamlit as st
import streamlit.components.v1 as components
import json
import os
import time
import random
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

# ==================== 内蔵デモトポロジー ====================
DEMO_TOPOLOGY = {
    "site_name": "Tokyo-DC",
    "topology": {
        # コア層
        "Core-Router01": {"type": "ROUTER", "metadata": {"vendor": "Cisco", "model": "ASR1001-X", "location": "Rack-A1"}},
        "Core-Router02": {"type": "ROUTER", "metadata": {"vendor": "Cisco", "model": "ASR1001-X", "location": "Rack-A2"}},
        # ディストリビューション層
        "Dist-SW01": {"type": "SWITCH", "metadata": {"vendor": "Cisco", "model": "Catalyst 9300", "location": "Rack-B1"}},
        "Dist-SW02": {"type": "SWITCH", "metadata": {"vendor": "Cisco", "model": "Catalyst 9300", "location": "Rack-B2"}},
        "Dist-SW03": {"type": "SWITCH", "metadata": {"vendor": "Juniper", "model": "EX4300", "location": "Rack-B3"}},
        # アクセス層
        "Access-SW01": {"type": "SWITCH", "metadata": {"vendor": "Cisco", "model": "Catalyst 2960", "location": "Rack-C1"}},
        "Access-SW02": {"type": "SWITCH", "metadata": {"vendor": "Cisco", "model": "Catalyst 2960", "location": "Rack-C2"}},
        "Access-SW03": {"type": "SWITCH", "metadata": {"vendor": "Cisco", "model": "Catalyst 2960", "location": "Rack-C3"}},
        "Access-SW04": {"type": "SWITCH", "metadata": {"vendor": "Juniper", "model": "EX2300", "location": "Rack-C4"}},
        "Access-SW05": {"type": "SWITCH", "metadata": {"vendor": "Juniper", "model": "EX2300", "location": "Rack-C5"}},
        "Access-SW06": {"type": "SWITCH", "metadata": {"vendor": "Arista", "model": "7010T", "location": "Rack-C6"}},
        # サーバー
        "Server01": {"type": "SERVER", "metadata": {"vendor": "Dell", "model": "PowerEdge R640", "location": "Rack-D1"}},
        "Server02": {"type": "SERVER", "metadata": {"vendor": "Dell", "model": "PowerEdge R640", "location": "Rack-D2"}},
        "Server03": {"type": "SERVER", "metadata": {"vendor": "HP", "model": "ProLiant DL380", "location": "Rack-D3"}},
        "Server04": {"type": "SERVER", "metadata": {"vendor": "HP", "model": "ProLiant DL380", "location": "Rack-D4"}},
        "Server05": {"type": "SERVER", "metadata": {"vendor": "Dell", "model": "PowerEdge R740", "location": "Rack-D5"}},
        "Server06": {"type": "SERVER", "metadata": {"vendor": "Dell", "model": "PowerEdge R740", "location": "Rack-D6"}},
        # ファイアウォール
        "FW01": {"type": "FIREWALL", "metadata": {"vendor": "Palo Alto", "model": "PA-3220", "location": "Rack-A3"}},
    },
    "connections": [
        # コア → ディストリビューション
        {"from": "Dist-SW01", "to": "Core-Router01", "type": "uplink"},
        {"from": "Dist-SW02", "to": "Core-Router01", "type": "uplink"},
        {"from": "Dist-SW02", "to": "Core-Router02", "type": "uplink"},
        {"from": "Dist-SW03", "to": "Core-Router02", "type": "uplink"},
        # ディストリビューション → アクセス
        {"from": "Access-SW01", "to": "Dist-SW01", "type": "uplink"},
        {"from": "Access-SW02", "to": "Dist-SW01", "type": "uplink"},
        {"from": "Access-SW03", "to": "Dist-SW02", "type": "uplink"},
        {"from": "Access-SW04", "to": "Dist-SW02", "type": "uplink"},
        {"from": "Access-SW05", "to": "Dist-SW03", "type": "uplink"},
        {"from": "Access-SW06", "to": "Dist-SW03", "type": "uplink"},
        # アクセス → サーバー
        {"from": "Server01", "to": "Access-SW01", "type": "uplink"},
        {"from": "Server02", "to": "Access-SW02", "type": "uplink"},
        {"from": "Server03", "to": "Access-SW03", "type": "uplink"},
        {"from": "Server04", "to": "Access-SW04", "type": "uplink"},
        {"from": "Server05", "to": "Access-SW05", "type": "uplink"},
        {"from": "Server06", "to": "Access-SW06", "type": "uplink"},
        # ファイアウォール
        {"from": "FW01", "to": "Core-Router01", "type": "uplink"},
    ]
}

# ==================== デモシナリオ定義 ====================
DEMO_SCENARIOS = {
    "simple": {
        "name": "🟢 シンプル障害（真因1件）",
        "description": "Core-Router01 がダウンし、配下の機器がすべて影響を受けるケース",
        "root_causes": ["Core-Router01"],
        "additional_alerts": []  # 真因の配下は自動生成
    },
    "multi_root": {
        "name": "🟡 複数真因（真因2件）",
        "description": "Core-Router01 と Dist-SW03 が同時にダウン。2系統で障害発生",
        "root_causes": ["Core-Router01", "Dist-SW03"],
        "additional_alerts": []
    },
    "cascade": {
        "name": "🔴 カスケード障害（真因3件 + 大量アラーム）",
        "description": "複数箇所で同時多発的に障害。大量アラームの中から真因を特定",
        "root_causes": ["Core-Router01", "Dist-SW02", "Access-SW06"],
        "additional_alerts": [
            # 追加のノイズアラーム（CPU高負荷など）
            {"host": "FW01", "name": "FW01: High CPU utilization (92%)", "severity": "3"},
            {"host": "Server02", "name": "Server02: Disk space low (85%)", "severity": "2"},
            {"host": "Core-Router02", "name": "Core-Router02: BGP neighbor flapping", "severity": "3"},
        ]
    },
    "noisy": {
        "name": "🟣 ノイジー環境（真因1件 + 大量ノイズ）",
        "description": "Dist-SW01 がダウン。関係ないアラームが多数混在し、真因特定が困難な状況",
        "root_causes": ["Dist-SW01"],
        "additional_alerts": [
            {"host": "Core-Router01", "name": "Core-Router01: Interface GigabitEthernet0/1 - High bandwidth utilization", "severity": "2"},
            {"host": "Core-Router02", "name": "Core-Router02: NTP synchronization lost", "severity": "1"},
            {"host": "Dist-SW02", "name": "Dist-SW02: Fan speed warning", "severity": "2"},
            {"host": "Dist-SW03", "name": "Dist-SW03: Power supply redundancy lost", "severity": "3"},
            {"host": "FW01", "name": "FW01: SSL certificate expiring in 7 days", "severity": "1"},
            {"host": "FW01", "name": "FW01: Session count above threshold", "severity": "2"},
            {"host": "Server03", "name": "Server03: Memory utilization high (88%)", "severity": "3"},
            {"host": "Server05", "name": "Server05: Scheduled backup failed", "severity": "2"},
        ]
    }
}


# ==================== モック関数 (AI Ops & API) ====================

def mock_stream_text(text: str):
    """AIのストリーミング生成を演出するモック"""
    chunk_size = 5
    for i in range(0, len(text), chunk_size):
        time.sleep(0.03)
        yield text[i:i+chunk_size]


def generate_remediation_mock(device_name: str, error: str, device_type: str = "SWITCH"):
    """デバイスタイプに応じた復旧手順を生成"""
    
    base_commands = {
        "ROUTER": """
   ```bash
   # ルーター診断コマンド
   show ip route summary
   show ip bgp summary
   show interfaces status
   
   # 復旧コマンド
   clear ip bgp * soft
   ```""",
        "SWITCH": """
   ```bash
   # スイッチ診断コマンド
   show spanning-tree summary
   show mac address-table count
   show interfaces status
   
   # 復旧コマンド
   conf t
   interface range GigabitEthernet1/0/1-48
    shutdown
    no shutdown
   end
   write memory
   ```""",
        "FIREWALL": """
   ```bash
   # ファイアウォール診断コマンド
   show session info
   show system resources
   show high-availability state
   
   # 復旧コマンド
   request restart system
   ```""",
        "SERVER": """
   ```bash
   # サーバー診断コマンド
   systemctl status
   journalctl -xe --no-pager | tail -50
   df -h
   free -m
   
   # 復旧コマンド
   systemctl restart network
   ```"""
    }
    
    cmd_section = base_commands.get(device_type, base_commands["SWITCH"])
    
    return f"""
**推奨される復旧手順 ({device_name})**

1. **接続状態の確認**
   対象機器へのSSH/管理接続を試行します... 
   - プライマリIP: `Timeout`
   - OOBM (Out-of-Band Management): `Success`
   
2. **ログの確認**
   エラーログ: `{error}` を検出しました。
   - 発生時刻: {time.strftime("%Y-%m-%d %H:%M:%S")}
   - 連続発生回数: 3回
   - 関連アラート: インターフェースダウン、SNMP応答なし

3. **推奨コマンドの実行**
   以下のコマンド投入を推奨します:
{cmd_section}

4. **エスカレーション判断**
   - 上記で復旧しない場合 → ハードウェア障害の可能性
   - ベンダーサポートへの連絡を推奨
   - 交換機の手配を検討

5. **事後対応**
   - 障害報告書の作成
   - 構成管理DBの更新
   - 監視閾値の見直し検討
"""


def generate_report_mock(device_name: str, impacts: List[str] = None):
    """影響範囲を含むレポート生成"""
    impact_section = ""
    if impacts:
        impact_list = "\n".join([f"   - {h}" for h in impacts])
        impact_section = f"""
### 影響を受けた機器 ({len(impacts)}台)
{impact_list}
"""
    
    return f"""
# 障害分析レポート: {device_name}

## 概要
| 項目 | 値 |
|------|-----|
| 発生日時 | {time.strftime("%Y-%m-%d %H:%M:%S")} |
| 対象機器 | {device_name} |
| 検出方法 | ICMP Ping / SNMP |
| 影響台数 | {len(impacts) if impacts else 0} 台 |

## 分析結果

### 根本原因の特定
トポロジー分析の結果、**{device_name}** が根本原因（Root Cause）であると特定されました。

### 推定される障害原因
1. ハードウェア障害（電源、ファン、メモリ等）
2. ソフトウェア障害（OSクラッシュ、プロセス異常終了）
3. 設定ミス（最近の変更作業による影響）
4. 外部要因（電源障害、空調障害、ケーブル断）
{impact_section}
## 対応タイムライン
| 時刻 | アクション |
|------|----------|
| {time.strftime("%H:%M:%S")} | アラート検出 |
| - | RCAツールによる分析開始 |
| - | 根本原因特定完了 |
| - | 復旧作業開始 |

## 推奨アクション
1. 対象機器への物理アクセス確認
2. コンソール接続による状態確認
3. 必要に応じてハードウェア交換
4. 構成バックアップからのリストア
"""


class MockZabbixAPI:
    """シナリオに基づいてアラームを生成するモックAPI"""
    
    def __init__(self, scenario_key: str = "simple", topology: Dict = None):
        self.scenario_key = scenario_key
        self.topology = topology or DEMO_TOPOLOGY
        self.scenario = DEMO_SCENARIOS.get(scenario_key, DEMO_SCENARIOS["simple"])
    
    def _get_all_downstream_hosts(self, root_host: str) -> List[str]:
        """指定ホストの配下にある全ホストを再帰的に取得"""
        connections = self.topology.get("connections", [])
        
        # 親→子のマップを作成
        parent_to_children = {}
        for conn in connections:
            if conn["type"] == "uplink":
                parent = conn["to"]
                child = conn["from"]
                if parent not in parent_to_children:
                    parent_to_children[parent] = []
                parent_to_children[parent].append(child)
        
        # 再帰的に配下を探索
        downstream = []
        queue = [root_host]
        visited = set()
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            children = parent_to_children.get(current, [])
            for child in children:
                if child not in visited:
                    downstream.append(child)
                    queue.append(child)
        
        return downstream
    
    def call(self, method: str, params: Any = None):
        time.sleep(0.3)
        
        if method == "problem.get":
            problems = []
            event_id = 1000
            
            # 真因のアラームを生成
            for rc_host in self.scenario["root_causes"]:
                dev_info = self.topology.get("topology", {}).get(rc_host, {})
                dev_type = dev_info.get("type", "SWITCH")
                
                problems.append({
                    "eventid": str(event_id),
                    "objectid": f"tr_{rc_host.lower()}",
                    "name": f"{rc_host} is unavailable (ICMP Ping)",
                    "severity": "5",  # Disaster
                    "hosts": [{"host": rc_host}],
                    "_is_root_cause": True,
                    "_device_type": dev_type
                })
                event_id += 1
                
                # 配下のホストも障害として追加
                downstream = self._get_all_downstream_hosts(rc_host)
                for ds_host in downstream:
                    ds_info = self.topology.get("topology", {}).get(ds_host, {})
                    ds_type = ds_info.get("type", "SWITCH")
                    
                    problems.append({
                        "eventid": str(event_id),
                        "objectid": f"tr_{ds_host.lower()}",
                        "name": f"{ds_host} is unavailable (ICMP Ping)",
                        "severity": "4",  # High
                        "hosts": [{"host": ds_host}],
                        "_is_root_cause": False,
                        "_device_type": ds_type
                    })
                    event_id += 1
            
            # 追加のノイズアラームを追加
            for alert in self.scenario.get("additional_alerts", []):
                problems.append({
                    "eventid": str(event_id),
                    "objectid": f"tr_noise_{event_id}",
                    "name": alert["name"],
                    "severity": alert["severity"],
                    "hosts": [{"host": alert["host"]}],
                    "_is_root_cause": False,
                    "_device_type": "NOISE"
                })
                event_id += 1
            
            # シャッフルして順番をランダムに（実際の環境を模倣）
            random.shuffle(problems)
            return problems
        
        return []


# ==================== RCAロジック (簡易版 - NetworkX不使用) ====================

def load_topology():
    """外部ファイルまたは内蔵デモトポロジーを読み込む"""
    path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    # 外部ファイルがない場合は内蔵デモトポロジーを使用
    return DEMO_TOPOLOGY


def perform_rca_simple(problems: List[Dict], topology: Dict) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    NetworkXを使わずに辞書操作だけでRCAを行う簡易ロジック
    
    Returns:
        root_causes: 真因リスト
        symptoms: 派生アラーム（真因の影響）
        unrelated: 関係ないアラーム（ノイズ）
    """
    # 接続関係から到達可能なホストの集合を作成
    all_hosts_in_topology = set(topology.get("topology", {}).keys())
    
    problem_hosts = set()
    host_problem_map = {}
    unavailable_hosts = set()  # "unavailable" アラームのホスト

    # 障害ホストのリスト化
    for p in problems:
        if not p.get("hosts"):
            continue
        h = p["hosts"][0]["host"]
        problem_hosts.add(h)
        host_problem_map[h] = p
        
        # "unavailable" アラームかどうかを判定
        if "unavailable" in p.get("name", "").lower():
            unavailable_hosts.add(h)

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
    unrelated = []

    for h in problem_hosts:
        prob = host_problem_map[h]
        
        # トポロジーに存在しないホスト、または "unavailable" でないアラームは unrelated
        if h not in all_hosts_in_topology:
            unrelated.append({"host": h, "data": prob})
            continue
        
        if "unavailable" not in prob.get("name", "").lower():
            unrelated.append({"host": h, "data": prob})
            continue

        # 親を探す
        parents = child_to_parents.get(h, [])

        # 親のいずれかが障害状態（unavailable）か？
        is_symptom = False
        for p in parents:
            if p in unavailable_hosts:
                is_symptom = True
                break

        if is_symptom:
            symptoms.append({"host": h, "data": prob})
        else:
            # 影響範囲（Impacts）の特定（再帰的に全配下を探索）
            impacts = get_all_impacts(h, unavailable_hosts, child_to_parents)
            
            dev_info = topology.get("topology", {}).get(h, {})
            root_causes.append({
                "host": h,
                "data": prob,
                "impacts": impacts,
                "device_type": dev_info.get("type", "SWITCH"),
                "metadata": dev_info.get("metadata", {})
            })

    # 深刻度順にソート（同じ深刻度なら影響範囲が大きい順）
    root_causes.sort(key=lambda x: (int(x["data"]["severity"]), len(x.get("impacts", []))), reverse=True)
    return root_causes, symptoms, unrelated


def get_all_impacts(root_host: str, problem_hosts: set, child_to_parents: Dict) -> List[str]:
    """指定ホストの配下で障害状態にあるホストを全て取得"""
    # 親→子のマップに変換
    parent_to_children = {}
    for child, parents in child_to_parents.items():
        for parent in parents:
            if parent not in parent_to_children:
                parent_to_children[parent] = []
            parent_to_children[parent].append(child)
    
    impacts = []
    queue = [root_host]
    visited = set()
    
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        
        children = parent_to_children.get(current, [])
        for child in children:
            if child in problem_hosts and child not in visited:
                impacts.append(child)
                queue.append(child)
    
    return impacts


# ==================== UIコンポーネント ====================

def render_visjs(topology, rc_list, sym_list, unrelated_list=None):
    """vis.js でトポロジーを可視化"""
    rc_hosts = set([r["host"] for r in rc_list])
    sym_hosts = set([s["host"] for s in sym_list])
    unrelated_hosts = set([u["host"] for u in (unrelated_list or [])])
    
    nodes = []
    for did, d in topology.get("topology", {}).items():
        # デフォルト（正常）
        color = "#66BB6A"  # 緑
        shape = "box"
        size = 25
        border_width = 1
        
        if did in rc_hosts:
            color = "#EF5350"  # 赤（真因）
            shape = "ellipse"
            size = 45
            border_width = 3
        elif did in sym_hosts:
            color = "#FFA726"  # オレンジ（派生）
            size = 30
        elif did in unrelated_hosts:
            color = "#AB47BC"  # 紫（ノイズ）
            shape = "diamond"
            size = 28

        meta = d.get("metadata", {})
        label = f"{did}\\n({meta.get('vendor', '')})"
        nodes.append({
            "id": did,
            "label": label,
            "color": {"background": color, "border": "#333" if did in rc_hosts else color},
            "shape": shape,
            "size": size,
            "borderWidth": border_width,
            "font": {"color": "white" if did in rc_hosts else ("white" if did in sym_hosts else "black")}
        })

    edges = [
        {"from": c["from"], "to": c["to"], "arrows": "to" if c["type"] == "uplink" else "", "color": "#999"}
        for c in topology.get("connections", [])
    ]

    # 凡例を追加
    legend_html = """
    <div style="position:absolute;top:10px;right:10px;background:white;padding:10px;border:1px solid #ccc;border-radius:5px;font-size:12px;">
        <div><span style="display:inline-block;width:15px;height:15px;background:#EF5350;border-radius:50%;margin-right:5px;"></span>Root Cause（真因）</div>
        <div><span style="display:inline-block;width:15px;height:15px;background:#FFA726;margin-right:5px;"></span>Symptom（派生）</div>
        <div><span style="display:inline-block;width:15px;height:15px;background:#AB47BC;transform:rotate(45deg);margin-right:5px;"></span>Unrelated（ノイズ）</div>
        <div><span style="display:inline-block;width:15px;height:15px;background:#66BB6A;margin-right:5px;"></span>Normal（正常）</div>
    </div>
    """

    html = f"""
<html><head>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>body{{margin:0;padding:0;}}#container{{position:relative;width:100%;height:450px;}}</style>
</head>
<body>
<div id="container">
    <div id="mynetwork" style="height:450px;border:1px solid lightgray;"></div>
    {legend_html}
</div>
<script>
var data = {{nodes: new vis.DataSet({json.dumps(nodes)}), edges: new vis.DataSet({json.dumps(edges)})}};
var options = {{
    layout:{{hierarchical:{{enabled:true, direction:"DU", sortMethod:"directed", levelSeparation: 100, nodeSpacing: 150}}}},
    physics:{{enabled:false}},
    interaction:{{hover:true, tooltipDelay:100}}
}};
new vis.Network(document.getElementById('mynetwork'), data, options);
</script></body></html>
"""
    components.html(html, height=470)


def render_ai_ops_panel(target_rc: Dict):
    """AI Ops パネル"""
    host = target_rc['host']
    error = target_rc['data']['name']
    device_type = target_rc.get('device_type', 'SWITCH')
    impacts = target_rc.get('impacts', [])
    metadata = target_rc.get('metadata', {})

    st.markdown(f"""
    **対象機器情報**
    - ホスト名: `{host}`
    - ベンダー: {metadata.get('vendor', 'N/A')}
    - モデル: {metadata.get('model', 'N/A')}
    - 設置場所: {metadata.get('location', 'N/A')}
    - 影響台数: {len(impacts)} 台
    """)

    tab_fix, tab_report, tab_chat = st.tabs(["🛠️ 修復コマンド", "📝 レポート", "💬 Chat"])

    with tab_fix:
        if st.button("🚀 修復案を生成", key="btn_fix"):
            st.write("--- AI Response ---")
            ph = st.empty()
            full_text = ""
            mock_text = generate_remediation_mock(host, error, device_type)
            for chunk in mock_stream_text(mock_text):
                full_text += chunk
                ph.markdown(full_text + "▌")
            ph.markdown(full_text)

    with tab_report:
        if st.button("📄 レポート生成", key="btn_rep"):
            ph = st.empty()
            full_text = ""
            mock_text = generate_report_mock(host, impacts)
            for chunk in mock_stream_text(mock_text):
                full_text += chunk
                ph.markdown(full_text + "▌")
            ph.markdown(full_text)

    with tab_chat:
        st.write("AIチャット機能（モック）")
        q = st.text_input("質問を入力", key="chat_input")
        if st.button("送信", key="chat_send") and q:
            with st.spinner("考え中..."):
                time.sleep(0.5)
            st.write(f"🤖 AI: '{q}' についての回答です。")
            st.write(f"対象機器 {host} ({device_type}) について、{metadata.get('vendor', '')} の公式ドキュメントを参照することを推奨します。")


def render_statistics(root_causes, symptoms, unrelated, total_alerts):
    """RCA統計情報を表示"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="🚨 総アラート数",
            value=total_alerts,
            help="Zabbixから取得した全アラート数"
        )
    
    with col2:
        st.metric(
            label="🎯 真因 (Root Cause)",
            value=len(root_causes),
            delta=f"-{total_alerts - len(root_causes)} 件削減" if total_alerts > len(root_causes) else None,
            delta_color="normal"
        )
    
    with col3:
        st.metric(
            label="🔗 派生アラート",
            value=len(symptoms),
            help="真因の影響で発生した二次的なアラート"
        )
    
    with col4:
        noise_reduction = ((total_alerts - len(root_causes)) / total_alerts * 100) if total_alerts > 0 else 0
        st.metric(
            label="📉 ノイズ削減率",
            value=f"{noise_reduction:.1f}%",
            help="RCAにより削減されたアラート数の割合"
        )


# ==================== メイン処理 ====================

def main():
    if "rca_data" not in st.session_state:
        st.session_state.rca_data = None
    if "selected_rc_host" not in st.session_state:
        st.session_state.selected_rc_host = None
    if "scenario" not in st.session_state:
        st.session_state.scenario = "simple"

    with st.sidebar:
        st.header("⚙️ RCA Config")
        
        # シナリオ選択
        st.subheader("📋 デモシナリオ")
        scenario_options = {k: v["name"] for k, v in DEMO_SCENARIOS.items()}
        selected_scenario = st.selectbox(
            "シナリオを選択",
            options=list(scenario_options.keys()),
            format_func=lambda x: scenario_options[x],
            key="scenario_select"
        )
        
        # シナリオの説明
        st.caption(DEMO_SCENARIOS[selected_scenario]["description"])
        
        st.divider()
        
        # データソース
        use_demo = st.checkbox("🧪 内蔵デモデータを使用", value=True, help="チェックを外すと外部トポロジーファイルを使用")
        
        st.divider()
        
        if st.button("🔄 シナリオ実行", type="primary", use_container_width=True):
            st.session_state.rca_data = None
            st.session_state.selected_rc_host = None
            st.session_state.scenario = selected_scenario
            st.rerun()
        
        if st.button("🗑️ リセット", use_container_width=True):
            st.session_state.rca_data = None
            st.session_state.selected_rc_host = None
            st.rerun()

    st.title("🔍 根本原因分析 & AI復旧支援")
    st.caption("大量のアラームから真因を特定し、ノイズを削減します")

    # データロード
    if use_demo:
        topo = DEMO_TOPOLOGY
    else:
        topo = load_topology()
        
    if not topo:
        st.error("⚠️ トポロジーデータがありません。'内蔵デモデータを使用' をチェックするか、Topology Builder でデータを作成してください。")
        return

    # APIコール (Mock)
    if st.session_state.rca_data is None:
        with st.spinner("Zabbix API からアラート取得中..."):
            api = MockZabbixAPI(st.session_state.scenario, topo)
            st.session_state.rca_data = api.call("problem.get")

    # RCA実行
    root_causes, symptoms, unrelated = perform_rca_simple(st.session_state.rca_data, topo)
    total_alerts = len(st.session_state.rca_data)

    # 統計情報
    render_statistics(root_causes, symptoms, unrelated, total_alerts)
    
    st.divider()

    # レイアウト
    c_map, c_list = st.columns([5, 4])

    with c_map:
        st.subheader("🗺️ 障害トポロジーマップ")
        render_visjs(topo, root_causes, symptoms, unrelated)

        if st.session_state.selected_rc_host:
            st.divider()
            target = next((r for r in root_causes if r["host"] == st.session_state.selected_rc_host), None)
            if target:
                st.subheader(f"🤖 AI Ops: {target['host']}")
                render_ai_ops_panel(target)
            else:
                st.info("選択解除されました。")

    with c_list:
        # 真因リスト
        st.subheader(f"🎯 真因 (Root Causes): {len(root_causes)}件")
        if not root_causes:
            st.success("✅ アクティブな真因はありません")
        
        for i, rc in enumerate(root_causes):
            sev = SEVERITY_MAP.get(rc["data"]["severity"], {})
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**🔴 {rc['host']}**")
                    st.caption(f"{rc.get('metadata', {}).get('vendor', '')} | {rc.get('device_type', '')}")
                with col2:
                    st.markdown(f"<span style='background-color:{sev.get('color', '#999')};color:white;padding:2px 8px;border-radius:3px;font-size:12px;'>{sev.get('label', 'Unknown')}</span>", unsafe_allow_html=True)
                
                st.error(rc["data"]["name"])
                
                if rc.get("impacts"):
                    with st.expander(f"📊 影響範囲: {len(rc['impacts'])}台"):
                        st.write(", ".join(rc["impacts"]))
                
                if st.button("🤖 AIアシスタント起動", key=f"ai_btn_{i}", use_container_width=True):
                    st.session_state.selected_rc_host = rc["host"]
                    st.rerun()
        
        # 派生アラート（折りたたみ）
        if symptoms:
            with st.expander(f"🔗 派生アラート (Symptoms): {len(symptoms)}件", expanded=False):
                for s in symptoms:
                    st.warning(f"**{s['host']}**: {s['data']['name']}")
        
        # ノイズアラート（折りたたみ）
        if unrelated:
            with st.expander(f"📢 その他のアラート: {len(unrelated)}件", expanded=False):
                for u in unrelated:
                    sev = SEVERITY_MAP.get(u["data"]["severity"], {})
                    st.info(f"**{u['host']}**: {u['data']['name']} [{sev.get('label', '')}]")


if __name__ == "__main__":
    main()
