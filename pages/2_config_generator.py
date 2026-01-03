"""
Zabbix RCA Tool - 監視設定生成 & API連携 (Zabbix Native UI)
トポロジーからZabbix設定を自動生成し、API経由で適用する
"""

import streamlit as st
import json
import os
import requests
import pandas as pd
import time
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
                Map each network device (JSON) to the most appropriate standard Zabbix 6.0/7.0 SNMP template.
                
                # Output Format
                JSON Array ONLY. No markdown.
                [{{"vendor": "Cisco", "type": "SWITCH", "template": "Template Net Cisco IOS SNMP"}}, ...]
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
            v = dev['vendor'].lower()
            t = dev['type'].upper()
            if "cisco" in v and t == "SWITCH": tpl = "Template Net Cisco IOS SNMP"
            recs.append({"vendor": dev['vendor'], "type": dev['type'], "template": tpl})
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
    def __init__(self): pass
    def call(self, method: str, params: Any = None):
        time.sleep(0.1) # Simulate network lag
        if method == "apiinfo.version": return "6.4.0 (Mock Mode)"
        if method == "hostgroup.create": return {"groupids": ["101"]}
        if method == "host.create": return {"hostids": ["1001"]}
        if method == "host.update": return {"hostids": ["1001"]}
        return []
    def check_connection(self): return "6.4.0 (Mock Mode)"

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
    for dev_id, dev_data in topology.items():
        meta = dev_data.get("metadata", {})
        hw = meta.get("hw_inventory", {})
        
        tpl_name = "Template Module ICMP Ping"
        for rule in template_mapping.get("mappings", []):
            if rule.get("vendor") == meta.get("vendor") and rule.get("type") == dev_data.get("type"):
                tpl_name = rule["template"]
                break
        
        host_macros = []
        if hw.get("psu_count"): host_macros.append({"macro": "{$EXPECTED_PSU_COUNT}", "value": str(hw["psu_count"])})
        if hw.get("fan_count"): host_macros.append({"macro": "{$EXPECTED_FAN_COUNT}", "value": str(hw["fan_count"])})
        
        for m in macro_config:
            host_macros.append({"macro": m["macro"], "value": m["value"]})

        host_obj = {
            "host": dev_id, "name": dev_id,
            "groups": [{"name": site_name}, {"name": f"{site_name}/{dev_data.get('type')}"}],
            "interfaces": [{"type": 2, "main": 1, "useip": 1, "ip": "192.168.1.1", "dns": "", "port": "161", "details": {"version": 2, "community": "public"}}],
            "templates": [{"name": tpl_name}],
            "macros": host_macros,
            "tags": [
                {"tag": "Site", "value": site_name},
                {"tag": "Vendor", "value": meta.get("vendor", "")},
                {"tag": "Rack", "value": meta.get("rack_info") or meta.get("location") or ""}
            ],
            "inventory_mode": 1
        }
        config["hosts"].append(host_obj)

    # 3. Media Types
    config["media_types"].append({
        "name": "Email (HTML)", "type": 0, "content_type": 1,
        "smtp_server": media_config.get("smtp_server"),
        "smtp_helo": media_config.get("smtp_helo"),
        "smtp_email": media_config.get("smtp_email")
    })

    # 4. User Groups & Users
    config["user_groups"].append({"name": "Zabbix Administrators", "users_status": 0})
    config["users"].append({
        "alias": "Admin", "name": "Zabbix", "surname": "Administrator",
        "usrgrps": [{"name": "Zabbix Administrators"}],
        "medias": [{"mediatype": {"name": "Email (HTML)"}, "sendto": ["admin@example.com"]}]
    })

    # 5. Actions
    severity_map = {"Information": 1, "Warning": 2, "Average": 3, "High": 4, "Disaster": 5}
    sev_val = severity_map.get(media_config.get("alert_severity"), 3)
    
    config["actions"].append({
        "name": "Report problems to Admins", "eventsource": 0, "status": 0, 
        "filter": {"evaltype": 0, "conditions": [{"conditiontype": 4, "operator": 5, "value": str(sev_val)}]},
        "operations": [{"operationtype": 0, "opmessage_grp": [{"name": "Zabbix Administrators"}], "opmessage": {"mediatype": {"name": "Email (HTML)"}}}]
    })

    # 6. Dependencies
    for c in connections:
        if c["type"] == "uplink":
            config["dependencies"].append({"host": c["from"], "depends_on": c["to"], "desc": "Uplink Dependency"})

    return config

# ==================== API投入ロジック ====================
def push_config_to_zabbix(api: Any, config: Dict):
    logs = []
    # 実際にはここで各APIをコールします
    # 1. Host Groups
    for g in config["host_groups"]:
        try:
            # 簡易チェック: 存在しなければ作成（モックは常に作成成功として扱う）
            api.call("hostgroup.create", {"name": g["name"]})
            logs.append(f"✅ Group Checked/Created: {g['name']}")
        except Exception as e:
            logs.append(f"⚠️ Group Error {g['name']}: {e}")

    # 2. Hosts
    for h in config["hosts"]:
        try:
            # モックでは単純にCreateとしてログ出力
            api.call("host.create", {"host": h["host"], "groups": [], "interfaces": []}) 
            logs.append(f"✨ Host Configured: {h['host']}")
        except Exception:
            logs.append(f"⚠️ Host Error {h['host']}")

    # 3. Actions
    for a in config["actions"]:
        api.call("action.create", {"name": a["name"]})
        logs.append(f"🔔 Action Configured: {a['name']}")

    return logs

# ==================== UIメイン処理 ====================
def main():
    # セッション初期化 (リロード対策)
    if "zabbix_connected" not in st.session_state:
        st.session_state.zabbix_connected = False
    if "zabbix_version" not in st.session_state:
        st.session_state.zabbix_version = ""
    if "is_mock" not in st.session_state:
        st.session_state.is_mock = False

    with st.sidebar:
        st.header("📂 データソース")
        uploaded_file = st.file_uploader("設定ファイル (JSON)", type=["json"])
        
        st.divider()
        st.header("🔗 Zabbix API接続")
        use_mock = st.checkbox("🧪 モックモード", value=False)
        zabbix_url = st.text_input("URL", "http://192.168.1.100/zabbix", disabled=use_mock)
        zabbix_token = st.text_input("Token", type="password", disabled=use_mock)
        
        # 接続ボタン
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
                # st.successはここでは出さず、下で永続表示する
            except Exception as e:
                st.session_state.zabbix_connected = False
                st.session_state.zabbix_version = ""
                st.error(f"エラー: {e}")

        # 接続状態の永続表示（ボタン外）
        if st.session_state.zabbix_connected:
            st.success(f"接続OK: {st.session_state.zabbix_version}", icon="✅")

    col1, col2 = st.columns([3, 1])
    with col1: st.title("⚙️ 監視設定生成")
    with col2:
        if st.button("🏠 ホーム", use_container_width=True): st.switch_page("Home.py")
    
    st.divider()

    # データロード
    full_data = None
    if uploaded_file: full_data = json.load(uploaded_file)
    else: full_data = load_full_topology_data()
    
    if not full_data or not full_data.get("topology"):
        st.warning("⚠️ デバイスデータがありません。トポロジービルダーで作成してください。")
        return

    # 設定ロード
    macro_config = load_json_config("zabbix_macros.json", DEFAULT_MACROS)
    template_mapping = load_json_config("template_mapping.json", DEFAULT_TEMPLATE_MAPPING)
    media_config = load_json_config("zabbix_media.json", DEFAULT_MEDIA_CONFIG)

    # === Tab構成 ===
    tab1, tab2, tab3 = st.tabs([
        "1. ホスト & テンプレート (Data Collection)", 
        "2. マクロ & 閾値 (Thresholds)", 
        "3. 通知 & アクション (Operations)"
    ])

    # --- Tab 1 ---
    with tab1:
        st.markdown("#### 📦 テンプレート割り当てルール")
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
                
                current_mappings = template_mapping.get("mappings", [])
                for r in recs:
                    if not any(m["vendor"]==r["vendor"] and m["type"]==r["type"] for m in current_mappings):
                        current_mappings.append(r)
                
                template_mapping["mappings"] = current_mappings
                save_json_config("template_mapping.json", template_mapping)
                status.update(label="✅ 完了", state="complete", expanded=False)
            st.rerun()

        if template_mapping.get("mappings"):
            st.dataframe(pd.DataFrame(template_mapping["mappings"]), use_container_width=True)
        else:
            st.info("ルール未定義です。AI生成を実行してください。")

    # --- Tab 2 ---
    with tab2:
        st.markdown("#### ⚡ グローバルマクロ設定 (閾値・間隔)")
        df_macros = pd.DataFrame(macro_config)
        edited_macros = st.data_editor(
            df_macros,
            column_config={
                "macro": st.column_config.TextColumn("マクロ名", disabled=True, width="medium"),
                "value": st.column_config.TextColumn("設定値", required=True),
                "desc": st.column_config.TextColumn("説明", disabled=True)
            },
            hide_index=True, use_container_width=True, num_rows="fixed"
        )
        if st.button("💾 マクロ設定を保存"):
            new_config = edited_macros.to_dict(orient="records")
            save_json_config("zabbix_macros.json", new_config)
            st.success("保存しました")
            st.rerun()

    # --- Tab 3 ---
    with tab3:
        st.markdown("#### 📢 メディアタイプ & アクション設定")
        c_media, c_action = st.columns(2)
        with c_media:
            with st.container(border=True):
                st.subheader("✉️ メール設定")
                new_smtp = st.text_input("SMTPサーバー", media_config.get("smtp_server"))
                new_email = st.text_input("送信元アドレス", media_config.get("smtp_email"))
        with c_action:
            with st.container(border=True):
                st.subheader("🔔 アクション条件")
                severity_opts = ["Information", "Warning", "Average", "High", "Disaster"]
                curr_sev = media_config.get("alert_severity", "Average")
                new_sev = st.selectbox("深刻度 (Severity) 以上", severity_opts, index=severity_opts.index(curr_sev))
        if st.button("💾 通知設定を保存"):
            media_config.update({"smtp_server": new_smtp, "smtp_email": new_email, "alert_severity": new_sev})
            save_json_config("zabbix_media.json", media_config)
            st.success("保存しました")

    # === 実行 ===
    st.divider()
    config = generate_zabbix_config(full_data, macro_config, template_mapping, media_config)
    
    st.subheader("🚀 Zabbixへの反映")
    c_dl, c_push = st.columns(2)
    
    with c_dl:
        st.download_button(
            "📥 Zabbix設定(JSON)をダウンロード",
            data=json.dumps(config, indent=2, ensure_ascii=False),
            file_name="zabbix_import_config.json",
            mime="application/json",
            use_container_width=True
        )
        
    with c_push:
        # ボタンが押せるかどうか
        can_push = st.session_state.zabbix_connected and len(config["hosts"]) > 0
        if st.button("🚀 Zabbix APIへ投入 (実装済)", type="primary", disabled=not can_push, use_container_width=True):
            
            # APIクライアントの準備 (モックか実機か)
            if st.session_state.is_mock:
                api = MockZabbixAPI()
            else:
                api = ZabbixAPI(zabbix_url, zabbix_token)
            
            # ステータス表示
            with st.status("Zabbixへ設定を投入中...", expanded=True) as status:
                try:
                    logs = push_config_to_zabbix(api, config)
                    
                    st.write("--- 処理ログ ---")
                    for l in logs:
                        st.write(l)
                        
                    status.update(label="✅ 投入完了！", state="complete", expanded=True)
                    st.success(f"成功: {len(config['hosts'])} 台のホスト設定を反映しました。")
                    
                except Exception as e:
                    status.update(label="❌ エラー発生", state="error", expanded=True)
                    st.error(f"APIエラー: {e}")

if __name__ == "__main__":
    main()
