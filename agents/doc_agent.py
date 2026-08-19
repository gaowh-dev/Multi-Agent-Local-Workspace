"""
DocAgent - 文档生成智能体

职责：
  1. 根据任务描述生成文档（README / 技术文档 / 报告 / 说明）
  2. 支持 Markdown 格式输出
  3. 文档写入 output 沙盒目录
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


DOC_SYSTEM_PROMPT = """你是一个专业的文档生成智能体（DocAgent）。

你的职责是根据任务描述和已有信息，生成结构清晰、内容完整的技术文档。

## 工作规则
1. 仔细分析任务需求，确定文档类型和目标读者
2. 生成结构完整的 Markdown 文档，包含标题、章节、列表、代码块等
3. 文档应包含：概述、详细说明、使用方法、注意事项等必要部分
4. 语言简洁专业，避免冗余
5. 输出严格的 JSON 格式

## 输出格式（严格 JSON）
```json
{
  "documents": [
    {
      "filename": "README.md",
      "title": "文档标题",
      "content": "完整的 Markdown 文档内容...",
      "description": "文档用途说明"
    }
  ],
  "summary": "本次文档生成的简要说明"
}
```

## 文档质量要求
- 标题层级清晰（# / ## / ###）
- 包含必要的代码示例和配置说明
- 如有步骤，使用有序列表
- 关键信息使用加粗或引用块标注
"""


class DocAgent:
    """文档生成智能体"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})
        self.agent_config = config.get("agents", {}).get("doc", {})
        self.max_iterations = self.agent_config.get("max_iterations", 3)
        self.output_dir = config.get("paths", {}).get(
            "output_dir", "D:/AI/Multi-Agent-Local-Workspace/output"
        )
        os.makedirs(self.output_dir, exist_ok=True)
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

    def execute(
        self,
        task: Dict[str, Any],
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        执行文档生成任务

        Args:
            task: 子任务字典
            context: 可选的上下文信息（如已生成的代码文件列表）

        Returns:
            执行结果字典
        """
        task_title = task.get("title", "未命名文档任务")
        task_desc = task.get("description", "")
        logger.info("DocAgent 开始执行: %s", task_title)

        context_text = ""
        if context:
            context_text = "\n\n## 参考上下文\n"
            if "code_files" in context:
                context_text += "已生成的代码文件：\n"
                for f in context["code_files"]:
                    context_text += f"- {f.get('filename', '?')}: {f.get('description', '')}\n"
            if "plan" in context:
                context_text += f"总体目标：{context['plan'].get('goal', '')}\n"

        messages = [
            SystemMessage(content=DOC_SYSTEM_PROMPT),
            HumanMessage(
                content=f"文档任务标题：{task_title}\n"
                        f"任务描述：{task_desc}\n"
                        f"预期输出：{task.get('expected_output', '')}"
                        f"{context_text}"
            ),
        ]

        last_error = None
        for attempt in range(self.max_iterations):
            try:
                response = self._llm.invoke(messages)
                content = response.content.strip()
                parsed = self._parse_json(content)

                if not parsed or "documents" not in parsed:
                    last_error = "返回内容不是有效 JSON 或缺少 documents 字段"
                    messages.append(HumanMessage(
                        content=f"格式错误：{last_error}\n请严格按 JSON 格式输出。"
                    ))
                    continue

                written_docs = []
                for doc in parsed["documents"]:
                    filename = doc.get("filename", "document.md")
                    doc_content = doc.get("content", "")

                    # 写入 output 目录
                    filepath = os.path.join(self.output_dir, filename)
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(doc_content)

                    written_docs.append({
                        "filename": filename,
                        "saved_path": filepath,
                        "title": doc.get("title", ""),
                        "size": len(doc_content),
                        "description": doc.get("description", ""),
                    })
                    logger.info("DocAgent 写入文档: %s", filepath)

                return {
                    "status": "completed",
                    "task": task_title,
                    "documents": written_docs,
                    "summary": parsed.get("summary", ""),
                }

            except Exception as e:
                last_error = str(e)
                logger.warning("DocAgent 尝试 %d 失败: %s", attempt + 1, e)
                messages.append(HumanMessage(
                    content=f"执行出错：{e}\n请重试。"
                ))

        return {
            "status": "failed",
            "task": task_title,
            "error": last_error,
            "documents": [],
        }

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any] | None:
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
            first = content.find("{")
            last = content.rfind("}")
            if first != -1 and last != -1:
                try:
                    return json.loads(content[first:last + 1])
                except json.JSONDecodeError:
                    return None
            return None
