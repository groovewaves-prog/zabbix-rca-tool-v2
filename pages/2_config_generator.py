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
import random
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

def load_local_topology():
    """サーバーローカルのトポロジーデータを読み込む"""
    topology_path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(topology_path):
        with open(topology_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# ==================== Zabbix API クライアント (実通信用) ====================
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
        """接続確認"""
        return self.call("apiinfo.version")

# ==================== Mock Zabbix API (デモ用) ====================
class MockZabbixAPI:
    """Zabbixサーバーがない環境でも動作確認するためのモッククラス"""
    def __init__(self):
        self.url = "http://mock-zabbix/api"
        self.group_counter = 10
        self.host_counter = 100
        self.template_counter = 500

    def call(self, method: str, params: Any = None):
        """API呼び出しをシミュレートしてダミーデータを返す"""
        time.sleep(0.1) 

        if method == "apiinfo.version":
            return "6.4.0 (Mock Mode)"
        elif method == "hostgroup.get":
            return []
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
        elif method == "host.create":
            return {"hostids": [str(self.host_counter + 1)]}
        elif method == "host.update":
            return {"hostids": [str(self.host_counter)]}
            
        return {}

    def check_connection(self):
        return self.call("apiinfo.version")

# ==================== 設定生成ロジック ====================
def generate_zabbix_config(data: Dict) -> Dict:
    """トポロジーデータからZabbix設定JSONを生成"""
    topology = data.get("topology", {})
    connections = data.get("connections", [])
    module_master = data.get("module_master_list", [])
    
    config = {
        "host_groups": [],
        "hosts": [],
        "templates": [],
        "summary": {}
    }
    
    # トポロジーが空の場合は空設定を返す
    if not topology:
        return config

    # 1. ホストグループ
    groups = set(["Network/Generated"])
    for d in topology.values():
        meta = d.get("metadata", {})
        if meta.get("vendor"): groups.add(f"Vendor/{meta['vendor']}")
        if meta.get("location"): groups.add(f"Location/{meta['location']}")
        groups.add(f"Network/Layer{d.get('layer', 0)}")

    config["host_groups"] = [{"name": g} for g in sorted(groups)]

    # 2. テンプレートマッピング (仮定義)
    template_map = {
        "Cisco": "Template Net Cisco IOS SNMP",
        "Juniper": "Template Net Juniper SNMP",
        "Linux": "Template OS Linux by Zabbix agent",
        "Windows": "Template OS Windows by Zabbix agent",
        "default": "Template Module ICMP Ping"
    }

    # 3. ホスト設定
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

        # マクロ (モジュール監視)
        macros = []
        if hw.get("psu_count"): macros.append({"macro": "{$EXPECTED_PSU_COUNT}", "value": str(hw["psu_count"])})
        if hw.get("fan_count"): macros.append({"macro": "{$EXPECTED_FAN_COUNT}", "value": str(hw["fan_count"])})
        
        custom_mods = hw.get("custom_modules", {})
        for mod_name in module_master:
            count = custom_mods.get(mod_name, 0)
            safe_name = mod_name.upper().replace("-", "_").replace(" ", "_").replace("+", "PLUS")
            macros.append({"macro": f"{{$EXPECTED_{safe_name}_COUNT}}", "value": str(count)})

        # タグ (LAG/VLAN)
        tags = [
            {"tag": "Layer", "value": str(dev_data.get("layer", 0))},
            {"tag": "Type", "value": dev_data.get("type", "Unknown")},
            {"tag": "Model", "value": meta.get("model", "Unknown")}
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
            "description": f"Generated by RCA Tool.\nLocation: {meta.get('location', 'N/A')}"
        }
        config["hosts"].append(host_obj)

    config["summary"] = {"hosts": len(config["hosts"]), "groups": len(config["host_groups"])}
    return config

# ==================== API投入ロジック ====================
def push_config_to_zabbix(api: Any, config: Dict):
    """API経由でZabbixに反映 (st.status対応)"""
    logs = []
    
    st.write("📂 ホストグループを確認中...")
    existing_groups = {g['name']: g['groupid'] for g in api.call("hostgroup.get", {"output": ["groupid", "name"]})}
    
    for group in config["host_groups"]:
        g_name = group["name"]
        if g_name not in existing_groups:
            res = api.call("hostgroup.create", {"name": g_name})
            existing_groups[g_name] = res['groupids'][0]
            logs.append(f"✅ グループ作成: {g_name}")
        else:
            logs.append(f"ℹ️ グループ既存: {g_name}")

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
            else: logs.append(f"⚠️ テンプレート不明: {t['name']} (スキップ)")

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

    return logs

# ==================== UIメイン処理 ====================
def main():
    # --- サイドバー (API設定) ---
    with st.sidebar:
        st.header("📂 トポロジーデータ読み込み")
        uploaded_file = st.file_uploader(
            "JSONファイルをアップロード", 
            type=["json"],
            help="手持ちのtopology.jsonを使用する場合はこちらからアップロードしてください"
        )
        
        st.divider()
        
        st.header("🔗 Zabbix Server 設定")
        use_mock = st.checkbox("🧪 モックモード (Zabbix不要)", value=False, help="Zabbix環境がない場合でも動作を確認できます")
        
        if "zabbix_connected" not in st.session_state:
            st.session_state.zabbix_connected = False
            st.session_state.zabbix_version = ""
            st.session_state.is_mock = False

        zabbix_url = st.text_input("URL", "http://192.168.1.100/zabbix", disabled=use_mock)
        zabbix_token = st.text_input("API Token", type="password", disabled=use_mock)
        
        if st.button("接続テスト", use_container_width=True):
            try:
                if use_mock:
                    api = MockZabbixAPI()
                    version = api.check_connection()
                    st.session_state.is_mock = True
                else:
                    if not zabbix_url or not zabbix_token:
                        st.warning("URLとトークンを入力してください")
                        raise Exception("Input required")
                    api = ZabbixAPI(zabbix_url, zabbix_token)
                    version = api.check_connection()
                    st.session_state.is_mock = False
                
                st.session_state.zabbix_connected = True
                st.session_state.zabbix_version = version
                st.success(f"接続成功! (v{version})")
                
            except Exception as e:
                st.session_state.zabbix_connected = False
                if str(e) != "Input required":
                    st.error(f"接続失敗: {e}")

        if st.session_state.zabbix_connected:
            mode_label = "Mock" if st.session_state.is_mock else "Real"
            st.success(f"✅ 接続済み ({mode_label} v{st.session_state.zabbix_version})")
        else:
            st.info("未接続")

    # --- メインコンテンツ ---
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("⚙️ 監視設定生成 & 自動投入")
        st.caption("トポロジービルダーで作成した構成情報を元に、Zabbixの設定を自動生成・投入します。")
    with col2:
        if st.button("🏠 ホームに戻る", use_container_width=True):
            st.switch_page("Home.py")
    
    st.divider()

    # 1. データ読み込み (アップロード優先 -> ローカルファイル)
    data = None
    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            st.info(f"📂 アップロードされたファイルを使用中: `{uploaded_file.name}`")
        except Exception as e:
            st.error(f"ファイル読み込みエラー: {e}")
            return
    else:
        data = load_local_topology()
        if data and data.get("topology"): # 中身があるかチェック
            st.info("📂 サーバー内の最新トポロジーデータを使用中")
        else:
            # データがない場合はここでリターンし、警告を表示
            st.warning("⚠️ トポロジーデータが見つかりません。")
            st.info("ファイルをアップロードするか、「トポロジービルダー」で構成を作成してください。")
            if st.button("🔧 トポロジービルダーを開く", type="primary"):
                st.switch_page("pages/1_topology_builder.py")
            return

    # 2. 設定生成 (自動実行)
    # ここで生成ロジックを必ず通す
    config = generate_zabbix_config(data)
    
    # 3. プレビュー表示
    st.subheader("1. 設定プレビュー")
    
    if not config["hosts"]:
        st.warning("生成されたホスト設定がありません。トポロジーにデバイスが含まれているか確認してください。")
    else:
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric("対象ホスト数", f"{len(config['hosts'])} 台")
        col_kpi2.metric("ホストグループ数", f"{len(config['host_groups'])} 個")
        col_kpi3.metric("適用テンプレート", "標準セット")

        with st.expander("詳細データを確認する (Table / JSON)", expanded=False):
            tab1, tab2 = st.tabs(["📋 ホスト一覧", "🔍 JSONソース"])
            with tab1:
                df_data = []
                for h in config["hosts"]:
                    macros_str = ", ".join([f"{m['macro']}={m['value']}" for m in h["macros"]])
                    tags_str = ", ".join([f"{t['tag']}:{t['value']}" for t in h["tags"]])
                    df_data.append({
                        "Host": h["host"],
                        "Groups": len(h["groups"]),
                        "Templates": [t["name"] for t in h["templates"]],
                        "Macros": macros_str,
                        "Tags": tags_str
                    })
                st.dataframe(pd.DataFrame(df_data), use_container_width=True)
            with tab2:
                st.json(config)

    st.divider()

    # 4. アクションエリア
    st.subheader("2. アクション実行")
    
    act_col1, act_col2 = st.columns(2)
    
    with act_col1:
        st.markdown("##### 📥 ファイル保存")
        st.caption("生成された設定をJSONファイルとしてダウンロードします。")
        st.download_button(
            label="設定JSONをダウンロード",
            data=json.dumps(config, ensure_ascii=False, indent=2),
            file_name="zabbix_auto_config.json",
            mime="application/json",
            use_container_width=True,
            disabled=len(config["hosts"]) == 0
        )

    with act_col2:
        st.markdown("##### 🚀 Zabbixへ投入")
        st.caption("API経由でZabbixサーバーに設定を即時反映します。")
        
        # 投入ボタンの有効化判定
        if not st.session_state.zabbix_connected:
            st.warning("👈 サイドバーでZabbix(またはモック)への接続テストを行ってください。")
            st.button("Zabbixへ投入 (未接続)", disabled=True, use_container_width=True)
        elif len(config["hosts"]) == 0:
            st.button("Zabbixへ投入 (データなし)", disabled=True, use_container_width=True)
        else:
            if st.button("設定を投入する", type="primary", use_container_width=True):
                
                if st.session_state.is_mock:
                    api = MockZabbixAPI()
                else:
                    api = ZabbixAPI(zabbix_url, zabbix_token)

                with st.status("Zabbixへの設定反映を実行中...", expanded=True) as status:
                    try:
                        logs = push_config_to_zabbix(api, config)
                        status.update(label="✅ 設定投入が完了しました！", state="complete", expanded=False)
                        st.success(f"成功: {len(config['hosts'])} 台のホスト設定を更新しました。")
                        with st.expander("実行ログ詳細"):
                            for log in logs:
                                st.write(log)
                    except Exception as e:
                        status.update(label="❌ エラーが発生しました", state="error")
                        st.error(f"詳細: {e}")

if __name__ == "__main__":
    main()
