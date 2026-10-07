# FlexResearch 测试与 Agent Evaluation 设计

更新时间：2026-09-29。本文件已依据当前实现重写；旧的“82 tests、11/52、无模型工具循环、无上下文”描述不再代表现状。最新验收状态以 [工程清单](COMPLETION_AUDIT.md) 和实际报告为准。

## 1. 三类证据不能混用

| 证据 | 证明什么 | 不证明什么 |
| --- | --- | --- |
| pytest、数学 oracle、模型决策回放 | 给定输入下的契约、计算、流程、错误边界 | 真实模型理解能力或人体实验有效性 |
| 独立进程 HTTP 测试 | 网络请求、真实文件/DB、完成后重启可恢复 | 浏览器 DOM、执行中崩溃恢复、生产并发 |
| Chromium E2E | 实际DOM交互、来源点击、上传/图/下载、刷新、API切换 | 真实外部模型/DOI解析、跨浏览器兼容性、生产并发 |
| live provider / 浏览器运行记录 | 指定模型/输入/当时服务下的实际表现 | 稳定 SLA、总体正确率、所有任务通过 |

不要把“文件存在”当作验收，也不要把一次在线请求成功当成内容正确。此前普通技术追问 session 189 的模型内容错误仍保留在运行记录中。

## 2. 当前实现与测试入口

- `app.py`：Flask API、意图路由、模型/书目适配、文件与 SQL 持久化。
- `flexresearch/provider_transport.py`、`tests/integration/test_provider_failures.py`：有限重试、Retry-After、错误码和无秘密的尝试记录；真实localhost超时/429与API持久化测试。
- `flexresearch/upload_recovery.py`、`tests/integration/test_database_recovery.py`：BEGIN有限重试、COMMIT回滚、独立原始CSV恢复副本和下载；真实SQLite锁、归档前后失败、磁盘失败。
- `flexresearch/document_indexing.py`、`app.py:commit_document_index`：只读准备→按时返回后提交；文档/分块/FTS/向量/实验关联在同一SQL事务。解析超时不晚到落库，重复SHA不新增档案；图片PDF仅提示OCR_REQUIRED，不声称已OCR。详见[文档索引](DOCUMENT_INDEXING.md)。
- `flexresearch/llm_agent.py`、`science_agent.py`：有界模型工具循环；分支白名单、参数校验、观察反馈和最终选择。
- `flexresearch/agent.py`：确定性 CSV 科学工作流。20 个注册工具不等于全都交由模型自由选择。
- `flexresearch/curve_agent.py`、`curve_features.py`：按明确单位/基线/目标点计算GF与循环保持率；实际实验上下文、文件哈希、参数、报告和图。
- `flexresearch/iv_analysis.py`、`signal_quality.py`：现有analyze_signal的显式单位I–V分支，完整实验上下文/计算/来源/SQL/报告/浏览器合约见[IV_ANALYSIS](IV_ANALYSIS.md)。不是只测兼容初筛算法。
- `tests/unit/`：schema、工具、检索、模型 schema 兼容、参数、意图等。
- `tests/scientific_validation/`：正弦、噪声、多峰、滤波、复阻抗、通道和比较的数学真值。
- `tests/integration/`：工具循环、RAG、状态、比较、历史/方法/报告、上下文。
- `tests/robustness/test_failure_injection.py`：文件、数值、参数、数据库、模型、工具错误。
- `tests/e2e/test_chat_csv_agent_workflow.py`：Flask test client，不能称浏览器 E2E。
- `tests/e2e/test_live_http_workflow.py`：独立服务和临时 vault；CSV→滤波→FFT→PNG→报告→重启回读；两页 PDF→检索/引用→去重；超大/损坏/无文本 PDF。
- `tests/e2e/test_browser_workflow.py`：18个真实Chromium流程与本地HTTP服务/临时vault；来源/CSV/报告/模型切换/锁恢复/曲线/PDF/统计/缺fs/I–V/通道切换/初始方案外，包含书目元数据证据不足、无来源卡；本批增加滤波缺参、补参、下载和刷新恢复。
- `tests/agent_eval/`：数据集契约、两次评测结果一致性、报告 rubric、评测器反例。
- `tests/test_app.py`：保留原 API 回归，未为了目录整洁破坏既有测试。

独立进程测试在应用网络适配层禁止公网调用。Chromium测试只在外部提供方适配边界回放，DOM、Flask、SQL和文件操作真实执行。合成DOI点击后的导航被拦截到测试页面，不冒充在线解析。截图/trace保存在output/playwright（Git忽略）；已实际查看本轮截图。测试不读写用户实验库，不修改真实API配置。

## 3. Golden Dataset 与运行方式

`eval/golden_cases.jsonl` 含 65 条版本化目标合约，涵盖文件、数据、信号、对比、文献、实验计划、异常、工具失败和歧义等类别。

当前为 60 条有 adapter 并执行、5 条跳过。60/60 是已执行集合的结果，数据集执行覆盖为 92.31%；不是全部 65 条通过，也不是在线 Agent 正确率。

字段：id、version、category、prompt、setup、oracle、expected、metrics、current_status。每条未完成合约保留原因；不得为提高通过率删除困难案例或把旧工具名悄悄换成更容易通过的路径。

此前完成file-008的413/FILE_TOO_LARGE/failed与无归档检查，以及literature-003/004的v2合约：原prompt/expected不变，替换planned fixture为明确标记的合成元数据，真实执行日期窗、参数、来源、空结果partial与持久化。其余未完成合约不标通过。

2026-09-13：failure-003升为v2，原prompt/expected不变；用合成1kΩ I-V fixture实际持SQLite写锁至少1.5秒，验证有限重试、partial状态、锁定期间原始文件可下载、解锁后人工重试仅一份归档。没有把数据库异常mock当成真实锁恢复。

2026-09-14：data-005/006升为v2，原prompt/expected不变；使用手算GF=2/循环1000保持率92%的合成fixture，实际上传并执行load_experiment_data→load_csv→extract_features。原必需工具按序出现，额外load_csv为真实字节读取；单位/基线/目标点、工具来源、DB参数和报告均校验。未删掉1500次70%的干扰末点。8个新负对照证明改错数值、基线、单位、源hash、工具ID、循环编号或顺序会失败。方法见CURVE_FEATURES_METHOD。

2026-09-14文档批次：file-003/006/007升为v2，原prompt/expected不变。ReportLab固定生成真实两页文本PDF与嵌入光栅图片、无可提取文字的PDF；实际执行index_document，检查输入/输出、SHA、页码、同ID去重、SQL与会话、OCR_REQUIRED且无方法/归档。当时51/65执行；6个新负对照污染工具名、页码、hash、去重标记、失败状态或方法claim时均失败。PDF已渲染并目视核对，不用空PDF冒充扫描件。

2026-09-14科学上下文批次：data-003/signal-005/experiment-004升v2，原prompt/expected不变；实际实验读取、同bytes解析/hash、完整统计或频谱、所有来源字段、SQL参数及原问题回读。缺fs请求明确澄清字段并无频率结论。三个新合约通过，当时54/65；8项新负对照能检出斜率/有效数/hash/工具/字段/伪造频率/错通道/主峰。旧科学/状态adapter仍要求原动作，另外精确要求新增的context步骤，非任意子集匹配。见SCIENTIFIC_CONTEXT_CONTRACTS。

2026-09-19/20 I–V批次：data-004升v2，原prompt/expected不变。合成电压V/电流mA、有2µA偏置的线性fixture独立真值为1000Ω；真实上传/实验读取/analyze_signal、精确窗口与样本索引、来源/SQL/报告/历史均校验。6个负对照检查数值、单位、窗口、hash、工具来源和顺序。首次adapter误读公开轨迹result字段，现按真实resultSummary验全量结果，保留失败报告，不放松数值或来源标准。

2026-09-21目标上下文批次：experiment-003升v2，原prompt/expected不变；setup明确补充实际执行的前一频谱任务，而不是从旧通道/fs断定FFT。无时间列的三通道合成数据分别2.4/1.2/3.6Hz，原追问实际ch2→ch4重算。验明目标/采样率/通道/实验与来源、SQL/历史/报告；当前单通道字符串与原selected_channels列表作等价比较。5个负对照污染参数、来源、轨迹和数值必须失败。缺目标和上轮滤波选择未明时单独测试澄清，见[ANALYSIS_GOAL_CONTEXT](ANALYSIS_GOAL_CONTEXT.md)。

2026-09-22初始草案批次：experiment-001升v2、保留原prompt/expected，使用明确合成空项目fixture。真实HTTP→create_experiment_plan→八章节/有限内容rubric→未定参数/请求hash/空历史→SQL/下载快照验证；6项负对照分别污染历史、数值、审批、章节、工具或hash，均失败。共66项负对照包含在87项agent_eval测试中。这里的内容规则不证明科研方案优劣，见[初始草案](INITIAL_EXPERIMENT_PLAN.md)。

2026-09-22书目边界批次：literature-002升v2，原prompt/expected/metrics不变；setup用显式选定的合成书目替换planned记录。HTTP→retrieve_paper_chunks→空全文证据/无数值claim→SQL/历史一致性实测。5项负对照污染实际HTTP数值、claims、paper ID、hash或工具名，均被拒绝。当时71项负对照包含在92项agent_eval测试中。不是DOI在线解析或开放科学语义评分，见[文献证据边界](PAPER_EVIDENCE_BOUNDARY.md)。

2026-09-28补参批次：experiment-005升v2，原prompt/final expected保持，setup显式新增fixture用户第二轮“0.5–3 Hz带通，4阶”。首轮必须needs_clarification、不得filter/export；第二轮真实读取→滤波→新CSV保存，校验原始bytes/hash不变、派生hash、来源run、历史和报告。5项负对照检出提前成功、轨迹、hash、原run及滤波参数污染。当时76项负对照包含在97项agent_eval测试中。多轮协议变更公开记录，不将其与旧单轮设置直接比较。见[补参续跑](PENDING_SIGNAL_REQUEST.md)。

`scripts/run_agent_eval.py` v3 负责：

2026-09-29脉搏批次新增signal-007 v2：显式上传filterParameters补齐原setup缺失的频带，原prompt/expected不变；不静默默认。实际实验读取、滤波、FFT/Hz×60、带版本/hash的PNG、SQL/历史/报告通过。6项负对照拒绝BPM/顺序/hash/换算方法/上游工具/频带污染；当前82项负对照包含在103项agent_eval测试。数学48/72/120BPM与常量拒绝单独验证，不是人体心率效能，详见[PULSE_WORKFLOW](PULSE_WORKFLOW.md)。

1. 校验数据集唯一 ID、字段和已实现集合与 adapters 一致。
2. 每条case使用独立vault、数据库、文件和provider probe状态，执行真实工具/API；只在模型/外部传输边界回放。正序/逆序得到相同评分，避免RAG夹具跨case污染。
3. 逐条输出 checks、actual、metrics、measurements、runtime events。
4. 以实际执行案例为通过率分母；未实现明确跳过。
5. 报告 dataset SHA-256、各指标分母、回放次数和运行时间。

当前离线 eval：外部模型调用 0，网络调用 0，model adapter 回放 13，transport 回放 6。回放不是模型实际选择准确率。

## 4. 指标的实际定义

| 指标 | 当前 oracle / 计算方式 | 当前适用案例数 |
| --- | --- | --- |
| Task Success | 案例所有 hard checks 通过 | 60 |
| Intent Accuracy | 路由标签及该场景禁止调用边界 | 7 |
| Tool Selection Accuracy | 该 adapter 中的预期工具/序列匹配 | 26 |
| Tool Argument Accuracy | 实验 ID、通道、fs、滤波、日期及曲线单位/基线等明确字段匹配 | 17 |
| Trajectory Correctness | 精确顺序或 required subsequence；另验预算/停止/锁重试 | 17 |
| Scientific Calculation Accuracy | 明确数学真值和容差 | 22 |
| Groundedness | 哈希、实验/通道绑定、页码/原句、有限 claim 支持规则 | 26 |
| Hallucination Rate | 特定禁止 claim、无结果时不捏造等规则 | 15 |
| Retrieval Precision@5 | top-5 中唯一相关 ID 数 / 实际返回槽位数 | 3 |
| Retrieval Recall@5 | top-5 中唯一相关 ID 数 / 标注相关 ID 总数 | 2 |
| Citation Correctness | 指定引用/页码/原句或DOI/URL绑定契约 | 6 |
| Structured Output Validity | 案例所需的 schema/字段/报告结构 | 30 |
| Recovery Rate | 注入失败后达到允许状态且不伪造结果 | 16 |
| Latency | 3个本地实际时延＋2个虚拟时钟故障预算；不能合并解释为在线延迟 | 5 |
| Cost Accounting | 已知 usage/费用必须确实记录；未知不等于零 | 7 |
| Report Content Quality | 原报告案例下的有限内容 rubric | 1 |

检索 precision 是“最多五条结果中的精度”，不是固定以 5 作分母的定义；不足五条不补空位，必须连同 recall/返回数量解释。重复 ID 占名次但不重复加分，防止 recall 超过 1。两个标注小语料不足以证明通用 RAG 效果。

聚合报告中的 passRate 表示满足该指标契约的案例比例。特别是 hallucination_rate 的 passRate=1 表示禁止规则全部通过，**不是幻觉率为 100%**；observedMean=0 也只代表这些受控样本，没有开放文本的全量人工标注分母。

## 5. 确定性与语义评测分开

确定性：工具名/参数、数值、schema、文件/哈希、执行顺序。数学不使用 LLM Judge。

语义规则：groundedness、hallucination、report_content_quality 单独标记为 semantic_rule_based。报告检查七类数值表述、单位/通道/工具来源、完整性、非因果限制和失败披露；未知陈述始终要求人工审核。

尚未完成：开放式科研解释的专家标注集、评分者一致性、在线模型重复评测和置信区间、通用 claim-level entailment。没有 LLM-as-a-Judge 服务；原需求允许 rule-based semantic eval，不应为了框架数量强行加 Judge。

### 普通模型失败合约（此前验收，本批仍回归通过）

failure-001/002保持原问题“解释柔性电极接触阻抗。”与expected不变：API开启模型后确实进入adapter，不再被固定短答截走。输出`partial`、`MODEL_TIMEOUT`/`MODEL_RATE_LIMITED`、`answerOrigin=unavailable`；聊天历史、agent_runs、JSONL保存一致失败和尝试记录，不附旧论文、不将未知费用写成0。

20秒延迟通过虚拟时钟模拟为超过12秒socket timeout，两次尝试约24.2秒虚拟时间；429按Retry-After=1秒后再尝试一次。`simulated_latency_ms`与实际adapter耗时分开，真实localhost I/O用短deadline另行集成测试。默认最多2次尝试（1次重试），一次格式修复可另发请求，逐请求记录；Retry-After超过2秒交互等待预算时停止，不提前重试。参考[HTTP Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after)与[urllib阻塞timeout](https://docs.python.org/3/library/urllib.request.html)。这不是全请求墙钟deadline，也不是工具线程强制取消。

4个新负对照修改API状态、回答来源、重试次数、错误码，评测均能失败；浏览器实际提交问题→看到限流/重试提示→刷新后保留失败状态。工具模型client也计入失败尝试和未知usage；工具父级的最终stop_reason仍有通用model_error，不能称所有路径领域错误已统一。

## 6. 评测器本身必须能发现错误

`tests/agent_eval/test_evaluator_negative_controls.py` 不只测试 helper：

- 让真实科学工作流先执行，再污染主频，Scientific Accuracy 必须失败。
- 污染 provenance hash，Groundedness 必须失败。
- 反转真实 trajectory，Trajectory 必须失败。
- 污染实际 tool name/channel，Tool Selection / Arguments 必须失败。
- 从实际 HTTP run 删除 cost，Cost Accounting 必须失败，且不能生成零成本 measurement。
- 重复检索 ID 不得抬高 precision/recall；None/NaN/Inf/负数/布尔成本不能当成合法费用。
- 新增5个HTTP输出负对照：错误日期参数、未来日期、改错DOI、空结果假completed、无结果答案捏造DOI，必须触发对应指标或task失败。
- 数据库恢复4个HTTP输出负对照：错误失败状态、SHA、重试轨迹及假测量ID，必须使failure-003对应的recovery/trajectory检查失败。
- 曲线8个HTTP输出负对照：数值、基线、单位、源hash、工具ID、循环编号或顺序被污染时，原GF/保持率合约不能通过；其中未列入原指标的硬约束仍会让Task Success失败。
- I–V6个HTTP输出负对照：数值、单位、窗口、源hash、来源工具ID和顺序被污染时，data-004相应数学/来源/任务检查失败；先验证未污染真实链路能通过，不能靠正例也失败的评测器制造假负对照。
- 通道切换5个HTTP输出负对照：改错通道、采样率、目标来源run、顺序或将1.2Hz改成旧通道2.4Hz时，experiment-003相应参数/轨迹/任务检查失败。全套负对照共60项，仍不是全仓库mutation testing。

这些是有限 mutation-style 负对照，不是全仓库 mutation testing。原报告 rubric 的独立正反例见 `test_report_content_rubric.py`。

## 7. 故障矩阵与边界

| 故障 | 实际验证位置 | 边界 |
| --- | --- | --- |
| 缺文件、损坏 CSV、列别名、NaN/Inf | robustness + scientific/integration | 数值失败不继续编造频谱 |
| 超大文件 | robustness + real HTTP + file-008 | 上传请求上限 8 MiB，不等于支持大文件分片 |
| 缺 fs、非法滤波 | robustness + processing context | 缺失/失败保留部分事实，不猜采样率 |
| DB 异常 | unit/integration、failure-003、Chromium | BEGIN有限重试、COMMIT回滚、原始文件下载/刷新/人工重试已验证；无通用幂等或崩溃checkpoint，见DATABASE_RECOVERY |
| LLM timeout、429/5xx、畸形返回 | robustness + tool-loop integration/eval | 有界重试/停止；稳定领域错误码还不统一 |
| 检索无结果 | RAG/paper-loop integration、literature-004、Chromium | partial/no_relevant_sources、无来源、历史一致；不把有效空JSON当任务完成 |
| Tool exception / timeout | unit、robustness、failure-004/008 | timeout 停止等待，不能强杀线程 |
| 文档注入/密钥请求 | RAG + failure-005/006 | 特定规则，不是通用安全证明 |
| 损坏/无文本 PDF | real HTTP | 结构化错误，无假方法/落库；无 OCR |
| 完成后重启 | real HTTP CSV case | 不证明执行中崩溃恢复或 checkpoint |

## 8. 运行、覆盖率与报告

完整复现：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pytest --cov=app --cov=flexresearch --cov-branch --cov-report=term-missing --cov-report=json:data/verification/pulse-workflow/coverage.json --junitxml=data/verification/pulse-workflow/pytest.xml --cov-fail-under=80 -q -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning
python scripts/run_agent_eval.py --output data/verification/pulse-workflow/eval.json
```

覆盖范围是 `app.py` + `flexresearch/`。测试/脚本/浏览器 JS 不在此 coverage 分母；独立子进程未自动合并进 Python coverage。报告分别披露行覆盖与分支覆盖，命令的组合 coverage 门槛为 80%。不要与此前仅行覆盖 90.17% 直接比较。

产物：pytest.xml（每例结果）、coverage.json（文件/行/分支）、eval.json（每例实际与分母）。它们证明本机这次执行；Makefile/CI 文件存在不代表远端 CI 运行过。

## 9. 已知未验收项

- 8 条 golden 仍是 partial；不能删除或算通过。
- 已通过18个Chromium流程；更多交互、扫描件和跨浏览器兼容性仍未全面覆盖。
- 公网模型的开放式技术答案质量未通过系统验收，已观察到错误。
- 真实科研/人体数据集、专家评审和临床验证未提供，不能伪造。
- 上传数据库锁的有限恢复已通过；进程中途崩溃、跨文件与数据库原子恢复、通用幂等及20人并发未完成。

以上缺口与已通过的有限验证并列记录。工程尚未全面验收，不恢复教学。

## 10. 日期合约与来源边界

recent_only 使用UTC当天作为上界，向前取三个日历年，同日包含；闰日下界按目标年份最后有效日。模型不能改写掉用户原问题的窗口，丢失条件时返回可恢复工具错误。from_year/to_date记录在实际规范化工具参数中，不是评测器补造。

来源日期保留YYYY / YYYY-MM / YYYY-MM-DD精度，只有整个不确定区间都落在窗口内才接纳；边界年仅有年份会排除，未知/非法日期不填假月日。date_excluded_records仅统计工具在适配器返回后再次排除的条目，不代表提供方原始响应的总排除数。日期来自公开元数据，不证明科学质量。

请求参数对照[Crossref日期过滤说明](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/)与[OpenAlex过滤文档](https://github.com/ourresearch/openalex-docs/blob/main/how-to-use-the-api/get-lists-of-entities/filter-entity-lists.md)。测试固定时钟并手工标注边界oracle，不能靠被测函数自己生成expected。

