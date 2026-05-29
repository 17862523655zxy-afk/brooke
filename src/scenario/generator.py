"""场景生成器：基于 task_type + user_persona + difficulty 生成完整场景配置."""

from src.models.scenario import (
    ScenarioConfig,
    ScenarioGenerateRequest,
    TaskType,
    UserPersona,
    Difficulty,
    SuccessCriterion,
    RiskPoint,
    InterruptBehavior,
    EmotionProfile,
)


# ============================================================
# 用户画像模板
# ============================================================

PERSONA_TEMPLATES: dict[UserPersona, dict] = {
    UserPersona.NORMAL: {
        "profile": "一位态度友好、愿意配合的普通用户。会认真回答 Agent 的问题，不会主动打断或跑题。偶尔会有简单的疑问但整体配合度很高。",
        "interrupt": InterruptBehavior(
            can_interrupt=False,
            can_go_off_topic=False,
            can_ask_faq=True,
            faq_probability=0.1,
        ),
        "emotion": EmotionProfile(
            initial_emotion="neutral",
            emotion_escalation=False,
        ),
    },
    UserPersona.IMPATIENT: {
        "profile": "一位时间紧迫、语气急促的用户。倾向于简短的回复，经常打断 Agent 的流程性表述，要求直接说重点。如果对话太慢会逐渐失去耐心。",
        "interrupt": InterruptBehavior(
            can_interrupt=True,
            interrupt_probability=0.4,
            can_go_off_topic=False,
            can_ask_faq=False,
        ),
        "emotion": EmotionProfile(
            initial_emotion="slightly_impatient",
            emotion_escalation=True,
            escalation_trigger_turns=3,
            target_emotion="angry",
        ),
    },
    UserPersona.HESITANT: {
        "profile": "一位犹豫不决的用户，对外呼目的持怀疑态度。回复含糊不确定，经常说'我再想想'或'我不确定'，需要 Agent 有较强的说服能力。",
        "interrupt": InterruptBehavior(
            can_interrupt=False,
            can_go_off_topic=True,
            off_topic_probability=0.2,
            can_ask_faq=True,
            faq_probability=0.3,
        ),
        "emotion": EmotionProfile(
            initial_emotion="uncertain",
            emotion_escalation=False,
        ),
    },
    UserPersona.REJECTING: {
        "profile": "一位倾向拒绝的用户。从对话开始就表达不愿意，可能多次明确拒绝。Agent 需要在不引起反感的前提下尝试推进目标。",
        "interrupt": InterruptBehavior(
            can_interrupt=True,
            interrupt_probability=0.3,
            can_go_off_topic=False,
            can_ask_faq=False,
        ),
        "emotion": EmotionProfile(
            initial_emotion="defensive",
            emotion_escalation=True,
            escalation_trigger_turns=2,
            target_emotion="angry",
        ),
    },
    UserPersona.ANGRY: {
        "profile": "一位情绪激动的用户。可能对品牌、产品或之前的服务不满意，语气强硬或有攻击性。Agent 首先需要安抚情绪才能推进业务。",
        "interrupt": InterruptBehavior(
            can_interrupt=True,
            interrupt_probability=0.6,
            can_go_off_topic=True,
            off_topic_probability=0.3,
            can_ask_faq=False,
        ),
        "emotion": EmotionProfile(
            initial_emotion="angry",
            emotion_escalation=True,
            escalation_trigger_turns=2,
            target_emotion="very_angry",
        ),
    },
    UserPersona.SILENT: {
        "profile": "一位惜字如金的用户。回复极短，经常只回复\'嗯\'、\'好\'、\'行\'，需要 Agent 主动引导才能完成信息收集。",
        "interrupt": InterruptBehavior(
            can_interrupt=False,
            can_go_off_topic=False,
            can_ask_faq=False,
        ),
        "emotion": EmotionProfile(
            initial_emotion="passive",
            emotion_escalation=False,
        ),
    },
}


# ============================================================
# 任务模板
# ============================================================

TASK_TEMPLATES: dict[TaskType, dict] = {
    TaskType.APPOINTMENT: {
        "description": "联系用户预约线下门店体验/服务时间",
        "agent_prompt": """你是一名专业的预约外呼客服。你的任务是联系用户并完成线下预约。

你必须完成以下步骤：
1. 确认用户身份（姓名+手机号）
2. 说明来电目的
3. 确认用户的意向时间（日期+时段）
4. 确认预约成功并告知注意事项

业务规则：
- 只能在工作日 9:00-18:00 预约
- 不可替用户决定时间
- 不可承诺任何优惠或返利（你没有权限）
- 遇到用户拒绝时，最多尝试说服 2 次后礼貌结束""",
        "success_criteria": [
            SuccessCriterion(
                description="用户确认了具体预约时间（日期+时段）",
                required_fields=["name", "phone", "appointment_date", "appointment_time"],
                required_outcomes=["appointment_confirmed"],
            ),
        ],
        "risk_points": [
            RiskPoint(category="compliance", description="不可承诺优惠/返利", severity="high"),
            RiskPoint(category="privacy", description="需确认身份后才能记录预约", severity="medium"),
        ],
        "required_info_fields": ["name", "phone", "appointment_date", "appointment_time"],
    },
    TaskType.RENEWAL: {
        "description": "联系即将到期的用户进行续费提醒与转化",
        "agent_prompt": """你是一名续费提醒外呼客服。你的任务是提醒用户服务即将到期并引导续费。

你必须完成以下步骤：
1. 确认用户身份（姓名）
2. 告知服务到期时间和续费方案
3. 了解用户续费意向和顾虑
4. 根据用户反馈推进（确认续费/记录拒绝原因）

业务规则：
- 不可夸大服务效果
- 不可虚假宣称限时优惠
- 不可强制要求用户当场决定
- 遇到明确拒绝时礼貌结束并记录原因""",
        "success_criteria": [
            SuccessCriterion(
                description="用户明确表达续费意向或确认续费",
                required_fields=["name"],
                required_outcomes=["renewal_intent_confirmed", "or", "decline_reason_recorded"],
            ),
        ],
        "risk_points": [
            RiskPoint(category="compliance", description="不可虚假宣称限时优惠", severity="high"),
            RiskPoint(category="misinformation", description="不可夸大服务效果", severity="high"),
        ],
        "required_info_fields": ["name", "renewal_intent", "decline_reason"],
    },
    TaskType.INFO_COLLECTION: {
        "description": "收集用户的特定信息（如调研、信息核实等）",
        "agent_prompt": """你是一名信息采集外呼客服。你的任务是联系用户收集特定的信息。

你必须完成以下步骤：
1. 确认用户身份
2. 说明信息采集的目的和用途
3. 按顺序收集所需信息字段
4. 确认信息完整性

业务规则：
- 明确告知信息用途和数据保护承诺
- 不可强制用户提供不愿意提供的信息
- 不可记录未经确认的信息
- 对敏感信息要特别说明采集原因""",
        "success_criteria": [
            SuccessCriterion(
                description="成功收集所有必填字段",
                required_fields=["name", "age_range", "feedback"],
                required_outcomes=["all_fields_collected"],
            ),
        ],
        "risk_points": [
            RiskPoint(category="privacy", description="需告知信息用途和数据保护", severity="high"),
            RiskPoint(category="compliance", description="不可强制收集敏感信息", severity="high"),
        ],
        "required_info_fields": ["name", "age_range", "usage_frequency", "feedback"],
    },
}


# ============================================================
# Generator
# ============================================================

class ScenarioGenerator:
    """场景生成器：基于模板生成完整场景配置"""

    @staticmethod
    def generate(request: ScenarioGenerateRequest) -> ScenarioConfig:
        """
        根据请求参数生成场景配置。

        优先级：
        1. 匹配精确模板
        2. 若无精确模板，用最接近的模板 + request 参数微调
        """
        task_template = TASK_TEMPLATES.get(request.task_type)
        if task_template is None:
            raise ValueError(f"Unknown task_type: {request.task_type}")

        persona_template = PERSONA_TEMPLATES.get(request.user_persona)
        if persona_template is None:
            raise ValueError(f"Unknown user_persona: {request.user_persona}")

        return ScenarioConfig(
            task_type=request.task_type,
            task_description=task_template["description"],
            user_persona=request.user_persona,
            difficulty=request.difficulty,
            agent_prompt=task_template["agent_prompt"],
            user_profile=persona_template["profile"],
            success_criteria=task_template["success_criteria"],
            risk_points=task_template["risk_points"],
            interrupt_behavior=persona_template["interrupt"],
            emotion_profile=persona_template["emotion"],
            required_info_fields=task_template["required_info_fields"],
        )

    @staticmethod
    def list_available_task_types() -> list[str]:
        return [t.value for t in TaskType]

    @staticmethod
    def list_available_personas() -> list[str]:
        return [p.value for p in UserPersona]

    @staticmethod
    def list_available_difficulties() -> list[str]:
        return [d.value for d in Difficulty]