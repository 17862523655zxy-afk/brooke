"""LLM-as-a-Judge：使用 LLM 对主观维度进行评分.

覆盖维度：
- Naturalness：回复自然度
- Recovery Ability：打断后恢复能力
- Robustness：面对复杂用户的稳定性
- Instruction Following：流程遵循度
"""

import json
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings
from src.models.scenario import ScenarioConfig
from src.models.dialogue import DialogueSession
from src.models.evaluation import (
    DimensionScore,
    EvalDimension,
    LlmEvalResult,
)


# Rubric 定义
RUBRICS = {
    EvalDimension.NATURALNESS: """
评分标准（1-5分）：
5分：回复非常自然，像真人对话，语气恰当，有温度感
3分：回复基本自然，但有些生硬或模板化
1分：回复明显机器化，不自然，像在念稿
""",
    EvalDimension.RECOVERY_ABILITY: """
评分标准（1-5分）：
5分：成功恢复主线，对话自然流畅，用户感知不到被打断
3分：能够恢复，但方式生硬，有明显的"拉回"痕迹
1分：无法恢复，对话中断或偏离主线后走不回来
""",
    EvalDimension.ROBUSTNESS: """
评分标准（1-5分）：
5分：面对复杂用户行为（情绪、打断、跑题）依然稳定推进任务
3分：部分情况下能应对，有些场景下出现混乱
1分：遇到异常行为后完全无法继续
""",
    EvalDimension.INSTRUCTION_FOLLOWING: """
评分标准（1-5分）：
5分：严格遵循业务流程，步骤完整，规则遵守到位
3分：大体遵循流程，但有小的遗漏或偏差
1分：严重偏离流程，跳过关键步骤或违反业务规则
""",
}


class LlmJudge:
    """LLM 评分器"""

    def __init__(self, scenario: ScenarioConfig, llm: Optional[ChatOpenAI] = None):
        self.scenario = scenario
        self.llm = llm or ChatOpenAI(
            model=settings.judge_model,
            temperature=settings.judge_temperature,
            openai_api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    def evaluate(self, dialogue: DialogueSession) -> tuple[list[DimensionScore], LlmEvalResult]:
        """执行 LLM 评分"""
        conversation = dialogue.to_conversation_text()
        scores: list[DimensionScore] = []
        llm_result = LlmEvalResult()

        # 评估自然度 (5%)
        nat_score = self._judge_dimension(
            conversation, EvalDimension.NATURALNESS
        )
        scores.append(DimensionScore(
            dimension=EvalDimension.NATURALNESS,
            score=nat_score * 20,  # 1-5 -> 0-100
            weight=5,
            is_rule_based=False,
        ))
        llm_result.naturalness_score = nat_score

        # 评估恢复能力 (10%)
        rec_score = self._judge_dimension(
            conversation, EvalDimension.RECOVERY_ABILITY
        )
        scores.append(DimensionScore(
            dimension=EvalDimension.RECOVERY_ABILITY,
            score=rec_score * 20,
            weight=10,
            is_rule_based=False,
        ))

        # 评估鲁棒性 (10%)
        rob_score = self._judge_dimension(
            conversation, EvalDimension.ROBUSTNESS
        )
        scores.append(DimensionScore(
            dimension=EvalDimension.ROBUSTNESS,
            score=rob_score * 20,
            weight=10,
            is_rule_based=False,
        ))

        # 评估流程遵循度 (15%)
        ins_score = self._judge_dimension(
            conversation, EvalDimension.INSTRUCTION_FOLLOWING
        )
        scores.append(DimensionScore(
            dimension=EvalDimension.INSTRUCTION_FOLLOWING,
            score=ins_score * 20,
            weight=15,
            is_rule_based=False,
        ))

        # 综合 LLM 评估
        llm_result.overall_quality_score = (
            nat_score + rec_score + rob_score + ins_score
        ) / 16  # 归一化到 0-1

        return scores, llm_result

    def _judge_dimension(
        self, conversation: str, dimension: EvalDimension
    ) -> float:
        """对单个维度评分（返回 1-5 分）"""
        rubric = RUBRICS.get(dimension, "请给出 1-5 分的评分。")

        system_prompt = f"""你是一个专业的外呼对话质量评审员。请根据以下标准对对话进行评分。

{dimension.value}
{rubric}

请只输出一个 JSON 对象，格式如下：
{{"score": <1-5的整数>,"reason": "<简短理由>"}}

只输出 JSON，不要输出其他内容。"""

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"请评审以下对话：\n\n{conversation}"),
            ])
            content = response.content.strip() if hasattr(response, "content") else str(response)

            # 尝试解析 JSON
            result = json.loads(content)
            score = float(result.get("score", 3))
            return max(1, min(5, score))
        except (json.JSONDecodeError, ValueError, KeyError):
            # fallback: 尝试提取数字
            import re
            match = re.search(r'"score"\s*:\s*(\d+)', content)
            if match:
                return max(1, min(5, float(match.group(1))))
            return 3.0  # 默认中等分