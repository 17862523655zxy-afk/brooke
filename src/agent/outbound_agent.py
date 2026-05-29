"""被评测的 Outbound Agent：基于 LLM 的外呼 Agent，维护对话状态、遵循业务流程."""

from dataclasses import dataclass, field
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings
from src.models.scenario import ScenarioConfig
from src.models.dialogue import Turn


@dataclass
class AgentState:
    """Agent 内部状态"""
    current_phase: str = "greeting"  # greeting / identity_check / purpose / negotiation / closing
    collected_fields: dict[str, str] = field(default_factory=dict)
    has_greeted: bool = False
    has_identified: bool = False
    has_stated_purpose: bool = False
    has_confirmed: bool = False
    rejection_count: int = 0
    max_rejections: int = 2


class OutboundAgent:
    """外呼 Agent —— 被评测对象"""

    def __init__(self, scenario: ScenarioConfig, llm: Optional[ChatOpenAI] = None):
        self.scenario = scenario
        self.llm = llm or ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            openai_api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        self.state = AgentState()

    def respond(self, user_message: str, dialogue_history: list[Turn]) -> Turn:
        """
        根据用户消息和对话历史生成 Agent 回复。

        执行流程：
        1. 更新内部状态（阶段推进、字段收集）
        2. 构建 prompt
        3. 调用 LLM 生成回复
        """
        turn_id = len(dialogue_history) + 1

        self._update_state(user_message, dialogue_history)

        messages = self._build_prompt(user_message, dialogue_history)

        response = self.llm.invoke(messages)
        content = response.content.strip() if hasattr(response, "content") else str(response)

        return Turn.agent_turn(
            turn_id, content, phase=self.state.current_phase
        )

    def _update_state(self, user_message: str, dialogue_history: list[Turn]):
        """更新 Agent 内部阶段状态"""
        msg_lower = user_message.lower()

        # 问候阶段 -> 身份确认阶段
        if self.state.current_phase == "greeting" and self.state.has_greeted:
            self.state.current_phase = "identity_check"
        if not self.state.has_greeted:
            self.state.has_greeted = True

        # 身份确认阶段 -> 说明目的
        if self.state.current_phase == "identity_check":
            # 检测用户是否提供了身份信息
            if any(kw in msg_lower for kw in ["我是", "对", "是的", "没错", "嗯"]):
                self.state.has_identified = True
                self.state.current_phase = "purpose"

        # 说明目的后 -> 协商/信息收集
        if self.state.has_stated_purpose:
            self.state.current_phase = "negotiation"

        # 检测拒绝
        reject_keywords = ["不需要", "不要", "没兴趣", "挂了", "别再打", "不用"]
        if any(kw in user_message for kw in reject_keywords):
            self.state.rejection_count += 1

        # 检测确认
        confirm_keywords = ["好的", "可以", "行", "没问题", "确认", "同意"]
        if any(kw in user_message for kw in confirm_keywords) and self.state.current_phase == "negotiation":
            self.state.has_confirmed = True
            self.state.current_phase = "closing"

    def _build_prompt(self, user_message: str, dialogue_history: list[Turn]) -> list:
        """构建 LLM prompt"""
        history_text = self._format_history(dialogue_history)

        fields_collected = ", ".join(
            f"{k}={v}" for k, v in self.state.collected_fields.items()
        ) if self.state.collected_fields else "无"

        remaining_fields = [
            f for f in self.scenario.required_info_fields
            if f not in self.state.collected_fields
        ]

        system_prompt = f"""你是一名专业的外呼客服 Agent。你需要严格遵循以下指令行事。

【任务指令】
{self.scenario.agent_prompt}

【当前状态】
- 当前阶段: {self.state.current_phase}
- 已收集信息: {fields_collected}
- 待收集信息: {remaining_fields}
- 已被拒绝次数: {self.state.rejection_count}/{self.state.max_rejections}

【历史对话】
{history_text}

【用户刚说】
{user_message}

【回答准则】
1. 严格遵循业务流程和业务规则
2. 如果已被拒绝 {self.state.max_rejections} 次，礼貌结束对话
3. 不要重复询问已经收集过的信息
4. 每次只问一个问题，不要一次抛多个问题
5. 遇到用户情绪激动时，先安抚再推进
6. 不可做出你没有权限的承诺

请以客服身份用自然的中文回复用户。直接给出回复内容。"""

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content="请回复用户刚才说的话。直接输出回复内容。"),
        ]

    @staticmethod
    def _format_history(dialogue_history: list[Turn]) -> str:
        if not dialogue_history:
            return "（对话开始）"
        lines = []
        for t in dialogue_history[-8:]:
            role = "我(Agent)" if t.speaker == "agent" else "用户"
            lines.append(f"{role}: {t.content}")
        return "\n".join(lines)

    def is_task_completed(self) -> bool:
        """判断任务是否完成"""
        return self.state.has_confirmed and self.state.current_phase == "closing"

    def should_terminate(self) -> bool:
        """判断是否应该终止"""
        return self.state.rejection_count >= self.state.max_rejections

    def reset(self):
        """重置 Agent 状态"""
        self.state = AgentState()