"""FastAPI 应用入口：提供 /run_eval, /scenarios, /report 等 API 端点."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.config import settings
from src.models.scenario import ScenarioGenerateRequest, TaskType, UserPersona, Difficulty
from src.models.dialogue import DialogueSession
from src.models.evaluation import EvalReport, AggregateStats
from src.scenario.generator import ScenarioGenerator
from src.orchestration.graph import DialogueOrchestrator
from src.evaluation.scorer import Scorer

app = FastAPI(
    title="外呼多轮对话评测系统",
    description="复杂外呼场景多轮对话自动化评测系统 MVP",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内存存储（MVP 阶段）
_reports: dict[str, EvalReport] = {}
_dialogues: dict[str, DialogueSession] = {}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "outbound-eval-system"}


@app.get("/scenarios")
async def list_scenarios():
    """列出可用的场景类型、用户画像和难度"""
    return {
        "task_types": ScenarioGenerator.list_available_task_types(),
        "user_personas": ScenarioGenerator.list_available_personas(),
        "difficulties": ScenarioGenerator.list_available_difficulties(),
    }


@app.post("/run_eval")
async def run_evaluation(request: ScenarioGenerateRequest):
    """
    运行一次完整的评测。

    流程：场景生成 → 多轮对话 → 自动评分 → 返回报告
    """
    # 1. 生成场景
    try:
        scenario = ScenarioGenerator.generate(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. 运行多轮对话
    orchestrator = DialogueOrchestrator(scenario, max_turns=settings.max_turns)
    dialogue = orchestrator.run()

    # 3. 评分
    scorer = Scorer(scenario)
    report = scorer.evaluate_with_failure(dialogue)

    # 4. 存储
    _reports[report.session_id] = report
    _dialogues[report.session_id] = dialogue

    return {
        "session_id": report.session_id,
        "scenario": {
            "task_type": scenario.task_type.value,
            "user_persona": scenario.user_persona.value,
            "difficulty": scenario.difficulty.value,
        },
        "dialogue": {
            "turn_count": dialogue.turn_count,
            "termination_reason": dialogue.termination_reason,
            "conversation": dialogue.to_conversation_text(),
        },
        "report": report.model_dump(),
    }


@app.get("/report/{session_id}")
async def get_report(session_id: str):
    """获取指定 session 的评测报告"""
    report = _reports.get(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    dialogue = _dialogues.get(session_id)
    return {
        "report": report.model_dump(),
        "dialogue": dialogue.to_conversation_text() if dialogue else "",
    }


@app.get("/stats")
async def get_stats():
    """获取汇总统计"""
    if not _reports:
        return AggregateStats()

    reports = list(_reports.values())
    total = len(reports)

    success_count = sum(
        1 for r in reports
        if r.rule_eval and r.rule_eval.task_completed
    )

    avg_score = sum(r.overall_score for r in reports) / total

    # 维度平均
    dim_avgs: dict[str, float] = {}
    for r in reports:
        for ds in r.dimension_scores:
            key = ds.dimension.value
            dim_avgs[key] = dim_avgs.get(key, 0) + ds.score
    for k in dim_avgs:
        dim_avgs[k] = dim_avgs[k] / total

    # 失败分布
    failure_dist: dict[str, int] = {}
    for r in reports:
        if r.failure_analysis:
            for ft in r.failure_analysis.failure_types:
                key = ft.value
                failure_dist[key] = failure_dist.get(key, 0) + 1

    return AggregateStats(
        total_sessions=total,
        success_rate=success_count / total if total > 0 else 0,
        avg_overall_score=avg_score,
        dimension_averages=dim_avgs,
        failure_distribution=failure_dist,
    )


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, reload=True)