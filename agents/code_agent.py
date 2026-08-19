"""
CodeAgent - 代码生成与沙盒执行智能体

职责：
  1. 根据子任务描述生成代码/脚本/配置文件
  2. 强制路径沙盒防护：仅允许读写 D:/AI/Multi-Agent-Local-Workspace/output
  3. 拦截所有 C 盘与系统目录访问
  4. 文件写入前进行路径白名单校验
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


CODE_SYSTEM_PROMPT = """你是一个专业的代码生成智能体（CodeAgent）。

你的职责是根据任务描述生成高质量、可运行的代码文件。

## 工作规则
1. 仔细阅读任务描述，理解需要实现的功能
2. 生成完整、可直接运行的代码，不要只给片段
3. 代码必须包含必要的注释和错误处理
4. 输出严格的 JSON 格式，包含文件名和文件内容
5. 文件名使用相对路径，将被写入沙盒目录

## 输出格式（严格 JSON）
```json
{
  "files": [
    {
      "filename": "main.py",
      "content": "完整的文件内容...",
      "description": "文件用途说明"
    }
  ],
  "summary": "本次生成的简要说明"
}
```

## 安全约束
- 禁止生成访问 C 盘或系统目录的代码
- 禁止生成删除系统文件、修改注册表的代码
- 禁止生成包含恶意代码、病毒、挖矿程序的内容
- 所有文件操作应使用相对路径
"""


class SandboxViolationError(Exception):
    """沙盒违规异常"""
    pass


class PathSandbox:
    """
    强制路径沙盒防护
    仅允许读写指定根目录，拦截 C 盘与系统目录
    """

    def __init__(self, config: Dict[str, Any]):
        sandbox_cfg = config.get("sandbox", {})
        self.allowed_root = os.path.abspath(
            sandbox_cfg.get(
                "allowed_root",
                "D:/AI/Multi-Agent-Local-Workspace/output"
            )
        )
        self.blocked_drives = [
            d.upper() for d in sandbox_cfg.get("blocked_drives", ["C:"])
        ]
        self.blocked_paths = [
            os.path.normpath(p) for p in sandbox_cfg.get("blocked_paths", [])
        ]
        self.max_file_size = sandbox_cfg.get("max_file_size_mb", 50) * 1024 * 1024
        self.allowed_extensions = set(
            ext.lower() for ext in sandbox_cfg.get("allowed_extensions", [])
        )

        # 确保沙盒根目录存在
        os.makedirs(self.allowed_root, exist_ok=True)
        logger.info("路径沙盒已初始化，允许根目录: %s", self.allowed_root)

    def validate_path(self, filepath: str) -> str:
        """
        校验文件路径是否在沙盒允许范围内

        Args:
            filepath: 待校验的文件路径（相对或绝对）

        Returns:
            校验通过后的绝对路径

        Raises:
            SandboxViolationError: 路径违规时抛出
        """
        # 转为绝对路径
        if os.path.isabs(filepath):
            abs_path = os.path.abspath(filepath)
        else:
            abs_path = os.path.abspath(os.path.join(self.allowed_root, filepath))

        # 规范化路径
        abs_path = os.path.normpath(abs_path)

        # 检查盘符
        drive = os.path.splitdrive(abs_path)[0].upper()
        if drive in self.blocked_drives:
            raise SandboxViolationError(
                f"禁止访问被拦截的盘符: {drive}（路径: {abs_path}）"
            )

        # 检查是否在允许根目录下
        if not abs_path.startswith(self.allowed_root):
            raise SandboxViolationError(
                f"路径超出沙盒范围: {abs_path}\n"
                f"允许的根目录: {self.allowed_root}"
            )

        # 检查是否命中系统目录黑名单
        for blocked in self.blocked_paths:
            if abs_path.lower().startswith(blocked.lower()):
                raise SandboxViolationError(
                    f"禁止访问系统目录: {blocked}（路径: {abs_path}）"
                )

        # 检查文件扩展名
        ext = os.path.splitext(abs_path)[1].lower()
        if self.allowed_extensions and ext not in self.allowed_extensions:
            raise SandboxViolationError(
                f"不允许的文件扩展名: {ext}（路径: {abs_path}）"
            )

        # 防止路径穿越（..）
        if ".." in abs_path.replace(self.allowed_root, "", 1):
            # 二次检查：解析后的路径是否仍在根目录内
            real_path = os.path.realpath(abs_path)
            if not real_path.startswith(os.path.realpath(self.allowed_root)):
                raise SandboxViolationError(
                    f"检测到路径穿越攻击: {abs_path}"
                )

        return abs_path

    def scan_code_for_violations(self, code: str) -> List[str]:
        """
        扫描代码内容中是否包含危险路径操作

        Args:
            code: 代码文本

        Returns:
            违规警告列表
        """
        warnings = []
        dangerous_patterns = [
            (r'["\']C:[\\/]', "引用了 C 盘绝对路径"),
            (r'["\']/etc/', "引用了 /etc 系统目录"),
            (r'["\']/usr/', "引用了 /usr 系统目录"),
            (r'["\']/var/', "引用了 /var 系统目录"),
            (r'["\']/root/', "引用了 /root 目录"),
            (r'["\']/home/', "引用了 /home 目录"),
            (r'shutil\.rmtree', "使用了 shutil.rmtree 递归删除"),
            (r'os\.system\s*\(', "使用了 os.system 命令执行"),
            (r'subprocess\.(call|run|Popen)', "使用了 subprocess 执行外部命令"),
            (r'eval\s*\(', "使用了 eval 动态执行"),
            (r'exec\s*\(', "使用了 exec 动态执行"),
            (r'__import__', "使用了 __import__ 动态导入"),
        ]

        for pattern, desc in dangerous_patterns:
            if re.search(pattern, code):
                warnings.append(f"[潜在风险] {desc}: 匹配模式 {pattern}")

        return warnings

    def write_file(self, filename: str, content: str) -> str:
        """
        在沙盒内写入文件

        Args:
            filename: 文件名（相对沙盒根目录）
            content: 文件内容

        Returns:
            写入后的绝对路径
        """
        # 校验路径
        safe_path = self.validate_path(filename)

        # 检查文件大小
        content_size = len(content.encode("utf-8", errors="replace"))
        if content_size > self.max_file_size:
            raise SandboxViolationError(
                f"文件大小 {content_size} 字节超过限制 {self.max_file_size} 字节"
            )

        # 确保父目录存在
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)

        # 写入文件
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("沙盒写入文件: %s (%d 字节)", safe_path, content_size)
        return safe_path

    def read_file(self, filename: str) -> str:
        """在沙盒内读取文件"""
        safe_path = self.validate_path(filename)
        if not os.path.exists(safe_path):
            raise FileNotFoundError(f"文件不存在: {safe_path}")
        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_files(self) -> List[str]:
        """列出沙盒内所有文件"""
        result = []
        for root, dirs, files in os.walk(self.allowed_root):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, self.allowed_root)
                result.append(rel)
        return sorted(result)


class CodeAgent:
    """代码生成智能体（带强制沙盒防护）"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})
        self.agent_config = config.get("agents", {}).get("code", {})
        self.max_iterations = self.agent_config.get("max_iterations", 5)
        self.sandbox = PathSandbox(config)
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

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行代码生成任务

        Args:
            task: 子任务字典，包含 title / description / expected_output

        Returns:
            执行结果字典
        """
        task_title = task.get("title", "未命名任务")
        task_desc = task.get("description", "")
        logger.info("CodeAgent 开始执行: %s", task_title)

        messages = [
            SystemMessage(content=CODE_SYSTEM_PROMPT),
            HumanMessage(
                content=f"任务标题：{task_title}\n"
                        f"任务描述：{task_desc}\n"
                        f"预期输出：{task.get('expected_output', '')}"
            ),
        ]

        last_error = None
        for attempt in range(self.max_iterations):
            try:
                response = self._llm.invoke(messages)
                content = response.content.strip()
                parsed = self._parse_json(content)

                if not parsed or "files" not in parsed:
                    last_error = "返回内容不是有效 JSON 或缺少 files 字段"
                    messages.append(HumanMessage(
                        content=f"格式错误：{last_error}\n请严格按 JSON 格式输出。"
                    ))
                    continue

                # 写入沙盒并收集结果
                written_files = []
                security_warnings = []

                for file_info in parsed["files"]:
                    filename = file_info.get("filename", "untitled.txt")
                    file_content = file_info.get("content", "")

                    # 扫描代码中的危险模式
                    warnings = self.sandbox.scan_code_for_violations(file_content)
                    if warnings:
                        security_warnings.extend(
                            f"{filename}: {w}" for w in warnings
                        )
                        logger.warning(
                            "文件 %s 存在安全警告: %s", filename, warnings
                        )

                    # 沙盒写入（路径校验在此处强制执行）
                    try:
                        saved_path = self.sandbox.write_file(
                            filename, file_content
                        )
                        written_files.append({
                            "filename": filename,
                            "saved_path": saved_path,
                            "size": len(file_content),
                            "description": file_info.get("description", ""),
                        })
                    except SandboxViolationError as e:
                        logger.error("沙盒拦截文件写入: %s - %s", filename, e)
                        written_files.append({
                            "filename": filename,
                            "error": f"沙盒拦截: {e}",
                            "status": "blocked",
                        })

                logger.info(
                    "CodeAgent 完成: 写入 %d 个文件, %d 条安全警告",
                    len(written_files), len(security_warnings)
                )

                return {
                    "status": "completed",
                    "task": task_title,
                    "files": written_files,
                    "summary": parsed.get("summary", ""),
                    "security_warnings": security_warnings,
                }

            except Exception as e:
                last_error = str(e)
                logger.warning("CodeAgent 尝试 %d 失败: %s", attempt + 1, e)
                messages.append(HumanMessage(
                    content=f"执行出错：{e}\n请重试。"
                ))

        return {
            "status": "failed",
            "task": task_title,
            "error": last_error,
            "files": [],
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
