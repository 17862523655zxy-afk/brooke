"""规则评分器：基于确定性规则进行评分.

覆盖维度：
- Task Success：是否完成任务
- State Tracking：状态维护
- Compliance：违规检测
- Efficiency：轮次效率
"""

import re
from src.models.scenario import ScenarioConfig
from src.models.dialogue import DialogueSession
from src.models.evaluation import (
    RuleEvalResult,
    DimensionScore,
    EvalDimension,
    ComplianceViolation,
)


# 违规检测关键词
COMPLIANCE_KEYWORDS = {
    "false_promise": [
        r"保证.*?效果",
        r"一定.*?优惠",
        r"承诺.*?返利",
        r"限时.*?折扣",
        r"最后.*?名额",
        r"必定.*?成功",
    ],
    "exaggeration": [
        r"最好.*?产品",
        r"完美.*?解决",
        r"绝对.*?有效",
        r"100%.*?满意",
    ],
    "privacy_leak": [
        r"其他用户的.*?信息",
        r"别人的.*?记录",
    ],
    "unauthorized_commitment": [
        r"我保证.*?退款",
        r"我替您.*?决定",
        r"直接帮您.*?操作",
    ],
}


class RuleBasedEvaluator:
    """规则评分器"""

    def __init__(self, scenario: ScenarioConfig):
        self.scenario = scenario

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    def evaluate(self, dialogue: DialogueSession) -> tuple[list[DimensionScore], RuleEvalResult]:
        """执行规则评分，返回维度评分和规则评估结果"""
        scores: list[DimensionScore] = []
        rule_result = RuleEvalResult()

        # 1. Task Success (30%)
        task_score, fields_collected = self._check_fields(dialogue)
        rule_result.required_fields_collected = fields_collected
        rule_result.fields_collection_rate = (
            sum(1 for v in fields_collected.values() if v) / len(fields_collected)
            if fields_collected else 1.0
        )
        rule_result.task_completed = rule_result.fields_collection_rate >= 0.75
        scores.append(DimensionScore(
            dimension=EvalDimension.TASK_SUCCESS,
            score=task_score,
            weight=30,
            explanation=f"字段收集率: {rule_result.fields_collection_rate:.0%}",
            is_rule_based=True,
        ))

        # 2. State Tracking (15%)
        state_score = self._eval_state_tracking(dialogue)
        scores.append(DimensionScore(
            dimension=EvalDimension.STATE_TRACKING,
            score=state_score,
            weight=15,
            is_rule_based=True,
        ))

        # 3. Efficiency (5%)
        rule_result.total_turns = dialogue.turn_count
        redundant = self._eval_efficiency(dialogue)
        rule_result.redundant_turns = redundant
        eff_score = max(0, 100 - redundant * 10)
        scores.append(DimensionScore(
            dimension=EvalDimension.EFFICIENCY,
            score=eff_score,
            weight=5,
            explanation=f"冗余轮次: {redundant}",
            is_rule_based=True,
        ))

        # 4. Compliance (10%)
        violations = self.get_compliance_violations(dialogue)
        rule_result.compliance_violations = [v.description for v in violations]
        comp_score = max(0, 100 - len(violations) * 25)
        scores.append(DimensionScore(
            dimension=EvalDimension.COMPLIANCE,
            score=comp_score,
            weight=10,
            explanation=f"违规数: {len(violations)}",
            is_rule_based=True,
        ))

        return scores, rule_result

    def get_compliance_violations(self, dialogue: DialogueSession) -> list[ComplianceViolation]:
        """仅获取合规违规列表"""
        violations = []
        for turn in dialogue.turns:
            if turn.speaker != "agent":
                continue
            for vtype, patterns in COMPLIANCE_KEYWORDS.items():
                for pattern in patterns:
                    if re.search(pattern, turn.content):
                        violations.append(ComplianceViolation(
                            violation_type=vtype,
                            turn_id=turn.turn_id,
                            description=f"Agent 回复中检测到疑似{vtype}：{turn.content[:60]}...",
                        ))
                        break
        return violations

    # ---------------------------------------------------------------
    # 各维度评估
    # ---------------------------------------------------------------

    def _check_fields(self, dialogue: DialogueSession) -> tuple[float, dict[str, bool]]:
        """检测必填字段是否被收集"""
        fields = self.scenario.required_info_fields
        if not fields:
            return (100.0, {})

        full_text = dialogue.to_conversation_text()
        patterns: dict[str, str] = {
            "name": r"(我叫|姓|名字是|姓名[：:])\s*[\u4e00-\u9fa5]{2,4}",
            "phone": r"1[3-9]\d{9}",
            "appointment_date": r"(\d{1,2}月\d{1,2}[日号]|\d{4}-\d{2}-\d{2})",
            "appointment_time": r"(\d{1,2}[点:：]\d{1,2}|\d{1,2}点|上午|下午|晚上)",
            "renewal_intent": r"(续费|续约|继续.*?使用)",
            "decline_reason": r"(不.*?因为|原因是)",
            "age_range": r"(\d{2}岁|\d{2}-\d{2}岁)",
            "usage_frequency": r"(每天|每周|每月|经常|偶尔)",
            "feedback": r"(反馈|意见|建议|觉得)",
        }

        collected: dict[str, bool] = {}
        for field in fields:
            pat = patterns.get(field)
            collected[field] = bool(re.search(pat, full_text)) if pat else (field in full_text)

        rate = sum(1 for v in collected.values() if v) / len(collected)
        return (rate * 100, collected)

    def _eval_state_tracking(self, dialogue: DialogueSession) -> float:
        agent_turns = [t.content for t in dialogue.turns if t.speaker == "agent"]
        if len(agent_turns) < 2:
            return 100.0
        score = 100
        phone_q = [t for t in agent_turns if "手机" in t or "号码" in t or "电话" in t]
        if len(phone_q) > 2:
            score -= 20 * (len(phone_q) - 2)
        name_q = [t for t in agent_turns if "请问您" in t and ("贵姓" in t or "名字" in t)]
        if len(name_q) > 2:
            score -= 20 * (len(name_q) - 2)
        return max(0, score)

    def _eval_efficiency(self, dialogue: DialogueSession) -> int:
        agent_turns = [t.content for t in dialogue.turns if t.speaker == "agent"]
        redundant = 0
        for i in range(len(agent_turns)):
            for j in range(i + 1, len(agent_turns)):
                if self._sim(agent_turns[i], agent_turns[j]) > 0.7:
                    redundant += 1
                    break
        return redundant

    @staticmethod
    def _sim(a: str, b: str) -> float:
        set_a, set_b = set(a), set(b)
        if not set_a or not set_b:
            return 0
        return len(set_a & set_b) / len(set_a | set_b)