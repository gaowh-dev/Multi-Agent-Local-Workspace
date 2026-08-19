# 🤖 Multi-Agent-Local-Workspace

> **本地多智能体协作平台 | 零 Token 费用 | 数据全部存储 D 盘 | 不烧钱**

基于 LangGraph 编排的本地多智能体协作系统，四个专业 Agent 协同完成从任务规划到代码生成、文档编写、安全审核的全流程。默认使用 Ollama 本地大模型，完全离线运行，**0 API 费用，0 Token 开销**。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 💰 **零费用运行** | 默认 Ollama 本地模型 `qwen2.5:7b-instruct`，不调用任何云端 API |
| 🔒 **数据本地化** | 所有项目文件、虚拟环境、向量库、日志、产物全部存储 D 盘，不写入 C 盘 |
| 🤖 **四 Agent 协作** | Planner（规划）→ Code（代码沙盒）→ Doc（文档）→ Review（安全审核） |
| 🛡️ **强制路径沙盒** | CodeAgent 仅允许读写 `D:/AI/Multi-Agent-Local-Workspace/output`，拦截 C 盘与系统目录 |
| 🌐 **Streamlit WebUI** | 可视化交互界面，实时展示各 Agent 执行进度和产物 |
| 🔄 **LangGraph 编排** | 支持并行执行（Code + Doc 同时运行），工作流可追溯 |
| ☁️ **云端备用模式** | 可选 OpenAI 兼容 API 作为备用后端 |

---

## 🏗️ 系统架构

```
用户输入
   │
   ▼
┌──────────────┐
│ PlannerAgent │  任务规划与拆解
└──────┬───────┘
       │
       ├──────────────┐
       ▼              ▼
┌──────────────┐ ┌──────────────┐
│  CodeAgent   │ │  DocAgent    │  并行执行
│ (沙盒防护)   │ │ (文档生成)   │
└──────┬───────┘ └──────┬───────┘
       │                │
       └────────┬───────┘
                ▼
        ┌──────────────┐
        │ ReviewAgent  │  安全审核 + 质量检查
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  结果汇总     │
        └──────────────┘
```

---

## 📁 项目目录结构

```
D:\AI\Multi-Agent-Local-Workspace\
├── 📄 config.yaml              # 全局配置文件（LLM/路径/沙盒/Agent）
├── 📄 requirements.txt         # Python 依赖清单
├── 📄 run.bat                  # Windows 一键启动脚本
├── 📄 .gitignore               # Git 忽略规则
├── 📄 README.md                # 项目说明文档
├── 📄 main_graph.py            # LangGraph 工作流编排
├── 📄 app.py                   # Streamlit WebUI 入口
│
├── 📂 agents/                  # Agent 模块包
│   ├── 📄 __init__.py
│   ├── 📄 planner_agent.py     # 规划智能体
│   ├── 📄 code_agent.py        # 代码智能体（含沙盒）
│   ├── 📄 doc_agent.py         # 文档智能体
│   └── 📄 review_agent.py      # 审核智能体
│
├── 📂 output/                  # 产物输出目录（CodeAgent 沙盒根目录）
├── 📂 logs/                    # 日志目录
├── 📂 vector_store/            # 向量数据库（Chroma 持久化）
├── 📂 data/                    # 数据目录
└── 📂 venv/                    # Python 虚拟环境（run.bat 自动创建）
```

---

## 💻 硬件要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| **CPU** | 4 核 | 8 核及以上 |
| **内存** | 16 GB | 32 GB |
| **GPU** | 无（纯 CPU 推理，较慢） | NVIDIA 8GB+ VRAM（CUDA 加速） |
| **硬盘** | 20 GB 可用空间（D 盘） | 50 GB+ SSD |
| **系统** | Windows 10/11 64位 | Windows 11 64位 |

> **说明**：`qwen2.5:7b-instruct` 模型约 4.7GB（Q4 量化），CPU 模式可运行但响应较慢，建议配备 GPU 加速。

---

## 🐍 Python 版本要求

- **推荐版本：Python 3.10** ✅
- **不推荐：Python 3.14** ⚠️ — 存在 `langgraph`、`chromadb` 等依赖的兼容问题
- 其他兼容版本：Python 3.9 / 3.11

> 下载地址：https://www.python.org/downloads/release/python-3100/

---

## 🚀 Windows 部署步骤

### 第一步：安装 Ollama

1. 访问 [Ollama 官网](https://ollama.com/download) 下载 Windows 安装包
2. 运行安装程序，默认安装即可
3. 验证安装：打开命令提示符（CMD），输入：
   ```bash
   ollama --version
   ```

### 第二步：拉取本地模型

```bash
# 拉取默认模型（约 4.7GB）
ollama pull qwen2.5:7b-instruct

# （可选）拉取嵌入模型，用于向量库
ollama pull nomic-embed-text

# 验证模型已安装
ollama list
```

### 第三步：启动 Ollama 服务

Ollama 安装后会自动在后台运行，默认地址：`http://localhost:11434`

### 第四步：一键启动项目

```bash
# 进入项目目录（注意使用 /d 参数切换盘符）
cd /d D:\AI\Multi-Agent-Local-Workspace

# 双击运行或命令行执行
run.bat
```

`run.bat` 会自动完成以下操作：
1. ✅ 检查 Python 版本（要求 3.10，拒绝 3.14）
2. ✅ 在项目内创建 `venv` 虚拟环境（存 D 盘，不使用 C 盘）
3. ✅ 设置 pip 缓存到 D 盘项目内
4. ✅ 安装所有依赖
5. ✅ 检查 Ollama 服务和模型
6. ✅ 启动 Streamlit WebUI

### 第五步：访问 WebUI

打开浏览器访问：**http://localhost:8501**

---

## ⚙️ 配置说明

编辑 `config.yaml` 可自定义各项配置：

### LLM 后端切换

```yaml
llm:
  default_backend: "ollama"  # 改为 "openai" 启用云端备用模式
```

### OpenAI 兼容云端备用模式

在 `config.yaml` 中设置 `default_backend: "openai"`，并配置 API Key：

```yaml
llm:
  default_backend: "openai"
  openai:
    api_key: "sk-your-api-key"
    base_url: "https://api.openai.com/v1"  # 可替换为 DeepSeek/通义千问等兼容端点
    model: "gpt-4o-mini"
```

也可通过环境变量设置：
```bash
set OPENAI_API_KEY=sk-your-api-key
```

### 沙盒配置

```yaml
sandbox:
  allowed_root: "D:/AI/Multi-Agent-Local-Workspace/output"
  blocked_drives:
    - "C:"
  max_file_size_mb: 50
```

---

## 🛡️ 安全沙盒机制

CodeAgent 内置**强制路径沙盒防护**，确保代码生成过程不会危害系统：

### 防护层级

1. **盘符拦截**：禁止访问 C 盘及其他被配置的盘符
2. **目录白名单**：仅允许读写 `output/` 目录及其子目录
3. **系统目录黑名单**：拦截 `C:/Windows`、`C:/Program Files`、`/etc`、`/usr` 等
4. **路径穿越检测**：防止 `../` 等路径穿越攻击
5. **文件扩展名限制**：仅允许写入白名单内的文件类型
6. **文件大小限制**：默认最大 50MB
7. **代码静态扫描**：自动检测 `eval`、`exec`、`os.system`、硬编码密钥等危险模式

### 违规处理

任何沙盒违规操作将被拦截并记录，文件不会被写入，同时在 WebUI 中显示警告信息。

---

## 🤖 Agent 角色说明

### PlannerAgent（规划智能体）
- 接收用户原始需求
- 拆解为 3-8 个可执行子任务
- 为每个子任务分配 Code 或 Doc Agent
- 标注依赖关系和执行顺序

### CodeAgent（代码智能体）
- 根据子任务生成完整可运行的代码
- 所有文件写入沙盒目录 `output/`
- 内置路径沙盒防护，禁止越权访问
- 生成前进行代码安全扫描

### DocAgent（文档智能体）
- 生成 README、技术文档、使用说明等
- 支持 Markdown 格式
- 可引用已生成的代码文件作为上下文

### ReviewAgent（审核智能体）
- **静态安全扫描**（强制执行）：检测危险 API、硬编码密钥、路径穿越等
- **LLM 智能审核**：代码质量、逻辑漏洞、依赖风险
- **文档质量检查**：结构完整性、内容准确性
- 输出评分和审核报告，严重问题直接拒绝

---

## 📊 使用示例

在 WebUI 中输入任务需求，例如：

> 写一个 Python 脚本，读取当前目录下所有 CSV 文件，合并数据并生成统计报告（包含均值、最大值、最小值），然后生成一份使用说明文档。

系统将自动执行：
1. **PlannerAgent** 拆解为：编写数据处理脚本 → 生成使用说明文档
2. **CodeAgent** 生成 `data_processor.py`（写入沙盒）
3. **DocAgent** 生成 `README_usage.md`
4. **ReviewAgent** 对代码和文档进行安全审核
5. 所有产物保存在 `output/` 目录

---

## 🔧 手动安装（不使用 run.bat）

```bash
# 1. 切换到项目目录
cd /d D:\AI\Multi-Agent-Local-Workspace

# 2. 创建虚拟环境（D 盘项目内）
py -3.10 -m venv venv

# 3. 激活虚拟环境
venv\Scripts\activate

# 4. 设置 pip 缓存到 D 盘
set PIP_CACHE_DIR=D:\AI\Multi-Agent-Local-Workspace\.pip_cache

# 5. 安装依赖
pip install -r requirements.txt

# 6. 启动 WebUI
streamlit run app.py
```

---

## 📝 常见问题

### Q: 启动时提示 "未检测到 Ollama"
A: 请先安装 Ollama 并确保服务在运行（`http://localhost:11434`），然后拉取模型 `ollama pull qwen2.5:7b-instruct`。

### Q: Python 3.14 可以用吗？
A: **不推荐**。Python 3.14 与 `langgraph`、`chromadb` 等依赖存在兼容问题，建议使用 Python 3.10。

### Q: 所有数据真的都在 D 盘吗？
A: 是的。项目代码、虚拟环境（`venv/`）、pip 缓存、向量库（`vector_store/`）、日志（`logs/`）、输出产物（`output/`）全部在 `D:\AI\Multi-Agent-Local-Workspace\` 目录内。Ollama 模型存储位置由 Ollama 自身管理，可通过环境变量 `OLLAMA_MODELS` 自定义到 D 盘。

### Q: 如何让 Ollama 模型也存到 D 盘？
A: 设置环境变量：
```bash
set OLLAMA_MODELS=D:\AI\ollama_models
```
然后重启 Ollama 服务。

### Q: CodeAgent 生成的文件在哪里？
A: 所有生成的文件都在 `D:\AI\Multi-Agent-Local-Workspace\output\` 目录下，可在 WebUI 的"产物文件"标签页查看和下载。

### Q: 如何切换到云端 API？
A: 编辑 `config.yaml`，将 `llm.default_backend` 改为 `"openai"`，并配置 `api_key` 和 `base_url`。

### Q: `cd D:\...` 后提示符还在 C 盘？
A: Windows CMD 中切换盘符需要加 `/d` 参数：`cd /d D:\AI\Multi-Agent-Local-Workspace`，或者先输入 `D:` 再 cd。

---

## 📄 许可证

MIT License

---

## 🤝 免责声明

- 本项目仅供学习和研究使用
- CodeAgent 的沙盒防护为应用层限制，不替代操作系统级安全隔离
- 生成的代码请自行审核后再在生产环境使用
- ReviewAgent 的安全审核为辅助手段，不保证 100% 发现所有问题

---

**Multi-Agent-Local-Workspace** — 让 AI 协作在本地安全、免费、高效地运行。
