"""
Zabbix RCA Tool - トポロジービルダー v2
グリッドベースのビジュアル配置 + 拡張可能なモジュール/冗長グループ
"""

import streamlit as st
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

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
    
    /* デバイスカード（グリッド内） */
    .device-node {
        padding: 12px 15px;
        border-radius: 10px;
        text-align: center;
        font-size: 0.85em;
        min-width: 110px;
        margin: 5px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    .device-router { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
    .device-switch { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; }
    .device-firewall { background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%); color: white; }
    .device-server { background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%); color: white; }
    .device-ap { background: linear-gradient(135deg, #f7971e 0%, #ffd200 100%); color: #333; }
    .device-storage { background: linear-gradient(135deg, #834d9b 0%, #d04ed6 100%); color: white; }
    .device-lb { background: linear-gradient(135deg, #4776E6 0%, #8E54E9 100%); color: white; }
    .device-default { background: #6c757d; color: white; }
    
    /* レイヤーラベル */
    .layer-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 8px 15px;
        border-radius: 8px;
        font-weight: bold;
        margin-bottom: 10px;
    }
    
    /* 接続線 */
    .connection-line {
        text-align: center;
        color: #adb5bd;
        font-size: 1.2em;
        padding: 5px 0;
    }
    
    /* ヒントボックス */
    .hint-box {
        padding: 15px;
        background: #e7f3ff;
        border-left: 4px solid #2196f3;
        border-radius: 0 8px 8px 0;
        margin: 15px 0;
    }
    
    /* 空セル */
    .empty-cell {
        border: 2px dashed #dee2e6;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
        color: #adb5bd;
        margin: 5px;
    }
</style>
""", unsafe_allow_html=True)

# ==================== 定数 ====================
DEVICE_TYPES = {
    "ROUTER": {"icon": "🔵", "color": "router", "label": "ルーター"},
    "SWITCH": {"icon": "🟢", "color": "switch", "label": "スイッチ"},
    "FIREWALL": {"icon": "🔴", "color": "firewall", "label": "ファイアウォール"},
    "SERVER": {"icon": "🔷", "color": "server", "label": "サーバー"},
    "ACCESS_POINT": {"icon": "📡", "color": "ap", "label": "アクセスポイント"},
    "LOAD_BALANCER": {"icon": "⚖️", "color": "lb", "label": "ロードバランサー"},
    "STORAGE": {"icon": "💾", "color": "storage", "label": "ストレージ"},
}

VENDORS = ["Cisco", "Juniper", "Fortinet", "Palo Alto", "Arista", "HPE", "Dell", "NetApp", "F5", "Other"]

# 拡張可能なモジュールタイプ
DEFAULT_MODULE_TYPES = {
    "PSU": {"label": "電源モジュール", "icon": "⚡", "description": "電源ユニット（冗長化推奨）"},
    "FAN": {"label": "ファンモジュール", "icon": "🌀", "description": "冷却ファン"},
    "SUPERVISOR": {"label": "スーパバイザ", "icon": "🧠", "description": "シャーシ型スイッチの制御モジュール（Cisco SUP等）"},
    "LINECARD": {"label": "ラインカード", "icon": "🔌", "description": "インターフェースモジュール"},
    "CONTROLLER": {"label": "コントローラ", "icon": "🎛️", "description": "ストレージコントローラ/WLCコントローラ"},
    "OPTICS": {"label": "光モジュール", "icon": "💡", "description": "SFP/QSFP等のトランシーバ"},
    "MEMORY": {"label": "メモリ", "icon": "🧩", "description": "RAM/DIMM"},
    "CPU": {"label": "CPU", "icon": "🔲", "description": "プロセッサ"},
    "DISK": {"label": "ディスク", "icon": "💿", "description": "HDD/SSD"},
}

# 冗長グループタイプ
REDUNDANCY_TYPES = {
    "physical": {
        "Active-Standby": "1台がアクティブ、他がスタンバイ",
        "Active-Active": "全台がアクティブで負荷分散",
        "Stack": "スタック構成（VSS, StackWise等）",
        "Cluster": "クラスタ構成",
    },
    "logical": {
        "VRRP/HSRP": "仮想IPによるゲートウェイ冗長",
        "RAG": "Redundancy Group（ファイアウォール等）",
        "VLAN": "VLAN冗長（STP/vPC/MLAG）",
        "LACP": "リンクアグリゲーション",
        "ECMP": "等コストマルチパス",
    }
}

LAYER_NAMES = {
    1: "WAN/Internet Edge",
    2: "Core",
    3: "Distribution",
    4: "Access",
    5: "Endpoint",
}

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ==================== セッション状態初期化 ====================
def init_session_state():
    if "devices" not in st.session_state:
        st.session_state.devices = {}
    if "redundancy_groups" not in st.session_state:
        st.session_state.redundancy_groups = {}
    if "custom_module_types" not in st.session_state:
        st.session_state.custom_module_types = {}

def get_device_style(device_type: str) -> dict:
    return DEVICE_TYPES.get(device_type, {"icon": "⬜", "color": "default", "label": device_type})

# ==================== グリッドビジュアライザ ====================
def render_topology_grid():
    """グリッドベースのトポロジー表示"""
    
    if not st.session_state.devices:
        st.info("📍 デバイスがありません。「➕ デバイス追加」タブから追加してください。")
        return
    
    # レイヤー別にデバイスをグループ化
    layers = {1: [], 2: [], 3: [], 4: [], 5: []}
    for dev_id, dev in st.session_state.devices.items():
        layer = dev.get("layer", 5)
        if layer in layers:
            layers[layer].append((dev_id, dev))
    
    # グリッド表示
    for layer_num in [1, 2, 3, 4, 5]:
        layer_devices = layers[layer_num]
        
        # 空レイヤーはスキップ（ただし上下にデバイスがある場合は表示）
        has_upper = any(layers[l] for l in range(1, layer_num))
        has_lower = any(layers[l] for l in range(layer_num + 1, 6))
        
        if not layer_devices and not (has_upper and has_lower):
            continue
        
        # レイヤーヘッダー
        st.markdown(f"""
        <div class="layer-header">
            📍 Layer {layer_num}: {LAYER_NAMES.get(layer_num, '')}
            <span style="float: right; font-weight: normal; opacity: 0.8;">
                {len(layer_devices)}台
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        if layer_devices:
            # デバイスをグリッド表示
            cols = st.columns(min(len(layer_devices), 6))
            
            for idx, (dev_id, dev) in enumerate(layer_devices):
                col_idx = idx % 6
                style = get_device_style(dev["type"])
                
                # 冗長グループ情報
                rg_info = ""
                for rg_id, rg in st.session_state.redundancy_groups.items():
                    if dev_id in rg.get("members", []):
                        rg_type = "🔧" if rg.get("type") == "physical" else "🌐"
                        rg_info = f"<div style='font-size:0.65em; opacity:0.85; margin-top:4px;'>{rg_type} {rg_id}</div>"
                        break
                
                # モジュール情報
                modules = dev.get("modules", [])
                mod_info = ""
                if modules:
                    mod_counts = {}
                    for m in modules:
                        t = m.get("type", "?")
                        mod_counts[t] = mod_counts.get(t, 0) + 1
                    mod_str = " ".join([f"{t}:{c}" for t, c in list(mod_counts.items())[:3]])
                    mod_info = f"<div style='font-size:0.6em; opacity:0.75; margin-top:2px;'>{mod_str}</div>"
                
                # 接続先
                parents = dev.get("parent_ids", [])
                conn_info = ""
                if parents:
                    conn_info = f"<div style='font-size:0.6em; opacity:0.75;'>↑ {', '.join(parents[:2])}</div>"
                
                with cols[col_idx]:
                    st.markdown(f"""
                    <div class="device-node device-{style['color']}">
                        <div style="font-size: 1.8em;">{style['icon']}</div>
                        <div style="font-weight: bold; margin: 4px 0;">{dev_id}</div>
                        <div style="font-size: 0.75em; opacity: 0.9;">{dev.get('metadata', {}).get('vendor', '') or ''}</div>
                        {conn_info}
                        {rg_info}
                        {mod_info}
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-cell">（このレイヤーにデバイスなし）</div>
            """, unsafe_allow_html=True)
        
        # 接続線（下にデバイスがある場合）
        if has_lower or any(layers[l] for l in range(layer_num + 1, 6)):
            st.markdown('<div class="connection-line">│<br>▼</div>', unsafe_allow_html=True)

# ==================== デバイス追加フォーム ====================
def render_device_form():
    """デバイス追加フォーム"""
    
    st.markdown("""
    <div class="hint-box">
        💡 <strong>ヒント:</strong> デバイスID は一意である必要があります（例: CORE_SW_01）
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("add_device_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            device_id = st.text_input(
                "デバイスID *",
                placeholder="例: CORE_SW_01",
                help="一意のID（英数字とアンダースコア）"
            )
            device_type = st.selectbox(
                "デバイスタイプ *",
                list(DEVICE_TYPES.keys()),
                format_func=lambda x: f"{DEVICE_TYPES[x]['icon']} {DEVICE_TYPES[x]['label']}"
            )
        
        with col2:
            vendor = st.selectbox("ベンダー", [""] + VENDORS)
            model = st.text_input("モデル", placeholder="例: C9500-24Y4C")
        
        with col3:
            layer = st.selectbox(
                "レイヤー *",
                [1, 2, 3, 4, 5],
                index=1,
                format_func=lambda x: f"Layer {x}: {LAYER_NAMES.get(x, '')}"
            )
            location = st.text_input("ロケーション", placeholder="例: DC1-Rack01")
        
        # 上位接続先
        st.markdown("**🔗 接続先（上位デバイス）**")
        upper_devices = [
            f"{d_id} (L{d['layer']})" 
            for d_id, d in st.session_state.devices.items()
            if d.get("layer", 5) < layer
        ]
        
        if upper_devices:
            selected_parents = st.multiselect(
                "上位デバイスを選択（複数選択でマルチパス）",
                upper_devices,
                help="このデバイスが接続する上位デバイス"
            )
            parent_ids = [p.split(" (L")[0] for p in selected_parents]
        else:
            parent_ids = []
            st.caption("（上位レイヤーにデバイスがないため、接続先は設定できません）")
        
        # モジュール構成
        st.markdown("**📦 モジュール構成**")
        
        all_modules = {**DEFAULT_MODULE_TYPES, **st.session_state.custom_module_types}
        module_inputs = {}
        
        mod_cols = st.columns(5)
        for idx, (mod_type, mod_info) in enumerate(list(all_modules.items())[:10]):
            with mod_cols[idx % 5]:
                count = st.number_input(
                    f"{mod_info['icon']} {mod_info['label'][:6]}",
                    min_value=0, max_value=16, value=0,
                    key=f"mod_{mod_type}",
                    help=mod_info.get("description", "")
                )
                module_inputs[mod_type] = count
        
        submitted = st.form_submit_button("➕ デバイスを追加", type="primary", use_container_width=True)
        
        if submitted:
            if not device_id:
                st.error("❌ デバイスIDは必須です")
            elif not device_id.replace("_", "").replace("-", "").isalnum():
                st.error("❌ デバイスIDは英数字、アンダースコア、ハイフンのみ")
            elif device_id in st.session_state.devices:
                st.error(f"❌ デバイスID '{device_id}' は既に存在します")
            else:
                # モジュールリスト構築
                modules = []
                for mod_type, count in module_inputs.items():
                    for i in range(count):
                        modules.append({
                            "type": mod_type,
                            "id": f"{mod_type}-{i+1}",
                            "status": "OK"
                        })
                
                st.session_state.devices[device_id] = {
                    "type": device_type,
                    "layer": layer,
                    "parent_ids": parent_ids,
                    "metadata": {
                        "vendor": vendor if vendor else None,
                        "model": model if model else None,
                        "location": location if location else None,
                    },
                    "modules": modules,
                }
                st.success(f"✅ デバイス '{device_id}' を追加しました")
                st.rerun()

# ==================== デバイス一覧 ====================
def render_device_list():
    """デバイス一覧と編集/削除"""
    
    if not st.session_state.devices:
        st.info("デバイスがありません")
        return
    
    st.markdown(f"**登録済み: {len(st.session_state.devices)}台**")
    
    # レイヤー別に表示
    for layer in [1, 2, 3, 4, 5]:
        layer_devices = [(d_id, d) for d_id, d in st.session_state.devices.items() if d.get("layer") == layer]
        
        if not layer_devices:
            continue
        
        st.markdown(f"**Layer {layer}: {LAYER_NAMES.get(layer, '')}** ({len(layer_devices)}台)")
        
        for dev_id, dev in layer_devices:
            style = get_device_style(dev["type"])
            
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                st.markdown(f"{style['icon']} **{dev_id}** ({dev['type']})")
            
            with col2:
                vendor = dev.get('metadata', {}).get('vendor', '-')
                model = dev.get('metadata', {}).get('model', '')
                st.caption(f"{vendor} {model}")
            
            with col3:
                # レイヤー変更
                new_layer = st.selectbox(
                    "Layer",
                    [1, 2, 3, 4, 5],
                    index=layer - 1,
                    key=f"layer_{dev_id}",
                    label_visibility="collapsed"
                )
                if new_layer != layer:
                    st.session_state.devices[dev_id]["layer"] = new_layer
                    st.rerun()
            
            with col4:
                if st.button("🗑️", key=f"del_{dev_id}"):
                    del st.session_state.devices[dev_id]
                    # 冗長グループからも削除
                    for rg_id in list(st.session_state.redundancy_groups.keys()):
                        rg = st.session_state.redundancy_groups[rg_id]
                        if dev_id in rg.get("members", []):
                            rg["members"].remove(dev_id)
                            if len(rg["members"]) < 2:
                                del st.session_state.redundancy_groups[rg_id]
                    st.rerun()
        
        st.markdown("---")

# ==================== カスタムモジュール ====================
def render_custom_modules():
    """カスタムモジュールタイプ管理"""
    
    st.markdown("### ⚙️ カスタムモジュールタイプ")
    st.caption("標準モジュール以外に独自のモジュールタイプを追加できます")
    
    # 標準モジュール一覧
    with st.expander("📋 標準モジュールタイプ一覧"):
        for key, info in DEFAULT_MODULE_TYPES.items():
            st.markdown(f"**{info['icon']} {key}**: {info['label']} - {info['description']}")
    
    # カスタム追加
    with st.form("add_module_type"):
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            mod_key = st.text_input("キー", placeholder="NIC")
        with col2:
            mod_label = st.text_input("表示名", placeholder="ネットワークカード")
        with col3:
            mod_icon = st.text_input("アイコン", placeholder="🔌", max_chars=2)
        
        mod_desc = st.text_input("説明", placeholder="ネットワークインターフェースカード")
        
        if st.form_submit_button("➕ 追加"):
            if mod_key and mod_label:
                st.session_state.custom_module_types[mod_key.upper()] = {
                    "label": mod_label,
                    "icon": mod_icon or "📦",
                    "description": mod_desc,
                }
                st.success(f"✅ '{mod_label}' を追加しました")
                st.rerun()
    
    # 登録済みカスタム
    if st.session_state.custom_module_types:
        st.markdown("**登録済みカスタムモジュール:**")
        for key, info in st.session_state.custom_module_types.items():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"{info['icon']} **{key}**: {info['label']}")
            with col2:
                if st.button("🗑️", key=f"del_mod_{key}"):
                    del st.session_state.custom_module_types[key]
                    st.rerun()

# ==================== 冗長グループ ====================
def render_redundancy_groups():
    """冗長グループ設定"""
    
    st.markdown("""
    <div class="hint-box">
        💡 <strong>物理冗長:</strong> HA Pair、Stack、Cluster<br>
        💡 <strong>論理冗長:</strong> VRRP/HSRP、RAG、VLAN冗長、LACP、ECMP
    </div>
    """, unsafe_allow_html=True)
    
    # 登録済み
    if st.session_state.redundancy_groups:
        st.markdown("**登録済み冗長グループ:**")
        
        for rg_id, rg in st.session_state.redundancy_groups.items():
            rg_type = rg.get("type", "physical")
            rg_subtype = rg.get("subtype", "-")
            members = rg.get("members", [])
            
            col1, col2, col3 = st.columns([3, 3, 1])
            
            with col1:
                icon = "🔧" if rg_type == "physical" else "🌐"
                st.markdown(f"{icon} **{rg_id}** ({rg_subtype})")
            with col2:
                st.caption(f"メンバー: {', '.join(members)}")
            with col3:
                if st.button("🗑️", key=f"del_rg_{rg_id}"):
                    del st.session_state.redundancy_groups[rg_id]
                    st.rerun()
        
        st.markdown("---")
    
    # 新規追加
    st.markdown("**➕ 新規グループ追加**")
    
    with st.form("add_rg"):
        col1, col2 = st.columns(2)
        
        with col1:
            group_name = st.text_input("グループ名", placeholder="CORE_HA")
            
            rg_category = st.radio(
                "カテゴリ",
                ["physical", "logical"],
                format_func=lambda x: "🔧 物理冗長" if x == "physical" else "🌐 論理冗長",
                horizontal=True
            )
            
            subtypes = REDUNDANCY_TYPES[rg_category]
            rg_subtype = st.selectbox(
                "冗長タイプ",
                list(subtypes.keys()),
                format_func=lambda x: f"{x}"
            )
            st.caption(subtypes[rg_subtype])
        
        with col2:
            members = st.multiselect(
                "メンバーデバイス（2台以上）",
                list(st.session_state.devices.keys())
            )
            
            # 追加設定
            extra_config = {}
            if rg_category == "logical":
                if rg_subtype == "VLAN":
                    extra_config["vlan_id"] = st.number_input("VLAN ID", 1, 4094, 100)
                elif rg_subtype == "VRRP/HSRP":
                    extra_config["virtual_ip"] = st.text_input("仮想IP", placeholder="192.168.1.1")
        
        if st.form_submit_button("➕ 追加", type="primary"):
            if not group_name:
                st.error("グループ名は必須です")
            elif group_name in st.session_state.redundancy_groups:
                st.error("グループ名が重複しています")
            elif len(members) < 2:
                st.error("2台以上選択してください")
            else:
                rg_data = {
                    "type": rg_category,
                    "subtype": rg_subtype,
                    "members": members,
                    **extra_config
                }
                st.session_state.redundancy_groups[group_name] = rg_data
                st.success(f"✅ '{group_name}' を追加しました")
                st.rerun()

# ==================== エクスポート ====================
def render_export():
    """JSONエクスポート"""
    
    if not st.session_state.devices:
        st.warning("エクスポートするデバイスがありません")
        return
    
    # JSON生成
    topology_json = {}
    for dev_id, dev in st.session_state.devices.items():
        parent_ids = dev.get("parent_ids", [])
        
        # hw_inventory 集計
        hw_inventory = {}
        for mod in dev.get("modules", []):
            key = f"{mod['type'].lower()}_count"
            hw_inventory[key] = hw_inventory.get(key, 0) + 1
        
        topology_json[dev_id] = {
            "type": dev["type"],
            "layer": dev.get("layer", 5),
            "parent_id": parent_ids[0] if parent_ids else None,
            "parent_ids": parent_ids,
            "metadata": {
                **dev.get("metadata", {}),
                "hw_inventory": hw_inventory,
            },
            "modules": dev.get("modules", []),
        }
    
    full_data = {
        "topology": topology_json,
        "redundancy_groups": st.session_state.redundancy_groups,
        "custom_module_types": st.session_state.custom_module_types,
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "device_count": len(topology_json),
            "version": "2.0",
        }
    }
    
    # サマリー
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("デバイス", len(topology_json))
    with col2:
        st.metric("冗長グループ", len(st.session_state.redundancy_groups))
    with col3:
        layers = set(d.get("layer", 0) for d in topology_json.values())
        st.metric("レイヤー", len(layers))
    with col4:
        total_modules = sum(len(d.get("modules", [])) for d in st.session_state.devices.values())
        st.metric("モジュール", total_modules)
    
    # プレビュー
    tab1, tab2 = st.tabs(["📊 サマリー", "📄 JSON"])
    
    with tab1:
        import pandas as pd
        rows = []
        for dev_id, dev in topology_json.items():
            rows.append({
                "ID": dev_id,
                "タイプ": dev["type"],
                "Layer": dev["layer"],
                "接続先": ", ".join(dev.get("parent_ids", [])) or "-",
                "ベンダー": dev["metadata"].get("vendor") or "-",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    
    with tab2:
        st.json(full_data)
    
    # ボタン
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            "📥 JSONダウンロード",
            json.dumps(full_data, ensure_ascii=False, indent=2),
            "topology.json",
            "application/json",
            use_container_width=True
        )
    
    with col2:
        if st.button("💾 保存して次へ", type="primary", use_container_width=True):
            os.makedirs(DATA_DIR, exist_ok=True)
            
            with open(os.path.join(DATA_DIR, "topology.json"), "w", encoding="utf-8") as f:
                json.dump(topology_json, f, ensure_ascii=False, indent=2)
            
            with open(os.path.join(DATA_DIR, "full_topology.json"), "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
            
            st.success("✅ 保存しました → 監視設定生成へ")

# ==================== メイン ====================
def main():
    init_session_state()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🔧 トポロジービルダー")
    with col2:
        if st.button("🏠 ホーム"):
            st.switch_page("Home.py")
    
    st.divider()
    
    # タブ
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🗺️ マップ",
        "➕ デバイス追加",
        "📋 デバイス一覧",
        "🔷 冗長グループ",
        "📤 エクスポート"
    ])
    
    with tab1:
        render_topology_grid()
    
    with tab2:
        render_device_form()
        st.divider()
        render_custom_modules()
    
    with tab3:
        render_device_list()
    
    with tab4:
        render_redundancy_groups()
    
    with tab5:
        render_export()

if __name__ == "__main__":
    main()
