"""LangGraph 编排模块：串联 Scenario → Simulator ↔ Agent 的多轮对话流程.

Graph 结构:
    START → agent_turn → user_turn → [check_termination]
                  ↑                             ↓
                  └────── (continue) ←──── [not finished]
                                                 ↓ (finished)
                                            TERMINATE
"""

import uuid
from typing import TypedDict, Annotated
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.models.scenario import ScenarioConfig
from src.models.dialogue import DialogueSession, Turn
from src.simulator.user_simulator import UserSimulator
from src.agent.outbound_agent import OutboundAgent


class OrchestrationState(TypedDict):
    """编排状态"""
    session_id: str
    scenario: ScenarioConfig
    dialogue: DialogueSession
    agent_turn: str  # 当前轮 Agent 回复
    user_turn: str  # 当前轮用户回复
    current_speaker: str  # agent / user
    should_terminate: bool
    termination_reason: str
    turn_count: int


class DialogueOrchestrator:
    """对话编排器"""

    def __init__(self, scenario: ScenarioConfig, max_turns: int = 15):
        self.scenario = scenario
        self.max_turns = max_turns
        self.simulator = UserSimulator(scenario)
        self.agent = OutboundAgent(scenario)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 状态图"""
        builder = StateGraph(OrchestrationState)

        # 添加节点
        builder.add_node("agent_turn", self._agent_turn_node)
        builder.add_node("user_turn", self._user_turn_node)
        builder.add_node("check_termination", self._check_termination_node)

        # 边: START -> agent_turn (Agent 先说第一句话)
        builder.set_entry_point("agent_turn")

        # agent_turn -> user_turn
        builder.add_edge("agent_turn", "user_turn")

        # user_turn -> check_termination
        builder.add_edge("user_turn", "check_termination")

        # check_termination -> agent_turn (继续) 或 END (结束)
        builder.add_conditional_edges(
            "check_termination",
            self._should_continue,
            {
                "continue": "agent_turn",
                "end": END,
            },
        )

        return builder.compile(checkpointer=MemorySaver())

    def _agent_turn_node(self, state: OrchestrationState) -> OrchestrationState:
        """Agent 发言节点"""
        dialogue = state["dialogue"]
        user_message = state.get("user_turn", "")

        # Agent 生成回复（第一轮时 user_message 为空）
        turn = self.agent.respond(user_message, dialogue.turns)
        dialogue.turns.append(turn)

        state["agent_turn"] = turn.content
        state["current_speaker"] = "agent"
        state["turn_count"] = dialogue.turn_count
        return state

    def _user_turn_node(self, state: OrchestrationState) -> OrchestrationState:
        """用户发言节点"""
        dialogue = state["dialogue"]
        agent_message = state["agent_turn"]

        # 用户生成回复
        turn = self.simulator.respond(agent_message, dialogue.turns)
        dialogue.turns.append(turn)

        state["user_turn"] = turn.content
        state["current_speaker"] = "user"
        state["turn_count"] = dialogue.turn_count
        return state

    def _check_termination_node(self, state: OrchestrationState) -> OrchestrationState:
        """检查终止条件"""
        dialogue = state["dialogue"]

        # 条件1: 达到最大轮数
        if dialogue.turn_count >= self.max_turns:
            state["should_terminate"] = True
            state["termination_reason"] = "max_turns_reached"
            dialogue.termination_reason = "max_turns_reached"
            dialogue.finished_at = datetime.now()
            return state

        # 条件2: Agent 判断任务完成
        if self.agent.is_task_completed():
            state["should_terminate"] = True
            state["termination_reason"] = "task_completed"
            dialogue.termination_reason = "task_completed"
            dialogue.finished_at = datetime.now()
            return state

        # 条件3: 用户多次拒绝
        if self.agent.should_terminate():
            state["should_terminate"] = True
            state["termination_reason"] = "user_rejected"
            dialogue.termination_reason = "user_rejected"
            dialogue.finished_at = datetime.now()
            return state

        state["should_terminate"] = False
        state["termination_reason"] = ""
        return state

    def _should_continue(self, state: OrchestrationState) -> str:
        return "end" if state["should_terminate"] else "continue"

    def run(self) -> DialogueSession:
        """运行一次完整对话评测"""
        session_id = str(uuid.uuid4())[:8]
        initial_state: OrchestrationState = {
            "session_id": session_id,
            "scenario": self.scenario,
            "dialogue": DialogueSession(
                session_id=session_id,
                scenario_id=f"{self.scenario.task_type.value}_{self.scenario.user_persona.value}",
                max_turns=self.max_turns,
                started_at=datetime.now(),
            ),
            "agent_turn": "",
            "user_turn": "",
            "current_speaker": "agent",
            "should_terminate": False,
            "termination_reason": "",
            "turn_count": 0,
        }

        result = self.graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}},
        )
        return result["dialogue"]