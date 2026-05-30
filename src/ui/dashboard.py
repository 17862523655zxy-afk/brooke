"""Streamlit 仪表盘：场景选择、对话展示、评分可视化、汇总统计."""

import json
from textwrap import dedent

import os

import streamlit as st
import requests

# 服务端地址（支持环境变量配置，方便部署）
API_BASE = os.environ.get("API_BASE", "http://localhost:8080")

# 页面配置
st.set_page_config(
    page_title="外呼评测系统",
    page_icon="📞",
    layout="wide",
)

st.title("复杂外呼场景多轮对话评测系统")
st.caption("Scenario → Dialogue → Evaluation → Failure Analysis")


# ====================================================
# 侧边栏：场景配置
# ====================================================

with st.sidebar:
    st.header("场景配置")

    task_type = st.selectbox(
        "任务类型",
        ["appointment", "renewal", "info_collection"],
        format_func=lambda x: {"appointment": "预约外呼", "renewal": "续费提醒", "info_collection": "信息采集"}[x],
    )

    user_persona = st.selectbox(
        "用户画像",
        ["normal", "impatient", "hesitant", "rejecting", "angry", "silent"],
        format_func=lambda x: {
            "normal": "正常用户", "impatient": "不耐烦用户",
            "hesitant": "犹豫用户", "rejecting": "拒绝用户",
            "angry": "愤怒用户", "silent": "沉默用户",
        }[x],
    )

    difficulty = st.selectbox(
        "难度",
        ["easy", "medium", "high"],
    )

    st.divider()

    run_col, _ = st.columns([1, 1])
    with run_col:
        run_btn = st.button("运行评测", type="primary", use_container_width=True)


# ====================================================
# 主区域
# ====================================================

def show_report(data: dict):
    """展示评测报告"""
    report = data.get("report", {})
    dialogue = data.get("dialogue", {})

    # ---- 概览 ----
    st.subheader("评测概览")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总分", f"{report.get('overall_score', 0):.1f}")
    with col2:
        st.metric("轮次", dialogue.get("turn_count", 0))
    with col3:
        terminated = dialogue.get("termination_reason", "unknown")
        reason_map = {
            "task_completed": "任务完成",
            "max_turns_reached": "达到上限",
            "user_rejected": "用户拒绝",
        }
        st.metric("终止原因", reason_map.get(terminated, terminated or "未知"))
    with col4:
        rule_eval = report.get("rule_eval", {})
        is_success = rule_eval.get("task_completed", False)
        st.metric("任务完成", "是" if is_success else "否")

    # ---- 维度评分 ----
    st.subheader("维度评分")

    dim_scores = report.get("dimension_scores", [])
    if dim_scores:
        dim_data = []
        for ds in dim_scores:
            dim_data.append({
                "维度": ds["dimension"],
                "分数": ds["score"],
                "权重": ds["weight"],
                "方式": "规则" if ds.get("is_rule_based") else "LLM",
                "说明": ds.get("explanation", ""),
            })

        dim_labels = {
            "task_success": "任务完成",
            "state_tracking": "状态追踪",
            "instruction_following": "流程遵循",
            "recovery_ability": "恢复能力",
            "robustness": "鲁棒性",
            "compliance": "合规",
            "naturalness": "自然度",
            "efficiency": "效率",
        }

        for d in dim_data:
            label = dim_labels.get(d["维度"], d["维度"])
            score = d["分数"]
            color = "green" if score >= 70 else ("orange" if score >= 40 else "red")
            st.markdown(
                f"**{label}** ({d['方式']}, 权重 {d['权重']}%)  "
                f":{color}[{score:.0f}分]  _{d['说明']}_"
            )
            st.progress(min(score / 100, 1.0))

    # ---- 对话文本 ----
    st.subheader("对话记录")
    conv_text = dialogue.get("conversation", "")
    if conv_text:
        st.text_area("完整对话", conv_text, height=300, disabled=True)

    # ---- 失败归因 ----
    failure = report.get("failure_analysis")
    if failure and failure.get("failure_types"):
        st.subheader("失败归因")
        st.warning(f"**根因**: {failure.get('root_cause', '未知')}")
        ft_labels = {
            "memory_failure": "记忆失败",
            "reasoning_failure": "推理失败",
            "policy_failure": "策略违规",
            "dialogue_drift": "目标偏离",
            "recovery_failure": "恢复失败",
            "faq_failure": "FAQ 错误",
            "emotion_failure": "情绪失败",
        }
        types_str = " → ".join(ft_labels.get(t, t) for t in failure.get("failure_types", []))
        st.info(f"**失败类型**: {types_str}")

        suggestions = failure.get("suggestions", [])
        if suggestions:
            st.markdown("**改进建议**:")
            for s in suggestions:
                st.markdown(f"- {s}")

    # ---- 违规记录 ----
    violations = report.get("compliance_violations", [])
    if violations:
        st.subheader("合规违规")
        for v in violations:
            sev_colors = {"low": "blue", "medium": "orange", "high": "red", "critical": "red"}
            color = sev_colors.get(v.get("severity", "medium"), "gray")
            st.markdown(
                f"- [轮次 {v.get('turn_id')}] :{color}[{v.get('severity')}] {v.get('description')}"
            )

    # ---- 用户画像分析 ----
    st.divider()
    persona_key = f"persona_analysis_{report.get('session_id', '0')}"
    if st.button("👤 分析用户画像", key=persona_key, use_container_width=True):
        show_persona_analysis(data)


def show_persona_analysis(data: dict):
    """展示用户画像行为分析"""
    scenario = data.get("scenario", {})
    dialogue = data.get("dialogue", {})
    report = data.get("report", {})

    persona = scenario.get("user_persona", "unknown")
    task_type = scenario.get("task_type", "unknown")

    # 用户画像标签映射
    persona_labels = {
        "normal": ("正常用户", "😐", "态度友好，愿意配合"),
        "impatient": ("不耐烦用户", "⏱️", "时间紧迫，语气急促，容易失去耐心"),
        "hesitant": ("犹豫用户", "🤔", "犹豫不决，持怀疑态度，回复含糊"),
        "rejecting": ("拒绝用户", "🚫", "倾向拒绝，戒备心强"),
        "angry": ("愤怒用户", "😠", "情绪激动，可能抱怨或质问"),
        "silent": ("沉默用户", "🤐", "惜字如金，回复极短"),
    }

    label, icon, desc = persona_labels.get(persona, ("未知用户", "❓", ""))

    # 使用 dialog 弹出分析页面
    @st.dialog(f"{icon} 用户画像深度分析", width="large")
    def persona_dialog():
        # === 基本信息 ===
        st.subheader("画像标签")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("画像类型", f"{icon} {label}")
        with col2:
            st.metric("任务场景", task_type)
        with col3:
            st.metric("对话轮次", dialogue.get("turn_count", 0))

        st.caption(desc)
        st.divider()

        # === 从对话中提取行为数据 ===
        turns = dialogue.get("turns", [])
        user_turns = [t for t in turns if t.get("speaker") == "user"]

        if not user_turns:
            st.info("暂无用户对话数据")
            return

        # 情绪变化
        emotions = [t.get("metadata", {}).get("emotion", "neutral") for t in user_turns]
        cooperation_levels = [t.get("metadata", {}).get("cooperation_level", 0.5) for t in user_turns]
        behaviours = [t.get("metadata", {}).get("behaviour", "normal") for t in user_turns]

        # === 情绪变化趋势 ===
        st.subheader("📈 情绪变化趋势")
        emotion_map = {
            "neutral": 3, "slightly_impatient": 2.5, "uncertain": 2.5,
            "impatient": 2, "defensive": 2, "passive": 2.5,
            "angry": 1, "very_angry": 0.5,
        }
        emotion_scores = [emotion_map.get(e, 3) for e in emotions]

        import pandas as pd
        df_emotion = pd.DataFrame({
            "轮次": list(range(1, len(emotion_scores) + 1)),
            "情绪指数": emotion_scores,
            "情绪标签": emotions,
            "合作度": cooperation_levels,
        })

        st.line_chart(df_emotion.set_index("轮次")[["情绪指数", "合作度"]])

        st.caption("""
        - **情绪指数**: 5=非常积极, 3=中性, 1=非常消极
        - **合作度**: 用户配合 Agent 的意愿程度
        """)

        # === 行为统计 ===
        st.subheader("📊 行为统计")
        behaviour_counts = {}
        for b in behaviours:
            behaviour_counts[b] = behaviour_counts.get(b, 0) + 1

        b_labels = {
            "normal": "正常回复", "interrupt": "打断",
            "off_topic": "跑题", "faq": "FAQ提问", "reject": "明确拒绝",
        }

        cols = st.columns(len(behaviour_counts) if behaviour_counts else 1)
        for i, (b, count) in enumerate(behaviour_counts.items()):
            with cols[i % len(cols)]:
                st.metric(b_labels.get(b, b), f"{count} 次")

        # === 关键行为节点 ===
        st.subheader("🔍 关键行为节点")
        key_events = []
        for i, t in enumerate(user_turns):
            turn_id = t.get("turn_id", i + 1)
            content = t.get("content", "")[:40]
            meta = t.get("metadata", {})
            behaviour = meta.get("behaviour", "normal")
            emotion = meta.get("emotion", "neutral")

            if behaviour != "normal":
                key_events.append({
                    "轮次": turn_id,
                    "行为": b_labels.get(behaviour, behaviour),
                    "情绪": emotion,
                    "内容": content + "..." if len(t.get("content", "")) > 40 else content,
                })

        if key_events:
            st.dataframe(key_events, use_container_width=True, hide_index=True)
        else:
            st.info("本次对话中未检测到特殊行为（打断/跑题/FAQ/拒绝）")

        # === 用户意图演变 ===
        st.subheader("🧠 用户意图演变")
        intent_stages = []
        for i, t in enumerate(user_turns):
            content = t.get("content", "")
            emotion = t.get("metadata", {}).get("emotion", "neutral")

            # 简单的意图推断
            if any(kw in content for kw in ["不需要", "不要", "没兴趣", "挂了"]):
                intent = "明确拒绝"
                stage_color = "red"
            elif any(kw in content for kw in ["嗯", "好", "行", "可以"]):
                intent = "配合/接受"
                stage_color = "green"
            elif any(kw in content for kw in ["犹豫", "想想", "不确定", "再考虑"]):
                intent = "犹豫不决"
                stage_color = "orange"
            elif any(kw in content for kw in ["为什么", "怎么", "什么"]):
                intent = "质疑/询问"
                stage_color = "blue"
            elif emotion in ["angry", "very_angry"]:
                intent = "情绪爆发"
                stage_color = "red"
            elif emotion in ["impatient", "slightly_impatient"]:
                intent = "失去耐心"
                stage_color = "orange"
            else:
                intent = "中性回应"
                stage_color = "gray"

            intent_stages.append({
                "轮次": t.get("turn_id", i + 1),
                "意图": intent,
                "情绪": emotion,
                "内容摘要": content[:30] + "..." if len(content) > 30 else content,
            })

        st.dataframe(intent_stages, use_container_width=True, hide_index=True)

        # === 对 Agent 的测试价值 ===
        st.divider()
        st.subheader("🎯 该画像对 Agent 的测试价值")

        test_values = {
            "normal": [
                "验证 Agent 标准流程执行能力",
                "基线对照组，衡量其他画像的难度系数",
            ],
            "impatient": [
                "测试 Agent 信息传递效率",
                "验证 Agent 是否能快速推进核心任务",
                "检测冗余话术和重复提问",
            ],
            "hesitant": [
                "测试 Agent 说服能力和信任建立",
                "验证 Agent 对模糊意图的理解",
                "检测过度推销或强制行为",
            ],
            "rejecting": [
                "测试 Agent 的边界意识和礼貌终止能力",
                "验证拒绝后的情绪处理",
                "检测是否遵守'最多尝试2次'规则",
            ],
            "angry": [
                "测试 Agent 情绪识别和安抚能力",
                "验证危机处理话术",
                "检测是否会激化矛盾",
            ],
            "silent": [
                "测试 Agent 主动引导和信息补全能力",
                "验证对极简回复的处理",
                "检测是否会陷入无效循环",
            ],
        }

        for v in test_values.get(persona, ["测试 Agent 通用能力"]):
            st.markdown(f"- {v}")

        # === 本次对话的关键发现 ===
        st.divider()
        st.subheader("📌 本次对话关键发现")

        findings = []
        if "angry" in emotions or "very_angry" in emotions:
            findings.append("用户情绪出现恶化，Agent 的安抚策略需要评估")
        if behaviour_counts.get("interrupt", 0) > 0:
            findings.append(f"用户打断 {behaviour_counts['interrupt']} 次，测试 Agent 的恢复能力")
        if behaviour_counts.get("off_topic", 0) > 0:
            findings.append(f"用户跑题 {behaviour_counts['off_topic']} 次，测试 Agent 的主线把控")
        if behaviour_counts.get("reject", 0) > 0:
            findings.append(f"用户明确拒绝 {behaviour_counts['reject']} 次，测试 Agent 的终止判断")

        # 合作度变化
        if cooperation_levels:
            first_coop = cooperation_levels[0]
            last_coop = cooperation_levels[-1]
            if last_coop < first_coop - 0.3:
                findings.append(f"用户合作度下降 ({first_coop:.1f} → {last_coop:.1f})，Agent 可能未能维持良好关系")
            elif last_coop > first_coop + 0.2:
                findings.append(f"用户合作度上升 ({first_coop:.1f} → {last_coop:.1f})，Agent 成功建立了信任")

        if not findings:
            findings.append("本次对话用户行为平稳，Agent 表现正常")

        for f in findings:
            st.markdown(f"- {f}")

    persona_dialog()


def show_stats():
    """展示汇总统计"""
    st.header("汇总统计")
    try:
        resp = requests.get(f"{API_BASE}/stats", timeout=60)
        if resp.status_code == 200:
            stats = resp.json()
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("评测总数", stats.get("total_sessions", 0))
            with col2:
                st.metric("成功率", f"{stats.get('success_rate', 0):.1%}")
            with col3:
                st.metric("平均分", f"{stats.get('avg_overall_score', 0):.1f}")

            # 维度平均
            dim_avgs = stats.get("dimension_averages", {})
            if dim_avgs:
                st.subheader("各维度平均分")
                dim_labels = {
                    "task_success": "任务完成", "state_tracking": "状态追踪",
                    "instruction_following": "流程遵循", "recovery_ability": "恢复能力",
                    "robustness": "鲁棒性", "compliance": "合规",
                    "naturalness": "自然度", "efficiency": "效率",
                }
                for k, v in dim_avgs.items():
                    label = dim_labels.get(k, k)
                    st.markdown(f"**{label}**: {v:.1f} 分")
                    st.progress(min(v / 100, 1.0))

            # 失败分布
            failure_dist = stats.get("failure_distribution", {})
            if failure_dist:
                st.subheader("失败类型分布")
                ft_labels = {
                    "memory_failure": "记忆失败", "reasoning_failure": "推理失败",
                    "policy_failure": "策略违规", "dialogue_drift": "目标偏离",
                    "recovery_failure": "恢复失败", "faq_failure": "FAQ 错误",
                    "emotion_failure": "情绪失败",
                }
                for k, v in failure_dist.items():
                    st.markdown(f"- {ft_labels.get(k, k)}: **{v}** 次")
        else:
            st.info("暂无评测数据，请先运行评测")
    except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
        st.info("后端服务正在启动中，请等待 30 秒后刷新页面（Render 免费实例冷启动较慢）")


# ====================================================
# 页面路由
# ====================================================

tab1, tab2 = st.tabs(["单次评测", "汇总统计"])

with tab1:
    if run_btn:
        with st.spinner("正在运行评测（生成场景 → 模拟对话 → 自动评分）..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/run_eval",
                    json={
                        "task_type": task_type,
                        "user_persona": user_persona,
                        "difficulty": difficulty,
                    },
                    timeout=120,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(f"评测完成！Session ID: {data['session_id']}")
                    show_report(data)
                else:
                    st.error(f"API 调用失败: {resp.status_code} - {resp.text}")
            except requests.exceptions.ConnectionError:
                st.error(
                    "无法连接到后端服务。请先启动 FastAPI 服务：\n\n"
                    "```bash\n"
                    "python -m src.main\n"
                    "```\n\n"
                    "然后在本页面重新运行评测。"
                )

    st.info("请在左侧选择场景配置后点击「运行评测」按钮")

with tab2:
    show_stats()