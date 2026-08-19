"""
PlannerAgent - 任务规划与拆解智能体

职责：
  1. 接收用户原始需求
  2. 拆解为可执行的子任务列表
  3. 为每个子任务分配目标 Agent（Code / Doc）
  4. 输出结构化任务计划
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


PLANNER_SYSTEM_PROMPT = """你是一个专业的任务规划智能体（PlannerAgent）。

你的职责是将用户的原始需求拆解为结构化、可执行的子任务列表。

## 工作规则
1. 仔细分析用户需求，识别需要完成的核心目标
2. 将大任务拆解为 3-8 个原子子任务，每个子任务应清晰、可独立执行
3. 为每个子任务分配合适的执行 Agent：
   - code: 需要编写/修改代码、脚本、配置文件
   - doc: 需要生成文档、说明、报告、README
4. 按执行顺序排列子任务，标注依赖关系
5. 输出严格的 JSON 格式，不要包含额外解释文字

## 输出格式（严格 JSON）
```json
{
  "goal": "总体目标描述",
  "tasks": [
    {
      "id": 1,
      "title": "子任务标题",
      "description": "详细描述",
      "agent": "code",
      "depends_on": [],
      "expected_output": "预期产物描述"
    }
  ]
}
```

## 注意事项
- 每个子任务必须有明确的预期输出
- code 类型任务的产物将写入沙盒目录 output/
- doc 类型任务生成文档文件
- 如果需求简单，子任务数量可以少，但至少 1 个
"""


class PlannerAgent:
    """任务规划智能体"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})
        self.agent_config = config.get("agents", {}).get("planner", {})
        self.max_iterations = self.agent_config.get("max_iterations", 3)
        self._llm = self._init_llm()

    def _init_llm(self):
        backend = self.llm_config.get("default_backend", "ollama")
        if backend == "openai":
            cfg = self.llm_config.get("openai", {})
            return ChatOpenAI(
                model=cfg.get("model", "gpt-4o-mini"),
                temperature=cfg.get("temperature", 0.7),
                max_tokens=cfg.get("max_tokens", 4096),
                base_url=cfg.get("base_url"),
                api_key=cfg.get("api_key"),
            )
        cfg = self.llm_config.get("ollama", {})
        return ChatOllama(
            model=cfg.get("model", "qwen2.5-7b-instruct"),
            base_url=cfg.get("base_url", "http://localhost:11434"),
            temperature=cfg.get("temperature", 0.7),
            num_predict=cfg.get("max_tokens", 4096),
            num_ctx=cfg.get("num_ctx", 8192),
        )

    def plan(self, user_request: str) -> Dict[str, Any]:
        """
        执行任务规划

        Args:
            user_request: 用户原始需求文本

        Returns:
            结构化任务计划字典
        """
        logger.info("PlannerAgent 开始规划任务: %s", user_request[:100])

        messages = [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=f"用户需求：\n{user_request}"),
        ]

        last_error = None
        for attempt in range(self.max_iterations):
            try:
                response = self._llm.invoke(messages)
                content = response.content.strip()

                # 提取 JSON（可能被 markdown 代码块包裹）
                plan = self._parse_json(content)
                if plan and "tasks" in plan:
                    logger.info(
                        "规划完成，共 %d 个子任务", len(plan["tasks"])
                    )
                    return plan

                last_error = "返回内容不是有效 JSON 或缺少 tasks 字段"
                messages.append(HumanMessage(
                    content=f"上一次输出格式错误：{last_error}\n"
                            f"请严格按照 JSON 格式重新输出。"
                ))
            except Exception as e:
                last_error = str(e)
                logger.warning("规划尝试 %d 失败: %s", attempt + 1, e)
                messages.append(HumanMessage(
                    content=f"调用出错：{e}\n请重试。"
                ))

        logger.error("规划失败，返回降级计划")
        return {
            "goal": user_request,
            "tasks": [
                {
                    "id": 1,
                    "title": "直接处理用户需求",
                    "description": user_request,
                    "agent": "code",
                    "depends_on": [],
                    "expected_output": "处理结果",
                }
            ],
            "warning": f"自动规划失败（{last_error}），使用降级计划",
        }

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any] | None:
        """从 LLM 输出中解析 JSON"""
        # 去除 markdown 代码块标记
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            content = content[start:end].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 尝试找到第一个 { 和最后一个 }
            first_brace = content.find("{")
            last_brace = content.rfind("}")
            if first_brace != -1 and last_brace != -1:
                try:
                    return json.loads(content[first_brace:last_brace + 1])
                except json.JSONDecodeError:
                    return None
            return None
