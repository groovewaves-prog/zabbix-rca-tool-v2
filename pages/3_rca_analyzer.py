"""
Zabbix RCA Tool - 根本原因分析
大量アラートから真因を特定
"""

import streamlit as st
import json
import os
import sys
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass

# inference_engine.pyをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
try:
    from inference_engine import LogicalRCA as AdvancedRCA
    HAS_ADVANCED_RCA = True
except ImportError:
    HAS_ADVANCED_RCA = False

# ==================== ページ設定 ====================
st.set_page_config(
    page_title="根本原因分析 - Zabbix RCA Tool",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== カスタムCSS ====================
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* KPIカード */
    .kpi-card {
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        color: white;
        margin: 5px;
    }
    .kpi-noise {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    .kpi-processed {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
    }
    .kpi-action {
        background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
    }
    .kpi-action-ok {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
    }
    .kpi-number {
        font-size: 2.5em;
        font-weight: bold;
        margin: 10px 0;
    }
    .kpi-label {
        font-size: 0.9em;
        opacity: 0.9;
    }
    .kpi-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        background: rgba(255,255,255,0.2);
        font-size: 0.8em;
        margin-top: 8px;
    }
    
    /* 分析結果カード */
    .result-card {
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        border-left: 4px solid;
    }
    .tier1-card {
        background: #ffebee;
        border-color: #f44336;
    }
    .tier2-card {
        background: #fff8e1;
        border-color: #ff9800;
    }
    .tier3-card {
        background: #e8f5e9;
        border-color: #4caf50;
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

# ==================== データクラス ====================
@dataclass
class Alert:
    device_id: str
    message: str
    timestamp: str = ""
    severity: str = "warning"

@dataclass
class AnalysisResult:
    device_id: str
    tier: int  # 1=真因候補, 2=要注意, 3=症状/波及
    confidence: float
    reason: str
    related_alerts: List[str]

# ==================== データディレクトリ ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

def load_topology():
    """トポロジーデータを読み込む"""
    topology_path = os.path.join(DATA_DIR, "topology.json")
    if os.path.exists(topology_path):
        with open(topology_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def load_alerts():
    """アラートデータを読み込む"""
    alerts_path = os.path.join(DATA_DIR, "alerts.json")
    if os.path.exists(alerts_path):
        with open(alerts_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"alerts": []}

def load_full_topology():
    """完全版トポロジーを読み込む"""
    full_path = os.path.join(DATA_DIR, "full_topology.json")
    if os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# ==================== RCAエンジン ====================
class LogicalRCA:
    """トポロジーベースの根本原因分析エンジン"""
    
    def __init__(self, topology: Dict, redundancy_groups: Dict = None):
        self.topology = topology
        self.redundancy_groups = redundancy_groups or {}
        self.device_children = self._build_children_map()
    
    def _build_children_map(self) -> Dict[str, List[str]]:
        """親→子のマッピングを構築"""
        children = {}
        for device_id, device in self.topology.items():
            # parent_id（単一）
            parent_id = device.get("parent_id")
            if parent_id:
                if parent_id not in children:
                    children[parent_id] = []
                if device_id not in children[parent_id]:
                    children[parent_id].append(device_id)
            
            # parent_ids（複数）
            for pid in device.get("parent_ids", []):
                if pid not in children:
                    children[pid] = []
                if device_id not in children[pid]:
                    children[pid].append(device_id)
        
        return children
    
    def _get_all_descendants(self, device_id: str) -> List[str]:
        """指定デバイスの全子孫を取得"""
        descendants = []
        queue = [device_id]
        while queue:
            current = queue.pop(0)
            children = self.device_children.get(current, [])
            descendants.extend(children)
            queue.extend(children)
        return descendants
    
    def _get_redundancy_group_members(self, device_id: str) -> List[str]:
        """デバイスが属する冗長グループのメンバーを取得"""
        for group_id, group in self.redundancy_groups.items():
            if device_id in group.get("members", []):
                return [m for m in group["members"] if m != device_id]
        return []
    
    def analyze(self, alerts: List[Alert]) -> List[AnalysisResult]:
        """アラートを分析して根本原因を特定"""
        results = []
        alert_devices = set(a.device_id for a in alerts)
        alert_messages = {a.device_id: a.message for a in alerts}
        
        analyzed_devices = set()
        
        for alert in alerts:
            device_id = alert.device_id
            if device_id in analyzed_devices:
                continue
            
            device = self.topology.get(device_id, {})
            
            # 1. サイレント障害検出（子がアラートで親が無アラート）
            parent_id = device.get("parent_id")
            parent_ids = device.get("parent_ids", [])
            all_parents = set([parent_id] if parent_id else []) | set(parent_ids)
            
            for pid in all_parents:
                if pid and pid not in alert_devices:
                    descendants = self._get_all_descendants(pid)
                    affected_descendants = [d for d in descendants if d in alert_devices]
                    
                    if len(affected_descendants) >= 2 and pid not in analyzed_devices:
                        results.append(AnalysisResult(
                            device_id=pid,
                            tier=1,
                            confidence=0.85,
                            reason=f"サイレント障害の可能性: {len(affected_descendants)}台の子デバイスでアラート発生、親デバイスはアラートなし",
                            related_alerts=[alert_messages.get(d, "") for d in affected_descendants[:5]]
                        ))
                        analyzed_devices.add(pid)
                        analyzed_devices.update(affected_descendants)
            
            if device_id in analyzed_devices:
                continue
            
            # 2. カスケード抑制（上流でアラートあり）
            upstream_alert = False
            for pid in all_parents:
                if pid and pid in alert_devices:
                    results.append(AnalysisResult(
                        device_id=device_id,
                        tier=3,
                        confidence=0.90,
                        reason=f"上流デバイス {pid} の障害による波及の可能性",
                        related_alerts=[alert_messages.get(pid, "")]
                    ))
                    analyzed_devices.add(device_id)
                    upstream_alert = True
                    break
            
            if upstream_alert:
                continue
            
            # 3. 冗長グループ考慮
            redundancy_members = self._get_redundancy_group_members(device_id)
            if redundancy_members:
                members_with_alerts = [m for m in redundancy_members if m in alert_devices]
                if members_with_alerts:
                    # 冗長ペアの両方でアラート → 共通原因の可能性
                    results.append(AnalysisResult(
                        device_id=device_id,
                        tier=1,
                        confidence=0.80,
                        reason=f"冗長グループ内の複数デバイス ({', '.join([device_id] + members_with_alerts)}) でアラート発生 - 共通原因の可能性",
                        related_alerts=[alert.message] + [alert_messages.get(m, "") for m in members_with_alerts]
                    ))
                    analyzed_devices.add(device_id)
                    analyzed_devices.update(members_with_alerts)
                    continue
                else:
                    # 冗長ペアの片方のみ → 冗長性により保護
                    results.append(AnalysisResult(
                        device_id=device_id,
                        tier=2,
                        confidence=0.70,
                        reason=f"冗長グループのパートナー ({', '.join(redundancy_members)}) は正常 - 冗長性により保護",
                        related_alerts=[alert.message]
                    ))
                    analyzed_devices.add(device_id)
                    continue
            
            # 4. ハードウェア障害判定（PSU/電源関連）
            hw_inventory = device.get("metadata", {}).get("hw_inventory", {})
            psu_count = hw_inventory.get("psu_count", 1)
            
            if "PSU" in alert.message or "Power" in alert.message:
                if psu_count >= 2:
                    if "Both" in alert.message or "Dual" in alert.message or "All" in alert.message:
                        results.append(AnalysisResult(
                            device_id=device_id,
                            tier=1,
                            confidence=0.95,
                            reason="Dual PSU Loss: 冗長電源が両方故障",
                            related_alerts=[alert.message]
                        ))
                    else:
                        results.append(AnalysisResult(
                            device_id=device_id,
                            tier=2,
                            confidence=0.70,
                            reason=f"Single PSU故障: 冗長性あり（{psu_count}台中1台）",
                            related_alerts=[alert.message]
                        ))
                else:
                    results.append(AnalysisResult(
                        device_id=device_id,
                        tier=1,
                        confidence=0.90,
                        reason="電源障害: 冗長性なし",
                        related_alerts=[alert.message]
                    ))
                analyzed_devices.add(device_id)
                continue
            
            # 5. 単独アラート
            layer = device.get("layer", 99)
            if layer <= 2:
                tier = 1
                confidence = 0.75
                reason = f"Layer{layer}のコアデバイスでアラート発生"
            else:
                tier = 2
                confidence = 0.60
                reason = "単独アラート"
            
            results.append(AnalysisResult(
                device_id=device_id,
                tier=tier,
                confidence=confidence,
                reason=reason,
                related_alerts=[alert.message]
            ))
            analyzed_devices.add(device_id)
        
        # ティアと信頼度でソート
        results.sort(key=lambda x: (x.tier, -x.confidence))
        
        return results

# ==================== KPIカード表示 ====================
def render_kpi_cards(total_alerts: int, tier1_count: int, tier3_count: int):
    """KPIカードを表示"""
    
    if total_alerts > 0:
        noise_reduction = ((total_alerts - tier1_count) / total_alerts) * 100
    else:
        noise_reduction = 0
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="kpi-card kpi-noise">
            <div class="kpi-label">ノイズ削減率</div>
            <div class="kpi-number">{noise_reduction:.1f}%</div>
            <div class="kpi-badge">アラート集約効果</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="kpi-card kpi-processed">
            <div class="kpi-label">抑制済みアラート</div>
            <div class="kpi-number">{tier3_count}</div>
            <div class="kpi-badge">波及・症状として分類</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        card_class = "kpi-action-ok" if tier1_count == 0 else "kpi-action"
        badge_text = "✓ 対処不要" if tier1_count == 0 else "要対応"
        st.markdown(f"""
        <div class="kpi-card {card_class}">
            <div class="kpi-label">真因候補</div>
            <div class="kpi-number">{tier1_count}</div>
            <div class="kpi-badge">{badge_text}</div>
        </div>
        """, unsafe_allow_html=True)

# ==================== 分析結果表示 ====================
def render_analysis_results(results: List[AnalysisResult]):
    """分析結果をティア別に表示"""
    
    tier_labels = {
        1: ("🔴 Tier 1: 真因候補（要対応）", "tier1-card"),
        2: ("🟡 Tier 2: 要注意", "tier2-card"),
        3: ("🟢 Tier 3: 症状/波及（抑制済み）", "tier3-card"),
    }
    
    for tier in [1, 2, 3]:
        tier_results = [r for r in results if r.tier == tier]
        if not tier_results:
            continue
        
        label, card_class = tier_labels[tier]
        st.subheader(f"{label} ({len(tier_results)}件)")
        
        for result in tier_results:
            st.markdown(f"""
            <div class="result-card {card_class}">
                <strong>{result.device_id}</strong>
                <span style="float:right; color:#666;">信頼度: {result.confidence*100:.0f}%</span>
                <br><small>{result.reason}</small>
            </div>
            """, unsafe_allow_html=True)
            
            if tier == 1:
                with st.expander(f"📋 {result.device_id} の詳細レポート"):
                    st.write(f"**デバイス:** {result.device_id}")
                    st.write(f"**分析結果:** {result.reason}")
                    st.write(f"**信頼度:** {result.confidence*100:.0f}%")
                    st.write("**関連アラート:**")
                    for alert_msg in result.related_alerts:
                        st.write(f"- {alert_msg}")

# ==================== サンプルアラート生成 ====================
def generate_sample_alerts(topology: Dict) -> List[Dict]:
    """トポロジーに基づいてサンプルアラートを生成"""
    alerts = []
    
    # Layer 2 のデバイスを真因として設定
    layer2_devices = [k for k, v in topology.items() if v.get("layer") == 2]
    
    if layer2_devices:
        root_cause = layer2_devices[0]
        alerts.append({
            "device_id": root_cause,
            "message": "ICMP Unreachable - No response",
            "severity": "high",
            "timestamp": datetime.now().isoformat()
        })
        
        # その下流デバイスにも波及アラートを追加
        for dev_id, dev in topology.items():
            parent_ids = [dev.get("parent_id")] + dev.get("parent_ids", [])
            if root_cause in parent_ids:
                alerts.append({
                    "device_id": dev_id,
                    "message": "Connection timeout to upstream device",
                    "severity": "warning",
                    "timestamp": datetime.now().isoformat()
                })
    
    # PSU障害のサンプル
    for dev_id, dev in topology.items():
        psu_count = dev.get("metadata", {}).get("hw_inventory", {}).get("psu_count", 0)
        if psu_count >= 2:
            alerts.append({
                "device_id": dev_id,
                "message": "PSU-1 failure detected",
                "severity": "warning",
                "timestamp": datetime.now().isoformat()
            })
            break
    
    return alerts

# ==================== メイン ====================
def main():
    # ヘッダー
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🎯 根本原因分析")
        st.caption("大量アラートから真因を特定")
    with col2:
        if st.button("🏠 ホームに戻る"):
            st.switch_page("Home.py")
    
    st.divider()
    
    # トポロジー読み込み
    topology = load_topology()
    full_topology = load_full_topology()
    alerts_data = load_alerts()
    
    if not topology:
        st.warning("⚠️ トポロジーデータがありません")
        st.info("👉 トポロジービルダーでトポロジーを作成してください")
        
        if st.button("🔧 トポロジービルダーを開く", type="primary"):
            st.switch_page("pages/1_topology_builder.py")
        return
    
    # トポロジー情報
    st.markdown(f"📍 **読み込み済みトポロジー:** {len(topology)}台のデバイス")
    
    st.divider()
    
    # アラートデータソース選択
    st.subheader("📥 アラートデータ入力")
    
    st.markdown("""
    <div class="hint-box">
        💡 <strong>ヒント:</strong> アラートデータを入力すると、トポロジー情報に基づいて根本原因を分析します。
    </div>
    """, unsafe_allow_html=True)
    
    alert_source = st.radio(
        "データソースを選択",
        ["📂 サンプルデータを生成", "📤 JSONをアップロード", "✍️ 手動入力"],
        horizontal=True
    )
    
    alerts_to_analyze = []
    
    if alert_source == "📂 サンプルデータを生成":
        if st.button("🔄 サンプルアラートを生成"):
            sample_alerts = generate_sample_alerts(topology)
            st.session_state.sample_alerts = sample_alerts
        
        if "sample_alerts" in st.session_state:
            sample_alerts = st.session_state.sample_alerts
            st.info(f"📊 {len(sample_alerts)}件のサンプルアラートを生成しました")
            
            with st.expander("サンプルアラート一覧"):
                for a in sample_alerts:
                    st.markdown(f"- **{a['device_id']}**: {a['message']} ({a['severity']})")
            
            for a in sample_alerts:
                alerts_to_analyze.append(Alert(
                    device_id=a["device_id"],
                    message=a["message"],
                    timestamp=a.get("timestamp", ""),
                    severity=a.get("severity", "warning")
                ))
    
    elif alert_source == "📤 JSONをアップロード":
        uploaded_file = st.file_uploader("アラートJSON", type=["json"])
        
        if uploaded_file:
            try:
                data = json.load(uploaded_file)
                alert_list = data.get("alerts", data) if isinstance(data, dict) else data
                
                for a in alert_list:
                    alerts_to_analyze.append(Alert(
                        device_id=a["device_id"],
                        message=a["message"],
                        timestamp=a.get("timestamp", ""),
                        severity=a.get("severity", "warning")
                    ))
                st.info(f"📊 {len(alerts_to_analyze)}件のアラートを読み込みました")
            except Exception as e:
                st.error(f"読み込みエラー: {e}")
        
        # サンプルJSON形式
        with st.expander("📝 JSON形式のサンプル"):
            st.code("""
{
  "alerts": [
    {
      "device_id": "CORE_SW_01",
      "message": "ICMP Unreachable",
      "severity": "high",
      "timestamp": "2024-01-15T10:30:00"
    },
    {
      "device_id": "L2_SW_01",
      "message": "Connection timeout",
      "severity": "warning"
    }
  ]
}
            """, language="json")
    
    else:  # 手動入力
        st.markdown("**アラートを入力（1行に1件）**")
        st.caption("形式: デバイスID, メッセージ, 重要度(optional)")
        
        manual_input = st.text_area(
            "アラート入力",
            placeholder="CORE_SW_01, ICMP Unreachable, high\nL2_SW_01, High Latency\nAP_01, Connection Lost",
            height=150,
            label_visibility="collapsed"
        )
        
        if manual_input:
            for line in manual_input.strip().split("\n"):
                if "," in line:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        alerts_to_analyze.append(Alert(
                            device_id=parts[0],
                            message=parts[1],
                            severity=parts[2] if len(parts) > 2 else "warning"
                        ))
            
            if alerts_to_analyze:
                st.info(f"📊 {len(alerts_to_analyze)}件のアラートを入力")
    
    st.divider()
    
    # 分析実行
    if alerts_to_analyze:
        # エンジン選択
        col1, col2 = st.columns([2, 1])
        with col1:
            if HAS_ADVANCED_RCA:
                engine_option = st.radio(
                    "分析エンジン",
                    ["🚀 高度な分析（inference_engine）", "⚡ 簡易分析"],
                    horizontal=True,
                    help="高度な分析はサイレント障害検出、AI分析機能を含みます"
                )
                use_advanced = "高度" in engine_option
            else:
                st.info("💡 inference_engine.py が見つかりません。簡易分析を使用します。")
                use_advanced = False
        
        if st.button("🔍 根本原因を分析", type="primary", use_container_width=True):
            with st.spinner("分析中..."):
                # 冗長グループ情報を取得
                redundancy_groups = {}
                if full_topology:
                    redundancy_groups = full_topology.get("redundancy_groups", {})
                
                if use_advanced and HAS_ADVANCED_RCA:
                    # inference_engine.pyのLogicalRCAを使用
                    advanced_rca = AdvancedRCA(topology)
                    
                    # アラートを変換
                    alarm_list = []
                    for a in alerts_to_analyze:
                        alarm_list.append({
                            "device": a.device_id,
                            "message": a.message,
                            "severity": a.severity,
                            "timestamp": a.timestamp
                        })
                    
                    # 分析実行
                    advanced_results = advanced_rca.analyze(alarm_list)
                    
                    # 結果をAnalysisResultに変換
                    results = []
                    for r in advanced_results:
                        # tierの判定
                        status = r.get("status", "YELLOW")
                        if status == "RED":
                            tier = 1
                        elif status == "YELLOW":
                            tier = 2
                        else:
                            tier = 3
                        
                        results.append(AnalysisResult(
                            device_id=r.get("device", "unknown"),
                            tier=tier,
                            confidence=0.85 if status == "RED" else 0.70 if status == "YELLOW" else 0.90,
                            reason=r.get("reason", ""),
                            related_alerts=[r.get("original_alert", "")]
                        ))
                else:
                    # 簡易版LogicalRCAを使用
                    rca = LogicalRCA(topology, redundancy_groups)
                    results = rca.analyze(alerts_to_analyze)
                
                st.session_state.rca_results = results
                st.session_state.rca_total_alerts = len(alerts_to_analyze)
    
    # 分析結果表示
    if "rca_results" in st.session_state:
        results = st.session_state.rca_results
        total_alerts = st.session_state.rca_total_alerts
        
        tier1_count = len([r for r in results if r.tier == 1])
        tier2_count = len([r for r in results if r.tier == 2])
        tier3_count = len([r for r in results if r.tier == 3])
        
        st.divider()
        st.subheader("📊 分析結果")
        
        # KPIカード
        render_kpi_cards(total_alerts, tier1_count, tier3_count)
        
        st.divider()
        
        # 分析サマリー
        st.markdown(f"""
        **📈 分析サマリー**
        - 入力アラート数: {total_alerts}件
        - 分析結果: {len(results)}件のインシデント
        - 真因候補 (Tier 1): {tier1_count}件
        - 要注意 (Tier 2): {tier2_count}件
        - 抑制済み (Tier 3): {tier3_count}件
        """)
        
        st.divider()
        
        # ティア別結果
        render_analysis_results(results)
        
        # レポートダウンロード
        st.divider()
        
        report_data = {
            "analysis_time": datetime.now().isoformat(),
            "input_alerts": total_alerts,
            "results": [
                {
                    "device_id": r.device_id,
                    "tier": r.tier,
                    "confidence": r.confidence,
                    "reason": r.reason,
                    "related_alerts": r.related_alerts
                }
                for r in results
            ],
            "summary": {
                "tier1_count": tier1_count,
                "tier2_count": tier2_count,
                "tier3_count": tier3_count,
                "noise_reduction": ((total_alerts - tier1_count) / total_alerts * 100) if total_alerts > 0 else 0
            }
        }
        
        st.download_button(
            "📥 分析レポートをダウンロード",
            json.dumps(report_data, ensure_ascii=False, indent=2),
            "rca_report.json",
            "application/json",
            use_container_width=True
        )

if __name__ == "__main__":
    main()
