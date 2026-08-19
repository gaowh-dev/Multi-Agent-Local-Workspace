"""
ReviewAgent - 安全审核与质量检查智能体

职责：
  1. 对 CodeAgent 生成的代码进行安全审核
  2. 检查代码质量、潜在漏洞、依赖风险
  3. 对 DocAgent 生成的文档进行质量检查
  4. 输出审核报告，必要时要求修正
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


REVIEW_SYSTEM_PROMPT = """你是一个专业的安全审核与质量检查智能体（ReviewAgent）。

你的职责是对其他 Agent 生成的代码和文档进行严格审核，确保安全性和质量。

## 审核维度

### 代码安全审核
1. **路径安全**：是否存在路径穿越、访问系统目录、C 盘访问
2. **命令注入**：是否存在 os.system / subprocess 调用用户输入
3. **代码注入**：是否存在 eval / exec 动态执行
4. **文件操作**：是否存在危险的删除、覆盖操作
5. **敏感信息**：是否硬编码密码、密钥、Token
6. **依赖风险**：是否引入已知有漏洞的第三方库
7. **资源耗尽**：是否存在无限循环、内存泄漏风险

### 代码质量检查
1. 代码结构是否清晰、模块化
2. 是否有适当的错误处理和异常捕获
3. 是否有必要的注释和文档字符串
4. 命名规范是否一致
5. 是否存在明显的逻辑错误

### 文档质量检查
1. 文档结构是否完整
2. 内容是否准确、无歧义
3. 是否包含必要的使用说明和示例
4. 格式是否规范

## 输出格式（严格 JSON）
```json
{
  "overall_score": 85,
  "passed": true,
  "security_issues": [
    {
      "severity": "high",
      "location": "main.py:42",
      "issue": "问题描述",
      "suggestion": "修复建议"
    }
  ],
  "quality_issues": [
    {
      "severity": "medium",
      "location": "main.py:15",
      "issue": "问题描述",
      "suggestion": "改进建议"
    }
  ],
  "summary": "审核总结",
  "recommendation": "approve / revise / reject"
}
```

## 评分标准
- 90-100: 优秀，可直接通过
- 70-89: 良好，有小问题建议改进
- 50-69: 一般，需要修改后重新审核
- 0-49: 不合格，必须重新生成

recommendation 字段：
- approve: 通过，无严重问题
- revise: 需要修改，存在中等问题
- reject: 拒绝，存在严重安全问题
"""


# 静态安全规则（不依赖 LLM，强制执行）
STATIC_SECURITY_RULES = [
    {
        "pattern": r'["\']C:[\\/]',
        "severity": "high",
        "issue": "硬编码 C 盘绝对路径",
        "suggestion": "使用相对路径或从配置文件读取路径，禁止直接访问 C 盘",
    },
    {
        "pattern": r'os\.system\s*\(',
        "severity": "high",
        "issue": "使用 os.system 执行系统命令",
        "suggestion": "避免使用 os.system，如需执行命令请使用 subprocess 并严格校验参数",
    },
    {
        "pattern": r'eval\s*\(',
        "severity": "critical",
        "issue": "使用 eval 动态执行代码",
        "suggestion": "禁止使用 eval，使用 ast.literal_eval 或显式解析替代",
    },
    {
        "pattern": r'exec\s*\(',
        "severity": "critical",
        "issue": "使用 exec 动态执行代码",
        "suggestion": "禁止使用 exec，重构为显式函数调用",
    },
    {
        "pattern": r'shutil\.rmtree',
        "severity": "high",
        "issue": "使用 shutil.rmtree 递归删除目录",
        "suggestion": "避免递归删除，如需删除请严格校验路径在沙盒内",
    },
    {
        "pattern": r'(password|passwd|pwd|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
        "severity": "high",
        "issue": "硬编码敏感信息（密码/密钥/Token）",
        "suggestion": "使用环境变量或配置文件管理敏感信息，不要硬编码",
    },
    {
        "pattern": r'pickle\.load',
        "severity": "high",
        "issue": "使用 pickle.load 反序列化不可信数据",
        "suggestion": "禁止对不可信数据使用 pickle，使用 JSON 等安全格式",
    },
    {
        "pattern": r'subprocess\.(call|run|Popen)\([^)]*shell\s*=\s*True',
        "severity": "critical",
        "issue": "subprocess 使用 shell=True 存在命令注入风险",
        "suggestion": "设置 shell=False，使用参数列表形式传递命令",
    },
    {
        "pattern": r'__import__\s*\(',
        "severity": "medium",
        "issue": "使用 __import__ 动态导入模块",
        "suggestion": "使用 importlib.import_module 并校验模块名白名单",
    },
]


class ReviewAgent:
    """安全审核与质量检查智能体"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})
        self.agent_config = config.get("agents", {}).get("review", {})
        self.max_iterations = self.agent_config.get("max_iterations", 3)
        self.security_check = self.agent_config.get("security_check", True)
        self.quality_check = self.agent_config.get("quality_check", True)
        self.output_dir = config.get("paths", {}).get(
            "output_dir", "D:/AI/Multi-Agent-Local-Workspace/output"
        )
        self._llm = self._init_llm()

    def _init_llm(self):
        backend = self.llm_config.get("default_backend", "ollama")
        if backend == "openai":
            cfg = self.llm_config.get("openai", {})
            return ChatOpenAI(
                model=cfg.get("model", "gpt-4o-mini"),
                temperature=cfg.get("temperature", 0.3),
                max_tokens=cfg.get("max_tokens", 4096),
                base_url=cfg.get("base_url"),
                api_key=cfg.get("api_key"),
            )
        cfg = self.llm_config.get("ollama", {})
        return ChatOllama(
            model=cfg.get("model", "qwen2.5-7b-instruct"),
            base_url=cfg.get("base_url", "http://localhost:11434"),
            temperature=0.3,
            num_predict=cfg.get("max_tokens", 4096),
            num_ctx=cfg.get("num_ctx", 8192),
        )

    def static_scan(self, code: str, filename: str = "") -> List[Dict[str, Any]]:
        """
        静态安全扫描（强制执行，不依赖 LLM）

        Args:
            code: 代码内容
            filename: 文件名（用于报告定位）

        Returns:
            安全问题列表
        """
        issues = []
        for rule in STATIC_SECURITY_RULES:
            matches = re.finditer(rule["pattern"], code, re.IGNORECASE)
            for match in matches:
                # 计算行号
                line_num = code[:match.start()].count("\n") + 1
                issues.append({
                    "severity": rule["severity"],
                    "location": f"{filename}:{line_num}",
                    "issue": rule["issue"],
                    "suggestion": rule["suggestion"],
                    "matched_text": match.group()[:80],
                })
        return issues

    def review_code(
        self,
        code: str,
        filename: str = "",
        task_context: str = "",
    ) -> Dict[str, Any]:
        """
        对代码进行完整审核（静态扫描 + LLM 智能审核）

        Args:
            code: 代码内容
            filename: 文件名
            task_context: 任务上下文

        Returns:
            审核报告
        """
        logger.info("ReviewAgent 开始审核代码: %s", filename)

        # 1. 强制执行静态扫描
        static_issues = self.static_scan(code, filename)

        # 2. LLM 智能审核
        llm_issues = []
        llm_summary = ""
        overall_score = 100
        recommendation = "approve"

        try:
            messages = [
                SystemMessage(content=REVIEW_SYSTEM_PROMPT),
                HumanMessage(
                    content=f"请审核以下代码文件：\n\n"
                            f"文件名：{filename}\n"
                            f"任务上下文：{task_context}\n\n"
                            f"代码内容：\n```python\n{code}\n```\n\n"
                            f"已知静态扫描发现 {len(static_issues)} 个问题，"
                            f"请在此基础上进行全面审核。"
                ),
            ]
            response = self._llm.invoke(messages)
            parsed = self._parse_json(response.content.strip())

            if parsed:
                overall_score = parsed.get("overall_score", 80)
                recommendation = parsed.get("recommendation", "approve")
                llm_summary = parsed.get("summary", "")
                llm_issues = parsed.get("security_issues", []) + parsed.get(
                    "quality_issues", []
                )
        except Exception as e:
            logger.warning("LLM 审核失败，仅使用静态扫描结果: %s", e)
            llm_summary = f"LLM 审核不可用，仅完成静态扫描: {e}"

        # 3. 合并结果
        all_issues = static_issues + llm_issues

        # 4. 根据静态扫描结果强制调整审核结论
        critical_count = sum(
            1 for i in static_issues if i["severity"] == "critical"
        )
        high_count = sum(
            1 for i in static_issues if i["severity"] == "high"
        )

        if critical_count > 0:
            recommendation = "reject"
            overall_score = min(overall_score, 30)
        elif high_count > 0:
            recommendation = "revise"
            overall_score = min(overall_score, 60)

        passed = recommendation == "approve"

        report = {
            "filename": filename,
            "overall_score": overall_score,
            "passed": passed,
            "recommendation": recommendation,
            "security_issues": [
                i for i in all_issues
                if i.get("severity") in ("critical", "high")
            ],
            "quality_issues": [
                i for i in all_issues
                if i.get("severity") in ("medium", "low")
            ],
            "static_scan_count": len(static_issues),
            "llm_scan_count": len(llm_issues),
            "summary": llm_summary,
        }

        logger.info(
            "审核完成: %s - 评分 %d, 结论 %s",
            filename, overall_score, recommendation
        )
        return report

    def review_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        对文档进行质量审核

        Args:
            documents: 文档列表，每个包含 filename 和 content

        Returns:
            审核报告
        """
        logger.info("ReviewAgent 开始审核文档，共 %d 份", len(documents))

        doc_reviews = []
        for doc in documents:
            filename = doc.get("filename", "")
            content = doc.get("content", "")

            # 基础质量检查
            issues = []
            if len(content) < 50:
                issues.append({
                    "severity": "medium",
                    "issue": "文档内容过短",
                    "suggestion": "补充更多详细说明和示例",
                })
            if not re.search(r'^#{1,3}\s', content, re.MULTILINE):
                issues.append({
                    "severity": "low",
                    "issue": "文档缺少标题层级",
                    "suggestion": "使用 # / ## / ### 组织文档结构",
                })

            score = max(60, 100 - len(issues) * 15)
            doc_reviews.append({
                "filename": filename,
                "score": score,
                "issues": issues,
                "passed": score >= 70,
            })

        return {
            "documents_reviewed": len(doc_reviews),
            "all_passed": all(d["passed"] for d in doc_reviews),
            "details": doc_reviews,
        }

    def execute(
        self,
        artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        执行完整审核流程

        Args:
            artifacts: 包含 code_files 和 documents 的字典

        Returns:
            综合审核报告
        """
        logger.info("ReviewAgent 开始综合审核")

        code_reports = []
        code_files = artifacts.get("code_files", [])

        for cf in code_files:
            if "error" in cf or cf.get("status") == "blocked":
                code_reports.append({
                    "filename": cf.get("filename", ""),
                    "overall_score": 0,
                    "passed": False,
                    "recommendation": "reject",
                    "summary": f"文件被沙盒拦截或写入失败: {cf.get('error', '')}",
                })
                continue

            filepath = cf.get("saved_path", "")
            if filepath and os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    code = f.read()
                report = self.review_code(
                    code,
                    filename=cf.get("filename", ""),
                    task_context=cf.get("description", ""),
                )
                code_reports.append(report)

        # 文档审核
        doc_report = self.review_documents(
            artifacts.get("documents", [])
        )

        # 综合结论
        all_code_passed = all(r["passed"] for r in code_reports) if code_reports else True
        all_doc_passed = doc_report.get("all_passed", True)

        final_passed = all_code_passed and all_doc_passed
        final_recommendation = "approve" if final_passed else (
            "reject" if any(r["recommendation"] == "reject" for r in code_reports)
            else "revise"
        )

        # 保存审核报告
        report_path = os.path.join(self.output_dir, "review_report.json")
        full_report = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "final_passed": final_passed,
            "final_recommendation": final_recommendation,
            "code_reviews": code_reports,
            "document_review": doc_report,
        }
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(full_report, f, ensure_ascii=False, indent=2)

        logger.info(
            "综合审核完成: %s, 报告已保存至 %s",
            final_recommendation, report_path
        )

        return full_report

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
