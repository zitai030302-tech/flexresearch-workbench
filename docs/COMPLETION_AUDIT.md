# 工程 CHECKLIST（原始完整要求）

核对日期：2026-09-29；本日已重新运行完整tests和eval。**工程尚未全面完成；教学暂停，不等待理解题。**
本表替代此前“工程交付候选已完成、只剩教学”的结论。

状态定义：✅ 已完成并实际验证；⚠️ 部分完成；❌ 尚未完成；⏭️ 不适用于当前工程验收。
✅ 只覆盖每行明确写出的范围，不代表任意输入、生产部署或临床正确性。

## 1. 本轮实际运行证据

本批新增21项，关闭signal-007显式处理metadata下的v2合约：Hz×60脉率候选、图hash/版本、完整来源与SQL/历史/报告/浏览器已验。缺fs、常量、普通FFT和参数冲突均另测；不能当临床心率准确率或无参默认滤波。详见[脉搏流程](PULSE_WORKFLOW.md)。

- 2026-09-29同步复核：产品提交`d9a71edfb2751f222efd35ceeb83a77dab619503`已与远端main一致；[GitHub CI 36443853250](https://github.com/zitai030302-tech/FlexResearch/actions/runs/36443853250)的Python3.11/3.12任务及tests、coverage门槛、deterministic eval步骤全部success。这是前一代码快照的远端证据，不能用于本批尚未推送的脉搏修改；下列本地数字为9月29日实测。

- 全量：**774 passed in 86.41s**，0 failed、0 errors、0 skipped；开启 ResourceWarning / PytestUnraisableExceptionWarning 错误门禁。
- 分类：unit 266、integration 258、e2e 28、scientific_validation 44、robustness 13、agent_eval 103、旧 API 回归 62。
- Coverage：5300/5720 statements＝**92.66%**；1532/1814 branches＝**84.45%**；组合90.68%，80%门槛通过。范围 app.py + flexresearch，不含浏览器JS，也未合并独立子进程覆盖。
- Eval v3：**65条；执行60、通过60、失败0、跳过5**；执行覆盖92.31%。外部模型/网络调用0；模型决策回放13、传输回放6。
- 评测数据 SHA-256：`0101b3170628cae414a8e5baaa8590b79b8c7ecd7b5244e676e81bf809e49632`。
- `git diff --check`、Python compileall、启动脚本 bash -n、chat.js node --check：退出0。
- 报告：[逐例 pytest XML](../data/verification/pulse-workflow/pytest.xml)、[coverage JSON](../data/verification/pulse-workflow/coverage.json)、[逐例 eval JSON](../data/verification/pulse-workflow/eval.json)。运行产物仅留本地，不提交实验资料或密钥。

前次补参批次新增32项（13unit、13integration、5评测负对照、1Chromium），实际验证滤波缺参→用户补参→原保存任务续跑→新CSV下载/来源/历史/刷新。修复未关闭下载响应与不完整新带误沿用旧带两个问题。experiment-005采用显式多轮v2协议：原prompt/final expected不改，setup增加用户补参，第一轮必须澄清；不再含糊声称单轮直接完成。详见[补参与续跑](PENDING_SIGNAL_REQUEST.md)。2026-09-27基线提交559c935已推送私有GitHub，远端Python3.11/3.12 CI通过；这条远端证据仅适用于该提交。

前次书目批次新增49项：22单测、21集成、5评测负对照、1Chromium流程。literature-002保持原问题与expected，实际查询显式选定的论文记录；没有摘要/全文就澄清，不用标题、备注或其他文档推定参数。SQL/JSONL/历史、SSE、缺失/歧义/非法ID与浏览器刷新均已验。详见[文献证据边界](PAPER_EVIDENCE_BOUNDARY.md)。

此前初始草案批次新增35项，experiment-001八章节、待确认参数、审核边界、请求hash、SQL/JSONL、下载及刷新仍通过回归。指定历史时不偷偷改用通用草案。详见[初始实验草案](INITIAL_EXPERIMENT_PLAN.md)。

此前目标上下文批次新增30项，关闭experiment-003：切换ch2→ch4实际重算2.4→1.2Hz，保存分析目标来源、SQL/报告/历史。不跨会话/文件继承，不静默丢掉滤波。详见[分析目标上下文](ANALYSIS_GOAL_CONTEXT.md)，仍通过全量回归。

此前I–V批次新增30项，关闭data-004完整工具、数值、来源和报告合约；详见[I–V完整工具合约](IV_ANALYSIS.md)，仍通过全量回归。

此前科学上下文批次新增31项，关闭data-003/signal-005/experiment-004；完整统计与缺fs澄清继续通过回归。详见[科学上下文合约](SCIENTIFIC_CONTEXT_CONTRACTS.md)。

历史316→375→420→449→511→546及失败过程保留在RUNTIME_VALIDATION。上一批文档索引35项、file-003/006/007原合约，以及[曲线算法](CURVE_FEATURES_METHOD.md)、[SQLite锁恢复](DATABASE_RECOVERY.md)均仍通过全量回归。文档解析超时不晚到提交、SQL索引回滚与图片PDF澄清的边界见[文档索引](DOCUMENT_INDEXING.md)，不是OCR或断电原子性。

## 2. 用户指定重点逐项核对

“已运行”均指本轮完整suite中实际执行，报告内可按路径/测试名称回查。静态文档审核单独写明，不伪装成执行测试。

路径约定：表内未写目录的Python模块均位于[`flexresearch/`](../flexresearch/)，只有[`app.py`](../app.py)在仓库根目录；`run_agent_eval.py`位于[`scripts/`](../scripts/run_agent_eval.py)。文档均在`docs/`，运行报告在`data/verification/pulse-workflow/`。下面每个✅都给出实现范围及实际验收方式，不将静态文档审核伪装为执行测试。

| 项目 | 状态 | 对应代码/文档；实际做了什么 | 是否运行；结果/剩余 |
| --- | --- | --- | --- |
| 当前系统完整审计 | ✅ | [CURRENT_SYSTEM_AUDIT](CURRENT_SYSTEM_AUDIT.md)：重核20问，区分当前/旧基线及实现、部分、占位、计划、不存在 | 已读代码、核SQL表、执行全量测试/eval；实际缺陷及修复分批保留，未完成项列在下方。不是独立安全审计 |
| 真实架构文档 | ✅ | [SOFTWARE_ARCHITECTURE_FOR_ME](SOFTWARE_ARCHITECTURE_FOR_ME.md)：13组件、真实请求链、20工具、SQL/文件边界 | 已逐节对照app.py/核心模块，覆盖experiment_analysis真实上下文读取、同字节解析、结构化澄清及分析目标继承；258项integration通过。无微服务/后台worker/Multi-Agent的包装 |
| Agent / Workflow / RAG定性 | ✅ | app.py、llm_agent.py、science_agent.py、agent.py：规则路由+确定性科学workflow+受限LLM工具循环+最小RAG | 已运行工具循环/科学/RAG测试通过；模型与本地调度明确分开，不称Multi-Agent |
| Tool Calling工程化 | ✅ | tooling.py、schemas.py、model_schema.py、document_indexing.py：20工具的输入/输出校验、异常、timeout、日志；分支白名单/有限循环；文档准备与提交分离 | 已运行unit及tool-loop integration通过；文档解析超时后无晚到提交、非法准备输出拒绝提交均通过。真实模型旧运行另存，timeout不等于强杀线程 |
| Structured Output | ✅ | schemas.py、science_agent.py、paper_tools.py：Pydantic工具结果；科学tool_run_id/文献URL选择及来源校验 | 已运行：30个适用golden结构合约通过，非法JSON/伪造ID/URL测试通过。不是所有API或provider强制schema |
| 实验数据provenance | ✅ | experiment_analysis.py、agent.py、csv_input.py、comparison.py、app.py：实验/源hash/通道/参数/工具ID、派生文件和双源比较 | 已运行错实验/文件/hash、读取中变化、统计/频谱及I–V单位/窗口/原索引来源、SQL/历史测试；来源污染负对照失败。解析与hash使用同一bytes，但hash不证明采集真实 |
| RAG | ✅ | document_indexing.py、retrieval.py、app.py：typed摄取→分页chunk→字符哈希向量/FTS5→同一SQLite事务→检索→授权context→引用 | 已运行RAG integration、真实HTTP和Chromium页码链接/去重/刷新通过；空白首物理页仍正确引用第2页，图片PDF明确失败。最小版本，无OCR/神经embedding/ANN |
| State / Memory | ✅ | conversation_context.py、experiment_tools.py、analysis_parameters.py、analysis_context.py：普通上下文、运行state、实验参数/目标、长期资料分开 | 已运行跨轮通道/目标/参数、来源与SQL/报告/浏览器刷新；缺目标、处理选择、作用域和会话隔离均已测。完成后重启历史回读通过，不含checkpoint |
| Unit Tests | ✅ | tests/unit/ | 已运行266/266；schema、科学工具、检索、参数、路由、日期精度、恢复副本/事务和曲线单位/基线/目标点等 |
| Integration Tests | ✅ | tests/integration/ | 已运行258/258；模型回放、RAG、实验状态、检索、历史/方法/比较/报告及真实SQLite锁 |
| E2E Tests | ✅ | tests/e2e/test_browser_workflow.py、test_live_http_workflow.py、test_chat_csv_agent_workflow.py：18项Chromium＋5项独立进程HTTP＋5项Flask | 已运行28/28。此前CSV/报告/来源/API/锁恢复/曲线/PDF/统计/缺fs/I–V/通道切换流程仍通过；本批新增脉率候选、图、报告下载及刷新后同字节下载；初始方案下载仍通过。外部边界回放，单浏览器不等于跨浏览器或在线模型质量 |
| Scientific Validation | ✅ | tests/scientific_validation/、lab_tools.py、signal_quality.py、comparison.py、curve_features.py | 已运行44/44；信号/滤波/复阻抗/比较/曲线真值及完整/缺失样本统计；此前增加的正、负、零电导近零拟合真值与外侧干扰点仍通过。不是人体/仪器校准验证 |
| Agent Evaluation | ⚠️ | scripts/run_agent_eval.py、tests/agent_eval/、EVALUATION_DESIGN.md | eval实际60/65执行通过；103项评测测试通过（含82项负对照）。开放模型质量/5个合约未完全验收 |
| Golden Dataset | ⚠️ | eval/golden_cases.jsonl：65条、版本和状态、至少9类任务 | 数据结构、adapter一致性、重复运行已通过；60执行，5跳过。≥40条要求已满足，完整数据集未跑通 |
| Tool Selection Accuracy | ⚠️ | run_agent_eval.py：26个适用案例；负对照污染实际工具名 | 离线26/26合约通过，错误名可被拒绝；**不是在线模型选择准确率**，缺代表性重复实测 |
| Tool Argument Accuracy | ⚠️ | run_agent_eval.py：17个适用案例；实验ID/通道/fs/日期参数 | 离线17/17合约通过，改错通道/日期会失败；模型回放不能证明真实模型参数生成率 |
| Trajectory Evaluation | ✅ | run_agent_eval.py、llm_agent.py、test_evaluator_negative_controls.py | 17个适用golden通过；精确/子序列、停止/预算、错误恢复及反序负对照已运行；锁重试记录污染可触发失败。范围限已有场景 |
| Groundedness / Hallucination Evaluation | ⚠️ | report_review.py、guardrails.py、run_agent_eval.py | 来源绑定26例、禁止claim15例和报告rubric已运行；**不是开放科学文本的完整蕴含/幻觉率** |
| Failure Injection / Robustness | ⚠️ | tests/robustness/、test_provider_failures.py、test_database_recovery.py、upload_recovery.py及相关e2e | 13项robustness和扩展测试通过；普通问答超时/429及真实SQLite BEGIN/COMMIT锁、原始文件恢复已实测。进程中途崩溃、通用幂等和跨领域统一错误码仍未完成 |
| Logging / Observability | ✅ | app.py持久化函数、tooling.py、static/debug.*：DB+JSONL+debug、用量/错误/来源 | 已运行日志压缩/回读/敏感边界测试通过；已有真实run记录。不含监控告警/SLA |
| Agent Run / Tool Call记录 | ✅ | app.py、agent_runs/tool_calls/analysis_runs | 已运行parent/child、参数、结果摘要、错误、source和latency回读；真实HTTP4步轨迹重启后一致 |
| 数据库设计 | ✅ | app.py:init_db/get_db；六核心表；upload_recovery.py | 实际SQLite已核到全部6表；外键/临时库/关闭连接/持久化及有限锁恢复测试通过。跨文件与DB原子恢复另列未完成 |
| 自动实验报告 | ✅ | history.py、report_narrative.py、report_review.py、app.py报告API | 已运行9类章节、图、数据质量、参数、measured/calculated/interpretation、来源与limits；重启回读一致。解释需人工复核 |
| Guardrails | ⚠️ | tooling.py、guardrails.py、science_agent.py、app.py | 原始只读/新产物/hash/作用域/授权/当前引用/特定医学禁语已测；通用科学语义防幻觉不完整，普通模型仍有错误 |
| 测试覆盖率 | ✅ | coverage.json；上述完整coverage命令 | 已运行，行92.66%、分支84.45%、组合90.68%；门槛通过。不冒充需求覆盖率 |
| 实际启动运行 | ✅ | tests/e2e/test_live_http_workflow.py、打开FlexResearch.command、RUNTIME_VALIDATION.md | 本轮独立进程真实启动5次，CSV场景另重启1次，全部HTTP检查通过。默认8765重新启动且health200；本批浏览器截图已核。默认页展示请求返回queued，模型仍未验证 |
| 完整test suite | ✅ | tests/、pytest.xml | 2026-09-29重新实际运行774/774通过，86.41s，严格资源警告；非仅创建测试 |
| eval suite | ⚠️ | run_agent_eval.py、eval.json | 命令确实执行且exit0；60通过，5明确skip。全量65条不能标通过 |
| PROJECT_TUTORIAL_FOR_ME.md | ✅ | [项目教程](PROJECT_TUTORIAL_FOR_ME.md)：30概念×人话/技术/实际代码/面试，四层state/三层结果 | 已读正文并对照核心符号/测试，本批刷新60/65与脉率候选边界；20工具、八类报告规则、实际实验读取与缺fs边界保留。文档审核，不是作者已掌握 |
| SOFTWARE_ARCHITECTURE_FOR_ME.md | ✅ | [架构教程](SOFTWARE_ARCHITECTURE_FOR_ME.md)：13组件+三类请求链+真实限制 | 已逐节静态对照，相关API/工具/浏览器测试通过；分别说明三类测试边界 |
| INTERVIEW_GUIDE.md | ✅ | [面试材料](INTERVIEW_GUIDE.md)：30秒/1分/3分介绍、80题×4字段 | 已逐题读完并对照现有符号、算法、状态/SQL/评测及测试；修正规划误写实现、指标分母、连接粒度等，文末保留审核记录。不代表作者已掌握 |
| WHAT_I_CAN_CLAIM_IN_INTERVIEW.md | ✅ | [真实性说明](WHAT_I_CAN_CLAIM_IN_INTERVIEW.md)：已实现、Codex辅助、理解但未从零、规划四类 | 已读全文并对照实现/测试/已知失败，更新数字；不虚构独立贡献、临床结果或用户收益 |

## 3. 原始24节要求映射（不漏项）

| 原始节 | 状态 | 本轮审计结论/证据 |
| --- | --- | --- |
| 1. 12项科研用途 | ⚠️ | 管资料/数据/计算/图/比较/论文/方法/历史计划/报告/provenance/异常/证据检查均有实现；方法与计划为有限规则，真实实验室实用性和开放解释还未全面验证 |
| 2. 20问审计、五状态 | ✅ | CURRENT_SYSTEM_AUDIT.md；代码/SQL/全量命令实核，结果见第2表 |
| 3. 定性和真实目标架构 | ✅ | SOFTWARE_ARCHITECTURE_FOR_ME.md；模型外层与Python workflow实际测试通过 |
| 4. 工具层工程化 | ✅ | tooling.py及20工具；unit/integration通过；数值由Python算 |
| 5. provenance | ✅ | 八类来源字段/双hash/上游工具；科学、比较、导出测试通过 |
| 6. 合理最小RAG | ✅ | PDF解析/分页/索引/检索/授权context/citation；integration与真实HTTP通过 |
| 7. 四类State/Memory | ✅ | conversation_context/experiment_tools/history；跨轮、隔离和重启回读通过 |
| 8. 分层自动化测试 | ✅ | 四个要求目录及额外scientific/robustness均运行；18个Chromium流程真实通过 |
| 9. 14维Agent Evaluation | ⚠️ | 14维均有有限分母，另加intent/report；代表性在线质量不足 |
| 10. ≥40条、9类Golden | ⚠️ | 65条且60执行满足数量；5个完整合约仍未通过 |
| 11. 科学数学真值 | ✅ | scientific_validation44/44；无LLM Judge计算数学 |
| 12. 确定性/语义Eval分开 | ✅ | EVALUATION_DESIGN、METRIC_JUDGES；数值/来源规则/报告rubric明确分轨并实跑 |
| 13. 故障注入与恢复 | ⚠️ | 原清单各类有测试入口；真实数据库锁和恢复副本已验，跨介质崩溃恢复/领域错误状态不完整 |
| 14. Run可观测性 | ✅ | run/tool/analysis+JSONL/debug；持久化、日志与HTTP回读实测通过 |
| 15. 最小六表数据库 | ✅ | init_db/get_db；6表已实查，外键/回读/连接关闭测试通过 |
| 16. 自动报告9类信息 | ✅ | 报告API/历史快照/数值解释；报告测试及HTTP产物回读通过 |
| 17. 科学Guardrails | ⚠️ | 科学数值与原始文件硬约束已测；自由文本不能保证无证据结论完全拦截 |
| 18. 启动、test、eval、实际文件trajectory | ⚠️ | 启动/test/eval/浏览器/合成及仓库demo有证据；代表性live质量未完成。仓库无可确认的真实人体原始样本，不捏造 |
| 19. 30概念教材 | ✅ | PROJECT_TUTORIAL_FOR_ME；全文复核、核心符号对照、运行证据链接，非仅创建文件 |
| 20. 13组件架构教程 | ✅ | SOFTWARE_ARCHITECTURE_FOR_ME；逐节实核，真实流程对应测试 |
| 21. 面试专项材料 | ✅ | INTERVIEW_GUIDE全部正文及代码/测试边界已复核，修正宏平均、MRR/nDCG等未实现指标的表述 |
| 22. 80题×4字段 | ✅ | Q01–Q80已逐题阅读和核对对应实现/规划；核验记录在文末。教学继续暂停 |
| 23. 真实性四类 | ✅ | WHAT_I_CAN_CLAIM_IN_INTERVIEW；全文对照代码/测试/失败，明确Codex辅助 |
| 24. 十项汇总＋互动教学 | ⚠️ / ⏭️ | FINAL_DELIVERY含10项工程汇总，但不是最终验收；互动教学按用户最新要求暂停，不属于当前工程门禁 |

## 4. 接下来必须处理，不能用教学代替

1. **剩余5个golden逐条核对**：保持原prompt/expected含义；真实未实现就实现，有实现但缺adapter就补完整验证，不能只改状态。
2. **错误恢复**：failure-003真实SQLite锁/事务失败与原始文件恢复已关闭；实验/文件/hash作用域、预算、缺fs与I–V工具/绘图失败仍回归通过。此前缺目标/滤波选择澄清继续通过；此前初始计划异常与非法输出明确失败、不返回成功草案。进程中途崩溃、通用幂等及其他工具父级领域错误仍需处理。有限BEGIN重试不代表跨介质原子恢复。
3. **开放模型质量验收**：必须与连通性、离线回放及浏览器操作分开，保留既有错误。
4. 每批修改后全量tests/eval复跑、同步文档数字，保留失败/跳过。此前不恢复教学。

累计已关闭：滚动三年窗/精度边界、空来源partial、Bio-Z同义匹配、浏览器14流程、80题文档审核、普通问答真实模型路由、超时/限流错误来源、逐golden状态隔离、failure-003实际锁/回滚/原始文件恢复、data-005/006的GF/指定循环保持率，以及file-003/006/007的typed文档索引/去重/图片PDF澄清合约。failure-001/002的20秒超时/Retry-After预算采用虚拟时钟注入，真实localhost短超时/429另测；不能当在线延迟分数。日期过滤保持保守精度边界，不是已验证全文或学术质量。

此前已关闭data-003、signal-005、experiment-004、data-004、experiment-003及experiment-001完整合约。此前关闭literature-002的书目证据不足合约；此前关闭experiment-005显式多轮v2合约；本批关闭signal-007显式处理metadata的v2合约；其余5条不因邻近工具已实现就自动标完。

### 剩余5条：不是全部“没写代码”，也不是已经验收

| Golden ID | 未完成的完整合约 |
| --- | --- |
| routing-006 | 最近论文检索已有在线标题检查；完整总结质量未评测 |
| routing-007 | 普通迁移率解释可调用模型；缺重复性和claim级内容评测 |
| literature-001 | typed检索和在线DOI已有；缺该原问题的冻结正例qrels与完整adapter |
| literature-005 | DOI URL已返回；指定三篇的citation/resolver合约无独立adapter |
| literature-007 | 不触发论文搜索的门控已测；开放生物阻抗解释质量未校准 |

逐条原prompt/expected与当前原因保留在`eval/golden_cases.jsonl`，执行报告明确skip。解决它们需要实现或增加完整适配验收，不是把状态改为implemented。

## 5. 明确不伪造、也不擅自扩张的项目

- ⏭️ 真正Multi-Agent、独立worker/scheduler/ANN/生产20人部署：本次可解释架构的“不存在/规划”项，不靠加框架装成已实现。
- ⏭️ 教学理解题：用户已暂停；不等待回答，不据此标工程blocked。
- ❌ 真实科研效能/人体或仪器验证：没有足够已授权数据和专家判定，不能用合成信号替代、不能编造通过率。
- ❌ 开放式科学解释的完整人工标注评测：未完成。有限规则和一次模型成功不足以声称完成。

**本清单是进度审计，不是最终完成声明。**

