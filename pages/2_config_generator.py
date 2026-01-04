"""
Zabbix RCA Tool - 監視設定生成 & API連携 (Zabbix Native UI)
トポロジーからZabbix設定を自動生成し、API経由で適用する
"""

import streamlit as st
import json
import os
import requests
import pandas as pd
from typing import Dict, List, Any

# Google Generative AI
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

# ==================== ディレクトリ ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== デフォルト設定 ====================
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

DEFAULT_MACROS = [
    {"macro": "{$ICMP_RESPONSE_TIME_WARN}", "value": "0.15", "desc": "Ping応答時間警告(秒)"},
    {"macro": "{$ICMP_PING_INTERVAL}", "value": "60", "desc": "Ping監視間隔(秒)"},
    {"macro": "{$CPU.UTIL.CRIT}", "value": "90", "desc": "CPU使用率 重度(%)"},
    {"macro": "{$CPU_CHECK_INTERVAL}", "value": "300", "desc": "CPU監視間隔(秒)"},
    {"macro": "{$MEM.UTIL.MAX}", "value": "90", "desc": "メモリ使用率 重度(%)"},
    {"macro": "{$PSU.STATUS.CRIT}", "value": "1", "desc": "PSU障害ステータス値"},
    {"macro": "{$FAN.STATUS.CRIT}", "value": "1", "desc": "FAN障害ステータス値"},
    {"macro": "{$SNMP.TIMEOUT}", "value": "5m", "desc": "SNMPタイムアウト"}
]

DEFAULT_MEDIA_CONFIG = {
    "smtp_server": "mail.example.com",
    "smtp_helo": "zabbix.example.com",
    "smtp_email": "zabbix@example.com",
    "alert_severity": "Average"
}

# ==================== データI/O関数 ====================
def load_full_topology_data():
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

# ==================== ユーティリティ関数 ====================
def filter_mappings_by_topology(mappings: List[Dict], topology: Dict) -> List[Dict]:
    valid_pairs = set()
    for dev in topology.values():
        meta = dev.get("metadata", {})
        vendor = meta.get("vendor")
        dev_type = dev.get("type")
        if vendor and dev_type:
            valid_pairs.add((vendor, dev_type))
    
    cleaned_mappings = []
    for m in mappings:
        if (m.get("vendor"), m.get("type")) in valid_pairs:
            cleaned_mappings.append(m)
    return cleaned_mappings

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
            if not clean_data["model"]: clean_data["model"] = "Unknown"
            sanitized_list.append(clean_data)
        return sanitized_list

    def recommend(self, raw_devices_summary: List[Dict]) -> List[Dict]:
        sanitized_devices = self.sanitize_device_data(raw_devices_summary)
        st.write(f"🔍 分析対象: {len(sanitized_devices)} ユニークモデル")
        
        if self.api_key and HAS_GEMINI:
            try:
                st.write("🤖 AI (Gemma 3) に問い合わせ中...")
                genai.configure(api_key=self.api_key)
                model = genai.GenerativeModel('gemma-3-12b-it')
                
                prompt = f"""
                Act as a Zabbix configuration expert.
                For each network device, determine:
                1. The most appropriate standard Zabbix 6.0/7.0 SNMP template.
                2. Any recommended macro overrides (thresholds).

                # Output Format
                JSON Array ONLY.
                [
                  {{
                    "vendor": "Cisco",
                    "type": "SWITCH",
                    "template": "Template Net Cisco IOS SNMP",
                    "macros": [{{"macro": "{{$CPU.UTIL.CRIT}}", "value": "95"}}]
                  }}
                ]
                If unknown, use "Template Module ICMP Ping".

                # Devices
                {json.dumps(sanitized_devices, ensure_ascii=False)}
                """
                
                response = model.generate_content(prompt)
                content = response.text.replace("```json", "").replace("```", "").strip()
                return json.loads(content)
            except Exception as e:
                st.error(f"AI Error: {e}")
        
        st.write("🧠 知識ベースと照合中 (Mock)...")
        recs = []
        for dev in sanitized_devices:
            tpl = "Template Module ICMP Ping"
            macros = []
            v = dev['vendor'].lower()
            t = dev['type'].upper()
            if "cisco" in v and t == "SWITCH":
                tpl = "Template Net Cisco IOS SNMP"
                macros = [{"macro": "{$CPU.UTIL.CRIT}", "value": "95"}]
            recs.append({"vendor": dev['vendor'], "type": dev['type'], "template": tpl, "macros": macros})
        return recs

# ==================== Zabbix API ====================
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
            res = requests.post(self.url, headers=self.headers, json=payload, timeout=10)
            res.raise_for_status()
            result = res.json()
            if 'error' in result: raise Exception(result['error']['data'])
            return result.get('result')
        except Exception as e: raise Exception(f"Connection Failed: {str(e)}")

    def check_connection(self): return self.call("apiinfo.version")

class MockZabbixAPI:
    def __init__(self):
        self._host_trigger_map = {
            "Router01": [{"triggerid": "20001", "description": "Router01 is unavailable"}],
            "Switch01": [{"triggerid": "20002", "description": "Switch01 is unavailable"}],
            "Switch02": [{"triggerid": "20003", "description": "Switch02 is unavailable"}],
        }

    def call(self, method: str, params: Any = None):
        if method == "apiinfo.version": return "6.4.0 (Mock)"
        if method == "hostgroup.get": return [{"groupid": "101", "name": "Tokyo-HQ"}, {"groupid": "102", "name": "Tokyo-HQ/SWITCH"}]
        if method == "hostgroup.create": return {"groupids": ["103"]}
        if method == "template.get": return [{"templateid": "1001", "name": "Template Module ICMP Ping"}, {"templateid": "1002", "name": "Template Net Cisco IOS SNMP"}]
        if method == "host.get": return []
        if method == "host.create": return {"hostids": ["5001"]}
        if method == "host.update": return {"hostids": ["5001"]}
        if method == "action.create": return {"actionids": ["9001"]}
        # 【追加】メディアタイプ関連
        if method == "mediatype.get": return []
        if method == "mediatype.create": return {"mediatypeids": ["3001"]}
        # 【追加】ユーザーグループ関連
        if method == "usergroup.get": return []
        if method == "usergroup.create": return {"usrgrpids": ["7001"]}
        # 【追加】ユーザー関連
        if method == "user.get": return []
        if method == "user.create": return {"userids": ["1001"]}
        # 【追加】トリガー依存関係
        if method == "trigger.get":
            host_filter = params.get("host") if params else None
            if host_filter and host_filter in self._host_trigger_map:
                return self._host_trigger_map[host_filter]
            return [{"triggerid": "29999", "description": "Generic trigger"}]
        if method == "trigger.adddependencies": return {"triggerids": [params.get("triggerid", "99999")]}
        return []

    def check_connection(self): return "6.4.0 (Mock)"

# ==================== 設定生成ロジック ====================
def generate_zabbix_config(full_data: Dict, macro_config: List[Dict], template_mapping: Dict, media_config: Dict) -> Dict:
    site_name = full_data.get("site_name", "Unknown-Site")
    topology = full_data.get("topology", {})
    connections = full_data.get("connections", [])
    
    config = {
        "host_groups": [], "hosts": [], "users": [], "user_groups": [], 
        "media_types": [], "actions": [], "dependencies": []
    }
    
    if not topology: return config

    # 1. Host Groups
    groups = set([site_name])
    for d in topology.values(): groups.add(f"{site_name}/{d.get('type', 'Other')}")
    config["host_groups"] = [{"name": g} for g in sorted(groups)]

    # 2. Hosts
    # 【修正】defaults を取得しておく
    defaults = template_mapping.get("defaults", DEFAULT_TEMPLATE_MAPPING["defaults"])

    for dev_id, dev_data in topology.items():
        meta = dev_data.get("metadata", {})
        hw = meta.get("hw_inventory", {})
        
        tpl_name = None
        ai_macros = []
        
        # まずAIマッピングを検索
        for rule in template_mapping.get("mappings", []):
            if rule.get("vendor") == meta.get("vendor") and rule.get("type") == dev_data.get("type"):
                tpl_name = rule["template"]
                ai_macros = rule.get("macros", [])
                break
        
        # 【修正】マッチしなかった場合は defaults から取得
        if not tpl_name:
            dev_type = dev_data.get("type", "").upper()
            tpl_name = defaults.get(dev_type, defaults.get("default", "Template Module ICMP Ping"))
        
        final_macros_dict = {m["macro"]: m["value"] for m in macro_config}
        for m in ai_macros:
            final_macros_dict[m["macro"]] = m["value"]
        if hw.get("psu_count"): final_macros_dict["{$EXPECTED_PSU_COUNT}"] = str(hw["psu_count"])
        if hw.get("fan_count"): final_macros_dict["{$EXPECTED_FAN_COUNT}"] = str(hw["fan_count"])

        host_obj = {
            "host": dev_id, "name": dev_id,
            "groups": [{"name": site_name}, {"name": f"{site_name}/{dev_data.get('type')}"}],
            "interfaces": [{"type": 2, "main": 1, "useip": 1, "ip": "192.168.1.1", "dns": "", "port": "161", "details": {"version": 2, "community": "public"}}],
            "templates": [{"name": tpl_name}],
            "macros": [{"macro": k, "value": v} for k, v in final_macros_dict.items()],
            "tags": [{"tag": "Site", "value": site_name}, {"tag": "Vendor", "value": meta.get("vendor", "")}, {"tag": "Rack", "value": meta.get("rack_info") or meta.get("location") or ""}],
            "inventory_mode": 1
        }
        config["hosts"].append(host_obj)

    # 3. Media/Users/Actions/Dependencies
    config["media_types"].append({
        "name": "Email (HTML)", "type": 0, "content_type": 1,
        "smtp_server": media_config.get("smtp_server"), "smtp_helo": media_config.get("smtp_helo"), "smtp_email": media_config.get("smtp_email")
    })
    config["user_groups"].append({"name": "Zabbix Administrators", "users_status": 0})
    config["users"].append({
        "alias": "Admin", "name": "Zabbix", "surname": "Administrator",
        "usrgrps": [{"name": "Zabbix Administrators"}],
        "medias": [{"mediatype": {"name": "Email (HTML)"}, "sendto": ["admin@example.com"]}]
    })
    severity_map = {"Information": 1, "Warning": 2, "Average": 3, "High": 4, "Disaster": 5}
    sev_val = severity_map.get(media_config.get("alert_severity"), 3)
    config["actions"].append({
        "name": "Report problems to Admins", "eventsource": 0, "status": 0, 
        "filter": {"evaltype": 0, "conditions": [{"conditiontype": 4, "operator": 5, "value": str(sev_val)}]},
        "operations": [{"operationtype": 0, "opmessage_grp": [{"name": "Zabbix Administrators"}], "opmessage": {"mediatype": {"name": "Email (HTML)"}}}]
    })
    for c in connections:
        if c["type"] == "uplink": config["dependencies"].append({"host": c["from"], "depends_on": c["to"], "desc": "Uplink Dependency"})

    return config

# ==================== API投入ロジック ====================
def push_config_to_zabbix(api: Any, config: Dict):
    logs = []
    
    # 1. Groups
    group_map = {}
    try:
        existing = api.call("hostgroup.get", {"output": ["groupid", "name"]})
        group_map = {g['name']: g['groupid'] for g in existing}
    except Exception as e: logs.append(f"ℹ️ Pre-fetch groups failed: {e}")

    for g in config["host_groups"]:
        g_name = g["name"]
        if g_name in group_map: logs.append(f"ℹ️ Group exists: {g_name}")
        else:
            try:
                res = api.call("hostgroup.create", {"name": g_name})
                new_id = res['groupids'][0]
                group_map[g_name] = new_id
                logs.append(f"✅ Group Created: {g_name}")
            except Exception as e: logs.append(f"⚠️ Group Create Failed {g_name}: {e}")

    # 2. Templates
    template_map = {}
    try:
        t_list = api.call("template.get", {"output": ["templateid", "name"]})
        template_map = {t['name']: t['templateid'] for t in t_list}
    except Exception as e:
        logs.append(f"ℹ️ Pre-fetch templates failed: {e}")

    # 【追加】3. Media Types
    mediatype_map = {}
    try:
        existing_mt = api.call("mediatype.get", {"output": ["mediatypeid", "name"]})
        mediatype_map = {m['name']: m['mediatypeid'] for m in existing_mt}
    except Exception as e:
        logs.append(f"ℹ️ Pre-fetch media types failed: {e}")

    for mt in config.get("media_types", []):
        mt_name = mt["name"]
        if mt_name in mediatype_map:
            logs.append(f"ℹ️ MediaType exists: {mt_name}")
        else:
            try:
                res = api.call("mediatype.create", {
                    "name": mt_name,
                    "type": mt.get("type", 0),
                    "content_type": mt.get("content_type", 1),
                    "smtp_server": mt.get("smtp_server", ""),
                    "smtp_helo": mt.get("smtp_helo", ""),
                    "smtp_email": mt.get("smtp_email", "")
                })
                new_id = res['mediatypeids'][0]
                mediatype_map[mt_name] = new_id
                logs.append(f"✅ MediaType Created: {mt_name}")
            except Exception as e:
                logs.append(f"⚠️ MediaType Create Failed {mt_name}: {e}")

    # 【追加】4. User Groups
    usergroup_map = {}
    try:
        existing_ug = api.call("usergroup.get", {"output": ["usrgrpid", "name"]})
        usergroup_map = {ug['name']: ug['usrgrpid'] for ug in existing_ug}
    except Exception as e:
        logs.append(f"ℹ️ Pre-fetch user groups failed: {e}")

    for ug in config.get("user_groups", []):
        ug_name = ug["name"]
        if ug_name in usergroup_map:
            logs.append(f"ℹ️ UserGroup exists: {ug_name}")
        else:
            try:
                res = api.call("usergroup.create", {
                    "name": ug_name,
                    "users_status": ug.get("users_status", 0)
                })
                new_id = res['usrgrpids'][0]
                usergroup_map[ug_name] = new_id
                logs.append(f"✅ UserGroup Created: {ug_name}")
            except Exception as e:
                logs.append(f"⚠️ UserGroup Create Failed {ug_name}: {e}")

    # 【追加】5. Users
    for user in config.get("users", []):
        user_alias = user.get("alias", "Unknown")
        try:
            existing_user = api.call("user.get", {"filter": {"alias": user_alias}})
            if existing_user:
                logs.append(f"ℹ️ User exists: {user_alias}")
            else:
                user_grp_ids = []
                for ug in user.get("usrgrps", []):
                    if ug["name"] in usergroup_map:
                        user_grp_ids.append({"usrgrpid": usergroup_map[ug["name"]]})
                
                medias = []
                for m in user.get("medias", []):
                    mt_name = m.get("mediatype", {}).get("name")
                    if mt_name and mt_name in mediatype_map:
                        medias.append({
                            "mediatypeid": mediatype_map[mt_name],
                            "sendto": m.get("sendto", [])
                        })
                
                api.call("user.create", {
                    "alias": user_alias,
                    "name": user.get("name", ""),
                    "surname": user.get("surname", ""),
                    "usrgrps": user_grp_ids,
                    "medias": medias
                })
                logs.append(f"✅ User Created: {user_alias}")
        except Exception as e:
            logs.append(f"⚠️ User Create Failed {user_alias}: {e}")

    # 6. Hosts
    host_map = {}  # ホスト名 -> hostid のマッピング（依存関係設定用）
    for h in config["hosts"]:
        h_group_ids = []
        for grp in h["groups"]:
            if grp["name"] in group_map: h_group_ids.append({"groupid": group_map[grp["name"]]})
        
        h_template_ids = []
        for tpl in h["templates"]:
            if tpl["name"] in template_map: h_template_ids.append({"templateid": template_map[tpl["name"]]})
            else: logs.append(f"⚠️ Template not found: {tpl['name']} (Skip)")

        host_payload = {
            "host": h["host"], "name": h["name"], "groups": h_group_ids, "templates": h_template_ids,
            "interfaces": h["interfaces"], "macros": h["macros"], "tags": h["tags"], "inventory_mode": h["inventory_mode"]
        }

        if not h_group_ids:
            logs.append(f"❌ Skip Host {h['host']}: No valid groups")
            continue

        try:
            existing = api.call("host.get", {"filter": {"host": h["host"]}})
            if existing:
                host_id = existing[0]['hostid']
                host_payload["hostid"] = host_id
                del host_payload["interfaces"]
                api.call("host.update", host_payload)
                logs.append(f"🔄 Host Updated: {h['host']}")
                host_map[h["host"]] = host_id
            else:
                res = api.call("host.create", host_payload)
                host_id = res['hostids'][0]
                logs.append(f"✨ Host Created: {h['host']}")
                host_map[h["host"]] = host_id
        except Exception as e: logs.append(f"❌ Host Error {h['host']}: {e}")

    # 7. Actions
    for a in config["actions"]:
        try:
            api.call("action.create", {"name": a["name"], "eventsource": 0, "status": 0, "filter": a["filter"], "operations": a["operations"]})
            logs.append(f"🔔 Action Configured: {a['name']}")
        except Exception as e:
            logs.append(f"⚠️ Action Create Failed {a['name']}: {e}")

    # 【追加】8. Trigger Dependencies
    for dep in config.get("dependencies", []):
        child_host = dep["host"]
        parent_host = dep["depends_on"]
        
        try:
            # 子ホストのトリガーを取得
            child_triggers = api.call("trigger.get", {
                "host": child_host,
                "output": ["triggerid", "description"]
            })
            # 親ホストのトリガーを取得
            parent_triggers = api.call("trigger.get", {
                "host": parent_host,
                "output": ["triggerid", "description"]
            })
            
            if not child_triggers or not parent_triggers:
                logs.append(f"ℹ️ Dependency Skip: No triggers for {child_host} -> {parent_host}")
                continue
            
            # 可用性トリガー（"unavailable"を含む）を優先して依存関係を設定
            child_trigger = None
            parent_trigger = None
            
            for t in child_triggers:
                if "unavailable" in t.get("description", "").lower():
                    child_trigger = t
                    break
            if not child_trigger and child_triggers:
                child_trigger = child_triggers[0]
            
            for t in parent_triggers:
                if "unavailable" in t.get("description", "").lower():
                    parent_trigger = t
                    break
            if not parent_trigger and parent_triggers:
                parent_trigger = parent_triggers[0]
            
            if child_trigger and parent_trigger:
                api.call("trigger.adddependencies", {
                    "triggerid": child_trigger["triggerid"],
                    "dependsOnTriggerid": parent_trigger["triggerid"]
                })
                logs.append(f"🔗 Dependency Set: {child_host} -> {parent_host}")
        except Exception as e:
            logs.append(f"⚠️ Dependency Failed {child_host} -> {parent_host}: {e}")

    return logs

# ==================== UIメイン処理 ====================
def main():
    if "zabbix_connected" not in st.session_state: st.session_state.zabbix_connected = False
    if "zabbix_version" not in st.session_state: st.session_state.zabbix_version = ""
    if "is_mock" not in st.session_state: st.session_state.is_mock = False
    if "rules_generated" not in st.session_state: st.session_state.rules_generated = False

    with st.sidebar:
        st.header("📂 データソース")
        uploaded_file = st.file_uploader("設定ファイル (JSON)", type=["json"])
        st.divider()
        st.header("🔗 Zabbix API接続")
        use_mock = st.checkbox("🧪 モックモード", value=False)
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
                st.session_state.zabbix_version = ver
            except Exception as e:
                st.session_state.zabbix_connected = False
                st.error(f"エラー: {e}")

        if st.session_state.zabbix_connected:
            st.success(f"接続OK: {st.session_state.zabbix_version}", icon="✅")

    col1, col2 = st.columns([3, 1])
    with col1: st.title("⚙️ 監視設定生成")
    with col2:
        if st.button("🏠 ホーム", use_container_width=True): st.switch_page("Home.py")
    
    st.divider()

    full_data = None
    if uploaded_file: full_data = json.load(uploaded_file)
    else: full_data = load_full_topology_data()
    
    if not full_data or not full_data.get("topology"):
        st.warning("⚠️ デバイスデータがありません。")
        return

    macro_config = load_json_config("zabbix_macros.json", DEFAULT_MACROS)
    template_mapping = load_json_config("template_mapping.json", DEFAULT_TEMPLATE_MAPPING)
    media_config = load_json_config("zabbix_media.json", DEFAULT_MEDIA_CONFIG)

    tab1, tab2, tab3 = st.tabs(["1. ホスト & テンプレート", "2. マクロ & 閾値", "3. 通知 & アクション"])

    # --- Tab 1 ---
    with tab1:
        st.markdown("#### 📦 テンプレート割り当て")
        
        if template_mapping.get("mappings"):
            cleaned = filter_mappings_by_topology(template_mapping["mappings"], full_data.get("topology", {}))
            if len(cleaned) != len(template_mapping["mappings"]):
                template_mapping["mappings"] = cleaned
                save_json_config("template_mapping.json", template_mapping)

        if st.button("✨ AIで推奨テンプレートを生成・適用", type="primary"):
            devices_summary = []
            seen = set()
            for d in full_data.get("topology", {}).values():
                meta = d.get("metadata", {})
                key = (meta.get("vendor"), d.get("type"), meta.get("model"))
                if key not in seen and key[0]:
                    seen.add(key)
                    devices_summary.append({"vendor": key[0], "type": key[1], "model": key[2]})
            
            with st.status("🤖 AIエージェントが分析中...", expanded=True) as status:
                ai = TemplateRecommenderAI()
                recs = ai.recommend(devices_summary)
                template_mapping["mappings"] = recs
                save_json_config("template_mapping.json", template_mapping)
                st.session_state.rules_generated = True
                status.update(label="✅ 完了", state="complete")
            st.rerun()

        if st.session_state.rules_generated and template_mapping.get("mappings"):
            st.caption("定義されたマッピングルール:")
            df_display = pd.DataFrame(template_mapping["mappings"])
            if "macros" in df_display.columns:
                df_display["macros"] = df_display["macros"].apply(lambda x: json.dumps(x, ensure_ascii=False) if x else "")
            st.dataframe(df_display, use_container_width=True)
            
            st.divider()
            st.markdown("##### 📋 生成されるホスト一覧")
            
            # 【修正】defaults を参照するように変更
            defaults = template_mapping.get("defaults", DEFAULT_TEMPLATE_MAPPING["defaults"])
            site_name = full_data.get("site_name", "Unknown-Site")
            host_preview_list = []
            for dev_id, dev_data in full_data.get("topology", {}).items():
                meta = dev_data.get("metadata", {})
                assigned_tpl = None
                
                # まずAIマッピングを検索
                for rule in template_mapping.get("mappings", []):
                    if rule.get("vendor") == meta.get("vendor") and rule.get("type") == dev_data.get("type"):
                        assigned_tpl = rule["template"]
                        break
                
                # マッチしなければdefaultsを使用
                if not assigned_tpl:
                    dev_type = dev_data.get("type", "").upper()
                    assigned_tpl = defaults.get(dev_type, defaults.get("default", "Template Module ICMP Ping"))
                
                host_preview_list.append({
                    "Site Name": site_name,
                    "Host Name": dev_id,
                    "Vendor": meta.get("vendor"),
                    "Type": dev_data.get("type"),
                    "Model": meta.get("model"),
                    "Assigned Template": assigned_tpl
                })
            
            st.dataframe(pd.DataFrame(host_preview_list), use_container_width=True)
            
        elif not st.session_state.rules_generated:
            st.info("上のボタンを押して生成を開始してください。")

    # --- Tab 2 ---
    with tab2:
        st.markdown("#### ⚡ グローバルマクロ設定")
        if st.session_state.rules_generated:
            df_macros = pd.DataFrame(macro_config)
            if "selected" not in df_macros.columns: df_macros.insert(0, "selected", False)
            edited_macros = st.data_editor(df_macros, column_config={"selected": st.column_config.CheckboxColumn("選択", width="small"), "macro": st.column_config.TextColumn("マクロ名", required=True), "value": st.column_config.TextColumn("設定値", required=True)}, hide_index=True, use_container_width=True, num_rows="dynamic")
            
            c_dup, c_del, c_save = st.columns([1, 1, 2])
            with c_dup:
                if st.button("📋 選択した行を複製", use_container_width=True):
                    sel = edited_macros[edited_macros["selected"]]
                    if not sel.empty:
                        new_data = edited_macros.drop(columns=["selected"]).to_dict(orient="records") + sel.drop(columns=["selected"]).to_dict(orient="records")
                        save_json_config("zabbix_macros.json", new_data)
                        st.rerun()
            with c_del:
                if st.button("🗑️ 選択した行を削除", use_container_width=True):
                    remain = edited_macros[edited_macros["selected"] == False]
                    new_data = remain.drop(columns=["selected"]).to_dict(orient="records")
                    save_json_config("zabbix_macros.json", new_data)
                    st.success("削除しました")
                    st.rerun()

            with c_save:
                if st.button("💾 設定を保存", type="primary", use_container_width=True):
                    save_json_config("zabbix_macros.json", edited_macros.drop(columns=["selected"]).to_dict(orient="records"))
                    st.success("保存しました")
        else:
            st.info("テンプレートの割り当て（Tab 1）完了後に設定可能になります。")

    # --- Tab 3 ---
    with tab3:
        st.markdown("#### 📢 通知設定")
        c_m, c_a = st.columns(2)
        with c_m:
            st.subheader("✉️ SMTP")
            ns = st.text_input("Server", media_config.get("smtp_server"))
            # 【修正】smtp_helo の編集フィールドを追加
            nh = st.text_input("HELO", media_config.get("smtp_helo"), help="SMTP HELO/EHLO で使用するドメイン名")
            ne = st.text_input("Email", media_config.get("smtp_email"))
        with c_a:
            st.subheader("🔔 条件")
            severity_options = ["Information", "Warning", "Average", "High", "Disaster"]
            current_sev = media_config.get("alert_severity", "Average")
            sev_index = severity_options.index(current_sev) if current_sev in severity_options else 2
            sev = st.selectbox("深刻度", severity_options, index=sev_index)
        if st.button("💾 保存"):
            # 【修正】smtp_helo も保存対象に追加
            media_config.update({"smtp_server": ns, "smtp_helo": nh, "smtp_email": ne, "alert_severity": sev})
            save_json_config("zabbix_media.json", media_config)
            st.success("保存しました")

    st.divider()
    config = generate_zabbix_config(full_data, macro_config, template_mapping, media_config)
    
    st.subheader("🚀 Zabbixへの反映")
    c_dl, c_push = st.columns(2)
    with c_dl:
        st.download_button("📥 JSONダウンロード", json.dumps(config, indent=2, ensure_ascii=False), "zabbix_config.json", "application/json", use_container_width=True)
    with c_push:
        can_push = st.session_state.zabbix_connected and len(config["hosts"]) > 0
        if st.button("🚀 Zabbix APIへ投入", disabled=not can_push, use_container_width=True):
            api = MockZabbixAPI() if st.session_state.is_mock else ZabbixAPI(zabbix_url, zabbix_token)
            with st.status("投入中...", expanded=True) as status:
                try:
                    logs = push_config_to_zabbix(api, config)
                    for l in logs: st.write(l)
                    status.update(label="完了", state="complete")
                    st.success(f"成功: {len(config['hosts'])} 台")
                except Exception as e:
                    st.error(f"エラー: {e}")

if __name__ == "__main__":
    main()
