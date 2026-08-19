"""
app.py - Streamlit WebUI 界面

Multi-Agent-Local-Workspace 可视化交互界面
启动命令: streamlit run app.py
访问地址: http://localhost:8501
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, Dict, List

# --- Disable proxy for local requests ---
import urllib.request
urllib.request.getproxies = lambda: {}
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import streamlit as st
import yaml

from main_graph import load_config, stream_workflow


# ============================================================
# 日志配置
# ============================================================
def setup_logging(config):
    log_cfg = config.get("logging", {})
    log_file = log_cfg.get("file", "D:/AI/Multi-Agent-Local-Workspace/logs/workspace.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, log_cfg.get("level", "INFO")),
        format=log_cfg.get("format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
CONFIG = load_config(CONFIG_PATH)
setup_logging(CONFIG)

OUTPUT_DIR = CONFIG.get("paths", {}).get(
    "output_dir", "D:/AI/Multi-Agent-Local-Workspace/output"
)


# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="Multi-Agent Local Workspace",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 Multi-Agent Local Workspace")
st.markdown("**本地多智能体协作平台 | 零 Token 费用 | 数据全部存储 D 盘**")
st.markdown("PlannerAgent（规划）→ CodeAgent（代码沙盒）→ DocAgent（文档）→ ReviewAgent（安全审核）")

# 侧边栏配置信息
with st.sidebar:
    st.header("⚙️ 当前配置")
    st.write(f"- **LLM 后端**: {CONFIG.get('llm', {}).get('default_backend', 'ollama')}")
    st.write(f"- **模型**: {CONFIG.get('llm', {}).get('ollama', {}).get('model', '')}")
    st.write(f"- **输出目录**: `{OUTPUT_DIR}`")
    st.write(f"- **沙盒根目录**: `{CONFIG.get('sandbox', {}).get('allowed_root', '')}`")
    st.divider()
    st.markdown("### 硬件提示")
    st.caption("确保 Ollama 服务已启动，模型已拉取: `ollama pull qwen2.5-7b-instruct`")


# ============================================================
# 辅助函数
# ============================================================
def list_output_files() -> List[str]:
    files = []
    if os.path.exists(OUTPUT_DIR):
        for root, dirs, filenames in os.walk(OUTPUT_DIR):
            for f in filenames:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, OUTPUT_DIR)
                files.append(rel)
    return sorted(files)


def read_output_file(filename: str) -> str:
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return f"文件不存在: {filepath}"
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"读取失败: {e}"


def format_summary(output: Dict[str, Any]) -> str:
    if not output:
        return ""
    lines = [
        "## 📊 执行摘要",
        f"- **总体目标**: {output.get('goal', '')}",
        f"- **规划子任务**: {output.get('total_tasks', 0)} 个",
        f"- **代码任务完成**: {output.get('code_tasks_completed', 0)} 个",
        f"- **文档任务完成**: {output.get('doc_tasks_completed', 0)} 个",
    ]
    gen = output.get("generated_files", {})
    if gen.get("code"):
        lines.append("\n### 💻 生成的代码文件")
        for f in gen["code"]:
            lines.append(f"- `{f.get('filename', '')}` ({f.get('size', 0)} bytes)")
    if gen.get("documents"):
        lines.append("\n### 📝 生成的文档")
        for d in gen["documents"]:
            lines.append(f"- `{d.get('filename', '')}` ({d.get('size', 0)} bytes)")
    warnings = output.get("security_warnings", [])
    if warnings:
        lines.append("\n### ⚠️ 安全警告")
        for w in warnings:
            lines.append(f"- {w}")
    review = output.get("review_result", {})
    lines.append("\n### 🔍 审核结果")
    lines.append(f"- **结论**: {'✅ 通过' if review.get('passed') else '❌ 未通过'}")
    lines.append(f"- **建议**: {review.get('recommendation', 'unknown')}")
    return "\n".join(lines)


# ============================================================
# 主界面
# ============================================================
tab1, tab2, tab3 = st.tabs(["🚀 任务执行", "📁 产物文件", "ℹ️ 关于"])

with tab1:
    st.subheader("📝 输入任务需求")
    user_request = st.text_area(
        "描述你需要完成的任务",
        placeholder="例如：写一个 Python 脚本，读取 CSV 文件并生成统计报告，附带使用说明文档。",
        height=120,
        key="task_input",
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        run_clicked = st.button("🚀 开始执行", type="primary", use_container_width=True)
    with col2:
        if st.button("🗑️ 清空", use_container_width=True):
            st.rerun()

    if run_clicked:
        if not user_request or not user_request.strip():
            st.warning("⚠️ 请输入任务需求后再执行。")
        else:
            st.divider()
            st.subheader("📊 执行进度")

            progress_placeholder = st.empty()
            progress_lines = []
            final_output = None
            review_report = None

            try:
                for step_output in stream_workflow(user_request, CONFIG_PATH):
                    for node_name, node_state in step_output.items():

                        if node_name == "planner":
                            plan = node_state.get("plan", {})
                            tasks = plan.get("tasks", [])
                            msg = f"**📋 PlannerAgent** 完成规划：共 {len(tasks)} 个子任务"
                            if plan.get("warning"):
                                msg += f"\n> ⚠️ {plan['warning']}"
                            for t in tasks:
                                msg += f"\n- `[{t.get('agent', '?')}]` {t.get('title', '')}"
                            progress_lines.append(msg)
                            progress_placeholder.markdown("\n\n".join(progress_lines))

                        elif node_name == "code_execution":
                            results = node_state.get("code_results", [])
                            msg = f"**💻 CodeAgent** 完成：执行 {len(results)} 个代码任务"
                            for r in results:
                                msg += f"\n- `[{r.get('status','?')}]` {r.get('task','')}"
                                for f in r.get("files", []):
                                    if "error" in f:
                                        msg += f"\n  - ❌ {f.get('filename')}: {f.get('error')}"
                                    else:
                                        msg += f"\n  - ✅ `{f.get('filename')}` ({f.get('size',0)} bytes)"
                                for w in r.get("security_warnings", []):
                                    msg += f"\n  - ⚠️ {w}"
                            progress_lines.append(msg)
                            progress_placeholder.markdown("\n\n".join(progress_lines))

                        elif node_name == "doc_execution":
                            results = node_state.get("doc_results", [])
                            msg = f"**📝 DocAgent** 完成：执行 {len(results)} 个文档任务"
                            for r in results:
                                msg += f"\n- `[{r.get('status','?')}]` {r.get('task','')}"
                                for d in r.get("documents", []):
                                    msg += f"\n  - ✅ `{d.get('filename')}` ({d.get('size',0)} bytes)"
                            progress_lines.append(msg)
                            progress_placeholder.markdown("\n\n".join(progress_lines))

                        elif node_name == "review":
                            report = node_state.get("review_report", {})
                            review_report = report
                            passed = report.get("final_passed", False)
                            rec = report.get("final_recommendation", "unknown")
                            msg = (
                                f"**🔍 ReviewAgent** 审核完成\n"
                                f"- 结论: **{'✅ 通过' if passed else '❌ 未通过'}** ({rec})"
                            )
                            progress_lines.append(msg)
                            progress_placeholder.markdown("\n\n".join(progress_lines))

                        elif node_name == "summarize":
                            final_output = node_state.get("final_output", {})
                            progress_lines.append("**🎉 工作流执行完成！**")
                            progress_placeholder.markdown("\n\n".join(progress_lines))

            except Exception as e:
                logger.error("工作流执行异常: %s", e, exc_info=True)
                progress_lines.append(f"**❌ 执行出错**: {str(e)}\n\n请检查 Ollama 服务是否启动，模型是否已拉取。")
                progress_placeholder.markdown("\n\n".join(progress_lines))

            # 显示最终结果
            if final_output:
                st.divider()
                st.subheader("📋 最终摘要")
                st.markdown(format_summary(final_output))

            if review_report:
                st.divider()
                with st.expander("🔍 查看完整安全审核报告 (JSON)", expanded=False):
                    st.json(review_report)

with tab2:
    st.subheader("📁 Output 目录产物")
    files = list_output_files()
    if not files:
        st.info("output 目录为空，执行任务后生成的文件将出现在这里。")
    else:
        st.write(f"共 {len(files)} 个文件：")
        selected_file = st.selectbox("选择文件查看内容", files)
        if selected_file:
            content = read_output_file(selected_file)
            ext = os.path.splitext(selected_file)[1].lower()
            if ext in (".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".sh", ".bat"):
                st.code(content, language="python" if ext == ".py" else None)
            elif ext in (".md", ".markdown"):
                st.markdown(content)
            elif ext == ".json":
                try:
                    st.json(json.loads(content))
                except Exception:
                    st.text(content)
            else:
                st.text(content)

            # 下载按钮
            st.download_button(
                label="📥 下载该文件",
                data=content,
                file_name=selected_file,
                mime="text/plain",
            )

    if st.button("🔄 刷新文件列表"):
        st.rerun()

with tab3:
    st.subheader("ℹ️ 关于本项目")
    st.markdown(
        """
        **Multi-Agent-Local-Workspace** 是一个完全本地化的多智能体协作平台。

        ### 核心特性
        - 💰 **零费用运行**：默认使用 Ollama 本地模型 qwen2.5-7b-instruct
        - 🔒 **数据安全**：所有文件、日志、向量库全部存储在 D 盘
        - 🛡️ **代码沙盒**：CodeAgent 仅允许读写 output 目录，拦截 C 盘访问
        - 🔄 **四 Agent 协作**：规划 → 代码 → 文档 → 审核

        ### 快速命令
        ```bash
        # 拉取模型
        ollama pull qwen2.5-7b-instruct

        # 启动 WebUI
        streamlit run app.py
        ```

        ### 项目路径
        - 项目根目录: `D:\\AI\\Multi-Agent-Local-Workspace`
        - 产物输出: `D:\\AI\\Multi-Agent-Local-Workspace\\output`
        - 日志文件: `D:\\AI\\Multi-Agent-Local-Workspace\\logs`
        """
    )
