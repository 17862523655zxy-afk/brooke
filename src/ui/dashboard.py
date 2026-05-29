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