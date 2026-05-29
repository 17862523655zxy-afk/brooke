"""评测结果数据模型."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class FailureType(str, Enum):
    MEMORY_FAILURE = "memory_failure"  # 忘记历史上下文
    REASONING_FAILURE = "reasoning_failure"  # 推理错误
    POLICY_FAILURE = "policy_failure"  # 违反业务规则
    DIALOGUE_DRIFT = "dialogue_drift"  # 偏离任务目标
    RECOVERY_FAILURE = "recovery_failure"  # 无法恢复主线
    FAQ_FAILURE = "faq_failure"  # FAQ 回答错误
    EMOTION_FAILURE = "emotion_failure"  # 情绪处理失败


class EvalDimension(str, Enum):
    TASK_SUCCESS = "task_success"
    STATE_TRACKING = "state_tracking"
    INSTRUCTION_FOLLOWING = "instruction_following"
    RECOVERY_ABILITY = "recovery_ability"
    ROBUSTNESS = "robustness"
    COMPLIANCE = "compliance"
    NATURALNESS = "naturalness"
    EFFICIENCY = "efficiency"


class DimensionScore(BaseModel):
    """单维度评分"""
    dimension: EvalDimension
    score: float  # 0-100 或 0-5 标准化
    weight: float  # 权重
    explanation: str = ""
    is_rule_based: bool = True


class RuleEvalResult(BaseModel):
    """规则评分结果"""
    task_completed: bool = False
    required_fields_collected: dict[str, bool] = Field(default_factory=dict)
    fields_collection_rate: float = 0.0
    compliance_violations: list[str] = Field(default_factory=list)
    redundant_turns: int = 0
    total_turns: int = 0


class LlmEvalResult(BaseModel):
    """LLM 评分结果"""
    naturalness_score: float = 0.0
    emotion_handling_score: float = 0.0
    persuasiveness_score: float = 0.0
    overall_quality_score: float = 0.0
    qualitative_feedback: str = ""


class ComplianceViolation(BaseModel):
    """合规违规记录"""
    violation_type: str
    turn_id: int
    description: str
    severity: str = "high"


class FailureAnalysis(BaseModel):
    """失败归因分析"""
    failure_types: list[FailureType] = Field(default_factory=list)
    primary_failure: Optional[FailureType] = None
    root_cause: str = ""
    related_turns: list[int] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    """完整评测报告"""
    session_id: str
    scenario_id: str
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    overall_score: float = 0.0
    rule_eval: Optional[RuleEvalResult] = None
    llm_eval: Optional[LlmEvalResult] = None
    compliance_violations: list[ComplianceViolation] = Field(default_factory=list)
    failure_analysis: Optional[FailureAnalysis] = None
    dialogue_summary: str = ""


class AggregateStats(BaseModel):
    """汇总统计"""
    total_sessions: int = 0
    success_rate: float = 0.0
    avg_overall_score: float = 0.0
    dimension_averages: dict[str, float] = Field(default_factory=dict)
    scenario_breakdown: dict[str, float] = Field(default_factory=dict)  # 场景类型 -> 成功率
    persona_breakdown: dict[str, float] = Field(default_factory=dict)  # 用户画像 -> 成功率
    failure_distribution: dict[str, int] = Field(default_factory=dict)  # 失败类型分布