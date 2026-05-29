"""对话数据模型."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Speaker(str):
    AGENT = "agent"
    USER = "user"


class Turn(BaseModel):
    """单轮对话"""
    turn_id: int
    speaker: str  # agent / user
    content: str
    timestamp: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)  # 情绪标记、行为标记等

    @classmethod
    def agent_turn(cls, turn_id: int, content: str, **meta) -> "Turn":
        return cls(turn_id=turn_id, speaker="agent", content=content, metadata=meta)

    @classmethod
    def user_turn(cls, turn_id: int, content: str, **meta) -> "Turn":
        return cls(turn_id=turn_id, speaker="user", content=content, metadata=meta)


class DialogueSession(BaseModel):
    """多轮对话会话"""
    session_id: str
    scenario_id: str
    turns: list[Turn] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    termination_reason: str = ""  # completed / max_turns_reached / error
    max_turns: int = 15

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def is_finished(self) -> bool:
        return self.termination_reason != "" or self.turn_count >= self.max_turns

    def to_conversation_text(self) -> str:
        """转为对话文本，用于 LLM 评测"""
        lines = []
        for t in self.turns:
            role = "Agent" if t.speaker == "agent" else "User"
            lines.append(f"[{role}]: {t.content}")
        return "\n".join(lines)

    def get_last_agent_turn(self) -> Optional[Turn]:
        for t in reversed(self.turns):
            if t.speaker == "agent":
                return t
        return None