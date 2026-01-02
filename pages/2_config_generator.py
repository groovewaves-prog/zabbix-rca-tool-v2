"""
Zabbix RCA Tool - 監視設定生成 & API連携
トポロジーからZabbix設定を自動生成し、API経由で適用する
"""

import streamlit as st
import json
import os
import requests
import pandas as pd
import time
from typing import Dict, List, Any

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="監視設定生成 - Zabbix RCA Tool",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== データディレクトリ ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== トリガールール（閾値定義付き） ====================
# threshold_macro: Zabbix側で制御に使うマクロ名
# default_value: デフォルトの閾値
DEFAULT_TRIGGER_RULES = [
    {
        "id": "ping_check",
        "name": "ICMP Ping Check",
        "severity": "High",
        "description": "死活監視",
        "condition_type": "always",
        "threshold_macro": "{$ICMP_LOSS_LIMIT}",
        "default_value": "20",
        "unit": "%"
    },
    {
        "id": "cpu_check",
        "name": "CPU Utilization",
        "severity": "Warning",
        "description": "リソース監視",
        "condition_type": "always",
        "threshold_macro": "{$CPU_UTIL_LIMIT}",
        "default_value": "80",
        "unit": "%"
    },
    {
        "id": "mem_check",
        "name": "Memory Utilization",
        "severity": "Warning",
        "description": "リソース監視",
        "condition_type": "always",
        "threshold_macro": "{$MEM_UTIL_LIMIT}",
        "default_value": "90",
        "unit": "%"
    },
    {
        "id": "psu_redundancy",
        "name": "PSU Status Check",
        "severity": "Average",
        "description": "PSU冗長性喪失",
        "condition_type": "field_gt",
        "field": "hw.psu_count",
        "value": 1,
        "threshold_macro": None,
        "default_value": None,
        "unit": ""
    },
    {
        "id": "lag_down",
        "name": "LAG Link Down",
        "severity": "Average",
        "description": "LAGメンバーダウン",
        "condition_type": "tag_exists",
        "tag": "Configuration",
        "value": "LAG",
        "threshold_macro": None,
        "default_value": None,
        "unit": ""
    },
    {
        "id": "module_missing",
        "name": "{mod_name} Module Missing",
        "severity": "Average",
        "description": "モジュール数不一致",
        "condition_type": "module_iterator",
        "threshold_macro": None,
        "default_value": None,
        "unit": ""
    }
]

def load_trigger_rules():
    """トリガー定義ルールを読み込む（なければデフォルト作成）"""
    rule_path = os.path.join(DATA_DIR, "trigger_rules.json")
    if not os.path.exists(rule_path):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(rule_path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_TRIGGER_RULES, f, indent=2, ensure_ascii=False)
        return DEFAULT_TRIGGER_RULES
    
    try:
        with open(rule_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_TRIGGER_RULES

def save_trigger_rules(rules):
    """トリガールール（閾値変更後）を保存"""
    rule_path = os.path.join(DATA_DIR, "trigger_rules.json")
    with open(rule_path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)

def load_local_topology():
    """サーバーローカルのトポロジーデータを読み込む"""
    topology_path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(topology_path):
        with open(topology_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# ==================== Zabbix API クライアント ====================
class ZabbixAPI:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip('/') + '/api_jsonrpc.php'
        self.headers = {'Content-Type': 'application/json'}
        self.auth = token
        self.id_counter = 1

    def call(self, method: str, params: Any = None):
        """汎用API呼び出し"""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "auth": self.auth,
            "id": self.id_counter
        }
        self.id_counter += 1
        
        try:
            response = requests.post(self.url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            if 'error' in result:
                raise Exception(f"Zabbix API Error: {result['error']['data']}")
            return result.get('result')
        except Exception as e:
            raise Exception(f"Connection Failed: {str(e)}")

    def check_connection(self):
        return self.call("apiinfo.version")

class MockZabbixAPI:
    """Mock API Client"""
    def __init__(self):
        self.url = "http://mock-zabbix/api"
        self.group_counter = 10
        self.host_counter = 100
        self.template_counter = 500

    def call(self, method: str, params: Any = None):
        time.sleep(0.1) 
        if method == "apiinfo.version": return "6.4.0 (Mock Mode)"
        elif method == "hostgroup.get": return []
        elif method == "hostgroup.create":
            self.group_counter += 1
            return {"groupids": [str(self.group_counter)]}
        elif method == "template.get":
            self.template_counter += 1
            return [{"templateid": str(self.template_counter)}]
        elif method == "host.get":
            host_name = params.get('filter', {}).get('host', '')
            if hash(host_name) % 2 == 0:
                return [{"hostid": str(self.host_counter + hash(host_name) % 100)}]
            return []
        elif method == "host.create": return {"hostids": [str(self.host_counter + 1)]}
        elif method == "host.update": return {"hostids": [str(self.host_counter)]}
        return {}

    def check_connection(self):
        return self.call("apiinfo.version")

# ==================== 設定生成ロジック ====================
def generate_zabbix_config(data: Dict, trigger_rules: List[Dict]) -> Dict:
    """トポロジーデータとトリガールール(閾値含む)からZabbix設定を生成"""
    topology = data.get("topology", {})
    connections = data.get("connections", [])
    module_master = data.get("module_master_list", [])
    
    config = {
        "host_groups": [],
        "hosts": [],
        "templates": [],
        "dependencies": [], 
        "triggers_preview": [],
        "summary": {}
    }
    
    if not topology: return config

    # 1. ホストグループ
    groups = set(["Network/Generated"])
    for d in topology.values():
        meta = d.get("metadata", {})
        if meta.get("vendor"): groups.add(f"Vendor/{meta['vendor']}")
        if meta.get("location"): groups.add(f"Location/{meta['location']}")
        groups.add(f"Network/Layer{d.get('layer', 0)}")

    config["host_groups"] = [{"name": g} for g in sorted(groups)]

    # 2. テンプレートマッピング
    template_map = {
        "Cisco": "Template Net Cisco IOS SNMP",
        "Juniper": "Template Net Juniper SNMP",
        "Linux": "Template OS Linux by Zabbix agent",
        "Windows": "Template OS Windows by Zabbix agent",
        "default": "Template Module ICMP Ping"
    }

    # 3. ホスト設定 & トリガープレビュー
    for dev_id, dev_data in topology.items():
        meta = dev_data.get("metadata", {})
        hw = meta.get("hw_inventory", {})
        
        # グループ
        host_groups = [{"name": "Network/Generated"}, {"name": f"Network/Layer{dev_data.get('layer',0)}"}]
        if meta.get("vendor"): host_groups.append({"name": f"Vendor/{meta['vendor']}"})
        
        # テンプレート
        vendor = meta.get("vendor", "default")
        template_name = template_map.get(vendor, template_map["default"])
        
        # インターフェース
        interfaces = [{
            "type": 2, "main": 1, "useip": 1, "ip": "192.168.1.1", "dns": "", "port": "161",
            "details": {"version": 2, "community": "public"}
        }]

        # --- マクロ生成 (モジュール数 + 閾値) ---
        macros = []
        
        # A. モジュール期待値マクロ
        if hw.get("psu_count"): 
            macros.append({"macro": "{$EXPECTED_PSU_COUNT}", "value": str(hw["psu_count"])})
        if hw.get("fan_count"): 
            macros.append({"macro": "{$EXPECTED_FAN_COUNT}", "value": str(hw["fan_count"])})
        
        custom_mods = hw.get("custom_modules", {})
        for mod_name in module_master:
            count = custom_mods.get(mod_name, 0)
            safe_name = mod_name.upper().replace("-", "_").replace(" ", "_").replace("+", "PLUS")
            macros.append({"macro": f"{{$EXPECTED_{safe_name}_COUNT}}", "value": str(count)})

        # B. 閾値マクロ (トリガールールから)
        for rule in trigger_rules:
            if rule.get("threshold_macro") and rule.get("default_value") is not None:
                macros.append({
                    "macro": rule["threshold_macro"],
                    "value": str(rule["default_value"])
                })

        # タグ設定
        tags = [
            {"tag": "Layer", "value": str(dev_data.get("layer", 0))},
            {"tag": "Type", "value": dev_data.get("type", "Unknown")}
        ]
        
        has_lag = False
        vlan_ids = set()
        for c in connections:
            if c["from"] == dev_id or c["to"] == dev_id:
                c_meta = c.get("metadata", {})
                if c_meta.get("lag_enabled"): has_lag = True
                if c_meta.get("vlans"):
                    for v in c_meta["vlans"].replace(" ", "").split(","):
                        if v: vlan_ids.add(v)
        
        if has_lag: tags.append({"tag": "Configuration", "value": "LAG"})
        if vlan_ids: tags.append({"tag": "VLANs", "value": ",".join(sorted(vlan_ids))})

        # --- トリガープレビュー ---
        host_triggers = []
        for rule in trigger_rules:
            should_apply = False
            
            if rule["condition_type"] == "always":
                should_apply = True
            elif rule["condition_type"] == "field_gt":
                field_path = rule.get("field", "").split(".")
                val = hw
                if field_path[0] == "hw": val = hw.get(field_path[1], 0)
                if isinstance(val, int) and val > rule.get("value", 0): should_apply = True
            elif rule["condition_type"] == "tag_exists":
                if any(t["tag"] == rule.get("tag") and t["value"] == rule.get("value") for t in tags):
                    should_apply = True
            
            # 閾値表示用の文字列作成
            threshold_str = ""
            if rule.get("default_value") is not None:
                threshold_str = f" (> {rule['default_value']}{rule.get('unit','')})"

            if should_apply:
                host_triggers.append({
                    "host": dev_id, 
                    "name": rule["name"] + threshold_str, 
                    "severity": rule["severity"], 
                    "desc": rule["description"]
                })
            elif rule["condition_type"] == "module_iterator":
                for mod_name in module_master:
                    count = custom_mods.get(mod_name, 0)
                    if count > 0:
                        host_triggers.append({
                            "host": dev_id, 
                            "name": rule["name"].format(mod_name=mod_name), 
                            "severity": rule["severity"], 
                            "desc": rule["description"]
                        })

        host_obj = {
            "host": dev_id, "name": dev_id, "groups": host_groups,
            "interfaces": interfaces, "templates": [{"name": template_name}],
            "macros": macros, "tags": tags, "inventory_mode": 1,
            "description": f"Generated by RCA Tool.\nLocation: {meta.get('location', 'N/A')}"
        }
        config["hosts"].append(host_obj)
        config["triggers_preview"].extend(host_triggers)

    # 4. 依存関係
    for c in connections:
        if c["type"] == "uplink":
            child = c["from"]
            parent = c["to"]
            config["dependencies"].append({
                "host": child,
                "depends_on_host": parent,
                "description": f"{child} は {parent} に依存"
            })

    config["summary"] = {
        "hosts": len(config["hosts"]),
        "groups": len(config["host_groups"]),
        "dependencies": len(config["dependencies"])
    }
    return config

# ==================== API投入ロジック ====================
def push_config_to_zabbix(api: Any, config: Dict):
    """API経由でZabbixに反映"""
    logs = []
    
    st.write("📂 ホストグループを確認中...")
    existing_groups = {g['name']: g['groupid'] for g in api.call("hostgroup.get", {"output": ["groupid", "name"]})}
    
    for group in config["host_groups"]:
        g_name = group["name"]
        if g_name not in existing_groups:
            res = api.call("hostgroup.create", {"name": g_name})
            existing_groups[g_name] = res['groupids'][0]
            logs.append(f"✅ グループ作成: {g_name}")
    
    st.write("📄 テンプレート情報を取得中...")
    template_cache = {}
    def get_template_id(name):
        if name in template_cache: return template_cache[name]
        res = api.call("template.get", {"filter": {"host": name}, "output": ["templateid"]})
        if res:
            tid = res[0]['templateid']
            template_cache[name] = tid
            return tid
        return None

    st.write("🖥️ ホスト設定を反映中...")
    for host_conf in config["hosts"]:
        hostname = host_conf["host"]
        group_ids = [{"groupid": existing_groups[g["name"]]} for g in host_conf["groups"] if g["name"] in existing_groups]
        template_ids = []
        for t in host_conf["templates"]:
            tid = get_template_id(t["name"])
            if tid: template_ids.append({"templateid": tid})

        host_payload = {
            "host": hostname, "name": host_conf["name"], "groups": group_ids,
            "interfaces": host_conf["interfaces"], "templates": template_ids,
            "macros": host_conf["macros"], "tags": host_conf["tags"], "inventory_mode": 1
        }

        existing = api.call("host.get", {"filter": {"host": hostname}, "output": ["hostid"]})
        if existing:
            host_payload["hostid"] = existing[0]['hostid']
            del host_payload["interfaces"] 
            api.call("host.update", host_payload)
            logs.append(f"🔄 ホスト更新: {hostname}")
        else:
            api.call("host.create", host_payload)
            logs.append(f"✨ ホスト作成: {hostname}")

    st.write("🔗 依存関係を設定中...")
    if config["dependencies"]:
        logs.append(f"ℹ️ 依存関係設定: {len(config['dependencies'])} 件を処理")

    return logs

# ==================== UIメイン処理 ====================
def main():
    with st.sidebar:
        st.header("📂 データソース")
        uploaded_file = st.file_uploader("設定ファイル (JSON)", type=["json"])
        
        st.divider()
        st.header("🔗 Zabbix接続")
        use_mock = st.checkbox("🧪 モックモード", value=False)
        
        if "zabbix_connected" not in st.session_state:
            st.session_state.zabbix_connected = False
            st.session_state.is_mock = False

        zabbix_url = st.text_input("URL", "http://192.168.1.100/zabbix", disabled=use_mock)
        zabbix_token = st.text_input("Token", type="password", disabled=use_mock)
        
        if st.button("接続テスト", use_container_width=True):
            try:
                if use_mock:
                    api = MockZabbixAPI()
                    st.session_state.is_mock = True
                else:
                    if not zabbix_url: raise Exception("URLを入力してください")
                    api = ZabbixAPI(zabbix_url, zabbix_token)
                    st.session_state.is_mock = False
                
                ver = api.check_connection()
                st.session_state.zabbix_connected = True
                st.success(f"接続OK: {ver}")
            except Exception as e:
                st.session_state.zabbix_connected = False
                st.error(f"エラー: {e}")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("⚙️ 監視設定生成")
    with col2:
        if st.button("🏠 ホーム", use_container_width=True):
            st.switch_page("Home.py")
    
    st.divider()

    # データロード
    data = None
    if uploaded_file:
        data = json.load(uploaded_file)
        st.info(f"📂 ファイル読み込み: {uploaded_file.name}")
    else:
        data = load_local_topology()
        if data and data.get("topology"):
            st.info("📂 サーバー上のデータを使用")
    
    if not data:
        st.warning("⚠️ データがありません。ファイルをアップロードするかトポロジービルダーを実行してください。")
        return

    # ルールロード & 編集機能
    trigger_rules = load_trigger_rules()
    
    # 閾値編集エリア
    with st.expander("🛠️ 監視閾値の設定", expanded=False):
        st.caption("ここで設定した値はZabbixのマクロとして各ホストに適用され、テンプレートのデフォルト値を上書きします。")
        threshold_rules = [r for r in trigger_rules if r.get("threshold_macro")]
        
        cols = st.columns(3)
        updated_rules = trigger_rules.copy()
        is_changed = False
        
        for i, rule in enumerate(threshold_rules):
            col = cols[i % 3]
            current_val = rule.get("default_value")
            unit = rule.get("unit", "")
            
            new_val = col.text_input(
                f"{rule['name']} ({unit})",
                value=current_val,
                key=f"thresh_{rule['id']}"
            )
            
            if new_val != current_val:
                for r in updated_rules:
                    if r["id"] == rule["id"]:
                        r["default_value"] = new_val
                        is_changed = True
        
        if is_changed:
            if st.button("閾値を保存して再計算", type="primary"):
                save_trigger_rules(updated_rules)
                st.rerun()

    # 設定生成
    config = generate_zabbix_config(data, trigger_rules)
    
    # === 設定内容の可視化エリア ===
    st.subheader("1. 設定内容の確認")
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("ホスト数", len(config["hosts"]))
    k2.metric("グループ数", len(config["host_groups"]))
    k3.metric("トリガー(予定)", len(config["triggers_preview"]))
    k4.metric("依存関係", len(config["dependencies"]))

    tab_host, tab_group, tab_trig, tab_dep, tab_json = st.tabs([
        "🖥️ ホスト", "📂 グループ", "⚡ トリガー", "🔗 依存関係", "🔍 JSON"
    ])

    with tab_host:
        df_hosts = []
        for h in config["hosts"]:
            macros_display = []
            for m in h["macros"]:
                # 閾値マクロなどは強調せず通常テキストで表示
                val = m['value']
                macros_display.append(f"{m['macro']}={val}")
                
            df_hosts.append({
                "ホスト名": h["host"],
                "テンプレート": h["templates"][0]["name"],
                "適用マクロ (閾値など)": ", ".join(macros_display)
            })
        st.dataframe(pd.DataFrame(df_hosts), use_container_width=True)

    with tab_group:
        st.dataframe(pd.DataFrame(config["host_groups"]), use_container_width=True)

    with tab_trig:
        st.caption("※ 現在の閾値設定に基づいて適用されるトリガーです")
        st.dataframe(pd.DataFrame(config["triggers_preview"]), use_container_width=True)

    with tab_dep:
        st.dataframe(pd.DataFrame(config["dependencies"]), use_container_width=True)

    with tab_json:
        st.json(config)

    st.divider()
    
    # === アクションエリア ===
    st.subheader("2. 実行")
    c_dl, c_push = st.columns(2)
    
    with c_dl:
        st.download_button(
            "📥 設定ファイルを保存",
            data=json.dumps(config, indent=2, ensure_ascii=False),
            file_name="zabbix_config.json",
            mime="application/json",
            use_container_width=True
        )
        
    with c_push:
        if not st.session_state.zabbix_connected:
            st.button("Zabbixへ投入 (未接続)", disabled=True, use_container_width=True)
        elif len(config["hosts"]) == 0:
            st.button("データなし", disabled=True, use_container_width=True)
        else:
            if st.button("🚀 Zabbixへ投入開始", type="primary", use_container_width=True):
                if st.session_state.is_mock:
                    api = MockZabbixAPI()
                else:
                    api = ZabbixAPI(zabbix_url, zabbix_token)
                
                with st.status("処理を実行中...", expanded=True) as status:
                    try:
                        logs = push_config_to_zabbix(api, config)
                        status.update(label="完了しました", state="complete", expanded=False)
                        st.success(f"成功: {len(config['hosts'])} 台の処理が完了")
                        with st.expander("詳細ログ"):
                            for l in logs: st.write(l)
                    except Exception as e:
                        status.update(label="エラー", state="error")
                        st.error(f"詳細: {e}")

if __name__ == "__main__":
    main()
