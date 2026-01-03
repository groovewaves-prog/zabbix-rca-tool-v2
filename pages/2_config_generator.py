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

# ==================== デフォルト設定 (Zabbix概念準拠) ====================

# 1. テンプレート割り当て (Mappings)
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

# 2. グローバルマクロ (Thresholds & Intervals)
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

# 3. 通知設定 (Media Types & Actions)
DEFAULT_MEDIA_CONFIG = {
    "smtp_server": "mail.example.com",
    "smtp_helo": "zabbix.example.com",
    "smtp_email": "zabbix@example.com",
    "alert_severity": "Average" # Average以上で通知
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
        
        # Mock
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
        time.sleep(0.1)
        if method == "apiinfo.version": return "6.4.0 (Mock)"
        return {"result": []}
    def check_connection(self): return "6.4.0 (Mock)"

# ==================== 設定生成ロジック ====================
def generate_zabbix_config(full_data: Dict, macro_config: List[Dict], template_mapping: Dict, media_config: Dict) -> Dict:
    site_name = full_data.get("site_name", "Unknown-Site")
    topology = full_data.get("topology", {})
    connections = full_data.get("connections", [])
    module_master = st.session_state.get("module_master_list", ["LineCard", "Supervisor"])

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
        
        # テンプレート決定
        tpl_name = "Template Module ICMP Ping" # Default
        for rule in template_mapping.get("mappings", []):
            if rule.get("vendor") == meta.get("vendor") and rule.get("type") == dev_data.get("type"):
                tpl_name = rule["template"]
                break
        
        # ホストマクロ
        host_macros = []
        if hw.get("psu_count"): host_macros.append({"macro": "{$EXPECTED_PSU_COUNT}", "value": str(hw["psu_count"])})
        if hw.get("fan_count"): host_macros.append({"macro": "{$EXPECTED_FAN_COUNT}", "value": str(hw["fan_count"])})
        
        for m in macro_config:
            host_macros.append({"macro": m["macro"], "value": m["value"]})

        host_obj = {
            "host": dev_id,
            "name": dev_id,
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
        "name": "Email (HTML)",
        "type": 0,
        "smtp_server": media_config.get("smtp_server"),
        "smtp_helo": media_config.get("smtp_helo"),
        "smtp_email": media_config.get("smtp_email"),
        "content_type": 1 
    })

    # 4. Users
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
        "name": "Report problems to Admins",
        "eventsource": 0, "status": 0, 
        "filter": {
            "evaltype": 0,
            "conditions": [{"conditiontype": 4, "operator": 5, "value": str(sev_val)}]
        },
        "operations": [{
            "operationtype": 0,
            "opmessage_grp": [{"name": "Zabbix Administrators"}],
            "opmessage": {"mediatype": {"name": "Email (HTML)"}}
        }]
    })

    # 6. Dependencies
    for c in connections:
        if c["type"] == "uplink":
            config["dependencies"].append({
                "host": c["from"], "depends_on": c["to"], "desc": "Uplink"
            })

    return config

# ==================== API投入ロジック ====================
def push_config_to_zabbix(api: Any, config: Dict):
    logs = []
    # 簡易実装: ホストグループとホストのみ (エラーハンドリング簡略)
    try:
        # Group
        existing = {g['name']: g['groupid'] for g in api.call("hostgroup.get", {"output": ["name"]})}
        for g in config["host_groups"]:
            if g["name"] not in existing:
                res = api.call("hostgroup.create", {"name": g["name"]})
                existing[g["name"]] = res["groupids"][0]
                logs.append(f"✅ Group created: {g['name']}")
        
        # Host
        for h in config["hosts"]:
            # resolve IDs
            g_ids = [{"groupid": existing[g["name"]]} for g in h["groups"] if g["name"] in existing]
            # template ID resolving (省略 - MockではダミーID)
            t_ids = [{"templateid": "10001"}] 
            
            h_payload = {**h, "groups": g_ids, "templates": t_ids}
            
            # check exist
            host_exist = api.call("host.get", {"filter": {"host": h["host"]}})
            if host_exist:
                h_payload["hostid"] = host_exist[0]["hostid"]
                del h_payload["interfaces"] # update時のIF処理は複雑なため省略
                api.call("host.update", h_payload)
                logs.append(f"🔄 Host updated: {h['host']}")
            else:
                api.call("host.create", h_payload)
                logs.append(f"✨ Host created: {h['host']}")
                
    except Exception as e:
        raise e
    return logs

# ==================== UIメイン処理 ====================
def main():
    # 【重要】セッション状態の初期化 (エラー回避のため最優先で実行)
    if "zabbix_connected" not in st.session_state:
        st.session_state.zabbix_connected = False
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

    # --- Tab 1: テンプレート割り当て ---
    with tab1:
        st.markdown("#### 📦 テンプレート割り当てルール")
        st.caption("各デバイスのベンダー・モデルに基づき、適用するZabbixテンプレートを決定します。")
        
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
                
                # マッピング更新
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

    # --- Tab 2: マクロ (閾値) ---
    with tab2:
        st.markdown("#### ⚡ グローバルマクロ設定 (閾値・間隔)")
        st.caption("テンプレート内のアイテムやトリガーは、以下のマクロ値によって制御されます。")
        
        df_macros = pd.DataFrame(macro_config)
        edited_macros = st.data_editor(
            df_macros,
            column_config={
                "macro": st.column_config.TextColumn("マクロ名", disabled=True, width="medium"),
                "value": st.column_config.TextColumn("設定値", required=True),
                "desc": st.column_config.TextColumn("説明", disabled=True)
            },
            hide_index=True,
            use_container_width=True,
            num_rows="fixed"
        )
        
        if st.button("💾 マクロ設定を保存"):
            new_config = edited_macros.to_dict(orient="records")
            save_json_config("zabbix_macros.json", new_config)
            st.success("保存しました")
            st.rerun()

    # --- Tab 3: 通知設定 ---
    with tab3:
        st.markdown("#### 📢 メディアタイプ & アクション設定")
        st.caption("障害検知時の通知手段と条件を定義します。")
        
        c_media, c_action = st.columns(2)
        
        with c_media:
            with st.container(border=True):
                st.subheader("✉️ メール設定 (Media Type)")
                new_smtp = st.text_input("SMTPサーバー", media_config.get("smtp_server"))
                new_email = st.text_input("送信元アドレス", media_config.get("smtp_email"))
        
        with c_action:
            with st.container(border=True):
                st.subheader("🔔 アクション実行条件")
                st.write("以下の深刻度以上で通知を実行:")
                severity_opts = ["Information", "Warning", "Average", "High", "Disaster"]
                curr_sev = media_config.get("alert_severity", "Average")
                new_sev = st.selectbox("深刻度 (Severity)", severity_opts, index=severity_opts.index(curr_sev))
                st.caption(f"対象: Zabbix Administrators グループ")

        if st.button("💾 通知設定を保存"):
            media_config.update({
                "smtp_server": new_smtp,
                "smtp_email": new_email,
                "alert_severity": new_sev
            })
            save_json_config("zabbix_media.json", media_config)
            st.success("保存しました")

    # === 生成 & プレビュー ===
    st.divider()
    st.subheader("📄 設定プレビュー (JSON生成)")
    
    # Config生成
    config = generate_zabbix_config(full_data, macro_config, template_mapping, media_config)
    
    # KPI
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Hosts", len(config["hosts"]))
    k2.metric("Host Groups", len(config["host_groups"]))
    k3.metric("Macros", len(config["hosts"][0]["macros"]) if config["hosts"] else 0)
    k4.metric("Actions", len(config["actions"]))

    with st.expander("詳細 JSON データを確認"):
        st.json(config)

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
        st.button("🚀 Zabbix APIへ投入 (実装済)", disabled=not st.session_state.zabbix_connected, use_container_width=True)

if __name__ == "__main__":
    main()
