# FlexResearch 当前系统审计

## 当前工作树增量审计（2026-09-29复核；最近改造为脉率候选与完整产物合约）

本批新增21项测试：显式脉搏请求由spectral_analysis输出Hz×60候选及方法版本；普通FFT不报心率，常量与缺fs不捏造脉率。图自带SHA/源SHA/渲染版本，报告分别核对Hz/BPM。HTTP filterParameters显式验参且拒绝冲突；signal-007 v2公开补充setup处理metadata。严格774项通过，golden60/65，其余5条不标完。详见[PULSE_WORKFLOW](PULSE_WORKFLOW.md)。

本节描述当前代码；后面的 2026-09-03 审计保留为改造前基线。两者不能混用。当前系统是 **确定性科学分析工作流 + 最小本地 RAG + 受限、有实验会话状态的 Tool Calling Agent**。文献分支调用 search_papers；实验编号分析分支调用 analyze_experiment，再由内部 Python 工作流计算、绘图。模型选择粗粒度工具，不是逐个决定 FFT/滤波算法。已有规则式历史审阅计划、初始多频扫描草案和实验聚合报告；没有自主实验设计、Multi-Agent 或 checkpoint 恢复。

2026-09-28补参增量：`PendingSignalRequest`保存原请求、来源run与实验/文件/hash作用域。仅有界参数回复可续跑，续跑前重核原run、原请求及实际文件；不完整新滤波条件仍澄清，不覆盖原始数据。新增32项测试，严格753项通过；experiment-005 v2显式加入fixture用户第二轮参数并验首轮不得提前执行，不能算旧单轮通过。详见[补参续跑](PENDING_SIGNAL_REQUEST.md)。

此前2026-09-22书目证据增量：paper_methods.py与app.py参数问题路由实际核对选定的论文记录。没有已验证全文关联时明确澄清，不用备注/标题/其他文档补参数；非法/歧义范围、SQL/JSONL/历史/SSE及浏览器刷新已验。新增49项测试，当时完整721项通过，literature-002原合约已验。详见[文献证据边界](PAPER_EVIDENCE_BOUNDARY.md)。

此前2026-09-22初始草案增量：`initial_plan.py`与`ExperimentPlanningInput`为现有create_experiment_plan增加明确初始模式；原experiment-001八章节、参数未定、请求hash、空历史/来源、工具失败与SQL/JSONL/下载/刷新已验。新增35项测试，完整672项通过；不是已审批协议或专家质量评分。详见[初始实验草案](INITIAL_EXPERIMENT_PLAN.md)。

| 原始审计问题 | 当前状态与代码证据 |
| --- | --- |
| 1. 入口 | 【已经实现】`app.py`，Flask；`python app.py` 在本机 8765 启动。 |
| 2. Web/UI | 【部分实现】原生 HTML/CSS/JS，统一聊天；实验图/报告、文档索引/重复/OCR失败及原问题能在历史会话恢复，支持 `?session=ID` 直达；窄窗口能打开 API 面板。高级台账仍独立。 |
| 3. Agent 在哪里 | 【部分实现】`LabAgent` 确定性科学编排；`ToolCallingAgent` 有界模型循环；`science_agent.py::run_science_loop` 和 `app.py::run_paper_agent` 接入两条聊天路径。 |
| 4. 是否有 LLM | 【已经实现】真实 OpenRouter 兼容适配器；历史 Lightning 配置下科学与文献模型链有在线成功证据，不代表当前配置可用。本批未修改本机模型配置、未调用在线模型，运行状态仍为unverified。普通、工具、手动探针均可更新状态；连接成功不代表回答正确。 |
| 5. Tool Calling | 【部分实现】模型按分支获得 search_papers、analyze_experiment 或 compare_stored_experiments schema；支持 observation、验参修复、重复/超预算拦截。其他应用工具尚未全部暴露给模型。 |
| 6. RAG | 【部分实现】解析→分页分块→特征哈希向量/FTS→检索→引用；本地或显式授权时摘录可进入模型。远程默认不发送私有摘录。 |
| 7. 向量数据库 | 【不存在】专用向量数据库/ANN 未引入；SQLite BLOB 保存 HashingVectorizer 特征，Python 计算 cosine。 |
| 8. Memory | 【部分实现】普通模型对话使用最近最多四个合格问答对/6000 字符，按 session 隔离；私有资料、旧来源、工具运行和失败回退形成边界。实验状态独立保存实验/文件/通道/fs/滤波参数、成功分析目标及来源 ID；无自主长期记忆整理。 |
| 9. State | 【部分实现】LabAgentState、ToolLoopState、ExperimentSessionState；上传绑定文件，换文件不继承旧参数/目标。AnalysisParameters/FilterParameters 验证截止频率和阶数；沿用仍从原文件重算且重新校验 Nyquist。AnalysisContext只继承成功的有限目标，缺目标或旧滤波选择不明则澄清；要求原始数据时不隐式滤波。无中间 checkpoint。 |
| 10. 实验数据读取 | 【已经实现】CSV 上传归档、SHA-256、只读 load_csv；experiment_analysis先实际load_experiment_data并检查实验/文件/hash，再从同一bytes解析与计算。无关联的独立文件不虚构实验ID；单列CSV不猜时间轴。 |
| 11. 科学工具 | 【已经实现】9 个基础科学工具和 11 个应用工具，共 20 个 schema。analyze_signal的信号质量分支标记可疑区段但不确认运动伪差，iv_curve分支按明确单位/近零窗口计算微分电阻；extract_features按明确基线/单位/目标点计算GF/保持率。compare_stored_experiments 校验单位/通道/频点；历史计划和报告有 typed schema。 |
| 12. Paper/PDF | 【部分实现】公开书目、typed index_document文本解析/同事务索引/去重/物理页码；retrieve_paper_chunks与summarize_method按文档ID验证哈希，从明确Methods章节抽取五类原文证据。图片PDF返回OCR_REQUIRED；无扫描OCR、完整语义方法总结或跨论文协议对比，复合导入并提取尚未全串联。 |
| 13. 实验管理 | 【部分实现】实验/项目/样品/测量/证据台账；历史计划可从已选实验解析项目最近三次，按最新单实验分析确定文件/通道，再调用真实比较工具。Bio-Z 对齐单位/频点后生成差异与条件变化驱动建议；脉搏特征历史比较尚未实现，不冒充自主实验设计。 |
| 14. 存储 | 【已经实现】本地 SQLite、uploads、measurements、artifacts、logs；秘密在环境配置中，数据目录内容不纳入 Git。`/data` 已限于两个公开 demo。 |
| 15. 数据库 | 【已经实现】复用 SQLite，六个要求的模型均有表；foreign_keys、busy_timeout 生效，事务上下文退出关闭连接。上传BEGIN有限重试、COMMIT回滚及独立原始CSV恢复已实测；不是跨介质原子事务。 |
| 16. 日志 | 【部分实现】agent_runs/tool_calls/analysis_runs、JSONL、模型用量、停止原因与 `/debug`；没有服务级监控告警。 |
| 17. Tests | 【已经实现】774 项 pytest 在严格资源警告下全过；行覆盖92.66%、分支覆盖84.45%。含18个Chromium流程、5个真实进程HTTP/重启、实际SQLite锁及82个评测负对照。浏览器外部边界回放，不是在线模型评分。 |
| 18. Eval | 【部分实现】65 条合约，60 个离线 adapter 执行且通过，5 条跳过；执行覆盖92.31%。context-chat-001 验证实际历史消息传递，report_content_quality 仍为1个原报告案例的窄rubric；failure-003实际持锁1.5秒，新增反例证明错误状态/哈希/重试轨迹/假归档会报失败。不是通用语言/人体数据或在线模型评分。 |
| 19. 运行 | 【已经实现】科学 session 185/191（约 10/13 秒）和文献 session 186（约 116 秒）在线闭环通过；工具计算/真实来源分别核验。只证明这些合成与公开资料路径；普通追问 session 189 内容仍有错误，不代表全系统可靠性。 |
| 20. 占位/计划 | 【占位】旧 trace 多角色名称和 `/api/plan` 固定模板；【部分实现】方法原文提取、Bio-Z 历史比较驱动规则计划；【计划】完整语义方法总结、脉搏特征历史设计；【不存在】真正 Multi-Agent、auth/RBAC/worker/checkpoint。 |

最近一次coverage实测：5720 statements、420 missed，行覆盖92.66%；1814分支、1532已覆盖，分支84.45%；组合90.68%。774项严格全量测试通过；CI与Makefile配置80%coverage floor，本轮执行分支覆盖。此前d9a71ed/0fa96d2已在GitHub通过CI，本批需独立核验。HTTP 200内嵌provider error统一归类并有限重试。

普通知识问答开启模型时不再用固定短答截流；本地参考仅用于关闭模型的路径，并标明非模型生成。provider_transport记录有限重试/Retry-After、HTTP/timeout错误，普通问答API、历史、DB、JSONL和浏览器展示一致失败，不报假成功。真实localhost超时/429 I/O及逐case隔离/正逆序评分已验证；当前60/65执行通过。工具模型client失败也计入尝试次数，父级领域错误码仍需补齐。

2026-09-21目标上下文增量：`analysis_context.py`将成功的频谱/统计/质量目标及来源run纳入实验状态，明确继续分析时同文件复用，新目标优先；缺目标或上一轮滤波选择不明则澄清，不靠fs猜FFT。experiment-003补真实前一任务后完整验收，ch2→ch4实际2.4→1.2Hz，SQL/来源/报告/刷新一致。新增30项测试通过；追问内嵌工具轨迹，明确科学请求不混入旧两列初筛指标。不是通用意图推理或checkpoint。详见ANALYSIS_GOAL_CONTEXT。

此前补上传数据库锁恢复：`upload_recovery.py`只在业务写入前重试BEGIN，COMMIT失败回滚，不重放事务体。持续BUSY时保存数据库独立的原始CSV/回执并验证下载；归档后失败明确已有ID、磁盘保存失败不报假保护。实际1.5秒写锁、短锁、COMMIT读锁、浏览器下载/刷新/一次人工重试均通过。失败期间数据库不可写，轨迹存独立回执而非伪造agent_run。详见DATABASE_RECOVERY；进程强杀、通用幂等和跨文件原子恢复仍未完成。

2026-09-14曲线增量：`curve_features.py`实现明确零应变基线与单位的GF、明确实测目标循环的保持率，`curve_agent.py`贯通实验上下文/原CSV读取/特征/绘图。修复旧GF混入加载点、循环末点替代目标、I–V未转换电流单位三类真实错误。data-005/006原问题/expected保持不变，GF=2与1000次92%的完整上传、来源/参数持久化、报告和浏览器刷新已验；8项新负对照能发现污染。该批当时仅完成I–V兼容数学，后续完整合约见下面I–V增量。详情见CURVE_FEATURES_METHOD。

2026-09-19/20 I–V增量：`iv_analysis.py`和现有analyze_signal的iv_curve分支接通原问题的实验读取、单位明确的零偏拟合、工具来源、SQL、报告和浏览器刷新。新增30项测试，data-004完整合约通过；零电导返回null，错误数据/单位/工具失败清除旧初筛值。报告规则扩展到第七类数值，正常聊天回复不重复展开方法限制。详见IV_ANALYSIS；不是仪器校准或自由科学文本验证。

2026-09-14文档增量：修复文档与索引分两次提交的半归档风险、忽略上传question/sessionId及空白首PDF页被trim吞掉的问题。index_document先只读准备，按时返回并校验后才提交；文档/分块/FTS/向量/实验关联同SQL事务，异常清理本次新文件，同SHA不覆盖旧档案。35项新增测试实际通过，file-003/006/007原合约关闭；真实图片PDF澄清而不编方法，解析超时后无晚到归档。日志失败仍明确已提交ID；不是线程强杀、OCR或断电恢复。详见DOCUMENT_INDEXING。

2026-09-14科学上下文增量：补齐实验读取→同字节CSV解析/hash→统计/频谱的真实轨迹，错实验/文件/hash与工具预算耗尽不计算。完整统计六值、斜率轴单位和工具参数进入SQL/报告；缺fs有结构化字段且不输出频率，单列数据仅用明确生成的样本索引。新增31项测试及8项评测负对照，关闭data-003/signal-005/experiment-004原合约；初轮Sniffer、单列SQL非空约束和旧轨迹断言失败均有修复及重跑证据。详见SCIENTIFIC_CONTEXT_CONTRACTS和RUNTIME_VALIDATION。

此前修复reference resistor文献误路由、超大请求/PDF错误边界、重复检索计分、成本未知误判；另修复滚动三年窗、日期精度校验、模型丢失时间限制、空文献选择标completed、Bio-Z同义词误排除、7条来源只显示6条。Chromium上传/下载/刷新、来源点击、API切换及失败保留已通过。仍缺5个golden及开放模型质量等验收，不能以绿测试宣称工程全部完成。

本轮定位了提供方对嵌套 `$defs` 的 HTTP 400，导出时展开引用且保留本地严格验参。Mini 后续仍有漏字段/非法参数；改为 Lightning 后科学和文献路径成功，失败记录不删除。论文过滤新增 trial registration、补充材料、实际 OpenAlex type 和原问题 Bio-Z 模态约束；模型改写不得绕开原问题。这是有限兼容与相关性规则，不是全部模型能力或论文科学性认证。

教程和80题面试材料已刷新；原始24节逐项核对见`COMPLETION_AUDIT.md`。用户已暂停教学，不等待理解题，也不把教学暂停当作工程阻塞。生成文档不代表本人已经掌握。

普通上下文证据：`conversation_context.py`、`tests/integration/test_conversation_context.py`、`docs/CONVERSATION_CONTEXT.md`。session 175 的两次真实追问已在浏览器显示，来源列表为空；状态随实际请求更新。它不自动接续旧论文来源、私有文件解释或文献检索式，不是无限记忆。

报告内容证据：`report_narrative.py` 转述具体科学结果和成功工具来源；`report_review.py` 针对七类数值陈述做七项规则核验，未知数值交给人工。`/api/agent-runs/<id>/report-review` 和聊天折叠入口已接入；session 174 报告 `ed4464be85a04c6e98827bcad5d240fa` 的七项结果已在浏览器展开。详见 `REPORT_CONTENT_EVAL.md`；仍非开放文本科学蕴含证明。

信号质量证据：`signal_quality.py`、`docs/SIGNAL_QUALITY_METHOD.md`、`scripts/live_signal_quality_smoke.py`。真实 HTTP session 174 的合成 12–16 s 波动被标出 401 点，IoU 0.997506；原始哈希/工具 ID 可追溯，浏览器已显示折叠质量卡和报告。未调用外部模型，不是已验证的人体运动伪差识别器。

跨轮参数证据：`tests/integration/test_processing_context.py` 和 `scripts/live_processing_context_smoke.py`；真实 HTTP session 169 已展示 0.5–3 Hz / 4 阶及“沿用参数来源”链接，滤波→FFT/导出/绘图均指向本轮上游 tool_run_id。原文件不改写、不反复滤波派生数据。无效新参数不回退旧值；滤波失败不改用原始信号继续 FFT/画图。此路径为确定性运行，外部模型调用 0 次。

历史工具证据：`flexresearch/history.py`、`tests/integration/test_history_reports.py`、`tests/integration/test_history_comparison_plan.py`。聚合报告保存快照并区分 measured/calculated/interpretation。计划以最新单实验分析为依据，比较不是新采集记录，失败不能跳过。Bio-Z 可比时以最早选定实验为描述性参考，生成真实比较子运行；计划再次检查来源分析 ID、文件哈希和条件快照，历史变化则拒绝过期比较。仅检查明确列出的条件字段；单变量候选不等于已排除全部混杂，缺协议不自动填值。每实验最多汇集 100 次分析；报告已增加有限内容 rubric，完整语义有用性/科研价值仍未评分。

方法提取边界：`flexresearch/paper_methods.py` 为本地确定性抽取，不是模型语义总结。只接受选定文档，验证原文件 SHA-256 与索引原文一致，保留否定词和原始数值；缺字段表示“未匹配到”，不是“论文没报告”。字符坐标相对 CRLF→LF 并 trim 的索引文本；PDF 页码来自导入分块。最多读取 200 块，长文截断明确标记；跨块断句/非标准章节可能漏检。session 166 的合成方法卡已通过真实 HTTP 并在浏览器显示五类可展开证据。

2026-09-09 新模型在线验收未通过：一次未调用工具便结束，另一次上游 503；均明确标记 partial，本地 Python 完成不能冒充模型编排成功。科学分支现在首次强制调用已确认范围的唯一工具，后续允许 observation→结果选择；这是约束工作流，不是模型自主选择分析算法。模型无视要求时 stop_reason=missing_required_tool。HTTP 合成上传→追问→滤波/FFT/CSV/PNG 路径在 session 165 完整通过，但此次未调用外部模型。

派生数据：明确要求“滤波并导出 CSV”时，export_signal 在原文件哈希仍一致的前提下创建独立 CSV。时间轴从确认的采样率生成相对秒，不冒充原始绝对时间；报告保存原始/派生哈希、通道、参数、上游滤波 tool_run_id。下载仅允许已归档且哈希未变化的派生 CSV。未完成滤波时不导出，未实现任意格式/多通道批量导出。

科学模型边界：默认远程 observation 只有工具状态和 toolRunId，不含原始数组、文件名、指标。明确授权或本地模型可以看到数值摘要，但不含原始数组。模型最终只能选择本轮成功的 toolRunId，最终数值答案仍由 Python 渲染。输入数值通道 ID 会无损转为字符串，不能把布尔/小数悄悄变为通道。实际运行证据见 `docs/RUNTIME_VALIDATION.md`。

后续真实 run `c118b8a908984c7ca53ef853612e0548` 执行了 3 次模型选择的检索，最终模型网络错误，仍为 partial。该运行还暴露了 Crossref 把征稿/出版信息标作 journal-article 的问题；已增加标题过滤与同标题去重，并通过独立回归测试。该过滤是保守规则，不保证识别所有非研究记录。

新增文献输出边界：模型只能提交 `selected_urls` 结构化选择；每个 URL 必须属于本次成功工具返回的记录。展示的标题、年份和 DOI 从原记录渲染，模型自由文本或虚构 URL 不进入答案。这证明的是书目选择和来源约束，不能称为论文全文总结或科学结论验证。

## 改造前基线审计（历史记录）

> 审计日期：2026-09-03
> 审计对象：工程化改造前的 Git 基线 `2e162c2` 与审计时本机 `data/flexresearch.db` 运行实例
> 审计方法：逐文件静态检查、SQLite schema/实例检查、`python -m pytest -q`、`make benchmark-lab`、`make benchmark-provider`、本机健康检查与当前模型连接探针。
> 边界：本文只描述审计开始时的干净基线，不把 README、界面文案、trace 中的角色名称或下一步规划视为已实现能力。审计期间其他并行任务产生的未提交改造不纳入本基线结论。

## 状态定义

- **【已经实现】**：存在实际代码路径，并有测试或本次运行证据支持。
- **【部分实现】**：已有可运行子集，但缺少该能力的关键闭环或工程边界。
- **【占位】**：有名称、界面、固定模板或 trace 展示，但背后不是所声称的独立能力。
- **【计划】**：只在文档或需求中出现，当前没有对应运行代码。
- **【不存在】**：仓库中未找到实现、依赖、schema 或测试证据。

## 先给结论：当前系统到底是什么

当前 FlexResearch 最准确的分类是：**规则驱动的 Flask 研究工作流 + 可选 LLM 文本生成 + 关键词/书目检索 + 本地科研台账**。

- 它已经超出纯静态 Chatbot：可以持久化会话、调用外部书目 API、分析 CSV、解析 PDF、管理项目与证据。
- 它还不是标准的 **LLM + Tools Agent**：LLM 请求中没有 `tools`/function schema，模型不选择工具，也不存在 observation 后再次决策的循环。
- 它还不是完整 **RAG Application**：本地资料有 parsing、chunking、FTS retrieval，但检索出的 chunk 没有进入 LLM prompt，因而没有形成 retrieval → context → generation 的闭环。
- 它不是 **Stateful Agent**：有数据库持久化，但没有 current experiment、selected channels、sample rate、analysis parameters 等运行状态，也没有 checkpoint/resume。
- 它不是 **Multi-Agent**：`Conductor`、`Planner`、`Researcher`、`Source Critic`、`Synthesizer` 是同一个同步函数写入的 trace 标签，不是拥有独立 prompt、state、tool 权限或消息传递的多个 Agent。

---

## 1. 入口文件是什么？

**状态：【已经实现】**

主入口是 [`app.py`](../app.py)：

- `app = Flask(...)` 在 `app.py:37` 创建应用。
- 模块导入时立即执行 `init_db()` 与 `ensure_document_indexes()`（`app.py:1184-1185`），会创建/迁移本地 SQLite schema 并补建文档索引。这意味着“导入模块”本身有数据库写入副作用。
- 直接运行时，`if __name__ == "__main__"` 在 `127.0.0.1:8765` 以 Flask debug server 启动（`app.py:2289-2291`）。
- [`Makefile`](../Makefile) 的 `make run` 会先尝试打开浏览器，再执行 `python app.py`。
- 容器入口是 [`Dockerfile`](../Dockerfile) 中的 `gunicorn --bind 0.0.0.0:${PORT} --workers 2 --timeout 120 app:app`；[`compose.yaml`](../compose.yaml) 将 `/app/data` 挂载到命名卷。

没有 Python package 分层、CLI 入口、application factory 或单独的 agent/service/worker 进程；所有后端逻辑集中在一个约 2,291 行的 `app.py` 中。

## 2. Web/UI 是什么？

**状态：【部分实现】**

UI 是原生 HTML/CSS/JavaScript，不是 React/Vue，也没有前端构建步骤。

真实页面路由：

| 路由 | 文件 | 当前用途 |
| --- | --- | --- |
| `/` | `static/chat.html` + `chat.js` | 默认单对话入口、会话列表、API 配置、文件上传 |
| `/lab` | `static/index.html` + `app.js` | 项目、样品、CSV、文档与固定实验草案工作台 |
| `/workspace` | `static/workspace.html` + `workspace.js` | 旧版研究问答与 trace 调试界面 |
| `/protocols` | `static/protocols.html/js` | 协议草案与人工审核 |
| `/benchmarks` | `static/benchmarks.html/js` | 性能指标台账与 DOI 验证 |
| `/library` | `static/library.html/js` | 论文、文档、证据卡与引用导出 |
| `/decisions` | `static/decisions.html/js` | 证据/测量快照与决策审核 |
| `/provenance` | `static/provenance.html/js` | 项目关系图 |

`/` 的单对话界面确实会把普通问题发到 `/api/research`，CSV 发到 `/api/analyze`，PDF/TXT/Markdown 发到 `/api/documents`（`static/chat.js:15-17`）。但它还不是“所有能力由一次对话统一调度”的完整界面：

- 附件与文本同时发送时，文本只显示在浏览器里，没有作为分析指令提交给后端；上传动作也没有写入 `research_messages`。
- CSV 上传只执行固定初筛；用户不能在同一请求中说“分析第 4 通道脉搏频率并画图”。
- 根聊天页的 CSV 结果只显示指标卡；`/lab` 才用浏览器 SVG 画临时折线图，图没有保存路径或 provenance。
- 高级功能仍分散在 6 个独立页面，根聊天并未通过意图路由调用这些功能。

因此“默认是单一对话入口”已实现，“完整单窗口 Agent 工作流”只实现了一部分。

## 3. 当前 Agent 在哪里？

**状态：【部分实现】**

所谓 Agent 的核心实际上是 `app.py` 中的同步编排函数 `run_research()`（`app.py:1088-1166`），配套函数包括：

- `selected_skill()`：按关键词选 `product`、`knowledge` 或 `literature`（`app.py:849-857`）。
- `requires_live_literature()` / `requests_recent_literature()`：判断是否允许书目联网（`app.py:838-846`）。
- `infer_track()`：把问题规则分类为四个研究方向（`app.py:553-561`）。
- `retrieve_chunk_evidence()`：检索本地文档 chunk（`app.py:508-536`）。
- `openalex_search()`、`crossref_search()`、`europepmc_search()`：外部书目请求。
- `direct_research_answer()`：四类硬编码知识短答（`app.py:1054-1071`）。
- `model_synthesis()`：其余知识问题的单次 LLM 生成。

`SKILL_REGISTRY`（`app.py:43-49`）只是五条技能元数据，`/api/skills` 只是把它返回给客户端；它不是可执行 Tool Registry，没有输入/输出 schema、权限、timeout、重试或统一执行器。

`run_research()` 没有“模型决策 → 工具 → observation → 再决策”的循环。一次请求的路径由 Python `if` 固定，最多调用一次模型。因此应称为 **workflow/orchestrator prototype**，不能称为自主 Agent 或 Multi-Agent。

## 4. 当前是否真的有 LLM？

**状态：【部分实现】**

有真实的 OpenAI-compatible HTTP 适配器：

- `model_configuration()` 从本机 `.env` 环境变量读取 API key/base URL/model，并允许 `data/provider-settings.json` 覆盖非秘密配置（`app.py:925-930`）。
- `model_synthesis()` 向 `{baseUrl}/chat/completions` 发送 system/user messages、temperature、max tokens 等参数（`app.py:955-980`）。
- `/api/providers` 不返回 key；`/api/providers` POST 可热切换 endpoint/model；`/api/providers/probe` 可测试实际模型与延迟（`app.py:1363-1399`）。
- 普通知识问题在 `useModel=true` 且不命中硬编码短答时才进入模型；文献请求目前由 `literature_metadata_digest()` 固定整理，通常不调用 LLM。

当前本机非秘密配置是 OpenRouter + `tencent/hy3:free`，key 状态为“已配置”。但本次对真实 provider 执行 `probe_model_connection()` 返回 **HTTP 404（约 1.47 秒）**。所以：

- “存在真实 LLM 调用代码”成立；
- “当前配置的真实模型此刻可用”不成立；
- `make benchmark-provider` 的 5/5 使用的是本地 mock provider，只证明适配器、热切换和 503 降级逻辑，不证明 OpenRouter/Hy3 当前可用。

另外，LLM 调用没有 response schema、token/cost 记录、重试、熔断、provider capability negotiation 或对输出事实性的验证。

## 5. 当前是否用了 Tool Calling？

**状态：【不存在】**

没有使用 OpenAI function calling、JSON tool schema、MCP、LangChain/LangGraph tool、Pydantic tool model 或自研等价协议。证据：

- `model_synthesis()` 的请求 payload 只有 `model`、`messages`、`temperature`、`max_tokens`、`reasoning`，没有 `tools`、`tool_choice` 或 function definitions（`app.py:972`）。
- 模型返回后只读取 `choices[0].message.content`，没有解析 `tool_calls`（`app.py:973`）。
- `requirements.txt` 中没有 Pydantic 或 Agent framework。
- CSV、检索、数据库函数由 Flask/Python 分支直接调用，而不是由 LLM 选择。

`SKILL_REGISTRY` 和 trace 中的“技能/Agent”名称是可见标签，不能作为 Tool Calling 的实现证据。

## 6. 当前是否用了 RAG？

**状态：【部分实现】**

已经有 **RAG 的检索前半段**：

1. `/api/documents` 接收 TXT/Markdown/CSV/PDF。
2. `extract_text()` 解码文本或用 `pypdf` 提取 PDF 文本（`app.py:1169-1181`）。
3. `split_document_chunks()` 按最多 1,000 字、160 字 overlap 分块，并避免跨 PDF 页（`app.py:389-411`）。
4. `index_document_chunks()` 写入 `document_chunks` 和 SQLite FTS5（`app.py:414-423`）。
5. `retrieve_chunk_evidence()` 用 FTS5/BM25 检索，失败时用 `LIKE`，返回 `local:<document>#<chunk>` 和页码锚点（`app.py:508-536`）。

但 **retrieval → context → generation 没有闭环**：

- `run_research()` 得到 `private_evidence` 后，只将其放进 API 返回值、trace 与 `research_run_sources`。
- `model_synthesis(query, deduplicated, plan)` 只接收用户问题、外部论文元数据和研究方向；本地 chunk/excerpt 没传入 prompt（`app.py:1148-1155`、`955-972`）。
- `/api/assistant` 的回答来自固定 `TEMPLATES`，本地命中只作为旁边列表返回（`app.py:564-580`）。
- `benchmark_lab.py` 的 `local_evidence_retrieval` 只断言找到了 `privateEvidence`，没有断言最终回答正确引用了该 chunk。

因此当前可以准确声称“本地文档解析、分块、关键词检索和可定位引用已实现”，不能声称“已完成端到端 RAG 问答”。

## 7. 当前是否有向量数据库？

**状态：【不存在】**

没有 embedding 模型、embedding 表、向量字段、FAISS/Chroma/Qdrant/Milvus/pgvector 或向量相似度检索。`document_chunks_fts` 是 SQLite FTS5 倒排全文索引，不是向量数据库；`bm25()` 是词项排名，不是语义向量检索。

这不是必然缺陷：对小型、本地、强调可解释性的资料库，FTS5 可以是合理 MVP。但当前无法处理同义表达、跨语言或词面不重合的语义召回，也没有 retrieval precision/recall 数据支持其效果。

## 8. 当前 Memory 怎么实现？

**状态：【部分实现】**

当前可被称为“持久记录”的部分：

- Conversation history：`research_sessions` 与 `research_messages` 保存会话标题、用户/助手消息和时间。
- Run history：`research_runs` 保存当前 query 与 `trace_json`，`research_run_sources` 保存本轮来源。
- Long-term domain records：projects、samples、measurements、documents、papers、evidence cards、protocols、benchmarks、decision packets 存在 SQLite 中。
- Browser selection：`static/chat.js:3` 用 `localStorage['flexresearch-session']` 只保存当前 session ID。

但这些记录没有被实现成 Agent Memory：

- `model_synthesis()` 每次只收到当前 query；过去 `research_messages` 没有送入模型。
- 没有消息窗口裁剪、摘要、检索式 memory、用户偏好、实体记忆或过期策略。
- 数据库中的历史实验不会被 Agent 自动检索来回答“根据前三次实验建议下一次”。
- 没有区分或实现 conversation context、short-term state、experiment state、long-term knowledge 的读写策略。

所以准确说法是“有会话与科研对象持久化”，不是“有 Agent Memory 系统”。

## 9. 当前状态怎么保存？

**状态：【部分实现】**

持久状态主要保存在 SQLite；模型的非秘密设置保存在 `data/provider-settings.json`；API key 只从 `.env`/进程环境读取；浏览器只保存当前 session ID。

每轮 research 请求会追加两条 `research_messages`、一条 `research_runs`、零到多条 `research_run_sources`，再更新 session 时间（`app.py:1156-1165`）。决策包把选中的 measurement/evidence card 复制成 `snapshot_json`，这是当前最接近不可变状态快照的实现。

缺失的 Agent 运行状态：

- 没有 `current_experiment`、selected channels、sample rate、analysis parameters、selected files。
- 没有明确状态机、pending tool call、iteration count、stop reason、checkpoint 或恢复接口。
- SSE `/api/research/stream` 先发送几个固定 `running` 事件，再同步执行整个 `run_research()`；它不是可恢复的后台执行，也没有持久化中间状态（`app.py:1484-1514`）。
- 多 worker/进程并发没有 state coordination。

## 10. 当前实验数据怎么读取？

**状态：【部分实现】**

唯一真正的数值实验数据入口是 `POST /api/analyze`：

- 只接受文件名以 `.csv` 结尾的上传。
- 全局上传上限为 8 MB（`app.py:38`）。
- 按 UTF-8-SIG 解码，`csv.Sniffer` 识别逗号、分号或 Tab，再由 Pandas `read_csv` 读取（`app.py:2247-2259`）。
- `detect_columns()` 只从数值列中启发式选择一个 x 和一个 y（`app.py:1188-1196`）。
- 分析后把原始 bytes 复制到 `data/measurements/<sha-prefix>_<filename>`，把 hash、列名、点数与部分指标写入 `measurements`（`app.py:2265-2283`）。

未实现：多通道 Bio-Z schema、复数阻抗/相位、频率扫频、channel map、采样率、单位 schema、TXT 仪器格式、目录/批次导入、超大文件流式读取、设备直连、数据版本或显式 processing parameters。

此外，本次检查当前工作区数据库时，`measurements` 有 1 条记录，但 `/api/measurements/1/integrity` 返回 `status=missing`：对应原始 CSV 不在 `data/measurements/`。这说明 hash 校验端点能识别缺失，但当前实例并非完整可复现数据集。

## 11. 当前有哪些 Data Analysis Tool？

**状态：【部分实现】**

以下是已运行的普通 Python 分析函数，不是已注册 Agent Tool：

| 函数 | 已实现计算 | 主要限制 |
| --- | --- | --- |
| `detect_columns()` | 选择两个数值列 | 基于列名启发式，只选一个 y |
| `_analyze_generic()` | 点数、前 N 点基线、max-min 幅度、首末漂移、线性斜率、归一化序列 | 没有单位/误差/重复实验；空数据等边界不完整 |
| `inferred_measurement_type()` | 识别 I–V、应变-电阻、循环稳定性、光谱响应、通用信号 | 依赖列名关键词 |
| `analyze()` | I–V 端点电流与近零偏微分电阻；应变 ΔR/R0 与估算 GF；循环首末保持率；光谱峰值、离散 FWHM、梯形积分 | 都是单曲线初筛，不是完整科学分析协议 |
| `/api/analyze` | 文件校验、执行分析、归档原始文件与指标 | 所有异常统一返回 HTTP 400，没有错误分类或分析 timeout |

`/lab` 用 JavaScript 根据返回的 series 画一条临时 SVG polyline（`static/app.js:101-113`），但不存在可复用的 `plot_signal` 工具、图片文件、图表 metadata 或图表 provenance。

**不存在的关键工具**：`load_csv` schema、`filter_signal`、FFT/PSD、pulse peak、Bio-Z magnitude/phase、quality metrics、feature extraction、channel selection、compare experiments、SciPy 滤波、Matplotlib 报告图。`requirements.txt` 也没有 SciPy、Matplotlib 或 scikit-learn。

## 12. 当前有哪些 Paper / PDF Tool？

**状态：【部分实现】**

已实现：

- 实时书目：`openalex_search()`（标题检索，可取公开 abstract）、`crossref_search()`/`crossref_lookup_doi()`、`europepmc_search()`。
- 检索防线：当前问题的中英术语展开、标题级 relevance score、元数据完整性 score、DOI/URL 记录和宽泛结果过滤。
- PDF：`pypdf.PdfReader` 文本提取、分页符保留、chunk/page anchor、SHA-256 去重与本地落盘。
- 论文台账：`papers` CRUD 子集、DOI 导入、reading/review 状态、BibTeX/RIS 导出。
- 证据卡：paper 或 document 二选一来源、人工填写 claim/type/locator/excerpt、命名审核。

关键限制：

- OpenAlex/Crossref 返回的多数是标题/书目元数据，不是全文；只有 OpenAlex 提供时才有公开 abstract。
- 没有 DOI 全文下载、开放获取 PDF 获取、章节/表格/图片解析、OCR、引用网络、撤稿 API 或真正的 method extraction。
- 本地 PDF chunk 没有送给 LLM，因此没有 grounded PDF QA 或 `summarize_method()`。
- evidence card 的 locator/excerpt 由人填写，系统不验证该摘录确实存在于指定页/图。
- `/api/literature` 是四条硬编码公共 seed 的本地筛选，不是主流程的实时论文 API；实时调用在 `/api/research` 内。

## 13. 当前有哪些实验管理功能？

**状态：【部分实现】**

已实现的台账/治理功能：

- 项目：创建与列出 `projects`。
- 样品：创建与列出 `samples`，可关联项目。
- 测量：CSV 分析后创建 `measurements`，可关联样品，可重新计算 SHA-256 完整性。
- 协议：由四类固定模板创建 draft，命名 reviewer approve/reject，并写 `audit_events`。
- 性能 benchmark：手工录入 metric/value/unit/condition，按同名指标+单位汇总，Crossref DOI 验证。
- 论文与证据卡：导入、人工阅读/审核、引用导出。
- 决策包：冻结 reviewed evidence cards 与 measurements 的 JSON 快照，审核并导出 Markdown/RO-Crate-style JSON-LD。
- Provenance graph：按显式外键/快照连接 project、paper、evidence、sample、measurement、protocol、benchmark、decision。

尚缺失：

- 没有 `experiments` 实体，无法表达一次真实实验的日期、操作者、仪器、AD5940 配置、电极布局、受试/样本、环境、通道、采样率和条件。
- 没有 `experiment_files`、`analysis_runs`、`tool_calls`，measurement 也没有 processing method、parameters、tool version 或 agent run link。
- 没有实验对比、异常标记、任务排程、设备采集、批量导入、版本控制、备份/恢复或 ELN/LIMS 同步。
- 没有认证/RBAC；所谓 reviewer 是请求中填写的字符串，不代表经过身份验证的人。
- `audit_events` 覆盖 protocol、benchmark、paper、evidence card、decision packet，但 project、sample、measurement、document 和 research run 没有统一审计事件。

## 14. 数据存在哪里？

**状态：【已经实现】**

默认数据根目录是 `data/`，可用 `FLEXRESEARCH_DATA_DIR` 改写：

- `data/flexresearch.db`：SQLite 业务数据、文档提取文本、chunk、会话、trace、来源、指标与快照。
- `data/uploads/`：上传的 PDF/TXT/Markdown/作为文档导入的 CSV 原始文件。
- `data/measurements/`：通过 `/api/analyze` 归档的原始 CSV。
- `data/provider-settings.json`：base URL 与 model ID，不存 API key。
- `.env`：本地 provider key 和默认配置。
- `data/demo_*.csv`：Git 跟踪的公开演示数据。

`.gitignore` 忽略数据库、uploads、measurements、provider settings 和 `.env`，降低误提交概率；这不是加密、访问控制或备份。

**重要风险**：`GET /data/<path:filename>`（`app.py:2223-2225`）把整个 `ROOT/data` 作为下载根，而不只允许两个 demo CSV。只要知道/猜到相对路径，当前代码可下载 `flexresearch.db`、`provider-settings.json`、`uploads/...` 或 `measurements/...`；系统又没有认证。这与“本地私有资料不外发”的产品文案不等价，部署到共享网络前必须收紧为 demo allowlist 或移除该路由。

## 15. 是否有数据库？

**状态：【已经实现】**

有本地 SQLite 数据库，`get_db()` 每次新建连接并设置 `sqlite3.Row`；`init_db()` 用 `CREATE TABLE IF NOT EXISTS` 初始化。

业务表共 15 个：

`projects`、`documents`、`samples`、`measurements`、`research_sessions`、`research_messages`、`research_runs`、`research_run_sources`、`document_chunks`、`protocols`、`audit_events`、`benchmarks`、`papers`、`evidence_cards`、`decision_packets`；另有一个 FTS5 虚表 `document_chunks_fts` 及 SQLite 自动生成的 shadow tables。

审计时本机实例包含：1 project、1 sample、1 measurement、119 sessions、132 runs、1 paper、1 evidence card、1 decision packet、0 documents、0 chunks、0 audit events。它们是被 `.gitignore` 排除的本地可变数据，不是仓库可复现实例。

工程限制：

- 虽然 schema 声明多个 `FOREIGN KEY`，当前连接的 `PRAGMA foreign_keys` 实测为 `0`，所以 SQLite 不会实际强制这些关系。
- 没有 migration framework；只有 `document_chunks.page_number` 的一次手写兼容迁移。
- 没有 ORM、连接池、事务 service、busy timeout、WAL、备份/恢复或并发写压力测试。
- Docker 默认使用 2 个 Gunicorn worker，但 SQLite 并发写锁边界没有验证。

## 16. 是否有日志？

**状态：【部分实现】**

已有两类持久记录：

- `research_runs.trace_json`：每轮保存 agent label、status、detail；`research_run_sources` 保存来源。
- `audit_events`：保存部分对象的 create/review/verify 动作、actor、detail 与时间。

API 返回的 `runId` 可以作为单轮标识；provider probe 与 benchmark 脚本会计算延迟。Flask/Gunicorn 也会产生默认控制台访问日志。

但没有统一 observability：

- 没有 Python `logging` 配置、结构化 JSON log、文件/日志平台输出或 trace/span ID。
- research run 不保存 start/end/duration、selected tool、tool args、tool result summary、model、token、cost、error type、retry、final status。
- 模型异常只压缩成 trace detail；`/api/analyze` 捕获所有异常并把字符串返回用户，不记录 stack trace。
- 没有 `tool_calls` 表、debug/trajectory 页面、指标聚合、告警或 health dependency checks。
- `/workspace` 显示当前返回的 trace，但不是跨 run 可查询的可观测性控制台。

## 17. 是否有测试？

**状态：【已经实现】**

有 pytest 测试和 GitHub Actions：

- `tests/test_app.py` 目前包含 55 个测试。
- 本次实际运行 `python -m pytest -q`：**55 passed in 2.81s**。
- 测试 fixture 用临时 `FLEXRESEARCH_DATA_DIR` 隔离数据库/文件。
- 已覆盖 health、provider 密钥隐藏/切换、intent 路由、文献 query/rerank、CSV 多类型初筛、项目/样品/测量关系、hash 回验、PDF/chunk/page anchor、本地检索、会话/trace/report、协议审核、benchmark、论文/证据卡、决策包、RO-Crate 与 provenance graph。
- `.github/workflows/verify.yml` 在 Python 3.11/3.12 上安装依赖、compileall、运行 pytest。

覆盖不足必须同时说明：

- 所有 pytest 都在一个文件中，没有 `tests/unit`、`tests/integration`、`tests/e2e`、`tests/agent_eval` 或 `tests/scientific_validation` 分层。
- 没有 coverage 配置或覆盖率报告，不能从“55 passed”推导出高代码覆盖率。
- 外部 API 在单测中主要被 monkeypatch；不证明实时 OpenAlex/Crossref/provider 的当前可用性。
- 没有 1 Hz sine/FFT、已知滤波、多峰、Bio-Z 数学 ground truth，因为对应算法尚未实现。
- 没有 NaN、列名漂移、超大文件、DB lock/corruption、LLM timeout、tool exception、并发和安全测试矩阵。
- 没有浏览器自动化/视觉 E2E；静态页面返回 200 不等于交互全部可用。

## 18. 是否有 Eval？

**状态：【部分实现】**

仓库有四个独立 acceptance/benchmark 脚本：

| 命令 | 真正验证的内容 | 本次结果/边界 |
| --- | --- | --- |
| `make benchmark` | 5 条真实 HTTP chat contract：身份、模型、暗电流、普通模型回答、近期文献 | 依赖已启动服务、真实模型和公网；本次服务未运行，未生成新结果 |
| `make benchmark-drb` | 下载 DeepResearch Bench 3 个公开 prompt，检查至少 3 条可点击、标题关键词匹配来源与标题级边界 | 只是 retrieval adapter，不是官方 RACE/FACT 分数，也不评判答案科学正确性；本次未运行 |
| `make benchmark-lab` | 临时服务中的 CSV、hash、PDF、chunk retrieval、报告引用 | 本次实际 **5/5**；但不检查最终回答是否基于 PDF 内容正确作答 |
| `make benchmark-provider` | 临时 mock provider 的密钥隐藏、立即切换、probe、HTTP 503 降级 | 本次实际 **5/5**；不证明真实 provider 可用 |

另有 `scripts/verify_live.py` 做 health、产品路由、暗电流和实时文献 smoke check。

这还不是需求中的 Agent Evaluation Framework：

- 没有 `eval/golden_cases.jsonl`，也没有至少 40 条覆盖文件/分析/信号/对比/文献/实验设计/异常/歧义的 golden cases。
- 没有统一记录 Task Success、Tool Selection/Argument Accuracy、Trajectory Correctness、Scientific Accuracy、Groundedness、Hallucination、Retrieval Precision/Recall、Citation Correctness、Recovery、Cost。
- 没有 deterministic eval 与 semantic eval 的正式分层，也没有 LLM-as-a-Judge 设计。
- 结果只打印 stdout，不持久化到 eval run、数据库或 CI artifact；CI 当前也不运行这些 benchmark。
- DeepResearch Bench 适配只跑 3/100 task，并用自定义规则，不应称为热门 benchmark 的官方成绩。

## 19. 当前哪些功能真的能运行？

**状态：【部分实现】**

以下能力有当前运行或自动化证据：

- Flask app 能导入并初始化临时数据库；55 个测试通过。
- 隔离式 CSV I–V 初筛、原始文件 SHA-256 回验、文本 PDF 导入、页码 chunk、本地检索和 Markdown 来源导出：`make benchmark-lab` 5/5。
- provider 设置不泄露 key、模型切换下一轮生效、probe 返回 actual model、HTTP 503 显式降级：本地 mock 下 `make benchmark-provider` 5/5。
- 项目/样品/测量、协议、performance benchmark、论文、证据卡、决策包与 provenance graph 的数据库 CRUD/审核主路径有 pytest 证据。
- 身份/产品问题不联网、暗电流等四类固定知识短答、只有显式文献意图才调用书目源，有单测证据。

本次没有验证为“当前可用”的部分：

- `127.0.0.1:8765` 在审计时没有服务进程，健康检查连接失败；这只是未启动，不代表代码不能启动。
- 当前真实 OpenRouter `tencent/hy3:free` 探针返回 HTTP 404，所以真实 LLM 问答当前不可用；mock benchmark 不能替代该事实。
- 本次未运行 OpenAlex/Crossref/Europe PMC 的 live benchmark，因此不能以本次审计证明实时文献端点此刻可用。
- 当前本机唯一 measurement 的原始 CSV 缺失，不能从当前数据库重现其指标。
- 没有真实 Bio-Z、多通道、Pulse Wave、EIT 或实验室私有文件样本的端到端验证。

结论：**通用柔性电子 workflow prototype 可运行；面向真实 Bio-Z 实验的 Agent 闭环尚未具备。**

## 20. 哪些只是 UI 或 stub？

**状态：【部分实现】**

| 名称/表象 | 实际状态 | 证据与准确解释 |
| --- | --- | --- |
| “Conductor / Planner / Researcher / Source Critic / Synthesizer” | 【占位】 | 都由一个 `run_research()` 顺序追加字典；没有独立 Agent、prompt、state、tool 权限或 agent-to-agent 消息 |
| “Multi-agent orchestration”文案 | 【占位】 | `docs/evaluation.md` 使用了该称呼，但实现是同步 workflow trace；不可据此声称 Multi-Agent |
| `SKILL_REGISTRY` / `/api/skills` | 【占位】 | 仅五条 label/external/output 元数据；不是可调用工具注册表或 schema |
| 实验 Planner | 【占位】 | `/api/plan` 和 protocol 创建从四个 `TEMPLATES` 返回固定 steps/metrics/risks；不会读取实验历史或由 LLM 规划 |
| SSE “流式 Agent” | 【部分实现】 | 有 SSE 格式，但先发固定状态，再同步跑完整函数；不是 token stream、逐 tool observation 或可恢复任务 |
| 本地资料“回答” | 【部分实现】 | 能检索并展示 chunk，但 chunk 不进入 LLM；答案不保证由资料支撑 |
| 根页面“上传文件后直接发送问题” | 【部分实现】 | 文件能处理，但同发文本没有传给分析/文档 API，也没有形成一轮可追溯对话任务 |
| 图表 | 【部分实现】 | `/lab` 浏览器生成临时 SVG 折线；根聊天只显示指标；没有 `plot_signal` 文件与 metadata |
| Literature Copilot（`/api/literature`） | 【占位】 | 只筛选 4 条硬编码 `EVIDENCE`；真正实时搜索位于 `/api/research` 的显式文献路径 |
| 自动实验报告 | 【部分实现】 | 有 session/decision Markdown 导出；没有含实验 metadata、质量、处理参数、图、Measured/Calculated/Interpretation 分栏的报告生成器 |
| 实验 provenance | 【部分实现】 | 有 project/sample/measurement hash 和 decision snapshot；缺 experiment_id、channel、processing method/parameters、tool_run_id |
| Tool Calling | 【不存在】 | 模型请求没有 tool schema/tool_calls |
| 向量 RAG | 【不存在】 | 只有 SQLite FTS5，没有 embedding/vector store，也没有检索 context 注入生成 |
| Bio-Z/信号工具 | 【不存在】 | 无阻抗复数处理、滤波、FFT、Pulse Wave、EIT、通道分析或实验对比 |
| Agent State/Memory | 【不存在】 | 有持久记录，但无运行状态模型、history-to-prompt memory、checkpoint/resume |
| Tool observability/recovery | 【不存在】 | 无 tool_calls 表、参数/结果/耗时日志、统一重试/timeout/recovery policy |
| 多用户实验室部署 | 【不存在】 | 无认证、RBAC、审计身份可信性、并发/备份验证；`SECURITY.md` 也明确不声称具备 |
| README roadmap 中的私有文档增强、RBAC、更多测量模板 | 【计划】 | `README.md:109-114` 有路线图文字；未出现的部分不能计入当前实现 |

## 当前最关键的真实性边界

在完成下一阶段工程化之前，可以真实表述：

> FlexResearch 是一个本地优先、规则路由、可选 LLM 的柔性电子研究工作流原型；已实现 CSV 初筛、文档分块关键词检索、书目发现、会话/来源留痕和一组人工审核科研台账。

当前不能表述：

- “LLM 能自主选择并调用科研工具”；
- “已经实现完整 RAG/向量数据库”；
- “是 Multi-Agent 系统”；
- “能分析 Bio-Z、Pulse Wave、EIT 或多通道生理信号”；
- “Agent 结论都可追溯到 experiment/tool parameters”；
- “已建立完整 Agent Evaluation Framework”；
- “通过了 DeepResearch Bench 官方评测”；
- “当前真实模型连接稳定可用”；
- “已可安全给实验室多人直接部署”。

这些缺口不是措辞问题，而是下一阶段必须由 schema、工具执行、ground-truth 测试、运行轨迹和真实 E2E 证据补上的工程能力。

