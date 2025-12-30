"""
Zabbix RCA Tool - 監視設定生成
トポロジーからZabbix設定を自動生成
"""

import streamlit as st
import json
import os
from datetime import datetime
from typing import Dict
import pandas as pd

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="監視設定生成 - Zabbix RCA Tool",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== カスタムCSS ====================
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    .config-card {
        padding: 20px;
        border-radius: 10px;
        background: #f8f9fa;
        margin: 10px 0;
    }
    .hint-box {
        padding: 15px;
        background: #e7f3ff;
        border-left: 4px solid #2196f3;
        border-radius: 0 8px 8px 0;
        margin: 15px 0;
    }
</style>
""", unsafe_allow_html=True)

# ==================== データディレクトリ ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def load_topology():
    """トポロジーデータを読み込む"""
    topology_path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(topology_path):
        with open(topology_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_full_topology():
    """完全版トポロジーデータを読み込む"""
    full_path = os.path.join(DATA_DIR, "full_topology.json")
    if os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# ==================== Zabbix設定生成 ====================
def generate_zabbix_config(topology: Dict) -> Dict:
    """トポロジーからZabbix設定を生成"""
    config = {
        "host_groups": [],
        "hosts": [],
        "templates": [],
        "triggers": [],
        "dependencies": []
    }
    
    # 属性収集
    layers = set()
    vendors = set()
    locations = set()
    ha_groups = set()
    
    for host_id, host_data in topology.items():
        layers.add(f"Layer{host_data.get('layer', 0)}")
        if host_data.get("metadata", {}).get("vendor"):
            vendors.add(host_data["metadata"]["vendor"])
        if host_data.get("metadata", {}).get("location"):
            locations.add(host_data["metadata"]["location"])
        if host_data.get("redundancy_group"):
            ha_groups.add(host_data["redundancy_group"])
    
    # ホストグループ生成
    config["host_groups"] = [
        *[{"name": f"Network/{layer}", "type": "layer"} for layer in sorted(layers)],
        *[{"name": f"Vendor/{vendor}", "type": "vendor"} for vendor in vendors],
        *[{"name": f"Location/{loc}", "type": "location"} for loc in locations],
        *[{"name": f"HA_Groups/{group}", "type": "ha"} for group in ha_groups]
    ]
    
    # テンプレートマッピング
    template_map = {
        ("Cisco", "ROUTER"): ["Template Cisco IOS-XE SNMP", "Template ICMP Ping"],
        ("Cisco", "SWITCH"): ["Template Cisco Catalyst SNMP", "Template ICMP Ping"],
        ("Juniper", "FIREWALL"): ["Template Juniper SRX SNMP", "Template ICMP Ping"],
        ("Juniper", "ROUTER"): ["Template Juniper JUNOS SNMP", "Template ICMP Ping"],
        ("Fortinet", "FIREWALL"): ["Template Fortinet FortiGate SNMP", "Template ICMP Ping"],
        ("Palo Alto", "FIREWALL"): ["Template Palo Alto SNMP", "Template ICMP Ping"],
        ("Arista", "SWITCH"): ["Template Arista EOS SNMP", "Template ICMP Ping"],
        ("default", "ROUTER"): ["Template Generic Router SNMP", "Template ICMP Ping"],
        ("default", "SWITCH"): ["Template Generic Switch SNMP", "Template ICMP Ping"],
        ("default", "FIREWALL"): ["Template Generic Firewall SNMP", "Template ICMP Ping"],
        ("default", "ACCESS_POINT"): ["Template Generic SNMP AP", "Template ICMP Ping"],
        ("default", "SERVER"): ["Template Linux by Zabbix Agent", "Template ICMP Ping"],
        ("default", "LOAD_BALANCER"): ["Template Generic Load Balancer", "Template ICMP Ping"],
        ("default", "STORAGE"): ["Template Generic Storage SNMP", "Template ICMP Ping"],
    }
    
    # ホスト設定生成
    for host_id, host_data in topology.items():
        vendor = host_data.get("metadata", {}).get("vendor", "default")
        device_type = host_data.get("type", "unknown")
        
        templates = template_map.get((vendor, device_type), 
                    template_map.get(("default", device_type), ["Template ICMP Ping"]))
        
        groups = [f"Network/Layer{host_data.get('layer', 0)}"]
        if vendor and vendor != "default":
            groups.append(f"Vendor/{vendor}")
        if host_data.get("metadata", {}).get("location"):
            groups.append(f"Location/{host_data['metadata']['location']}")
        if host_data.get("redundancy_group"):
            groups.append(f"HA_Groups/{host_data['redundancy_group']}")
        
        host_config = {
            "host_id": host_id,
            "name": host_id,
            "groups": groups,
            "templates": templates,
            "tags": [
                {"tag": "layer", "value": str(host_data.get("layer", 0))},
                {"tag": "type", "value": device_type},
            ],
            "macros": {}
        }
        
        if vendor and vendor != "default":
            host_config["tags"].append({"tag": "vendor", "value": vendor})
        
        # モデル情報のタグ追加
        if host_data.get("metadata", {}).get("model"):
            host_config["tags"].append({"tag": "model", "value": host_data["metadata"]["model"]})
        
        # PSU_COUNTマクロの設定
        if host_data.get("metadata", {}).get("hw_inventory", {}).get("psu_count"):
            host_config["macros"]["{$PSU_COUNT}"] = host_data["metadata"]["hw_inventory"]["psu_count"]
        
        config["hosts"].append(host_config)
        
        # 依存関係
        if host_data.get("parent_id"):
            config["dependencies"].append({
                "host": host_id,
                "depends_on": host_data["parent_id"],
                "type": "parent"
            })
        
        # マルチパス対応（parent_ids）
        if host_data.get("parent_ids"):
            for i, parent_id in enumerate(host_data["parent_ids"]):
                if i == 0 and parent_id == host_data.get("parent_id"):
                    continue  # 既に追加済み
                config["dependencies"].append({
                    "host": host_id,
                    "depends_on": parent_id,
                    "type": "secondary" if i > 0 else "primary"
                })
    
    # トリガー生成
    for host_id, host_data in topology.items():
        device_type = host_data.get("type", "unknown")
        layer = host_data.get("layer", 99)
        
        # 到達性トリガー
        config["triggers"].append({
            "host": host_id,
            "name": f"{host_id} is unreachable",
            "expression": f"nodata(/{host_id}/icmp.ping,5m)=1",
            "severity": "high" if layer <= 2 else "average"
        })
        
        # ネットワーク機器のCPUトリガー
        if device_type in ["ROUTER", "SWITCH", "FIREWALL", "LOAD_BALANCER"]:
            config["triggers"].append({
                "host": host_id,
                "name": f"{host_id} CPU usage is high",
                "expression": f"last(/{host_id}/system.cpu.util)>80",
                "severity": "warning"
            })
        
        # サーバーのメモリトリガー
        if device_type == "SERVER":
            config["triggers"].append({
                "host": host_id,
                "name": f"{host_id} Memory usage is high",
                "expression": f"last(/{host_id}/vm.memory.util)>90",
                "severity": "warning"
            })
        
        # ストレージのディスクトリガー
        if device_type == "STORAGE":
            config["triggers"].append({
                "host": host_id,
                "name": f"{host_id} Disk space is low",
                "expression": f"last(/{host_id}/vfs.fs.pused)>85",
                "severity": "warning"
            })
        
        # HA監視
        if host_data.get("redundancy_group"):
            config["triggers"].append({
                "host": host_id,
                "name": f"HA Failover detected - {host_id}",
                "expression": f"change(/{host_id}/ha.role,1h)<>0",
                "severity": "warning"
            })
        
        # PSU監視
        psu_count = host_data.get("metadata", {}).get("hw_inventory", {}).get("psu_count", 0)
        if psu_count >= 2:
            config["triggers"].append({
                "host": host_id,
                "name": f"{host_id} PSU failure detected",
                "expression": f"last(/{host_id}/sensor.psu.status)<>0",
                "severity": "warning"
            })
    
    # サマリー追加
    config["summary"] = {
        "host_count": len(config["hosts"]),
        "group_count": len(config["host_groups"]),
        "trigger_count": len(config["triggers"]),
        "dependency_count": len(config["dependencies"])
    }
    
    return config

# ==================== 設定表示 ====================
def display_config_summary(config: Dict):
    """設定を人が読みやすい形式で表示"""
    
    tab1, tab2 = st.tabs(["📊 サマリー表示", "📄 JSON表示"])
    
    with tab1:
        # ホストグループ
        st.subheader("🏷️ ホストグループ")
        if config.get("host_groups"):
            groups_df = pd.DataFrame(config["host_groups"])
            st.dataframe(groups_df, use_container_width=True, hide_index=True)
        
        # ホスト設定
        st.subheader("🖥️ ホスト設定")
        if config.get("hosts"):
            hosts_data = []
            for host in config["hosts"]:
                hosts_data.append({
                    "ホスト名": host.get("host_id", ""),
                    "グループ": ", ".join(host.get("groups", [])),
                    "テンプレート": ", ".join(host.get("templates", [])),
                })
            hosts_df = pd.DataFrame(hosts_data)
            st.dataframe(hosts_df, use_container_width=True, hide_index=True)
        
        # トリガー
        st.subheader("⚡ トリガー")
        if config.get("triggers"):
            triggers_data = []
            for trigger in config["triggers"]:
                triggers_data.append({
                    "ホスト": trigger.get("host", ""),
                    "トリガー名": trigger.get("name", ""),
                    "重要度": trigger.get("severity", ""),
                })
            triggers_df = pd.DataFrame(triggers_data)
            st.dataframe(triggers_df, use_container_width=True, hide_index=True)
        
        # 依存関係
        st.subheader("🔗 依存関係")
        if config.get("dependencies"):
            deps_data = []
            for dep in config["dependencies"]:
                deps_data.append({
                    "ホスト": dep.get("host", ""),
                    "依存先": dep.get("depends_on", ""),
                    "タイプ": dep.get("type", ""),
                })
            deps_df = pd.DataFrame(deps_data)
            st.dataframe(deps_df, use_container_width=True, hide_index=True)
        else:
            st.info("依存関係は設定されていません")
    
    with tab2:
        st.json(config)

# ==================== メイン ====================
def main():
    # ヘッダー
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("⚙️ 監視設定生成")
        st.caption("トポロジーからZabbix監視設定を自動生成")
    with col2:
        if st.button("🏠 ホームに戻る"):
            st.switch_page("Home.py")
    
    st.divider()
    
    # トポロジー読み込み
    topology = load_topology()
    full_topology = load_full_topology()
    
    if not topology:
        st.warning("⚠️ トポロジーデータがありません")
        st.info("👉 トポロジービルダーでトポロジーを作成してください")
        
        if st.button("🔧 トポロジービルダーを開く", type="primary"):
            st.switch_page("pages/1_topology_builder.py")
        return
    
    # トポロジー情報表示
    st.subheader("🗺️ 読み込み済みトポロジー")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("デバイス数", f"{len(topology)}台")
    with col2:
        layers = set(v.get("layer", 0) for v in topology.values())
        st.metric("レイヤー数", len(layers))
    with col3:
        if full_topology:
            rg_count = len(full_topology.get("redundancy_groups", {}))
            st.metric("冗長グループ", rg_count)
        else:
            st.metric("冗長グループ", "-")
    
    # レイヤー別デバイス一覧
    with st.expander("📋 デバイス一覧"):
        for layer in sorted(set(v.get("layer", 0) for v in topology.values())):
            layer_devices = [(k, v) for k, v in topology.items() if v.get("layer") == layer]
            st.markdown(f"**Layer {layer}** ({len(layer_devices)}台)")
            for dev_id, dev in layer_devices:
                vendor = dev.get("metadata", {}).get("vendor", "-")
                st.markdown(f"  └─ {dev_id} ({dev['type']}) - {vendor}")
    
    st.divider()
    
    # 設定生成
    st.subheader("🔧 監視設定生成")
    
    st.markdown("""
    <div class="hint-box">
        💡 <strong>生成される設定:</strong>
        <ul>
            <li>ホストグループ（レイヤー別、ベンダー別、ロケーション別、HA グループ別）</li>
            <li>ホスト設定（テンプレート、タグ、マクロ）</li>
            <li>トリガー（到達性、リソース使用率、HA フェイルオーバー）</li>
            <li>依存関係（トポロジーの親子関係に基づく）</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("🔧 監視設定を生成", type="primary", use_container_width=True):
        with st.spinner("設定を生成中..."):
            config = generate_zabbix_config(topology)
            st.session_state.generated_config = config
            
            # 保存
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, "zabbix_config.json"), "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
    
    # 生成結果表示
    if "generated_config" in st.session_state:
        config = st.session_state.generated_config
        summary = config.get("summary", {})
        
        st.success(
            f"✅ Zabbix設定を生成しました：・ホスト: {summary.get('host_count', 0)}台"
            f"・ホストグループ: {summary.get('group_count', 0)}個"
            f"・トリガー: {summary.get('trigger_count', 0)}個"
            f"・依存関係: {summary.get('dependency_count', 0)}件"
        )
        
        with st.expander("📋 生成された設定を表示", expanded=True):
            display_config_summary(config)
        
        # ダウンロード
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📥 設定JSONをダウンロード",
                json.dumps(config, ensure_ascii=False, indent=2),
                "zabbix_config.json",
                "application/json",
                use_container_width=True
            )
        with col2:
            if st.button("🎯 根本原因分析へ進む", use_container_width=True):
                st.switch_page("pages/3_rca_analyzer.py")
    
    # Zabbixへのインポート手順
    st.divider()
    with st.expander("📖 Zabbixへのインポート手順"):
        st.markdown("""
        ### 方法1: Zabbix API経由
        
        ```python
        import requests
        import json
        
        # Zabbix API設定
        ZABBIX_URL = "http://your-zabbix-server/api_jsonrpc.php"
        AUTH_TOKEN = "your-auth-token"
        
        # 設定ファイルを読み込み
        with open("zabbix_config.json") as f:
            config = json.load(f)
        
        # ホストグループ作成
        for group in config["host_groups"]:
            # API呼び出し...
        
        # ホスト作成
        for host in config["hosts"]:
            # API呼び出し...
        ```
        
        ### 方法2: Zabbix Web UI経由
        
        1. **Configuration** → **Host groups** でグループを作成
        2. **Configuration** → **Hosts** でホストを作成
        3. 各ホストにテンプレートを割り当て
        4. **Configuration** → **Actions** で依存関係を設定
        
        ### 方法3: zabbix_export形式への変換
        
        生成された設定をZabbixのエクスポート形式（XML/YAML）に変換し、
        Web UIからインポートすることも可能です。
        """)

if __name__ == "__main__":
    main()
