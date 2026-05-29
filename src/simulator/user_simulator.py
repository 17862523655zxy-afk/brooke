"""用户模拟器：模拟真实用户行为，支持情绪变化、打断、跑题、FAQ 等复杂行为.

采用状态机 + LLM 混合驱动：
- 状态机：管理用户内部状态（情绪等级、合作度、是否打断等）
- LLM：根据当前状态和对话历史生成自然的用户回复
"""

import random
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings
from src.models.scenario import ScenarioConfig, UserPersona, InterruptBehavior, EmotionProfile
from src.models.dialogue import Turn


class UserState(str, Enum):
    NORMAL = "normal"
    SLIGHTLY_IMPATIENT = "slightly_impatient"
    IMPATIENT = "impatient"
    ANGRY = "angry"
    VERY_ANGRY = "very_angry"
    UNCERTAIN = "uncertain"
    DEFENSIVE = "defensive"
    PASSIVE = "passive"


# 情绪升级映射
EMOTION_ESCALATION: dict[str, str] = {
    "neutral": "slightly_impatient",
    "slightly_impatient": "impatient",
    "impatient": "angry",
    "angry": "very_angry",
    "defensive": "angry",
}

# 行为触发映射
BEHAVIOR_PROMPTS: dict[str, str] = {
    "interrupt": "你现在打断了 Agent 的发言，插入自己的话。你不需要等 Agent 说完，直接打断。",
    "off_topic": "你突然想到一个完全无关的问题，现在提出这个问题，偏离当前对话主题。",
    "faq": "你现在有一个关于产品/服务的常见问题，直接向 Agent 提问。",
    "reject": "你现在决定拒绝 Agent 的提议/请求，明确表达拒绝态度。",
}


@dataclass
class UserInternalState:
    """用户内部状态"""
    emotion: str = "neutral"
    cooperation_level: float = 0.8  # 0-1，合作度
    patience_remaining: int = 10  # 剩余耐心轮次
    has_interrupted_recently: bool = False
    off_topic_count: int = 0
    turn_count: int = 0
    collected_info: dict[str, str] = field(default_factory=dict)


class UserSimulator:
    """用户模拟器"""

    def __init__(self, scenario: ScenarioConfig, llm: Optional[ChatOpenAI] = None):
        self.scenario = scenario
        self.llm = llm or ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            openai_api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.state = UserInternalState()
        self._init_state_from_persona(scenario.user_persona, scenario.emotion_profile)

    def _init_state_from_persona(self, persona: UserPersona, emotion_profile: EmotionProfile):
        """根据用户画像初始化内部状态"""
        emotion_map = {
            UserPersona.NORMAL: ("neutral", 0.8, 10),
            UserPersona.IMPATIENT: ("slightly_impatient", 0.5, 4),
            UserPersona.HESITANT: ("uncertain", 0.4, 8),
            UserPersona.REJECTING: ("defensive", 0.2, 5),
            UserPersona.ANGRY: ("angry", 0.15, 3),
            UserPersona.SILENT: ("passive", 0.6, 10),
        }
        emotion, coop, patience = emotion_map.get(persona, ("neutral", 0.8, 10))
        self.state.emotion = emotion
        self.state.cooperation_level = coop
        self.state.patience_remaining = patience

    def respond(self, agent_message: str, dialogue_history: list[Turn]) -> Turn:
        """
        根据 Agent 消息和对话历史生成用户回复。

        执行流程：
        1. 更新内部状态（时间、情绪等）
        2. 检测是否需要触发特殊行为（打断、跑题、FAQ）
        3. 调用 LLM 生成自然语言回复
        4. 返回 Turn 对象
        """
        self.state.turn_count += 1
        turn_id = self.state.turn_count

        behaviour = self._check_special_behaviour()

        # 更新情绪
        self._update_emotion(agent_message)

        # 构建 prompt
        messages = self._build_prompt(agent_message, dialogue_history, behaviour)

        # 调用 LLM
        response = self.llm.invoke(messages)
        content = response.content.strip() if hasattr(response, "content") else str(response)

        metadata = {
            "emotion": self.state.emotion,
            "cooperation_level": self.state.cooperation_level,
            "behaviour": behaviour or "normal",
        }

        return Turn.user_turn(turn_id, content, **metadata)

    def _check_special_behaviour(self) -> Optional[str]:
        """检测是否触发特殊行为"""
        ib = self.scenario.interrupt_behavior

        # 打断
        if ib.can_interrupt and not self.state.has_interrupted_recently:
            if random.random() < ib.interrupt_probability:
                self.state.has_interrupted_recently = True
                return "interrupt"
        self.state.has_interrupted_recently = False

        # 跑题
        if ib.can_go_off_topic:
            if random.random() < ib.off_topic_probability:
                self.state.off_topic_count += 1
                return "off_topic"

        # FAQ
        if ib.can_ask_faq:
            if random.random() < ib.faq_probability:
                return "faq"

        return None

    def _update_emotion(self, agent_message: str):
        """更新用户情绪状态"""
        ep = self.scenario.emotion_profile

        # 情绪升级
        if ep.emotion_escalation and self.state.patience_remaining <= ep.escalation_trigger_turns:
            next_emotion = EMOTION_ESCALATION.get(self.state.emotion)
            if next_emotion:
                self.state.emotion = next_emotion
                self.state.cooperation_level = max(0.05, self.state.cooperation_level - 0.2)

        # 耐心递减
        self.state.patience_remaining -= 1

    def _build_prompt(
        self,
        agent_message: str,
        dialogue_history: list[Turn],
        behaviour: Optional[str],
    ) -> list:
        """构建 LLM prompt"""
        history_text = self._format_history(dialogue_history)

        # 根据画像确定回答风格
        style_instructions = {
            "neutral": "语气平和，正常回答问题",
            "uncertain": "语气犹豫，频繁使用'嗯...'、'我不太确定'、'我再想想'",
            "slightly_impatient": "语气略显急促，回复较短",
            "impatient": "语气明显不耐烦，要求说重点，回复很短",
            "angry": "语气愤怒，可能抱怨或质问",
            "very_angry": "语气非常愤怒，可能直接挂断或强烈指责",
            "defensive": "语气戒备，怀疑来电目的",
            "passive": "回复极短，通常1-3个字，如'嗯'、'好'、'行'",
        }

        current_style = style_instructions.get(self.state.emotion, "语气平和")

        # 收集信息注入
        collected_info_text = ""
        if self.state.collected_info:
            collected_info_text = "你已知的个人信息：" + ", ".join(
                f"{k}={v}" for k, v in self.state.collected_info.items()
            )

        # 特殊行为指令
        behaviour_instruction = ""
        if behaviour:
            behaviour_instruction = f"【特殊行为】{BEHAVIOR_PROMPTS.get(behaviour, '')}"

        system_prompt = f"""你正在扮演一位接到外呼电话的真实用户。

【你的身份】
{self.scenario.user_profile}

【当前情绪状态】
{current_style}
具体情绪标签: {self.state.emotion}
合作度: {self.state.cooperation_level:.2f}

【你的个人信息】
{collected_info_text}

【回答规则】
1. 始终以用户口吻回复，不要写得像客服
2. 回复长度符合你的当前情绪（不耐烦就短，犹豫就有很多语气词）
3. 不要主动推进流程，你只是一个被联系的普通用户
4. 不要使用"作为用户"等元描述
5. 如果 Agent 问你个人信息，根据合作度决定是否如实提供：
   - 合作度 > 0.7: 如实提供
   - 合作度 0.3-0.7: 可能提供但保留态度
   - 合作度 < 0.3: 拒绝或提供模糊信息
{behaviour_instruction}

【Agent 刚说的一句话】
{agent_message}

请用一句自然的中文回复 Agent。直接给出回复内容，不要添加任何前缀或标签。"""

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content="请以用户身份回复 Agent 刚才说的话。只输出回复内容本身。"),
        ]

    @staticmethod
    def _format_history(dialogue_history: list[Turn]) -> str:
        if not dialogue_history:
            return "（这是对话的第一轮）"
        lines = []
        for t in dialogue_history[-6:]:  # 最近 6 轮
            role = "Agent" if t.speaker == "agent" else "User"
            lines.append(f"{role}: {t.content}")
        return "\n".join(lines)

    def reset(self):
        """重置模拟器状态"""
        self.state = UserInternalState()
        self._init_state_from_persona(self.scenario.user_persona, self.scenario.emotion_profile)