"""
Zabbix RCA Tool - トポロジービルダー
ウィザード形式でトポロジーを作成
"""

import streamlit as st
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import uuid

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="トポロジービルダー - Zabbix RCA Tool",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== カスタムCSS ====================
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* ステッププログレス */
    .step-container {
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 20px 0;
        padding: 20px;
        background: #f8f9fa;
        border-radius: 10px;
    }
    .step-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        margin: 0 10px;
        min-width: 100px;
    }
    .step-circle {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        margin-bottom: 8px;
    }
    .step-active {
        background: #667eea;
        color: white;
    }
    .step-completed {
        background: #28a745;
        color: white;
    }
    .step-pending {
        background: #e9ecef;
        color: #6c757d;
    }
    .step-label {
        font-size: 0.85em;
        text-align: center;
        color: #495057;
    }
    .step-connector {
        width: 50px;
        height: 3px;
        background: #e9ecef;
        margin: 0 5px;
    }
    .step-connector-active {
        background: #28a745;
    }
    
    /* デバイスカード */
    .device-card {
        padding: 15px;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        margin: 10px 0;
        background: white;
    }
    .device-card:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    
    /* モジュールリスト */
    .module-item {
        padding: 8px 12px;
        background: #f8f9fa;
        border-radius: 5px;
        margin: 5px 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    /* ヒントボックス */
    .hint-box {
        padding: 15px;
        background: #e7f3ff;
        border-left: 4px solid #2196f3;
        border-radius: 0 8px 8px 0;
        margin: 15px 0;
    }
    
    /* 冗長グループカード */
    .redundancy-card {
        padding: 15px;
        border: 2px solid #667eea;
        border-radius: 10px;
        margin: 10px 0;
        background: #f8f9ff;
    }
</style>
""", unsafe_allow_html=True)

# ==================== 定数 ====================
DEVICE_TYPES = ["ROUTER", "SWITCH", "FIREWALL", "SERVER", "ACCESS_POINT", "LOAD_BALANCER", "STORAGE"]
VENDORS = ["Cisco", "Juniper", "Fortinet", "Palo Alto", "Arista", "HPE", "Dell", "Other"]
MODULE_TYPES = ["PSU", "FAN", "SUPERVISOR", "LINECARD", "CONTROLLER"]
REDUNDANCY_TYPES = ["Active-Standby", "Active-Active", "Stack", "VRRP/HSRP", "Cluster"]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== セッション状態初期化 ====================
def init_session_state():
    """セッション状態を初期化"""
    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 1
    
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    
    if "redundancy_groups" not in st.session_state:
        st.session_state.redundancy_groups = {}
    
    if "editing_device" not in st.session_state:
        st.session_state.editing_device = None

# ==================== ステッププログレス表示 ====================
def render_step_progress(current_step: int):
    """ステッププログレスバーを表示"""
    steps = [
        ("1", "デバイス定義"),
        ("2", "階層配置"),
        ("3", "接続関係"),
        ("4", "冗長設定"),
        ("5", "確認・出力")
    ]
    
    cols = st.columns(9)
    for i, (num, label) in enumerate(steps):
        step_num = int(num)
        
        # ステップサークル
        with cols[i * 2]:
            if step_num < current_step:
                st.markdown(f"""
                <div style="text-align: center;">
                    <div style="width: 40px; height: 40px; border-radius: 50%; background: #28a745; 
                         color: white; display: inline-flex; align-items: center; justify-content: center; font-weight: bold;">
                        ✓
                    </div>
                    <div style="font-size: 0.8em; margin-top: 5px; color: #28a745;">{label}</div>
                </div>
                """, unsafe_allow_html=True)
            elif step_num == current_step:
                st.markdown(f"""
                <div style="text-align: center;">
                    <div style="width: 40px; height: 40px; border-radius: 50%; background: #667eea; 
                         color: white; display: inline-flex; align-items: center; justify-content: center; font-weight: bold;">
                        {num}
                    </div>
                    <div style="font-size: 0.8em; margin-top: 5px; color: #667eea; font-weight: bold;">{label}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="text-align: center;">
                    <div style="width: 40px; height: 40px; border-radius: 50%; background: #e9ecef; 
                         color: #6c757d; display: inline-flex; align-items: center; justify-content: center; font-weight: bold;">
                        {num}
                    </div>
                    <div style="font-size: 0.8em; margin-top: 5px; color: #6c757d;">{label}</div>
                </div>
                """, unsafe_allow_html=True)
        
        # コネクター（最後以外）
        if i < len(steps) - 1:
            with cols[i * 2 + 1]:
                color = "#28a745" if step_num < current_step else "#e9ecef"
                st.markdown(f"""
                <div style="display: flex; align-items: center; height: 60px;">
                    <div style="width: 100%; height: 3px; background: {color};"></div>
                </div>
                """, unsafe_allow_html=True)

# ==================== Step 1: デバイス定義 ====================
def render_step1_devices():
    """Step 1: デバイス定義"""
    st.header("🔧 Step 1: デバイス定義")
    
    st.markdown("""
    <div class="hint-box">
        💡 <strong>ヒント:</strong> ネットワーク機器、サーバー、ストレージなどのデバイスを登録します。
        各デバイスの内部モジュール（電源、ファン等）の冗長構成も設定できます。
    </div>
    """, unsafe_allow_html=True)
    
    # 登録済みデバイス一覧
    if st.session_state.devices:
        st.subheader(f"📋 登録済みデバイス ({len(st.session_state.devices)}台)")
        
        for device_id, device in st.session_state.devices.items():
            with st.expander(f"{'🔵' if device['type'] == 'ROUTER' else '🟢' if device['type'] == 'SWITCH' else '🔴' if device['type'] == 'FIREWALL' else '🟣'} {device_id}", expanded=False):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.write(f"**タイプ:** {device['type']}")
                    st.write(f"**ベンダー:** {device.get('vendor', '-')}")
                with col2:
                    st.write(f"**モデル:** {device.get('model', '-')}")
                    st.write(f"**ロケーション:** {device.get('location', '-')}")
                with col3:
                    if st.button("🗑️ 削除", key=f"del_{device_id}"):
                        del st.session_state.devices[device_id]
                        st.rerun()
                
                # モジュール情報
                if device.get("modules"):
                    st.write("**📦 モジュール構成:**")
                    for mod_type, modules in device["modules"].items():
                        st.write(f"  - {mod_type}: {len(modules)}個")
    
    st.divider()
    
    # 新規デバイス追加フォーム
    st.subheader("➕ 新規デバイス追加")
    
    with st.form("add_device_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            device_id = st.text_input(
                "デバイスID *",
                placeholder="例: WAN_ROUTER_01",
                help="一意のIDを入力してください"
            )
            device_type = st.selectbox("デバイスタイプ *", DEVICE_TYPES)
            vendor = st.selectbox("ベンダー", [""] + VENDORS)
        
        with col2:
            model = st.text_input("モデル", placeholder="例: ASR1001-X")
            location = st.text_input("ロケーション", placeholder="例: DC1-Rack01")
        
        # モジュール構成
        st.markdown("---")
        st.markdown("**📦 モジュール構成（任意）**")
        
        mod_col1, mod_col2, mod_col3, mod_col4 = st.columns(4)
        with mod_col1:
            psu_count = st.number_input("電源モジュール数", min_value=0, max_value=8, value=0)
        with mod_col2:
            fan_count = st.number_input("ファンモジュール数", min_value=0, max_value=8, value=0)
        with mod_col3:
            sup_count = st.number_input("スーパバイザ数", min_value=0, max_value=4, value=0)
        with mod_col4:
            ctrl_count = st.number_input("コントローラ数", min_value=0, max_value=4, value=0)
        
        submitted = st.form_submit_button("➕ デバイスを追加", type="primary", use_container_width=True)
        
        if submitted:
            if not device_id:
                st.error("デバイスIDは必須です")
            elif device_id in st.session_state.devices:
                st.error(f"デバイスID '{device_id}' は既に存在します")
            else:
                # モジュール構成を作成
                modules = {}
                if psu_count > 0:
                    modules["PSU"] = [{"id": f"PSU-{i+1}", "status": "OK"} for i in range(psu_count)]
                if fan_count > 0:
                    modules["FAN"] = [{"id": f"FAN-{i+1}", "status": "OK"} for i in range(fan_count)]
                if sup_count > 0:
                    modules["SUPERVISOR"] = [{"id": f"SUP-{i+1}", "status": "OK"} for i in range(sup_count)]
                if ctrl_count > 0:
                    modules["CONTROLLER"] = [{"id": f"CTRL-{i+1}", "status": "OK"} for i in range(ctrl_count)]
                
                # デバイスを追加
                st.session_state.devices[device_id] = {
                    "type": device_type,
                    "vendor": vendor if vendor else None,
                    "model": model if model else None,
                    "location": location if location else None,
                    "layer": None,  # Step 2で設定
                    "parent_ids": [],  # Step 3で設定
                    "modules": modules if modules else None,
                }
                st.success(f"✅ デバイス '{device_id}' を追加しました")
                st.rerun()
    
    # テンプレートからの一括追加
    st.divider()
    with st.expander("📝 テンプレートから一括追加"):
        st.markdown("""
        以下の形式でデバイスを一括登録できます:
        ```
        デバイスID, タイプ, ベンダー, モデル, PSU数
        ```
        """)
        
        template_input = st.text_area(
            "デバイス情報",
            placeholder="WAN_ROUTER_01, ROUTER, Cisco, ASR1001-X, 2\nCORE_SW_01, SWITCH, Cisco, C9500, 2",
            height=150
        )
        
        if st.button("一括追加", key="bulk_add"):
            if template_input:
                added = 0
                for line in template_input.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        dev_id = parts[0]
                        if dev_id and dev_id not in st.session_state.devices:
                            modules = {}
                            if len(parts) >= 5 and parts[4].isdigit():
                                psu = int(parts[4])
                                if psu > 0:
                                    modules["PSU"] = [{"id": f"PSU-{i+1}", "status": "OK"} for i in range(psu)]
                            
                            st.session_state.devices[dev_id] = {
                                "type": parts[1] if len(parts) > 1 and parts[1] in DEVICE_TYPES else "SWITCH",
                                "vendor": parts[2] if len(parts) > 2 else None,
                                "model": parts[3] if len(parts) > 3 else None,
                                "location": None,
                                "layer": None,
                                "parent_ids": [],
                                "modules": modules if modules else None,
                            }
                            added += 1
                
                if added > 0:
                    st.success(f"✅ {added}台のデバイスを追加しました")
                    st.rerun()

# ==================== Step 2: 階層配置 ====================
def render_step2_layers():
    """Step 2: 階層配置"""
    st.header("📍 Step 2: 階層配置")
    
    st.markdown("""
    <div class="hint-box">
        💡 <strong>ヒント:</strong> 各デバイスをネットワーク階層（Layer）に配置します。
        Layer 1 が最上位（WAN/Internet Edge）、数字が大きいほど末端に近くなります。
    </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state.devices:
        st.warning("⚠️ デバイスが登録されていません。Step 1でデバイスを追加してください。")
        return
    
    # レイヤー定義のガイド
    with st.expander("📖 レイヤー構成ガイド"):
        st.markdown("""
        | Layer | 名称 | 役割 | 例 |
        |-------|------|------|-----|
        | 1 | WAN Edge | インターネット/WAN境界 | WANルーター、エッジルーター |
        | 2 | Core | コアネットワーク | コアスイッチ、ファイアウォール |
        | 3 | Distribution | ディストリビューション層 | L3スイッチ、ロードバランサー |
        | 4 | Access | アクセス層 | L2スイッチ、アクセスポイント |
        | 5 | Endpoint | エンドポイント | サーバー、ストレージ |
        """)
    
    st.divider()
    
    # 一括設定
    st.subheader("⚡ クイック設定")
    
    col1, col2 = st.columns(2)
    with col1:
        auto_layer = st.selectbox(
            "レイヤーを選択",
            [1, 2, 3, 4, 5],
            format_func=lambda x: f"Layer {x}"
        )
    with col2:
        device_types_for_layer = st.multiselect(
            "対象デバイスタイプ",
            DEVICE_TYPES,
            default=[]
        )
    
    if st.button("選択したタイプに一括適用", key="bulk_layer"):
        if device_types_for_layer:
            updated = 0
            for dev_id, dev in st.session_state.devices.items():
                if dev["type"] in device_types_for_layer:
                    st.session_state.devices[dev_id]["layer"] = auto_layer
                    updated += 1
            if updated > 0:
                st.success(f"✅ {updated}台のデバイスにLayer {auto_layer}を設定しました")
                st.rerun()
    
    st.divider()
    
    # 個別設定
    st.subheader("📋 デバイス別レイヤー設定")
    
    # レイヤー別にグループ化して表示
    for layer in [1, 2, 3, 4, 5, None]:
        layer_devices = [(k, v) for k, v in st.session_state.devices.items() if v.get("layer") == layer]
        
        if layer is None:
            label = "❓ 未設定"
            if not layer_devices:
                continue
        else:
            label = f"📍 Layer {layer}"
        
        with st.expander(f"{label} ({len(layer_devices)}台)", expanded=(layer is None)):
            if layer_devices:
                for dev_id, dev in layer_devices:
                    col1, col2, col3 = st.columns([3, 2, 2])
                    with col1:
                        st.write(f"**{dev_id}** ({dev['type']})")
                    with col2:
                        st.caption(f"{dev.get('vendor', '-')} {dev.get('model', '')}")
                    with col3:
                        new_layer = st.selectbox(
                            "Layer",
                            [None, 1, 2, 3, 4, 5],
                            index=[None, 1, 2, 3, 4, 5].index(dev.get("layer")),
                            key=f"layer_{dev_id}",
                            format_func=lambda x: "未設定" if x is None else f"Layer {x}",
                            label_visibility="collapsed"
                        )
                        if new_layer != dev.get("layer"):
                            st.session_state.devices[dev_id]["layer"] = new_layer
                            st.rerun()
            else:
                st.caption("このレイヤーにデバイスはありません")

# ==================== Step 3: 接続関係 ====================
def render_step3_connections():
    """Step 3: 接続関係"""
    st.header("🔗 Step 3: 接続関係")
    
    st.markdown("""
    <div class="hint-box">
        💡 <strong>ヒント:</strong> 各デバイスの上位接続先（親デバイス）を設定します。
        複数選択でマルチパス/冗長接続を表現できます。
    </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state.devices:
        st.warning("⚠️ デバイスが登録されていません。")
        return
    
    # レイヤーが設定されていないデバイスをチェック
    unassigned = [k for k, v in st.session_state.devices.items() if v.get("layer") is None]
    if unassigned:
        st.warning(f"⚠️ {len(unassigned)}台のデバイスにレイヤーが設定されていません。Step 2で設定してください。")
    
    st.divider()
    
    # レイヤー順に表示（下位レイヤーから）
    for layer in [5, 4, 3, 2, 1]:
        layer_devices = [(k, v) for k, v in st.session_state.devices.items() if v.get("layer") == layer]
        
        if not layer_devices:
            continue
        
        st.subheader(f"📍 Layer {layer}")
        
        # このレイヤーより上位のデバイスを接続先候補として取得
        upper_devices = [k for k, v in st.session_state.devices.items() 
                        if v.get("layer") is not None and v.get("layer") < layer]
        
        for dev_id, dev in layer_devices:
            col1, col2 = st.columns([1, 2])
            
            with col1:
                icon = "🔵" if dev["type"] == "ROUTER" else "🟢" if dev["type"] == "SWITCH" else "🔴" if dev["type"] == "FIREWALL" else "🟣"
                st.write(f"{icon} **{dev_id}**")
                st.caption(f"{dev['type']} | {dev.get('vendor', '-')}")
            
            with col2:
                if upper_devices:
                    current_parents = dev.get("parent_ids", [])
                    
                    selected_parents = st.multiselect(
                        "接続先（上位デバイス）",
                        upper_devices,
                        default=[p for p in current_parents if p in upper_devices],
                        key=f"conn_{dev_id}",
                        help="複数選択でマルチパス構成を設定できます"
                    )
                    
                    if selected_parents != current_parents:
                        st.session_state.devices[dev_id]["parent_ids"] = selected_parents
                else:
                    st.caption("（最上位レイヤーのため接続先なし）")
            
            st.markdown("---")
    
    # 接続関係のプレビュー
    st.divider()
    st.subheader("🗺️ 接続関係プレビュー")
    
    # テキストベースの簡易ツリー表示
    for layer in [1, 2, 3, 4, 5]:
        layer_devices = [(k, v) for k, v in st.session_state.devices.items() if v.get("layer") == layer]
        if layer_devices:
            st.markdown(f"**Layer {layer}**")
            for dev_id, dev in layer_devices:
                parents = dev.get("parent_ids", [])
                if parents:
                    parent_str = ", ".join(parents)
                    st.markdown(f"  └─ {dev_id} ← ({parent_str})")
                else:
                    st.markdown(f"  └─ {dev_id}")

# ==================== Step 4: 冗長設定 ====================
def render_step4_redundancy():
    """Step 4: 冗長設定"""
    st.header("🔷 Step 4: 冗長グループ設定")
    
    st.markdown("""
    <div class="hint-box">
        💡 <strong>ヒント:</strong> デバイス間の冗長関係（HA Pair、Stack等）を定義します。
        これにより、冗長構成を考慮した障害分析が可能になります。
    </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state.devices:
        st.warning("⚠️ デバイスが登録されていません。")
        return
    
    # 登録済み冗長グループ
    if st.session_state.redundancy_groups:
        st.subheader(f"📋 登録済み冗長グループ ({len(st.session_state.redundancy_groups)}件)")
        
        for group_id, group in st.session_state.redundancy_groups.items():
            with st.expander(f"🔷 {group_id}", expanded=True):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.write(f"**タイプ:** {group['type']}")
                with col2:
                    st.write(f"**メンバー:** {', '.join(group['members'])}")
                with col3:
                    if st.button("🗑️ 削除", key=f"del_grp_{group_id}"):
                        del st.session_state.redundancy_groups[group_id]
                        st.rerun()
    
    st.divider()
    
    # 新規冗長グループ追加
    st.subheader("➕ 新規冗長グループ追加")
    
    with st.form("add_redundancy_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            group_name = st.text_input(
                "グループ名 *",
                placeholder="例: CORE_HA_GROUP"
            )
            redundancy_type = st.selectbox(
                "冗長タイプ *",
                REDUNDANCY_TYPES
            )
        
        with col2:
            # デバイス選択（同じレイヤーのデバイスを推奨）
            available_devices = list(st.session_state.devices.keys())
            
            # 既にグループに所属しているデバイスを表示
            already_in_group = []
            for grp in st.session_state.redundancy_groups.values():
                already_in_group.extend(grp["members"])
            
            members = st.multiselect(
                "メンバーデバイス *",
                available_devices,
                help="冗長構成を組むデバイスを選択（通常2台以上）"
            )
            
            if already_in_group:
                st.caption(f"ℹ️ 既に他のグループに所属: {', '.join(set(already_in_group))}")
        
        # 冗長タイプの説明
        type_descriptions = {
            "Active-Standby": "1台がアクティブ、他がスタンバイ。障害時に切り替え。",
            "Active-Active": "全台がアクティブで負荷分散。",
            "Stack": "複数スイッチを1台の論理スイッチとして動作。",
            "VRRP/HSRP": "仮想IPによるゲートウェイ冗長。",
            "Cluster": "クラスタ構成（DBクラスタ、アプリクラスタ等）。"
        }
        st.info(f"ℹ️ {type_descriptions.get(redundancy_type, '')}")
        
        submitted = st.form_submit_button("➕ グループを追加", type="primary", use_container_width=True)
        
        if submitted:
            if not group_name:
                st.error("グループ名は必須です")
            elif group_name in st.session_state.redundancy_groups:
                st.error(f"グループ '{group_name}' は既に存在します")
            elif len(members) < 2:
                st.error("2台以上のデバイスを選択してください")
            else:
                st.session_state.redundancy_groups[group_name] = {
                    "type": redundancy_type,
                    "members": members
                }
                st.success(f"✅ 冗長グループ '{group_name}' を追加しました")
                st.rerun()
    
    # 自動検出提案
    st.divider()
    with st.expander("🔍 冗長グループ候補の自動検出"):
        st.markdown("同じレイヤー・同じタイプのデバイスペアを検出します。")
        
        # 同じレイヤー・タイプでグループ化
        candidates = {}
        for dev_id, dev in st.session_state.devices.items():
            key = (dev.get("layer"), dev.get("type"))
            if key[0] is not None:
                if key not in candidates:
                    candidates[key] = []
                candidates[key].append(dev_id)
        
        found = False
        for (layer, dev_type), devices in candidates.items():
            if len(devices) >= 2:
                found = True
                st.write(f"**Layer {layer} - {dev_type}**: {', '.join(devices)}")
                suggested_name = f"{dev_type}_L{layer}_HA"
                if st.button(f"グループ作成: {suggested_name}", key=f"auto_{layer}_{dev_type}"):
                    if suggested_name not in st.session_state.redundancy_groups:
                        st.session_state.redundancy_groups[suggested_name] = {
                            "type": "Active-Standby",
                            "members": devices[:2]  # 最初の2台
                        }
                        st.success(f"✅ '{suggested_name}' を作成しました")
                        st.rerun()
        
        if not found:
            st.info("候補となるデバイスペアが見つかりませんでした。")

# ==================== Step 5: 確認・出力 ====================
def render_step5_export():
    """Step 5: 確認・出力"""
    st.header("📤 Step 5: 確認・出力")
    
    if not st.session_state.devices:
        st.warning("⚠️ デバイスが登録されていません。")
        return
    
    # サマリー
    st.subheader("📊 トポロジーサマリー")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("デバイス数", f"{len(st.session_state.devices)}台")
    
    with col2:
        layers = set(v.get("layer") for v in st.session_state.devices.values() if v.get("layer"))
        st.metric("レイヤー数", len(layers))
    
    with col3:
        connections = sum(len(v.get("parent_ids", [])) for v in st.session_state.devices.values())
        st.metric("接続関係", connections)
    
    with col4:
        st.metric("冗長グループ", len(st.session_state.redundancy_groups))
    
    st.divider()
    
    # ビジュアルプレビュー
    st.subheader("🗺️ トポロジープレビュー")
    
    # テキストベースのツリー表示
    preview_text = []
    for layer in [1, 2, 3, 4, 5]:
        layer_devices = [(k, v) for k, v in st.session_state.devices.items() if v.get("layer") == layer]
        if layer_devices:
            preview_text.append(f"Layer {layer}:")
            for dev_id, dev in layer_devices:
                # 冗長グループ情報
                groups = [gid for gid, g in st.session_state.redundancy_groups.items() if dev_id in g["members"]]
                group_str = f" [{', '.join(groups)}]" if groups else ""
                
                # モジュール情報
                modules = dev.get("modules", {})
                mod_str = ""
                if modules:
                    mod_parts = [f"{k}:{len(v)}" for k, v in modules.items()]
                    mod_str = f" ({', '.join(mod_parts)})"
                
                preview_text.append(f"  └─ {dev_id} ({dev['type']}){group_str}{mod_str}")
    
    st.code("\n".join(preview_text), language=None)
    
    st.divider()
    
    # JSON生成
    st.subheader("📄 JSONデータ")
    
    # トポロジーJSONを生成
    topology_json = {}
    for dev_id, dev in st.session_state.devices.items():
        # 冗長グループを検索
        redundancy_group = None
        for gid, g in st.session_state.redundancy_groups.items():
            if dev_id in g["members"]:
                redundancy_group = gid
                break
        
        # parent_id（後方互換性のため最初の1つ）
        parent_ids = dev.get("parent_ids", [])
        primary_parent = parent_ids[0] if parent_ids else None
        
        topology_json[dev_id] = {
            "type": dev["type"],
            "layer": dev.get("layer", 0),
            "parent_id": primary_parent,
            "parent_ids": parent_ids,  # マルチパス対応
            "redundancy_group": redundancy_group,
            "metadata": {
                "vendor": dev.get("vendor"),
                "model": dev.get("model"),
                "location": dev.get("location"),
                "hw_inventory": {}
            }
        }
        
        # モジュール情報をhw_inventoryに変換
        if dev.get("modules"):
            modules = dev["modules"]
            if "PSU" in modules:
                topology_json[dev_id]["metadata"]["hw_inventory"]["psu_count"] = len(modules["PSU"])
            if "FAN" in modules:
                topology_json[dev_id]["metadata"]["hw_inventory"]["fan_count"] = len(modules["FAN"])
            if "SUPERVISOR" in modules:
                topology_json[dev_id]["metadata"]["hw_inventory"]["supervisor_count"] = len(modules["SUPERVISOR"])
    
    # 冗長グループ情報も含める
    output_data = {
        "topology": topology_json,
        "redundancy_groups": st.session_state.redundancy_groups,
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "device_count": len(topology_json),
            "version": "2.0"
        }
    }
    
    tab1, tab2 = st.tabs(["📊 サマリー表示", "📄 JSON表示"])
    
    with tab1:
        # デバイス一覧表
        st.markdown("**🖥️ デバイス一覧**")
        device_rows = []
        for dev_id, dev in topology_json.items():
            device_rows.append({
                "デバイスID": dev_id,
                "タイプ": dev["type"],
                "Layer": dev["layer"],
                "接続先": ", ".join(dev.get("parent_ids", [])) or "-",
                "冗長グループ": dev.get("redundancy_group") or "-",
                "ベンダー": dev["metadata"].get("vendor") or "-"
            })
        
        import pandas as pd
        st.dataframe(pd.DataFrame(device_rows), use_container_width=True, hide_index=True)
        
        # 冗長グループ一覧
        if st.session_state.redundancy_groups:
            st.markdown("**🔷 冗長グループ一覧**")
            group_rows = []
            for gid, g in st.session_state.redundancy_groups.items():
                group_rows.append({
                    "グループ名": gid,
                    "タイプ": g["type"],
                    "メンバー": ", ".join(g["members"])
                })
            st.dataframe(pd.DataFrame(group_rows), use_container_width=True, hide_index=True)
    
    with tab2:
        st.json(output_data)
    
    st.divider()
    
    # エクスポート
    col1, col2 = st.columns(2)
    
    with col1:
        # JSONダウンロード
        json_str = json.dumps(output_data, ensure_ascii=False, indent=2)
        st.download_button(
            "📥 JSONをダウンロード",
            json_str,
            "topology.json",
            "application/json",
            use_container_width=True
        )
    
    with col2:
        # 保存して適用
        if st.button("💾 保存して次のステップへ", type="primary", use_container_width=True):
            # dataディレクトリに保存
            os.makedirs(DATA_DIR, exist_ok=True)
            
            # topology.json（後方互換形式）
            with open(os.path.join(DATA_DIR, "topology.json"), "w", encoding="utf-8") as f:
                json.dump(topology_json, f, ensure_ascii=False, indent=2)
            
            # full_topology.json（完全版）
            with open(os.path.join(DATA_DIR, "full_topology.json"), "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            st.success("✅ トポロジーデータを保存しました")
            st.info("👉 次は「監視設定生成」ページでZabbix設定を生成してください")

# ==================== メイン ====================
def main():
    init_session_state()
    
    # ヘッダー
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🔧 トポロジービルダー")
        st.caption("ウィザード形式でネットワークトポロジーを作成")
    with col2:
        if st.button("🏠 ホームに戻る"):
            st.switch_page("Home.py")
    
    st.divider()
    
    # ステッププログレス
    render_step_progress(st.session_state.wizard_step)
    
    st.divider()
    
    # 現在のステップを表示
    if st.session_state.wizard_step == 1:
        render_step1_devices()
    elif st.session_state.wizard_step == 2:
        render_step2_layers()
    elif st.session_state.wizard_step == 3:
        render_step3_connections()
    elif st.session_state.wizard_step == 4:
        render_step4_redundancy()
    elif st.session_state.wizard_step == 5:
        render_step5_export()
    
    # ナビゲーションボタン
    st.divider()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if st.session_state.wizard_step > 1:
            if st.button("← 戻る", use_container_width=True):
                st.session_state.wizard_step -= 1
                st.rerun()
    
    with col2:
        # 進捗インジケーター
        st.progress(st.session_state.wizard_step / 5)
        st.caption(f"Step {st.session_state.wizard_step} / 5")
    
    with col3:
        if st.session_state.wizard_step < 5:
            # 次へ進むための条件チェック
            can_proceed = True
            if st.session_state.wizard_step == 1 and not st.session_state.devices:
                can_proceed = False
            elif st.session_state.wizard_step == 2:
                unassigned = [k for k, v in st.session_state.devices.items() if v.get("layer") is None]
                if unassigned:
                    can_proceed = False
            
            if st.button("次へ →", use_container_width=True, disabled=not can_proceed, type="primary"):
                st.session_state.wizard_step += 1
                st.rerun()
            
            if not can_proceed:
                if st.session_state.wizard_step == 1:
                    st.caption("⚠️ デバイスを追加してください")
                elif st.session_state.wizard_step == 2:
                    st.caption("⚠️ 全デバイスにレイヤーを設定してください")

if __name__ == "__main__":
    main()
