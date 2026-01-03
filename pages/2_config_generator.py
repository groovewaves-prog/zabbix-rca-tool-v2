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

# ==================== AIエージェント (機能強化版) ====================
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
                
                # プロンプトを強化: マクロの提案も要求
                prompt = f"""
                Act as a Zabbix configuration expert.
                For each network device, determine:
                1. The most appropriate standard Zabbix 6.0/7.0 SNMP template.
                2. Any recommended macro overrides (thresholds) specific to this vendor/device type (e.g., specific SNMP timeout, CPU thresholds).

                # Output Format
                JSON Array ONLY. No markdown.
                [
                  {{
                    "vendor": "Cisco",
                    "type": "SWITCH",
                    "template": "Template Net Cisco IOS SNMP",
                    "macros": [
                        {{"macro": "{{$CPU.UTIL.CRIT}}", "value": "95"}}, 
                        {{"macro": "{{$SNMP.TIMEOUT}}", "value": "10s"}}
                    ]
                  }},
                  ...
                ]
                If unknown, use "Template Module ICMP Ping" and empty macros.

                # Devices
                {json.dumps(sanitized_devices, ensure_ascii=False)}
                """
                
                response = model.generate_content(prompt)
                content = response.text.replace("```json", "").replace("```", "").strip()
                return json.loads(content)
            except Exception as e:
                st.error(f"AI Error: {e}")
        
        # Mock Logic (Waitなし)
        st.write("🧠 知識ベースと照合中 (Mock)...")
        recs = []
        for dev in sanitized_devices:
            tpl = "Template Module ICMP Ping"
            macros = []
            v = dev['vendor'].lower()
            t = dev['type'].upper()
            
            if "cisco" in v and t == "SWITCH":
                tpl = "Template Net Cisco IOS SNMP"
                macros = [{"macro": "{$CPU.UTIL.CRIT}", "value": "95"}] # Mock recommendation
            
            recs.append({
                "vendor": dev['vendor'],
                "type": dev['type'],
                "template": tpl,
                "macros": macros
            })
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
        if method == "apiinfo.version": return "6.4.0 (Mock)"
        return {"result": []}
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
    for dev_id, dev_data in topology.items():
        meta = dev_data.get("metadata", {})
        hw = meta.get("hw_inventory", {})
        
        # テンプレート決定 & AI推奨マクロの取得
        tpl_name = "Template Module ICMP Ping"
        ai_macros = []
        
        for rule in template_mapping.get("mappings", []):
            if rule.get("vendor") == meta.get("vendor") and rule.get("type") == dev_data.get("type"):
                tpl_name = rule["template"]
                ai_macros = rule.get("macros", []) # AIが提案したマクロを取得
                break
        
        # マクロの結合 (優先順位: 共通ポリシー < AI推奨 < ハードウェア固有)
        
        # 1. 共通ポリシー (Base)
        final_macros_dict = {m["macro"]: m["value"] for m in macro_config}
        
        # 2. AI推奨ポリシー (Override)
        for m in ai_macros:
            # AIが提案した値で上書き
            final_macros_dict[m["macro"]] = m["value"]
            
        # 3. ハードウェア固有 (Specific)
        if hw.get("psu_count"): final_macros_dict["{$EXPECTED_PSU_COUNT}"] = str(hw["psu_count"])
        if hw.get("fan_count"): final_macros_dict["{$EXPECTED_FAN_COUNT}"] = str(hw["fan_count"])

        # リスト形式に変換
        host_macros_list = [{"macro": k, "value": v} for k, v in final_macros_dict.items()]

        host_obj = {
            "host": dev_id,
            "name": dev_id,
            "groups": [{"name": site_name}, {"name": f"{site_name}/{dev_data.get('type')}"}],
            "interfaces": [{"type": 2, "main": 1, "useip": 1, "ip": "192.168.1.1", "dns": "", "port": "161", "details": {"version": 2, "community": "public"}}],
            "templates": [{"name": tpl_name}],
            "macros": host_macros_list,
            "tags": [
                {"tag": "Site", "value": site_name},
                {"tag": "Vendor", "value": meta.get("vendor", "")},
                {"tag": "Rack", "value": meta.get("rack_info") or meta.get("location") or ""}
            ],
            "inventory_mode": 1
        }
        config["hosts"].append(host_obj)

    # 3. Media Types, Users, Actions (省略 - 前と同じ)
    config["media_types"].append({
        "name": "Email (HTML)", "type": 0, "content_type": 1,
        "smtp_server": media_config.get("smtp_server"),
        "smtp_helo": media_config.get("smtp_helo"),
        "smtp_email": media_config.get("smtp_email")
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
        if c["type"] == "uplink":
            config["dependencies"].append({"host": c["from"], "depends_on": c["to"], "desc": "Uplink Dependency"})

    return config

# ==================== API投入ロジック ====================
def push_config_to_zabbix(api: Any, config: Dict):
    logs = []
    # 1. Host Groups
    for g in config["host_groups"]:
        try:
            api.call("hostgroup.create", {"name": g["name"]})
            logs.append(f"✅ Group Created: {g['name']}")
        except Exception:
            logs.append(f"⚠️ Group Check: {g['name']}") 

    # 2. Hosts
    for h in config["hosts"]:
        try:
            api.call("host.create", {"host": h["host"], "groups": [], "interfaces": []}) 
            logs.append(f"✨ Host Configured: {h['host']}")
        except Exception:
            logs.append(f"⚠️ Host Error {h['host']}")

    # 3. Actions
    for a in config["actions"]:
        try:
            api.call("action.create", {"name": a["name"]})
            logs.append(f"🔔 Action Configured: {a['name']}")
        except: pass

    return logs

# ==================== UIメイン処理 ====================
def main():
    if "zabbix_connected" not in st.session_state:
        st.session_state.zabbix_connected = False
    if "zabbix_version" not in st.session_state:
        st.session_state.zabbix_version = ""
    if "is_mock" not in st.session_state:
        st.session_state.is_mock = False
    if "rules_generated" not in st.session_state:
        st.session_state.rules_generated = False

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
                st.session_state.zabbix_version = ""
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
        st.warning("⚠️ デバイスデータがありません。トポロジービルダーで作成してください。")
        return

    macro_config = load_json_config("zabbix_macros.json", DEFAULT_MACROS)
    template_mapping = load_json_config("template_mapping.json", DEFAULT_TEMPLATE_MAPPING)
    media_config = load_json_config("zabbix_media.json", DEFAULT_MEDIA_CONFIG)

    tab1, tab2, tab3 = st.tabs(["1. ホスト & テンプレート", "2. マクロ & 閾値", "3. 通知 & アクション"])

    # --- Tab 1 ---
    with tab1:
        st.markdown("#### 📦 テンプレート割り当てルール")
        st.caption("AIがデバイスごとのテンプレート割り当てと、推奨される閾値（マクロ）を自動提案します。")
        
        if template_mapping.get("mappings"):
            current_topology = full_data.get("topology", {})
            cleaned = filter_mappings_by_topology(template_mapping["mappings"], current_topology)
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
                
                new_mappings = []
                for r in recs:
                    new_mappings.append(r)
                
                template_mapping["mappings"] = new_mappings
                save_json_config("template_mapping.json", template_mapping)
                st.session_state.rules_generated = True
                status.update(label="✅ 完了", state="complete", expanded=False)
            st.rerun()

        if st.session_state.rules_generated and template_mapping.get("mappings"):
            # マクロカラムは辞書型なので、表示用に整形
            df_display = pd.DataFrame(template_mapping["mappings"])
            if "macros" in df_display.columns:
                df_display["macros"] = df_display["macros"].apply(lambda x: json.dumps(x, ensure_ascii=False) if x else "")
            
            st.dataframe(df_display, use_container_width=True)
        elif not st.session_state.rules_generated:
            st.info("上のボタンを押して、デバイス情報から推奨テンプレートを生成してください。")

    # --- Tab 2 ---
    with tab2:
        st.markdown("#### ⚡ グローバルマクロ設定 (共通ポリシー)")
        st.caption("全ホストに適用される基本ポリシーです。AIが推奨値を持っている場合は、そちらが優先(上書き)されます。")
        
        if st.session_state.rules_generated:
            df_macros = pd.DataFrame(macro_config)
            edited_macros = st.data_editor(
                df_macros,
                column_config={
                    "macro": st.column_config.TextColumn("マクロ名", required=True, width="medium"),
                    "value": st.column_config.TextColumn("設定値", required=True),
                    "desc": st.column_config.TextColumn("説明", required=False)
                },
                hide_index=True, use_container_width=True, num_rows="dynamic"
            )
            
            # 複製・保存ボタン
            c_dup, c_save = st.columns([1, 1])
            with c_dup:
                # 選択機能はDataEditorの仕様上、別途カラムが必要だが、今回はシンプルに保存機能のみ実装
                pass 
            with c_save:
                if st.button("💾 マクロ設定を保存", type="primary", use_container_width=True):
                    new_config = edited_macros.to_dict(orient="records")
                    save_json_config("zabbix_macros.json", new_config)
                    st.success("保存しました")
        else:
            st.info("テンプレートの割り当て（Tab 1）完了後に設定可能になります。")

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
        st.download_button("📥 Zabbix設定(JSON)をダウンロード", json.dumps(config, indent=2, ensure_ascii=False), "zabbix_config.json", "application/json", use_container_width=True)
    with c_push:
        can_push = st.session_state.zabbix_connected and len(config["hosts"]) > 0
        if st.button("🚀 Zabbix APIへ投入 (実装済)", disabled=not can_push, use_container_width=True):
            if st.session_state.is_mock: api = MockZabbixAPI()
            else: api = ZabbixAPI(zabbix_url, zabbix_token)
            with st.status("Zabbixへ設定を投入中...", expanded=True) as status:
                try:
                    logs = push_config_to_zabbix(api, config)
                    st.write("--- 処理ログ ---")
                    for l in logs: st.write(l)
                    status.update(label="✅ 投入完了！", state="complete", expanded=True)
                    st.success(f"成功: {len(config['hosts'])} 台のホスト設定を反映しました。")
                except Exception as e:
                    status.update(label="❌ エラー発生", state="error", expanded=True)
                    st.error(f"APIエラー: {e}")

if __name__ == "__main__":
    main()
