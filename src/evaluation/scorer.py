"""综合评分器：合并 Rule-based 评分和 LLM 评分，生成完整评测报告."""

from src.models.scenario import ScenarioConfig
from src.models.dialogue import DialogueSession
from src.models.evaluation import (
    EvalReport,
    DimensionScore,
    EvalDimension,
    RuleEvalResult,
    LlmEvalResult,
    ComplianceViolation,
    FailureAnalysis,
)
from src.evaluation.rule_based import RuleBasedEvaluator
from src.evaluation.llm_judge import LlmJudge


# 维度权重配置
WEIGHTS: dict[EvalDimension, float] = {
    EvalDimension.TASK_SUCCESS: 30,
    EvalDimension.STATE_TRACKING: 15,
    EvalDimension.INSTRUCTION_FOLLOWING: 15,
    EvalDimension.RECOVERY_ABILITY: 10,
    EvalDimension.ROBUSTNESS: 10,
    EvalDimension.COMPLIANCE: 10,
    EvalDimension.NATURALNESS: 5,
    EvalDimension.EFFICIENCY: 5,
}


class Scorer:
    """综合评分器"""

    def __init__(self, scenario: ScenarioConfig):
        self.scenario = scenario
        self.rule_evaluator = RuleBasedEvaluator(scenario)
        self.llm_judge = LlmJudge(scenario)

    def evaluate(self, dialogue: DialogueSession) -> EvalReport:
        """
        执行完整评测，返回 EvalReport。

        流程：
        1. 规则评分（Task Success, State Tracking, Compliance, Efficiency）
        2. LLM 评分（Naturalness, Recovery, Robustness, Instruction Following）
        3. 合并 -> 计算加权总分
        4. 合规违规记录
        """
        # 1. 规则评分
        rule_scores, rule_result = self.rule_evaluator.evaluate(dialogue)

        # 2. LLM 评分
        llm_scores, llm_result = self.llm_judge.evaluate(dialogue)

        # 3. 合并所有维度评分
        all_scores: list[DimensionScore] = []
        total_weight = 0.0
        weighted_sum = 0.0

        for ds in rule_scores + llm_scores:
            all_scores.append(ds)
            total_weight += ds.weight
            weighted_sum += ds.score * ds.weight

        # 4. 合规违规
        violations = self.rule_evaluator.get_compliance_violations(dialogue)

        # 合规一票否决：有 high/critical 级别违规时最高分 50
        has_critical = any(
            v.severity in ("high", "critical") for v in violations
        )
        overall_score = weighted_sum / total_weight if total_weight > 0 else 0
        if has_critical:
            overall_score = min(overall_score, 50.0)

        # 5. 构建报告
        report = EvalReport(
            session_id=dialogue.session_id,
            scenario_id=dialogue.scenario_id,
            dimension_scores=all_scores,
            overall_score=round(overall_score, 1),
            rule_eval=rule_result,
            llm_eval=llm_result,
            compliance_violations=violations,
            dialogue_summary=self._build_summary(dialogue),
        )

        return report

    def evaluate_with_failure(self, dialogue: DialogueSession) -> EvalReport:
        """评估并附带失败归因"""
        report = self.evaluate(dialogue)

        # 如果总体分较低，进行失败归因
        if report.overall_score < 60:
            from src.failure.analyzer import FailureAnalyzer
            analyzer = FailureAnalyzer(self.scenario)
            report.failure_analysis = analyzer.analyze(dialogue, report)

        return report

    @staticmethod
    def _build_summary(dialogue: DialogueSession) -> str:
        """生成对话摘要"""
        agent_turns = [t for t in dialogue.turns if t.speaker == "agent"]
        user_turns = [t for t in dialogue.turns if t.speaker == "user"]
        return (
            f"共 {dialogue.turn_count} 轮对话，"
            f"Agent 发言 {len(agent_turns)} 次，"
            f"用户发言 {len(user_turns)} 次，"
            f"终止原因: {dialogue.termination_reason or '未终止'}"
        )