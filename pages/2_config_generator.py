"""
Zabbix RCA Tool - 監視設定生成 & API連携 (AI Assisted - Gemma 3)
トポロジーからZabbix設定を自動生成し、API経由で適用する
"""

import streamlit as st
import json
import os
import requests
import pandas as pd
import time
from typing import Dict, List, Any

# Google Generative AI ライブラリのインポート試行
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="監視設定生成 - Zabbix RCA Tool",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== データディレクトリ ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== デフォルト定義 ====================
DEFAULT_TRIGGER_RULES = [
    {
        "id": "ping_check",
        "name": "ICMP Ping Status",
        "severity": "High",
        "description": "死活監視 (0=Down, 1=Up)",
        "condition_type": "always",
        "threshold_macro": "{$ICMP_RESPONSE_TIME_WARN}",
        "default_value": "0",
        "unit": "status",
        "interval_macro": "{$ICMP_PING_INTERVAL}",
        "default_interval": "60"
    },
    {
        "id": "cpu_check",
        "name": "High CPU Utilization",
        "severity": "Warning",
        "description": "CPU使用率が高騰しています",
        "condition_type": "always",
        "threshold_macro": "{$CPU.UTIL.CRIT}",
        "default_value": "90",
        "unit": "%",
        "interval_macro": "{$CPU_CHECK_INTERVAL}",
        "default_interval": "300"
    },
    {
        "id": "psu_check",
        "name": "PSU Failure / Redundancy Lost",
        "severity": "Average",
        "description": "電源ユニットの障害または冗長性が失われています",
        "condition_type": "field_gt",
        "field": "hw.psu_count",
        "value": 1,
        "threshold_macro": "{$PSU.STATUS.CRIT}",
        "default_value": "1",
        "unit": "status",
        "interval_macro": "{$PSU_CHECK_INTERVAL}",
        "default_interval": "3600"
    },
    {
        "id": "lag_check",
        "name": "LAG Interface Degraded",
        "severity": "Average",
        "description": "LAGメンバーの一部がダウンしています",
        "condition_type": "tag_exists",
        "tag": "Configuration",
        "value": "LAG",
        "threshold_macro": None,
        "default_value": None,
        "unit": "",
        "interval_macro": "{$LAG_CHECK_INTERVAL}",
        "default_interval": "60"
    }
]

DEFAULT_TEMPLATE_MAPPING = {
    "mappings": [],
    "defaults": {
        "SWITCH": "Template Module Generic Switch SNMP",
        "ROUTER": "Template Module Generic Router SNMP",
        "FIREWALL": "Template Module Generic Firewall SNMP",
        "SERVER": "Template OS Linux by Zabbix agent",
        "default": "Template Module ICMP Ping"
    }
}

# ==================== データI/O関数 ====================
def load_full_topology_data():
    """トポロジーファイル全体を読み込む"""
    path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_json_config(filename, default_data):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2, ensure_ascii=False)
        return default_data
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_data

def save_json_config(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_trigger_rules(rules):
    save_json_config("trigger_rules.json", rules)

# ==================== AIエージェント ====================
class TemplateRecommenderAI:
    def __init__(self):
        self.api_key = st.secrets.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def sanitize_device_data(self, devices: List[Dict]) -> List[Dict]:
        sanitized_list = []
        for d in devices:
            clean_data = {
                "vendor": d.get("vendor", "Unknown"),
                "type": d.get("type", "Unknown"),
                "model": d.get("model", "")
            }
            if not clean_data["model"]:
                clean_data["model"] = "Unknown"
            sanitized_list.append(clean_data)
        return sanitized_list

    def recommend(self, raw_devices_summary: List[Dict]) -> List[Dict]:
        sanitized_devices = self.sanitize_device_data(raw_devices_summary)
        
        # 処理状況の表示（ウェイトなし）
        st.write(f"🔍 分析対象: {len(sanitized_devices)} デバイス")
        
        # Google Gemini API
        if self.api_key and HAS_GEMINI:
            try:
                st.write("🤖 AI (Gemma 3) に問い合わせ中...")
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel('gemma-3-12b-it')
                
                prompt = f"""
                You are a Zabbix configuration expert.
                Analyze the following list of network devices (JSON format) and identify the most appropriate standard SNMP template included in Zabbix 6.0/7.0 for each device.

                # Constraints
                - Output MUST be a valid JSON array only. Do not include markdown formatting.
                - Format each element as: {{"vendor": "...", "type": "...", "template": "..."}}
                - If no specific template is found, use "Template Module ICMP Ping".

                # Device List
                {json.dumps(sanitized_devices, ensure_ascii=False)}
                """
                
                response = model.generate_content(prompt)
                content = response.text
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[0]
                
                return json.loads(content.strip())

            except Exception as e:
                st.error(f"AI API Error: {e}")
                st.warning("AI通信に失敗しました。モックロジックを使用します。")
        
        # Mock Logic (Wait無し)
        st.write("🧠 知識ベースと照合中 (Mock)...")
        recommendations = []
        for dev in sanitized_devices:
            vendor = dev['vendor'].lower()
            dtype = dev['type'].upper()
            template = "Template Module ICMP Ping"
            if "cisco" in vendor and dtype == "SWITCH": template = "Template Net Cisco IOS SNMP"
            recommendations.append({"vendor": dev['vendor'], "type": dev['type'], "template": template})
        
        return recommendations

# ==================== Zabbix API Client ====================
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
            response = requests.post(self.url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            if 'error' in result: raise Exception(f"Zabbix API Error: {result['error']['data']}")
            return result.get('result')
        except Exception as e: raise Exception(f"Connection Failed: {str(e)}")

    def check_connection(self): return self.call("apiinfo.version")

class MockZabbixAPI:
    def __init__(self):
        self.url = "http://mock-zabbix/api"
        self.id_counter = 1
    def call(self, method: str, params: Any = None):
        if method == "apiinfo.version": return "6.4.0 (Mock)"
        elif method == "hostgroup.get": return []
        elif method == "hostgroup.create": return {"groupids": ["100"]}
        elif method == "template.get": return [{"templateid": "10001"}]
        elif method == "host.get": return []
        elif method == "host.create": return {"hostids": ["500"]}
        elif method == "host.update": return {"hostids": ["500"]}
        elif method == "action.create": return {"actionids": ["1"]}
        return {}
    def check_connection(self): return self.call("apiinfo.version")

# ==================== 設定生成ロジック ====================
def determine_template(vendor, device_type, mapping_data):
    for rule in mapping_data.get("mappings", []):
        if rule.get("vendor") == vendor and rule.get("type") == device_type:
            return rule["template"]
    defaults = mapping_data.get("defaults", {})
    return defaults.get(device_type, defaults.get("default", "Template Module ICMP Ping"))

def generate_zabbix_config(full_data: Dict, options: Dict, trigger_rules: List, template_mapping: Dict) -> Dict:
    site_name = full_data.get("site_name", "Unknown-Site")
    topology = full_data.get("topology", {})
    connections = full_data.get("connections", [])
    module_master = st.session_state.get("module_master_list", ["LineCard", "Supervisor", "SFP+"])

    config = {
        "host_groups": [], "hosts": [], "actions": [], "dependencies": [], "summary": {}
    }
    
    if not topology: return config

    # 1. Host Groups
    groups = set()
    groups.add(site_name)
    for d in topology.values():
        dev_type = d.get("type", "Other")
        groups.add(f"{site_name}/{dev_type}")
    config["host_groups"] = [{"name": g} for g in sorted(groups)]

    # 2. Hosts
    for dev_id, dev_data in topology.items():
        meta = dev_data.get("metadata", {})
        hw = meta.get("hw_inventory", {})
        vendor = meta.get("vendor", "default")
        dev_type = dev_data.get("type", "Other")
        rack_info = meta.get("rack_info") or meta.get("location") or "Unspecified"
        
        host_groups = [{"name": site_name}, {"name": f"{site_name}/{dev_type}"}]
        template_name = determine_template(vendor, dev_type, template_mapping)
        
        interfaces = [{
            "type": 2, "main": 1, "useip": 1, "ip": "192.168.1.1", "dns": "", "port": "161",
            "details": {"version": 2, "community": "public"}
        }]

        macros = []
        if hw.get("psu_count"): macros.append({"macro": "{$EXPECTED_PSU_COUNT}", "value": str(hw["psu_count"])})
        if hw.get("fan_count"): macros.append({"macro": "{$EXPECTED_FAN_COUNT}", "value": str(hw["fan_count"])})
        for mod_name in module_master:
            count = hw.get("custom_modules", {}).get(mod_name, 0)
            safe_name = mod_name.upper().replace("-", "_").replace(" ", "_").replace("+", "PLUS")
            macros.append({"macro": f"{{$EXPECTED_{safe_name}_COUNT}}", "value": str(count)})

        for rule in trigger_rules:
            if rule.get("threshold_macro") and rule.get("default_value") is not None:
                macros.append({"macro": rule["threshold_macro"], "value": str(rule["default_value"])})
            if rule.get("interval_macro") and rule.get("default_interval") is not None:
                macros.append({"macro": rule["interval_macro"], "value": f"{rule['default_interval']}s"})

        tags = [
            {"tag": "Layer", "value": str(dev_data.get("layer", 0))},
            {"tag": "Vendor", "value": vendor},
            {"tag": "Model", "value": meta.get("model", "Unknown")},
            {"tag": "Location", "value": rack_info}
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

        host_obj = {
            "host": dev_id, "name": dev_id, "groups": host_groups,
            "interfaces": interfaces, "templates": [{"name": template_name}],
            "macros": macros, "tags": tags, "inventory_mode": 1,
            "description": f"Generated by RCA Tool.\nSite: {site_name}\nRack: {rack_info}\nVendor: {vendor}"
        }
        config["hosts"].append(host_obj)

    # 3. Dependencies
    for c in connections:
        if c["type"] == "uplink":
            child = c["from"]
            parent = c["to"]
            config["dependencies"].append({
                "host": child, "depends_on_host": parent,
                "description": f"Uplink: {child} -> {parent}"
            })

    # 4. Actions
    if options["create_action"]:
        config["actions"].append({
            "name": "Report problems to Admin",
            "eventsource": 0, "status": 0, "esc_period": "10m",
            "operations": [{"operationtype": 0, "opmessage_grp": [{"usrgrpid": "7"}], "opmessage": {"default_msg": 1, "mediatypeid": "1"}}]
        })

    config["summary"] = {
        "hosts": len(config["hosts"]),
        "groups": len(config["host_groups"]),
        "dependencies": len(config["dependencies"]),
        "actions": len(config["actions"])
    }
    return config

# ==================== API投入ロジック ====================
def push_config_to_zabbix(api: Any, config: Dict):
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
            else: logs.append(f"⚠️ テンプレート未定義: {t['name']} (スキップ)")

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

    if config.get("actions"):
        st.write("🔔 通知アクションを設定中...")
        for action in config["actions"]:
            exists = api.call("action.get", {"filter": {"name": action["name"]}})
            if not exists:
                api.call("action.create", action)
                logs.append(f"✅ アクション作成: {action['name']}")

    st.write("🔗 依存関係を設定中...")
    if config["dependencies"]:
        logs.append(f"ℹ️ 依存関係設定: {len(config['dependencies'])} 件")

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

        zabbix_url = st.text_input("URL", "[http://192.168.1.100/zabbix](http://192.168.1.100/zabbix)", disabled=use_mock)
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
        st.title("⚙️ 監視設定生成 (AI Assisted)")
    with col2:
        if st.button("🏠 ホーム", use_container_width=True):
            st.switch_page("Home.py")
    
    st.divider()

    # データロード
    full_data = None
    if uploaded_file:
        full_data = json.load(uploaded_file)
        st.info(f"📂 ファイル読み込み: {uploaded_file.name}")
    else:
        full_data = load_full_topology_data()
        if full_data and full_data.get("topology"):
            st.info("📂 サーバー上のデータを使用")
    
    # データの存在チェック
    if not full_data or not full_data.get("topology"):
        st.warning("⚠️ トポロジーデータが見つからないか、デバイスが登録されていません。トポロジービルダーでデバイスを追加してください。")
        return

    trigger_rules = load_json_config("trigger_rules.json", DEFAULT_TRIGGER_RULES)
    template_mapping = load_json_config("template_mapping.json", DEFAULT_TEMPLATE_MAPPING)

    # --- 1. テンプレート割り当てルール (AI) ---
    with st.expander("1. テンプレート割り当てルール (Vendor/Type定義)", expanded=True):
        st.write("トポロジー内のデバイス情報（ベンダー、モデル）を分析し、最適なZabbixテンプレートを自動割り当てします。")
        
        if st.button("✨ AIで推奨テンプレートを生成・適用", type="primary"):
            devices_summary = []
            seen = set()
            for d in full_data.get("topology", {}).values():
                meta = d.get("metadata", {})
                key = (meta.get("vendor"), d.get("type"), meta.get("model"))
                if key not in seen and key[0]:
                    seen.add(key)
                    devices_summary.append({"vendor": key[0], "type": key[1], "model": key[2]})
            
            if not devices_summary:
                st.warning("有効なベンダー情報を持つデバイスが見つかりませんでした。")
            else:
                with st.status("🤖 AIエージェントが分析中...", expanded=True) as status:
                    ai = TemplateRecommenderAI()
                    recommendations = ai.recommend(devices_summary)
                    
                    st.write("マッピングルールを更新中...")
                    current_mappings = template_mapping.get("mappings", [])
                    added_count = 0
                    for rec in recommendations:
                        exists = any(
                            m["vendor"] == rec["vendor"] and m["type"] == rec["type"] 
                            for m in current_mappings
                        )
                        if not exists:
                            current_mappings.append(rec)
                            added_count += 1
                    
                    template_mapping["mappings"] = current_mappings
                    save_json_config("template_mapping.json", template_mapping)
                    status.update(label="✅ 完了", state="complete", expanded=False)
                
                st.success(f"✅ {added_count} 件の新しいマッピングルールを追加しました！")
                st.rerun()

        if template_mapping.get("mappings"):
            st.caption("現在の適用ルール:")
            st.dataframe(pd.DataFrame(template_mapping["mappings"]), use_container_width=True)

    # --- 2. 共通監視ポリシー (閾値・間隔設定) ---
    st.subheader("2. 共通監視ポリシー (閾値・間隔設定)")
    
    with st.container(border=True):
        create_action = st.toggle("標準通知設定を作成", value=True)
        st.divider()
        st.markdown("##### ⚡ トリガー設定 (閾値 / 監視間隔)")
        st.caption("各監視項目の閾値および監視間隔を編集できます。設定内容は「保存」後に「Zabbix設定ファイル」に反映されます。")

        rows = []
        for r in trigger_rules:
            if r.get("threshold_macro") or r.get("interval_macro"):
                rows.append({
                    "Trigger Name": r["name"],
                    "Macro (Threshold)": r.get("threshold_macro", "-"),
                    "Threshold Value": r.get("default_value", "-"),
                    "Unit": r.get("unit", ""),
                    "Macro (Interval)": r.get("interval_macro", "-"),
                    "Interval (sec)": r.get("default_interval", "-"),
                    "_id": r["id"]
                })
        
        df_triggers = pd.DataFrame(rows)

        if not df_triggers.empty:
            edited_df = st.data_editor(
                df_triggers,
                column_config={
                    "Trigger Name": st.column_config.TextColumn("監視項目名", disabled=True, width="medium"),
                    "Macro (Threshold)": st.column_config.TextColumn("閾値マクロ", disabled=True, width="small"),
                    "Threshold Value": st.column_config.TextColumn("閾値", required=True),
                    "Unit": st.column_config.TextColumn("単位", disabled=True, width="small"),
                    "Macro (Interval)": st.column_config.TextColumn("間隔マクロ", disabled=True, width="small"),
                    "Interval (sec)": st.column_config.TextColumn("監視間隔(秒)", required=True),
                    "_id": None 
                },
                hide_index=True,
                use_container_width=True,
                num_rows="fixed"
            )

            if st.button("💾 設定を保存して反映", type="primary"):
                is_changed = False
                for index, row in edited_df.iterrows():
                    rule_id = row["_id"]
                    new_thresh = row["Threshold Value"]
                    new_int = row["Interval (sec)"]
                    
                    for rule in trigger_rules:
                        if rule["id"] == rule_id:
                            if rule.get("default_value") != new_thresh:
                                rule["default_value"] = new_thresh
                                is_changed = True
                            if rule.get("default_interval") != new_int:
                                rule["default_interval"] = new_int
                                is_changed = True
                
                if is_changed:
                    save_trigger_rules(trigger_rules)
                    st.success("設定を更新しました！")
                    st.rerun()
                else:
                    st.info("変更はありませんでした。")
        else:
            st.info("設定可能なルールがありません。")

    # 設定生成
    options = {"create_action": create_action, "interval": 60}
    config = generate_zabbix_config(full_data, options, trigger_rules, template_mapping)
    
    st.subheader("1. 設定内容の確認")
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("ホスト数", len(config["hosts"]))
    k2.metric("グループ数", len(config["host_groups"]))
    k3.metric("アクション", len(config["actions"]))
    k4.metric("依存関係", len(config["dependencies"]))

    tab_host, tab_group, tab_dep, tab_json = st.tabs([
        "🖥️ ホスト詳細", "📂 グループ構成", "🔗 依存関係", "🔍 JSON"
    ])

    with tab_host:
        df_hosts = []
        for h in config["hosts"]:
            macros_display = []
            for m in h["macros"]:
                val = m['value']
                macros_display.append(f"{m['macro']}={val}")
            
            df_hosts.append({
                "ホスト名": h["host"],
                "テンプレート": h["templates"][0]["name"],
                "グループ": ", ".join([g["name"] for g in h["groups"]]),
                "適用マクロ": ", ".join(macros_display)
            })
        st.dataframe(pd.DataFrame(df_hosts), use_container_width=True)

    with tab_group:
        st.caption(f"※ 拠点名({full_data.get('site_name','Unknown')})/機器タイプ の階層構造")
        st.dataframe(pd.DataFrame(config["host_groups"]), use_container_width=True)

    with tab_dep:
        st.dataframe(pd.DataFrame(config["dependencies"]), use_container_width=True)

    with tab_json:
        st.json(config)

    st.divider()
    
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
