"""场景数据模型."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    APPOINTMENT = "appointment"  # 预约外呼
    RENEWAL = "renewal"  # 续费提醒
    INFO_COLLECTION = "info_collection"  # 信息采集


class UserPersona(str, Enum):
    NORMAL = "normal"  # 正常用户
    IMPATIENT = "impatient"  # 不耐烦用户
    HESITANT = "hesitant"  # 犹豫用户
    REJECTING = "rejecting"  # 拒绝用户
    ANGRY = "angry"  # 愤怒用户
    SILENT = "silent"  # 沉默用户


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HIGH = "high"


class SuccessCriterion(BaseModel):
    """成功标准"""
    description: str
    required_fields: list[str] = Field(default_factory=list)
    required_outcomes: list[str] = Field(default_factory=list)


class RiskPoint(BaseModel):
    """风险点"""
    category: str  # compliance / privacy / misinformation
    description: str
    severity: str = "medium"  # low / medium / high / critical


class InterruptBehavior(BaseModel):
    """用户干扰行为配置"""
    can_interrupt: bool = False
    interrupt_probability: float = 0.0
    can_go_off_topic: bool = False
    off_topic_probability: float = 0.0
    can_ask_faq: bool = False
    faq_probability: float = 0.0


class EmotionProfile(BaseModel):
    """情绪变化配置"""
    initial_emotion: str = "neutral"
    emotion_escalation: bool = False  # 情绪是否升级
    escalation_trigger_turns: int = 3
    target_emotion: Optional[str] = None


class ScenarioConfig(BaseModel):
    """场景完整配置"""
    task_type: TaskType
    task_description: str
    user_persona: UserPersona
    difficulty: Difficulty
    agent_prompt: str
    user_profile: str  # 用户画像自然语言描述
    success_criteria: list[SuccessCriterion]
    risk_points: list[RiskPoint] = Field(default_factory=list)
    interrupt_behavior: InterruptBehavior = Field(default_factory=InterruptBehavior)
    emotion_profile: EmotionProfile = Field(default_factory=EmotionProfile)
    required_info_fields: list[str] = Field(default_factory=list)


class ScenarioGenerateRequest(BaseModel):
    """场景生成请求"""
    task_type: TaskType
    user_persona: UserPersona
    difficulty: Difficulty = Difficulty.MEDIUM
    custom_constraints: Optional[str] = None