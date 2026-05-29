"""失败归因分析器：对评测低分对话进行根因分析，归类到 7 种 Failure Type."""

import re
from typing import Optional

from src.models.scenario import ScenarioConfig
from src.models.dialogue import DialogueSession
from src.models.evaluation import (
    EvalReport,
    EvalDimension,
    FailureType,
    FailureAnalysis,
    DimensionScore,
)


# 失败模式检测规则
FAILURE_PATTERNS: dict[FailureType, dict] = {
    FailureType.MEMORY_FAILURE: {
        "keywords": ["再说一遍", "又问了", "重复", "已经告诉", "刚刚说过"],
        "check": "detect_repeated_questions",
        "suggestion": "Agent 在后续轮次中重复询问了已收集的信息。建议：在 prompt 中强调信息记忆机制，使用结构化状态存储。",
    },
    FailureType.RECOVERY_FAILURE: {
        "keywords": ["打断", "岔开", "跑题", "回不", "偏离"],
        "check": "detect_recovery_failure",
        "suggestion": "Agent 在被打断或跑题后未能有效恢复主线。建议：在 prompt 中增加恢复引导话术（如'好的，我们回到刚才的话题...'）。",
    },
    FailureType.POLICY_FAILURE: {
        "keywords": ["违规", "虚假承诺", "优惠", "保证", "一定"],
        "check": "detect_policy_violations",
        "suggestion": "Agent 做出了超出权限的承诺或违反了业务规则。建议：在 prompt 中明确权限边界，增加负面例子。",
    },
    FailureType.DIALOGUE_DRIFT: {
        "keywords": [],
        "check": "detect_dialogue_drift",
        "suggestion": "对话逐渐偏离了核心任务目标。建议：在 Agent prompt 中增加目标检查点，定期确认是否在推进任务。",
    },
    FailureType.REASONING_FAILURE: {
        "keywords": ["逻辑", "矛盾", "不对"],
        "check": None,  # 主要靠 LLM 评分中的 Instruction Following 低分推断
        "suggestion": "Agent 在推理过程中出现了逻辑错误。建议：检查 prompt 中的业务逻辑是否清晰，增加分步推理指导。",
    },
    FailureType.FAQ_FAILURE: {
        "keywords": ["问题", "问一下", "请问"],
        "check": None,
        "suggestion": "Agent 对用户的 FAQ 问题回答不准确。建议：检查是否有 FAQ 知识库注入，提高知识检索准确性。",
    },
    FailureType.EMOTION_FAILURE: {
        "keywords": ["生气", "不耐烦", "安抚", "情绪"],
        "check": "detect_emotion_failure",
        "suggestion": "Agent 未能有效识别和应对用户情绪。建议：在 prompt 中增加情绪感知和安抚话术指导。",
    },
}


class FailureAnalyzer:
    """失败归因分析器"""

    def __init__(self, scenario: ScenarioConfig):
        self.scenario = scenario

    def analyze(
        self, dialogue: DialogueSession, report: EvalReport
    ) -> FailureAnalysis:
        """
        对低分对话进行归因分析。

        分析逻辑：
        1. 从各维度评分中找出最低分数项
        2. 匹配对应的 Failure Type
        3. 检测对话中的具体失败模式
        4. 生成改进建议
        """
        failure_types: list[FailureType] = []
        related_turns: list[int] = []
        reasons: list[str] = []

        # 1. 从维度评分反向推导失败类型
        dim_to_failure: dict[EvalDimension, FailureType] = {
            EvalDimension.STATE_TRACKING: FailureType.MEMORY_FAILURE,
            EvalDimension.RECOVERY_ABILITY: FailureType.RECOVERY_FAILURE,
            EvalDimension.COMPLIANCE: FailureType.POLICY_FAILURE,
            EvalDimension.INSTRUCTION_FOLLOWING: FailureType.DIALOGUE_DRIFT,
            EvalDimension.NATURALNESS: FailureType.DIALOGUE_DRIFT,
        }

        low_score_dims: list[DimensionScore] = [
            ds for ds in report.dimension_scores if ds.score < 50
        ]

        for ds in low_score_dims:
            ft = dim_to_failure.get(ds.dimension)
            if ft and ft not in failure_types:
                failure_types.append(ft)
                reasons.append(f"{ds.dimension.value} 评分过低（{ds.score:.0f}分）: {ds.explanation}")

        # 2. 检测具体失败模式
        if self._detect_repeated_questions(dialogue):
            if FailureType.MEMORY_FAILURE not in failure_types:
                failure_types.append(FailureType.MEMORY_FAILURE)
            reasons.append("检测到 Agent 重复提问相同内容")
            related_turns.extend(self._find_repeated_question_turns(dialogue))

        if self._detect_recovery_failure(dialogue):
            if FailureType.RECOVERY_FAILURE not in failure_types:
                failure_types.append(FailureType.RECOVERY_FAILURE)
            reasons.append("检测到用户打断/跑题后 Agent 未恢复主线")

        # 3. 情绪失败检测
        user_meta = [t.metadata for t in dialogue.turns if t.speaker == "user"]
        has_escalation = any(m.get("emotion") in ("angry", "very_angry") for m in user_meta)
        if has_escalation:
            if FailureType.EMOTION_FAILURE not in failure_types:
                failure_types.append(FailureType.EMOTION_FAILURE)
            reasons.append("用户情绪持续恶化，Agent 未有效安抚")

        # 4. 任务未完成
        if report.rule_eval and not report.rule_eval.task_completed:
            reasons.append("核心任务目标未达成")

        # 5. 合规违规
        if report.compliance_violations:
            if FailureType.POLICY_FAILURE not in failure_types:
                failure_types.append(FailureType.POLICY_FAILURE)

        # 默认
        if not failure_types:
            failure_types.append(FailureType.DIALOGUE_DRIFT)

        # 确定首要失败类型
        primary = failure_types[0] if failure_types else FailureType.DIALOGUE_DRIFT

        # 生成建议
        suggestions = self._generate_suggestions(failure_types, reasons)

        return FailureAnalysis(
            failure_types=failure_types,
            primary_failure=primary,
            root_cause="; ".join(reasons) if reasons else "未发现明确根因",
            related_turns=related_turns,
            suggestions=suggestions,
        )

    # ---------------------------------------------------------------
    # 检测方法
    # ---------------------------------------------------------------

    @staticmethod
    def _detect_repeated_questions(dialogue: DialogueSession) -> bool:
        agent_turns = [t.content for t in dialogue.turns if t.speaker == "agent"]
        if len(agent_turns) < 2:
            return False
        for i in range(len(agent_turns)):
            for j in range(i + 1, len(agent_turns)):
                if FailureAnalyzer._text_similarity(agent_turns[i], agent_turns[j]) > 0.6:
                    return True
        return False

    @staticmethod
    def _detect_recovery_failure(dialogue: DialogueSession) -> bool:
        user_behaviours = [
            t.metadata.get("behaviour", "") for t in dialogue.turns if t.speaker == "user"
        ]
        has_interrupt = "interrupt" in user_behaviours or "off_topic" in user_behaviours
        if not has_interrupt:
            return False
        # 检查后续轮次是否回到主线
        agent_turns = [t.content for t in dialogue.turns if t.speaker == "agent"]
        recovery_phrases = ["回到", "继续", "刚才说到", "接着说"]
        for t in agent_turns[-3:]:
            if any(p in t for p in recovery_phrases):
                return False
        return True

    @staticmethod
    def _find_repeated_question_turns(dialogue: DialogueSession) -> list[int]:
        turns = []
        agent_turns = [(t.content, t.turn_id) for t in dialogue.turns if t.speaker == "agent"]
        for i in range(len(agent_turns)):
            for j in range(i + 1, len(agent_turns)):
                if FailureAnalyzer._text_similarity(agent_turns[i][0], agent_turns[j][0]) > 0.6:
                    if agent_turns[i][1] not in turns:
                        turns.append(agent_turns[i][1])
                    if agent_turns[j][1] not in turns:
                        turns.append(agent_turns[j][1])
        return sorted(turns)

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        set_a, set_b = set(a), set(b)
        if not set_a or not set_b:
            return 0
        return len(set_a & set_b) / len(set_a | set_b)

    @staticmethod
    def _generate_suggestions(
        failure_types: list[FailureType], reasons: list[str]
    ) -> list[str]:
        suggestions = []
        for ft in failure_types:
            pattern = FAILURE_PATTERNS.get(ft)
            if pattern and pattern.get("suggestion"):
                suggestions.append(pattern["suggestion"])
        return suggestions if suggestions else ["请人工审查对话记录进一步分析"]