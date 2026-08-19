"""
main_graph.py - LangGraph 工作流编排

工作流：
  用户输入 → PlannerAgent（规划拆解）→ 并行执行 CodeAgent / DocAgent
  → ReviewAgent（安全审核）→ 结果汇总输出

所有数据存储在 D 盘项目目录内，零 token 费用（本地 Ollama 模式）
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, TypedDict

import yaml
from langgraph.graph import END, StateGraph

from agents import CodeAgent, DocAgent, PlannerAgent, ReviewAgent

logger = logging.getLogger(__name__)


# ============================================================
# 工作流状态定义
# ============================================================
class WorkflowState(TypedDict, total=False):
    """LangGraph 工作流共享状态"""
    user_request: str
    plan: Dict[str, Any]
    code_results: List[Dict[str, Any]]
    doc_results: List[Dict[str, Any]]
    review_report: Dict[str, Any]
    final_output: Dict[str, Any]
    errors: List[str]
    execution_log: List[Dict[str, Any]]


# ============================================================
# 配置加载
# ============================================================
def load_config(config_path: str | None = None) -> Dict[str, Any]:
    """加载 config.yaml 配置文件"""
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.yaml"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# 工作流节点函数
# ============================================================
def planner_node(state: WorkflowState) -> WorkflowState:
    """
    PlannerAgent 节点：任务规划与拆解
    """
    logger.info("=== [节点] PlannerAgent 开始 ===")
    start_time = time.time()

    config = state.get("_config", {})
    planner = PlannerAgent(config)
    plan = planner.plan(state["user_request"])

    elapsed = time.time() - start_time
    log_entry = {
        "agent": "PlannerAgent",
        "status": "completed",
        "duration_seconds": round(elapsed, 2),
        "tasks_count": len(plan.get("tasks", [])),
    }

    logger.info(
        "PlannerAgent 完成，耗时 %.2fs，%d 个子任务",
        elapsed, len(plan.get("tasks", []))
    )

    return {
        "plan": plan,
        "execution_log": state.get("execution_log", []) + [log_entry],
    }


def code_execution_node(state: WorkflowState) -> WorkflowState:
    """
    CodeAgent 节点：执行所有 code 类型子任务
    """
    logger.info("=== [节点] CodeAgent 开始 ===")
    config = state.get("_config", {})
    code_agent = CodeAgent(config)

    plan = state.get("plan", {})
    tasks = plan.get("tasks", [])
    code_tasks = [t for t in tasks if t.get("agent") == "code"]

    results = []
    for task in code_tasks:
        start_time = time.time()
        try:
            result = code_agent.execute(task)
            result["duration_seconds"] = round(time.time() - start_time, 2)
            results.append(result)
        except Exception as e:
            logger.error("CodeAgent 任务执行异常: %s", e)
            results.append({
                "status": "error",
                "task": task.get("title", ""),
                "error": str(e),
                "files": [],
            })

    logger.info("CodeAgent 完成，执行 %d 个任务", len(code_tasks))

    return {
        "code_results": results,
    }


def doc_execution_node(state: WorkflowState) -> WorkflowState:
    """
    DocAgent 节点：执行所有 doc 类型子任务
    """
    logger.info("=== [节点] DocAgent 开始 ===")
    config = state.get("_config", {})
    doc_agent = DocAgent(config)

    plan = state.get("plan", {})
    tasks = plan.get("tasks", [])
    doc_tasks = [t for t in tasks if t.get("agent") == "doc"]

    # 构建上下文（传入已生成的代码文件信息）
    context = {"plan": plan}
    code_files = []
    for cr in state.get("code_results", []):
        for f in cr.get("files", []):
            if "error" not in f:
                code_files.append(f)
    context["code_files"] = code_files

    results = []
    for task in doc_tasks:
        start_time = time.time()
        try:
            result = doc_agent.execute(task, context=context)
            result["duration_seconds"] = round(time.time() - start_time, 2)
            results.append(result)
        except Exception as e:
            logger.error("DocAgent 任务执行异常: %s", e)
            results.append({
                "status": "error",
                "task": task.get("title", ""),
                "error": str(e),
                "documents": [],
            })

    logger.info("DocAgent 完成，执行 %d 个任务", len(doc_tasks))

    return {
        "doc_results": results,
    }


def review_node(state: WorkflowState) -> WorkflowState:
    """
    ReviewAgent 节点：安全审核与质量检查
    """
    logger.info("=== [节点] ReviewAgent 开始 ===")
    config = state.get("_config", {})
    review_agent = ReviewAgent(config)

    # 收集所有产物
    code_files = []
    for cr in state.get("code_results", []):
        for f in cr.get("files", []):
            code_files.append(f)

    documents = []
    for dr in state.get("doc_results", []):
        for d in dr.get("documents", []):
            filepath = d.get("saved_path", "")
            content = ""
            if filepath and os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            documents.append({
                "filename": d.get("filename", ""),
                "content": content,
            })

    artifacts = {
        "code_files": code_files,
        "documents": documents,
    }

    start_time = time.time()
    report = review_agent.execute(artifacts)
    elapsed = time.time() - start_time

    log_entry = {
        "agent": "ReviewAgent",
        "status": "completed",
        "duration_seconds": round(elapsed, 2),
        "final_recommendation": report.get("final_recommendation", "unknown"),
        "final_passed": report.get("final_passed", False),
    }

    logger.info(
        "ReviewAgent 完成，耗时 %.2fs，结论: %s",
        elapsed, report.get("final_recommendation")
    )

    return {
        "review_report": report,
        "execution_log": state.get("execution_log", []) + [log_entry],
    }


def summarize_node(state: WorkflowState) -> WorkflowState:
    """
    结果汇总节点
    """
    logger.info("=== [节点] 结果汇总 ===")

    plan = state.get("plan", {})
    code_results = state.get("code_results", [])
    doc_results = state.get("doc_results", [])
    review_report = state.get("review_report", {})

    # 统计生成的文件
    all_code_files = []
    for cr in code_results:
        for f in cr.get("files", []):
            all_code_files.append(f)

    all_documents = []
    for dr in doc_results:
        for d in dr.get("documents", []):
            all_documents.append(d)

    # 统计安全警告
    all_warnings = []
    for cr in code_results:
        all_warnings.extend(cr.get("security_warnings", []))

    final_output = {
        "goal": plan.get("goal", state.get("user_request", "")),
        "total_tasks": len(plan.get("tasks", [])),
        "code_tasks_completed": sum(
            1 for cr in code_results if cr.get("status") == "completed"
        ),
        "doc_tasks_completed": sum(
            1 for dr in doc_results if dr.get("status") == "completed"
        ),
        "generated_files": {
            "code": [
                {
                    "filename": f.get("filename"),
                    "path": f.get("saved_path"),
                    "size": f.get("size"),
                }
                for f in all_code_files
                if "error" not in f
            ],
            "documents": [
                {
                    "filename": d.get("filename"),
                    "path": d.get("saved_path"),
                    "size": d.get("size"),
                }
                for d in all_documents
            ],
        },
        "security_warnings": all_warnings,
        "review_result": {
            "passed": review_report.get("final_passed", False),
            "recommendation": review_report.get("final_recommendation", "unknown"),
            "report_path": os.path.join(
                state.get("_config", {}).get("paths", {}).get(
                    "output_dir", "D:/AI/Multi-Agent-Local-Workspace/output"
                ),
                "review_report.json",
            ),
        },
        "execution_log": state.get("execution_log", []),
    }

    logger.info("工作流完成，最终结果已汇总")
    return {"final_output": final_output}


# ============================================================
# 工作流构建
# ============================================================
def build_workflow(config: Dict[str, Any]) -> StateGraph:
    """
    构建 LangGraph 工作流

    流程：
      START → planner → [code_execution, doc_execution] → review → summarize → END

    注意：code 和 doc 并行执行（LangGraph 支持扇出/扇入）
    """
    workflow = StateGraph(WorkflowState)

    # 添加节点
    workflow.add_node("planner", planner_node)
    workflow.add_node("code_execution", code_execution_node)
    workflow.add_node("doc_execution", doc_execution_node)
    workflow.add_node("review", review_node)
    workflow.add_node("summarize", summarize_node)

    # 设置入口
    workflow.set_entry_point("planner")

    # planner → 并行 code + doc
    workflow.add_edge("planner", "code_execution")
    workflow.add_edge("planner", "doc_execution")

    # code + doc → review（扇入）
    workflow.add_edge("code_execution", "review")
    workflow.add_edge("doc_execution", "review")

    # review → summarize → END
    workflow.add_edge("review", "summarize")
    workflow.add_edge("summarize", END)

    return workflow


# ============================================================
# 工作流执行入口
# ============================================================
def run_workflow(
    user_request: str,
    config_path: str | None = None,
) -> Dict[str, Any]:
    """
    执行完整的多智能体工作流

    Args:
        user_request: 用户原始需求
        config_path: 配置文件路径（可选）

    Returns:
        最终输出字典
    """
    config = load_config(config_path)

    # 确保所有 D 盘目录存在
    for key in ("output_dir", "logs_dir", "vector_store_dir", "data_dir"):
        dir_path = config.get("paths", {}).get(key)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    # 构建并编译工作流
    workflow = build_workflow(config)
    app = workflow.compile()

    # 初始状态
    initial_state: WorkflowState = {
        "user_request": user_request,
        "_config": config,
        "code_results": [],
        "doc_results": [],
        "execution_log": [],
        "errors": [],
    }

    # 执行工作流
    logger.info("工作流开始执行，用户需求: %s", user_request[:100])
    final_state = app.invoke(initial_state)

    return final_state.get("final_output", {})


def stream_workflow(
    user_request: str,
    config_path: str | None = None,
):
    """
    流式执行工作流，逐节点产出结果（用于 WebUI 实时展示）

    Yields:
        每个节点执行后的状态快照
    """
    config = load_config(config_path)

    for key in ("output_dir", "logs_dir", "vector_store_dir", "data_dir"):
        dir_path = config.get("paths", {}).get(key)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    workflow = build_workflow(config)
    app = workflow.compile()

    initial_state: WorkflowState = {
        "user_request": user_request,
        "_config": config,
        "code_results": [],
        "doc_results": [],
        "execution_log": [],
        "errors": [],
    }

    for output in app.stream(initial_state):
        yield output


if __name__ == "__main__":
    # 命令行测试入口
    logging.basicConfig(level=logging.INFO)
    test_request = "写一个 Python 脚本，读取当前目录下的所有 txt 文件并统计字数，然后生成一份使用说明文档。"
    result = run_workflow(test_request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
