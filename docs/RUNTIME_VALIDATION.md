# 运行验收记录

## 最新工程复审（2026-09-29；脉率候选与完整产物合约）

- 严格全量命令实际退出0：**774 passed in 86.41s**。新增21项＝7数学真值＋7HTTP集成＋6评测负对照＋1Chromium流程。分类为unit266、integration258、e2e28、scientific44、robustness13、agent_eval103、旧API62。
- Coverage：5300/5720语句＝92.66%；1532/1814分支＝84.45%；组合90.68%，80%门槛通过。420未覆盖语句、282未覆盖分支；仍仅app.py+flexresearch，不含前端JS或子进程合并。
- 全量后独立eval实际exit0：65条，60执行/60通过/0失败/5跳过，执行覆盖92.31%；数据SHA`0101b3170628cae414a8e5baaa8590b79b8c7ecd7b5244e676e81bf809e49632`。新增分母task60、trajectory17、science22、groundedness26；其余不变。外部LLM/网络0，模型adapter回放13、transport回放6、成本0。p50=11.994ms/p95=101.536ms仅本地adapter，不是产品延迟。
- 频谱工具在显式脉搏请求时由Python执行Hz×60换算；普通FFT不产生脉率候选，常量信号拒绝估计，缺fs无Hz/BPM结论。聊天/报告明确不是已验证心率。图记录自身hash、源hash及方法版本；报告分别检查Hz和BPM解释完整性。
- signal-007 v2原prompt/expected保留，setup明确补充滤波参数表单；实际执行实验读取→CSV→滤波→FFT→PNG，校验1.2Hz/72BPM、原始bytes、处理参数/工具来源、PNG下载与SQL/历史/报告。不把新增metadata当成旧v1本来已有，也不将合成真值冒充人体效能。
- 定向14项通过0.98s；6项负对照通过1.00s，能够拒绝BPM、轨迹、hash、方法、上游工具和频带污染；真实Chromium流程1项通过3.80s，18个浏览器流程均在全量suite中通过。浏览器用明确频带的自然语言请求，不冒充无参输入。截图已查看，PNG和五步轨迹可见；下载和刷新后相同报告字节已实际断言。
- 本批未调用线上模型或文献服务；教学继续暂停，工程仍未全面完成。
- 确认旧服务PID75155来自本项目、数据库无running/pending后正常TERM；端口清空再启动新代码（终端session7430，debug/reloader关闭）。默认8765 health实际200/status=ok，模型仍unverified，本批未修改本机模型配置。请求展示窗口返回queued，未将其当作默认窗口已目视确认。Python compileall、chat.js语法及git diff检查实际退出0。

复现命令：`python -m pytest -q -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning --cov=app --cov=flexresearch --cov-branch --cov-report=json:data/verification/pulse-workflow/coverage.json --cov-report=term --cov-fail-under=80 --junitxml=data/verification/pulse-workflow/pytest.xml`；`python scripts/run_agent_eval.py --output data/verification/pulse-workflow/eval.json`。使用`/opt/miniconda3/bin/python`。报告仍只留本地，不上传用户实验库；[数值与协议边界](PULSE_WORKFLOW.md)。

## 历史工程复审（2026-09-28；补参后恢复滤波保存任务）

- 完整严格suite：**753 passed in 79.22s**；0失败/错误/跳过。unit266、integration251、e2e27、scientific37、robustness13、agent_eval97、旧API62。721→753新增32项。
- 语句5277/5697＝92.63%；分支1520/1802＝84.35%；组合90.64%，80%门槛通过。范围仍为app.py+flexresearch，未包含JS或合并子进程。
- 独立eval：65条，59执行/59通过/0失败/6跳过，执行覆盖90.77%；数据SHA `0f3aeecbf2fbcd6132ce5f47abc80e80c5c5e0bd7974d4301a65b9f7e2078313`。外部LLM/网络0；13次模型adapter回放、6次transport回放。新增适用分母：task59、trajectory16、groundedness25；其余沿用上一快照。
- 原请求“滤波并保存结果，但不要改原始文件。”先澄清，0.5–3Hz/4阶作为fixture用户第二轮输入；真实读取experiment→CSV→filter→export，验证原始/派生hash、来源run、SQL/报告/历史与下载。experiment-005 v2明确记录多轮协议补充，原prompt/final expected未改，不能与旧单轮设置直接比较。
- 新增5项负对照能检出提前报成功、顺序、hash、来源run和参数污染。Chromium新增真实上传→刷新→补参→下载→刷新→再次下载；输出在`output/playwright/test_browser_pending_filter_resume_download_and_reload/`。只回放外部模型决策，不计在线能力。
- 初轮严格suite 8 failed/744 passed：新增adapter和测试下载响应未关闭。修复响应生命周期后复跑。另有回归实际复现“采样率100Hz，改为低通5”缺Hz却沿用原带；现返回澄清。18项定向严格测试通过，随后完成上述753项全量。
- 全量后独立eval exit0；compileall、node --check和git diff --check均exit0。教学继续暂停，整体目标未完成。
- 收尾时8765无监听，启动当前代码（终端session15759，debug/reloader关闭）；`/api/health`实际200/status=ok，模型配置存在但仍unverified，本批未发在线模型请求。已请求在Codex显示页面，工具返回queued，不将此称为已目视确认默认窗口。本批Chromium测试final.png已查看，首轮澄清、第二轮滤波保存与下载入口均可见。

复现：`python -m pytest -q -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning --cov=app --cov=flexresearch --cov-branch --cov-report=json:data/verification/pending-filter/coverage.json --cov-fail-under=80 --junitxml=data/verification/pending-filter/pytest.xml`；`python scripts/run_agent_eval.py --output data/verification/pending-filter/eval.json`。本机解释器为`/opt/miniconda3/bin/python`（3.13.9）。报告在上述本地忽略目录；GitHub可从源码重跑。

详见[补参合约](PENDING_SIGNAL_REQUEST.md)与[工程清单](COMPLETION_AUDIT.md)。基线提交`559c935`的CI记录保留为历史证据。

2026-09-29同步复核：本批产品提交`d9a71edfb2751f222efd35ceeb83a77dab619503`已推送私有仓库，`git ls-remote`确认远端main与本地一致，工作树干净、无在途pytest/eval/git提交进程。[GitHub Actions 36443853250](https://github.com/zitai030302-tech/FlexResearch/actions/runs/36443853250)已completed/success；Python3.11与3.12均通过编译、完整tests、coverage门槛及deterministic eval步骤（完成时间分别为2026-09-28 23:33:21和23:34:38，北京时间）。这是该提交的远端步骤状态证据，不是实时模型质量或6条未执行golden的通过证据。本次未改产品代码、未重跑本地suite；仅补记已核实的CI结果。详细日志下载遇到网络EOF，未据此新增远端测试数量或coverage数值声明。

## 历史工程复审（2026-09-22；书目记录不能冒充方法证据）

教学继续暂停。本批关闭literature-002原合约；仍有7个golden、开放模型质量与部分恢复机制未验收，目标保持进行中。

- 最终完整suite **721 passed in 77.61s**，exit0；JUnit记录721 tests、0 errors、0 failures、0 skipped，开始时间2026-09-22 14:25:38 +08:00。ResourceWarning和PytestUnraisableExceptionWarning按错误处理。分类：unit253、integration238、e2e26、scientific_validation37、robustness13、agent_eval92、旧API62。
- Coverage：5207/5627语句＝**92.54%**；1487/1768分支＝**84.11%**；组合**90.52%**，80%门槛通过。420未覆盖语句、281未覆盖分支、255partial branches。范围app.py+flexresearch，不含浏览器JS，也未合并独立子进程覆盖。
- 全量后独立eval，exit0：**65条、58执行/58通过/0失败/7跳过**，执行覆盖89.23%。数据SHA-256 `62d2e80036efc9e27acaef07048ba6786c0abb383ac2f2dbb05ab5d578168f2b`。13次模型adapter回放、6次transport回放；评测外部模型/网络调用0、成本0。本地adapter p50=9.524ms、p95=142.925ms，不是在线模型延迟。
- 指标适用分母：task58、intent7、selection26、arguments17、trajectory15、science21、groundedness24、hallucination15、precision3、recall2、citation6、structured30、recovery16、latency5、cost7、report1。71项评测负对照包含在92项agent_eval测试中；不是开放任务成功率。
- 672→721新增49项＝22unit＋21integration＋5评测负对照＋1Chromium。定向114项通过9.72s，评测与浏览器20项通过34.19s；补严格ID类型、多编号列表歧义及真实文档仍可摘录的回归后，最终721项全量通过。全量之后仅同步文档，未再修改产品代码。
- literature-002保持原prompt/expected/metrics；v2 setup用明确合成书目fixture与paperId取代planned记录。实际HTTP→retrieve_paper_chunks→选定SQLite书目→无全文澄清/空numericClaims→SQL/历史回读全部通过。临时库另有Methods干扰文本，不能被混用。合成DOI不是已验证出版物，本项不评在线解析。
- typed输入要求document_id/paper_id二选一；元数据结果不能携带全文分块/文档/文件/hash，不能交给方法摘录器。不存在记录或工具异常返回error，而非成功核验。未选定、多编号、与显式API范围冲突等均澄清，不默认拿第一篇。参数问题仍可通过明确文档编号走已有hash检查/方法原句摘录。
- 5个负对照分别污染实际HTTP数值、numericClaims、paper ID、源hash和工具名，均使相应指标失败。此处groundedness/hallucination只是有限证据边界规则，不是通用科学文本蕴含或在线模型评分。
- 26项E2E＝16个Chromium＋5个独立进程HTTP＋5个Flask。Playwright技能用于同一聊天窗口实际提交书目问题、展开记录、确认无来源卡、刷新恢复；final.png已查看，简短提示与折叠记录正常，没有Crossref卡片。截图/trace：output/playwright/test_browser_metadata_only_paper_clarifies_without_foreign_sources/。自动测试临时vault，不污染真实实验库。
- 默认8765已确认PID30487无running/pending记录后正常TERM；端口无监听再启动新代码，当前PID43287，终端session65842。health实际200/status=ok，免费Lightning配置未改、仍unverified。没有因等待超时重复启动。
- 复用现有应用tab2，刷新后实际提交“论文1的具体采样率和滤波参数是什么？”。现有书目记录被正确识别为无绑定全文；UI显示短澄清和“论文1·仅书目记录”，已展示并保留窗口。run `679803e141514911a31a01ba7cfba898`，session119；API/SQL回读确认literature/partial、deterministic-python、token0/cost0、numericClaims空。仅新增聊天运行记录，未修改书目、实验、原文件或旧错误回答；没有发送模型/外部检索请求。
- SSE删除执行前固定声称“正在请求实时学术元数据”的事件，只显示实际轨迹。它仍不是逐token流式回答，不以此声称完整流式Agent已实现。
- 文档同步时发现教程旧数字“57执行、9跳过”未随上批同步，已修正为58/7；历史批次数字保留。表格和链接检查与内容审核分开，不因创建文档就宣称作者已经掌握。
- 最终静态命令Python compileall、node --check、bash -n、git diff --check分别运行，均exit0。文档核验exit0：32项重点＝24✅/8⚠️、原始24节、7个remaining ID与dataset partial集合一致；30概念×4字段、80题×4字段、13组件；14份文档/README的127个本地Markdown链接缺失0。JUnit721条与eval SHA/58执行/7跳过一致。工具API实返20项，演示run实返唯一retrieve_paper_chunks与空source_refs。

报告：[pytest.xml](../data/verification/engineering-audit/pytest.xml)、[coverage.json](../data/verification/engineering-audit/coverage.json)、[eval.json](../data/verification/engineering-audit/eval.json)；[书目证据合约](PAPER_EVIDENCE_BOUNDARY.md)、[32项CHECKLIST与24节要求](COMPLETION_AUDIT.md)。

## 历史工程复审（2026-09-22；无历史依据的初始实验草案）

教学继续暂停。本批关闭experiment-001原合约；仍有8个golden、开放模型质量和部分恢复机制未验收，不宣称工程全部完成。

- 最终完整suite **672 passed in 74.64s**，exit0；JUnit记录672 tests、0 errors、0 failures、0 skipped，开始时间2026-09-22 14:02:06 +08:00。ResourceWarning和PytestUnraisableExceptionWarning按错误处理。分类：unit231、integration217、e2e25、scientific_validation37、robustness13、agent_eval87、旧API62。
- Coverage：5152/5572语句＝**92.46%**；1461/1742分支＝**83.87%**；组合**90.42%**，80%门槛通过。420未覆盖语句、281未覆盖分支、255partial branches。范围app.py+flexresearch，不含浏览器JS，也未合并独立子进程覆盖。
- 全量之后独立eval，exit0：**65条、57执行/57通过/0失败/8跳过**，执行覆盖87.69%。数据SHA-256 `459d721973d22023d09dd72bf37f467b9b21827441e78358f404622b2eb1d09a`；13次模型adapter回放、6次transport回放，评测外部模型/网络调用0、成本0。本地adapter p50=8.526ms、p95=114.793ms，不是在线延迟。
- 指标适用分母：task57、intent7、selection26、arguments17、trajectory15、science21、groundedness23、hallucination14、precision3、recall2、citation6、structured30、recovery16、latency5、cost7、report1。未执行项不进入通过率分母；66个负对照包含在87项agent_eval测试中。
- 637→672新增35项＝22unit＋6integration＋6评测负对照＋1Chromium。首轮定向46项通过2.62s，后续组合117项通过27.29s；补明确停止原因/内置规则表述后进行最终全量672项。静态Python compileall、node --check、bash -n、git diff --check实际exit0。全量之后只同步文档，未改产品代码。
- experiment-001保留原prompt/expected/metrics；v2仅将planned空项目替换为明确合成fixture，并补实际adapter。真实HTTP→create_experiment_plan初始模式→八章节/有限内容rubric→未定参数/请求hash/空历史→SQL/JSONL/下载快照通过。状态completed指草案生成，不是实验执行或协议审批；固定approval_required=true、executable=false。既有指定历史的计划仍回归通过，不会在历史范围缺失时回退成通用草案。
- 原问题没有给出具体采集参数，ADC采样率、每通道输出率、频点、稳定等待/重复次数等保持空或待确认；不从提问数字推定审批。结构化输出拒绝虚构历史、数值、审批与请求hash。六个负对照修改实际HTTP响应的历史/数值/审批/章节/工具名/hash，评测均拒绝。规则rubric不等于专家评价实验方案价值。
- 25个E2E＝15个真实Chromium流程＋5个独立进程HTTP流程＋5个Flask流程。Playwright技能用于实际浏览器验收：原请求→逐章展开→下载→刷新→再次下载同字节快照。本批final.png已查看，回复简短，八章节折叠、下载及输入框可见；无Crossref或虚假历史来源。截图/trace在output/playwright/test_browser_initial_plan_sections_download_and_reload/。自动测试使用临时vault，禁止外部模型/提供方调用。
- 默认8765旧终端session5962已不存在，lsof确认端口无监听、数据库running/pending为0，之后启动当前代码，PID30487（终端session80386）。health实际200/status=ok；免费Lightning配置未改、模型仍unverified。不是因一次等待超时就重复启动，也未终止用户活动。
- 在现有应用窗口实际提交原问题，保留原问答，生成session119的run `7e6cfb61b085476e8aea038809a58edf`。UI显示八章节、下载和“采样率·待确认”，窗口已可见并保留。API回读证明一条真实create_experiment_plan、deterministic-python、无来源文件、无历史结果、report200且与SQL快照同字节；没有调用模型或创建实验测量。该演示只新增聊天与计划运行记录，不覆盖旧错误回答。
- 实现时查阅ADI官方数据手册，核对ADC/DFT/ODR概念，链接和适用边界写在INITIAL_EXPERIMENT_PLAN；这不是应用在本次请求中检索到的论文，不记作运行时证据。
- 文档结构/证据一致性检查exit0：32项重点（24✅、8⚠️）、原始24节映射、剩余8个ID与数据集partial集合完全一致；80题×4字段、30概念×4字段、13组件齐全。13份当前文档/README的115个本地Markdown链接缺失数0；JUnit分类、数据集SHA及变更指标分母均与报告一致。结构检查不能代替内容审核或证明作者已经掌握。

最终报告：[pytest.xml](../data/verification/engineering-audit/pytest.xml)、[coverage.json](../data/verification/engineering-audit/coverage.json)、[eval.json](../data/verification/engineering-audit/eval.json)；[初始草案合约](INITIAL_EXPERIMENT_PLAN.md)、[32项CHECKLIST与24节原要求](COMPLETION_AUDIT.md)。均为本机实测，不冒充远端CI、专家审核、人体实验效能或在线模型准确率。

## 历史工程复审（2026-09-21；通道切换与分析目标状态）

教学继续暂停。本批关闭experiment-003完整合约；仍有9个golden、开放模型质量和部分恢复机制未验收，不宣称工程全部完成。

- 最终完整suite **637 passed in 70.55s**，exit0；JUnit记录637 tests、0 errors、0 failures、0 skipped，开始时间2026-09-21 21:35:42 +08:00。ResourceWarning和PytestUnraisableExceptionWarning按错误处理。分类：unit209、integration211、e2e24、scientific_validation37、robustness13、agent_eval81、旧API62。
- Coverage：5056/5477语句＝**92.31%**；1427/1708分支＝**83.55%**；组合**90.23%**，80%门槛通过。421未覆盖语句、281未覆盖分支、255partial branches。范围app.py+flexresearch，不含浏览器JS，也未合并独立子进程覆盖。
- 全量之后独立eval，exit0：**65条、56执行/56通过/0失败/9跳过**，执行覆盖86.15%。数据SHA-256 `88490c55cb329b380678d26764fda6369ce02be71a85953d763aa3eb3da17d81`；13次模型adapter回放、6次transport回放，外部模型/网络调用0、成本0。本地adapter p50=9.084ms、p95=117.918ms，不是在线延迟。
- 指标适用分母：task56、intent7、selection26、arguments17、trajectory15、science21、groundedness23、hallucination13、precision3、recall2、citation6、structured29、recovery16、latency5、cost7、report1。未执行项不进入通过率分母；60个负对照包含在81项agent_eval测试中。
- 607→637新增30项＝14unit＋10integration＋5评测负对照＋1Chromium。experiment-003原prompt/expected不变；v2的setup补充实际执行的前一任务“通道2，采样率100Hz，分析FFT主峰”。旧setup只有通道和fs，不能证明目标；不伪称旧setup已包含目标，也不直接造数据库记忆。
- 合成CSV没有时间列，ch2/ch4/ch14分别2.4/1.2/3.6Hz；前一上传实际计算ch2，原追问实际读取实验003→原CSV→计算ch4。精确检查100Hz、通道4、目标来源run、SQL/报告/历史与原文件不变；不会复制前一2.4Hz。5个新增负对照污染通道、fs、目标来源、顺序或数值，均能被评测拒绝。
- analysis_context只记成功的频谱/统计/质量目标，当前明确目标优先，同会话/文件明确继续才复用。无目标、旧滤波选择不明则结构化澄清；失败/部分任务不能成为成功目标，不跨新上传继承，不静默丢掉滤波。滤波参数与分析目标的来源分别保留，不是自由文本长期记忆或checkpoint。
- 聊天追问与上传共用内嵌工具轨迹、目标来源链接和报告。明确科学任务清除无关旧两列初筛卡片及measurement旧指标；实际typed结果保留。第一条用户消息移除欢迎卡，对话区独立滚动；未重写用户历史回答。
- 失败记录：首轮51通过/3失败（2.85s），旧科学模型回放未复制新增已确认analysis_context；修正为复制实际完整scope，严格验参仍保留。随后114通过/1失败（43.81s）暴露追问缺内嵌轨迹，修产品共用trace卡。另次24通过/1失败（17.93s）来自测试误要求整个展开卡必须装进单一视口；改验实际报告下载可达、刷新后再次下载且字节一致，没有放宽数值/来源/轨迹要求。
- 之后35项浏览器/目标组合通过17.37s；补滤波选择边界后37项上下文回归通过1.90s；最终637项全量通过70.55s。中途eval进度报告为channel-switch-progress-eval.json，最终报告为eval.json。最终全量之后只同步文档，未再改产品代码。
- 24个E2E＝14个真实Chromium流程＋5个独立进程HTTP流程＋5个Flask流程。Playwright技能用于实际浏览器验收；本批两轮原问题→2.4/1.2Hz→三工具轨迹/目标来源→下载→刷新→同字节下载通过。最终final.png已查看：通道、结果和来源显示正确；展开长卡需滚动，不声称整卡能装进一屏。测试使用临时vault并禁止外部提供方请求，不污染用户真实库。
- Python compileall、node --check static/chat.js、bash -n双击启动器、git diff --check分别实际执行，均exit0。清单、架构、教程、README及面试材料同步本批数字；下方历史批次保留当时数字。
- 默认8765：确认旧PID63726的工作目录/命令及running/pending记录0后正常TERM，当前代码以PID3761运行（终端session5962）。health实际200/status=ok；/api/tools实际200、20项，并含analyze_experiment.analysis_context输入schema；新版chat.js提供内嵌轨迹与目标来源。复用已有应用标签reload、设置可见并保留，核到输入框、原“在干嘛/你是谁/你好”历史和免费Lightning“未验证”。未改模型/API配置、旧问答，未发真实模型请求；服务健康不等于模型质量验收。
- 文档结构/链接检查实际exit0：32项重点（24✅、8⚠️）、原始24节映射、剩余9个ID与golden的partial集合完全一致；Q01–Q80及每题四字段无缺项，30个概念齐全；12份当前文档/README的93个本地Markdown链接缺失数0。JUnit逐例分类与上方209/211/24/37/13/81/62一致。架构组件表实际13项，修正标题误写14；结构检查不替代内容审核，更不证明用户已掌握。

最终报告：[pytest.xml](../data/verification/engineering-audit/pytest.xml)、[coverage.json](../data/verification/engineering-audit/coverage.json)、[eval.json](../data/verification/engineering-audit/eval.json)；[分析目标合约](ANALYSIS_GOAL_CONTEXT.md)、[32项CHECKLIST与24节原要求](COMPLETION_AUDIT.md)。浏览器证据：`output/playwright/test_browser_channel_switch_goal_report_and_reload/final.png`及trace。全部是本机执行证据，不冒充远端CI、真实实验效能或线上准确率。

## 历史工程复审（2026-09-20；I–V完整工具链）

教学继续暂停。本批关闭data-004原问题的完整合约；仍有10个golden、开放模型质量和部分恢复机制未验收，不宣称工程全部完成。

- 最终完整suite **607 passed in 69.38s**，exit0；JUnit记录607 tests、0 errors、0 failures、0 skipped，开始时间2026-09-20 14:18:04 +08:00。ResourceWarning和PytestUnraisableExceptionWarning按错误处理。分类：unit195、integration201、e2e23、scientific_validation37、robustness13、agent_eval76、旧API62。
- Coverage：4987/5408语句＝**92.22%**；1407/1688分支＝**83.35%**；组合**90.11%**，80%门槛通过。421未覆盖语句、281未覆盖分支、255partial branches。范围app.py+flexresearch，不含浏览器JS，也未合并独立子进程覆盖。
- 全量之后独立eval，exit0：**65条、55执行/55通过/0失败/10跳过**，执行覆盖84.62%。数据SHA-256 `b1c1f66a307af8c4a430a8ebf5a35d6b136318e87203bd73658c6ab3e94f735d`；13次模型adapter回放、6次transport回放，外部模型/网络调用0、成本0。本地adapter p50=8.05ms、p95=139.319ms，不是在线延迟。
- 指标适用分母：task55、intent7、selection26、arguments16、trajectory14、science21、groundedness23、hallucination13、precision3、recall2、citation6、structured29、recovery16、latency5、cost7、report1。未执行项不进入通过率分母；55个负对照包含在76项agent_eval测试中。
- 577→607新增30项＝11unit＋9integration＋3数学真值＋6评测负对照＋1Chromium。data-004原prompt/expected不变；fixture明确合成，I=V/1000+2µA、电流列mA，独立真值1000Ω。实际执行实验读取→同bytes/hash的CSV→analyze_signal(iv_curve)→来源/SQL/报告/刷新，检查±0.1V窗口和原索引1/2/3；外侧非线性干扰点另验，不能误用全范围斜率。
- 缺单位、混合候选、缺失/非有限值、不支持的滤波/通道或截断输入拒绝猜测；零电导返回null；工具失败不残留旧1000Ω指标，绘图失败保留已验证数值并标partial。报告新增第七类有限数值规则；不是通用科学Judge。成功聊天结论限制在150字内，不内联重复全部限制，详情/报告仍完整保留。
- 失败记录：首轮同名unit/integration文件导致collection exit2、未执行；将单测文件改名test_iv_tool_contracts.py后，31项定向测试通过0.70s。首轮独立eval 54/55通过，adapter误读取公开轨迹的result而非实际resultSummary；修正为完整结果精确校验后82项定向测试通过22.64s，未放宽数值/来源合约。初次失败eval保留为iv-progress-eval.json。
- 浏览器＋负对照定向56项通过10.66s；首次完整607项通过69.39s（9月19日），随后缩短成功聊天文本、补长度/限制保留断言，再进行本日最终607项全量复跑。最终全量之后仅同步文档，未再修改产品代码。
- 23个E2E＝13个真实Chromium流程＋5个独立进程HTTP流程＋5个Flask流程。Playwright技能用于实际浏览器验收；本批I–V原问题→1000Ω/±0.1V/3样本→报告下载/hash→刷新通过。已查看最终final.png，短回复、数值卡片、折叠方法、3工具轨迹和输入框显示完整。测试使用临时vault并禁止外部提供方请求，不污染用户真实库。
- Python compileall、node --check static/chat.js、bash -n双击启动器、git diff --check分别执行，均exit0。清单、架构、README及面试材料已同步本批数字；下方历史批次保留当时数字。
- 文档结构检查exit0：32项重点（24✅、8⚠️）、原始24节映射、剩余10个ID与golden中partial集合完全一致；Q01–Q80无缺项，11份当前文档/README的本地Markdown链接缺失数0。JUnit逐例分类也与上述195/201/23/37/13/76/62一致。结构和链接检查不替代文档内容审核，也不证明用户已经掌握。
- 默认8765：旧PID20237确认无running/pending记录后正常TERM，当前代码以PID63726运行（终端session10564）。health实际200/status=ok；/api/tools实际200、20项，并含analyze_signal.iv_curve输入schema。复用已有应用标签reload、设置可见并保留，实际核到输入框、旧历史与免费Lightning“未验证”。未改模型/API配置或旧问答，未发真实模型请求；服务健康不等于模型质量验收。

最终报告：[pytest.xml](../data/verification/engineering-audit/pytest.xml)、[coverage.json](../data/verification/engineering-audit/coverage.json)、[eval.json](../data/verification/engineering-audit/eval.json)；[I–V合约](IV_ANALYSIS.md)、[32项CHECKLIST与24节原要求](COMPLETION_AUDIT.md)。浏览器证据：`output/playwright/test_browser_iv_tool_values_report_and_reload/final.png`及trace。全部是本机执行证据，不冒充远端CI、真实实验效能或线上准确率。

## 历史工程复审（2026-09-19；全量重跑与清单复核）

教学继续暂停。本次重新运行当前工作树，而不是将9月14日的报告日期改为今天。工程仍有11个golden及开放模型质量等未验收项，不宣称全部完成。

- 全量 **577 passed in 73.99s**，exit0；JUnit记录577 tests、0 errors、0 failures、0 skipped，开始时间2026-09-19 23:35:35 +08:00。ResourceWarning和PytestUnraisableExceptionWarning按错误处理。分类：unit184、integration192、e2e22、scientific_validation34、robustness13、agent_eval70、旧API62。
- Coverage：4884/5304语句＝**92.08%**；1368/1648分支＝**83.01%**；组合**89.93%**，80%门槛通过。420未覆盖语句、280未覆盖分支、254partial branches。范围app.py+flexresearch，不含JS和独立子进程覆盖合并。
- 全量之后独立重跑eval，exit0：**65条、54执行/54通过/0失败/11跳过**，执行覆盖83.08%。数据SHA-256 `a94866dc340b88309bad675bf9761fef5000de04396e48adf37c87d0266e5eac`。13次模型adapter回放、6次transport回放，外部模型/网络调用0、成本0；本地adapter p50=8.369ms、p95=159.507ms，不能当在线SLO。
- 指标适用分母：task54、intent7、selection26、arguments16、trajectory14、science20、groundedness22、hallucination13、precision3、recall2、citation6、structured29、recovery16、latency5、cost7、report1。未执行项不进入通过率分母；49个评测负对照包含在70项agent_eval测试中。
- 22个E2E＝12个真实Chromium流程＋5个独立进程HTTP流程＋5个Flask流程。Playwright技能用于浏览器验收；本次统计六值/单位/报告下载/刷新与缺fs不显示假数值的两张final.png已重新查看，页面无内容遮挡。测试用临时vault，外部提供方边界回放，不污染真实实验库。
- Python compileall、node --check static/chat.js、bash -n双击启动器和git diff --check均exit0。清单、架构、教程、面试材料中漏同步的51/14与546已纠正；历史批次保留当时数字。
- 文档结构/链接核验实际exit0：32项重点（24✅、8⚠️）、24节原要求映射、剩余11个ID与golden中的partial集合完全一致；面试Q01–Q80无缺项，10份当前审计/学习/方法文档的Markdown本地链接缺失数0。该检查只证明结构与证据索引一致，不冒充文档科学内容评审。
- 默认8765仍由PID20237运行，本次health实际200/status=ok，`/api/tools`实际返回20项。当前无应用标签，创建一个可见标签；首次导航等待超时，但随后同一标签的真实页面已加载并核到输入框、原历史和免费Lightning“未验证”，已保留。未更改API配置或旧问答、未发真实模型请求；本地服务健康不等于API已验证或回答正确。

本地报告：`data/verification/engineering-audit/{pytest.xml,coverage.json,eval.json}`；截图和trace：`output/playwright/`。这些是本机执行证据，不是远端CI或临床验证。

### 最近完成的科学上下文改造及首次验收（2026-09-14）

- 546→577新增31项：8unit、9integration、4数学真值、8评测负对照、2Chromium。新增experiment_analysis与csv_input，关联实验先实际load_experiment_data，再校验作用域/hash并从同一bytes解析计算。单列CSV仅生成明确标注的样本索引，不猜采样率或时间。
- 基础统计来自analyze_signal：有效数、均值、最小/最大、线性漂移与斜率轴单位写入API/SQL/报告/聊天历史。独立真值y=2+4t验证均值6、漂移8、斜率4/秒；缺中间值不压缩原索引。统计UI不再混用兼容初筛的漂移定义。
- 缺fs频率请求返回needs_clarification与sample_rate_hz字段，不输出频率数值或图。补充参数可续跑。实验023的原问题实际分析ch4=1.2Hz，同时fixture含ch14=2.4Hz干扰，来源和状态均验；不照抄问题里的1.2。
- data-003/signal-005/experiment-004保留原prompt/expected，补真实HTTP适配器、精确上下文轨迹、数值oracle、全部来源字段和SQL/历史回读。原科学模型/沿用参数评测仅显式新增真实load_experiment_data步骤，没有放松为任意工具子集。
- 首轮定向30通过/2失败暴露单列Sniffer和旧轨迹断言；随后25通过/2失败暴露单列SQL轴非空约束和旧tuple解包。修复后20项通过0.49s，组合70项通过8.48s，12个Chromium通过15.28s。一次测试路径拼错只得到exit4/未执行，未计为验证成功。
- 首轮全量576通过/1失败69.06s，旧缺fs测试仍期待笼统停止状态。改为严格断言needs_clarification、缺失字段和空计算结果后，577项全量通过69.67s。本次9月19日又独立复跑通过，见上。
- 首次progress eval为50/54通过：一次过宽补丁误改lookup轨迹，同时科学模型旧轨迹未加上下文步骤。恢复lookup精确合约并修正科学路径后54/54通过；失败和修复报告分别保留为scientific-context-progress-eval.json、scientific-context-progress-eval-fixed.json。9月14日最终eval p50=8.169ms、p95=156.159ms；原问题与expected未改。
- 上一默认服务PID14480确认无running/pending记录后正常TERM，新代码以PID20237启动。全部本批输入为明确合成/demo资料，外部模型/网络调用0。文档索引、曲线和锁恢复回归仍通过；详情见SCIENTIFIC_CONTEXT_CONTRACTS。

## 历史工程复审（2026-09-14；文档工具与原子索引）

本段优先于以下历史批次。教学继续暂停；工程仍有14个golden及开放模型质量等未验收项，不宣称全部完成。

- 全量 **546 passed in 63.43s**，0失败/跳过，ResourceWarning/PytestUnraisableExceptionWarning作为错误；unit176、integration183、e2e20、scientific30、robustness13、agent_eval62、旧API62。
- Coverage：4805/5223语句＝**92.00%**，1339/1618分支＝**82.76%**，组合**89.81%**，80%门槛通过；418未覆盖语句、279未覆盖分支、253partial branches。JS和独立子进程覆盖不在此合并分母。
- Eval v3：65条，**51执行/51通过/0失败/14跳过**，执行覆盖78.46%；模型回放13、传输回放6，外部模型/网络调用0、成本0。dataset SHA-256 `8f73f94150f3125a87be33bc09967066855bbb807a8e93c89ce4caccb0194982`；本地adapter p50 7.905ms/p95 156.933ms，不是在线延迟。最终eval在全量测试后单独运行，exit0。
- 新增index_document（20个工具＝9基础＋11应用）：请求作用域bytes只在准备worker内部，工具参数仅授权upload_id和metadata；输出严格校验。文档/分块/FTS/向量/实验关联同SQL事务，异常回滚并清理本次排他创建的唯一新文件；同SHA复用ID、核验旧文件而不覆盖。
- 准备与提交分离：解析/分块/向量无写入，按时返回并通过schema才在调用线程提交；实际阻塞解析、超时返回、释放worker后，仍无文档落库。不是强杀线程或全请求硬deadline。提交后的日志故障返回DOCUMENT_LOG_FAILED、明确已提交ID，避免假称未归档并要求重复上传。
- file-003/006/007升v2，原prompt/expected保持不变：真实两页PDF→index_document→hash/页码引用→持久化；同PDF第二次返回同ID且不新增档案；图片型PDF返回OCR_REQUIRED/needs_clarification，无方法claim、无归档、无假采样率。索引完成不代表复合“导入并提取方法”已完成，该复合请求明确partial。
- 新增35项＝15unit＋12integration＋6评测负对照＋2Chromium。初轮兼容测试24通过/1失败（旧工具数19），定向新测试23通过/1失败（测试把真实tool_name写成toolName）；按实际契约修正，未放宽断言。随后35项通过0.82s、组合99项通过33.55s，全量546项通过。
- PDF技能用于测试文件制作与渲染检查：ReportLab4.4.9、Pillow12.0.0构造固定字节的合成文档；扫描fixture是嵌入真实光栅图且无可提取文字，不是空PDF。Poppler渲染后已查看two_page-1/2.png与scan-1.png，无内容遮挡；测试文件在output/pdf/document-fixtures，仅本地运行产物，不冒充实验室资料。
- Playwright技能用于实际浏览器流程验证：共10个Chromium流程通过。本批上传原问题→两页引用链接各实际打开并核页码/内容→刷新→重复导入同ID→刷新；另有图片PDF的失败提示/原问题刷新恢复。两个文档流程final.png已查看，trace/截图在output/playwright。使用临时vault且禁止外部提供方调用，不污染真实实验库。
- 6个新增负对照污染工具名、页码、hash、duplicate标记、成功状态或方法claim，均能被原评测合约拒绝。当前负对照共41项，评测测试共62项；指标适用分母：task51、intent7、selection25、arguments16、trajectory14、science18、groundedness21、hallucination12、precision3、recall2、citation6、structured27、recovery15、latency5、cost7、report1。
- 默认8765：确认旧PID2656及running/pending记录0后正常TERM停止，当前代码PID14480（终端session40516）运行，health返回200/status=ok。复用已有应用标签reload、设为可见并保留，实际核到输入框、原历史会话和免费Lightning“未验证”。没有更改API配置、重写旧问答或调用真实provider；本机健康检查不等于模型连通/内容质量验收。

报告：`data/verification/engineering-audit/{pytest.xml,coverage.json,eval.json}`，进度报告`document-progress-eval.json`。完整命令见EVALUATION_DESIGN；文档/失败边界见DOCUMENT_INDEXING；32项工程CHECKLIST与原24节映射已同步。不恢复教学，不等待理解题。

## 历史工程复审（2026-09-14；GF/目标循环曲线合约）

本段优先于以下历史批次。教学暂停；工程仍有17个golden及开放模型质量等未验收项，不宣称全部完成。

- 全量 **511 passed in 58.53s**，0失败/跳过，ResourceWarning/PytestUnraisableExceptionWarning作为错误；unit161、integration171、e2e18、scientific30、robustness13、agent_eval56、旧API62。
- Coverage：4633/5065语句＝**91.47%**，1303/1588分支＝**82.05%**，组合**89.22%**，80%门槛通过；432未覆盖语句、285未覆盖分支。JS和独立子进程覆盖不在此合并分母。
- Eval v3：65条，**48执行/48通过/0失败/17跳过**，执行覆盖73.85%；模型回放13、传输回放6，外部模型/网络调用0、成本0。最终dataset SHA-256 `76381193f0fbde35f772e4e9928e0e143ba0980ea46b74f2ae160d7160bfaf85`；本地adapter p50 6.542ms/p95 160.305ms，不是在线延迟。全量tests后仅修订data-004的partial证据说明，再独立运行eval成功；原prompt/expected未改。
- 修复三类计算错误：GF基线由前几点均值改为实测零应变记录均值；循环保持率按用户明确的实测目标点，不使用最后一个点代替；I–V明确转换电压/电流SI单位并检查零偏窗口。输入单位/基线/循环有歧义时拒绝猜测，方法边界见CURVE_FEATURES_METHOD。
- data-005/006保持原prompt/expected，合成fixture的GF=2、1000次保持率92%均通过真实上传→load_experiment_data→load_csv→extract_features→参数/hash/数据库→报告；fixture仍含1500次70%的干扰末点。I–V1000Ω只完成算法与兼容路径真值，data-004指定typed轨迹仍partial，没有把数学测试冒充全合约验收。
- 本批449→511新增62项：31unit、11数学真值、10integration、8评测负对照、2Chromium流程。覆盖缺零点/单位冲突/缺目标循环/源文件篡改/实际PNG/绘图超时；绘图失败保留已验证GF但不伪造图。数据库measurement卡片、analysis_runs参数、provenance和历史回复使用同一工具结果。
- 失败如实保留：首轮曲线测试51通过/1失败，中文“计算GF”的单词边界误路由已修复，定向56项再跑通过；之后组合69项通过30.83s、另一组49项通过1.08s。首次全量507通过/1失败60.67s，旧schema测试仍精确断言8工具，更新为实际9工具集合，未放宽成子集断言。再加3个失败集成测试后全量511通过。
- Chromium共8流程实际执行。本批两条曲线流程检查GF/保持率可见数值、工具轨迹、报告下载/来源、刷新；1200次不存在时不显示1500次70%的旧指标。两个`test_browser_curve_features_report_and_reload[...]`的final.png均已实际查看；trace/截图在output/playwright。用临时vault并禁止外部调用，不污染真实实验库。
- 8个新评测负对照污染GF/保持率数值、基线、单位、源hash、工具ID、目标循环或顺序，均能被原合约拒绝。评测测试合计56，有限负对照合计35；metric分母：task48、tool selection24、arguments16、trajectory14、science18、groundedness21、hallucination11、precision3、recall2、citation5、structured25、recovery14、latency5、cost7、report1（另intent7）。未覆盖的开放文本不能写成100%准确。
- 工程CHECKLIST含32项重点与原始24节映射；架构/教程/面试/真实性材料同步19工具、六类报告规则和48/65边界。历史449/420等证据保留；不恢复教学、不询问理解题。

完整命令见EVALUATION_DESIGN，最终本地报告：`data/verification/engineering-audit/{pytest.xml,coverage.json,eval.json}`。

- 最终静态检查：Python compileall（app/flexresearch/evaluator/tests）、node --check chat.js、bash -n双击启动器、git diff --check均退出0。
- 默认8765：确认旧PID90798及running/pending记录为0后正常TERM停止，启动新代码PID2656（终端session69952）。health与chat.js均200，真实`/api/tools`返回19个schema并含extract_features。未更改免费Lightning API配置，也未发真实provider请求；状态明确unverified，不能当模型连通或内容质量验证。
- 复用已有应用标签reload、设为可见并保留，实际确认输入框、历史会话和“nemotron-3.5-lightning · 未验证”。不新建重复窗口、不重写用户旧问答。曲线交互质量由本批两个独立Chromium完整流程验证，默认用户库不添加演示数据。

## 历史工程复审（2026-09-13；实际数据库锁恢复）

本段优先于历史快照。教学继续暂停；工程仍有19个golden及开放模型质量等未验收项，不能宣称全部完成。

- 全量 **449 passed in 55.97s**，ResourceWarning/PytestUnraisableExceptionWarning作为错误。unit130、integration161、e2e16、scientific19、robustness13、agent_eval48、旧API62；0失败/跳过。
- Coverage：4436/4855语句＝**91.37%**，1226/1500分支＝**81.73%**，组合89.10%，80%门槛通过；419未覆盖语句、274未覆盖分支。JS和独立子进程未合并。
- Eval v3：65条，**46执行/46通过/0失败/19跳过**，执行覆盖70.77%；模型回放13、传输回放6，外部模型/网络调用0、成本0。dataset SHA-256 `d35d63f635f199c126c73461509d086e6c41abf4126567b655966c08ade5e43d`。本地adapter p50 6.716ms/p95 176.55ms，不是在线延迟。
- failure-003保持原问题/expected，以明确合成I-V fixture实际持SQLite写锁至少1.5秒。最多3次BEGIN尝试，每次busy_timeout250ms，间隔50/100ms；失败partial/DATABASE_BUSY，锁未释放时可校验下载原始CSV，数据库仍0条归档。释放后一次人工重试只新增1条measurement/experiment/file。
- `upload_recovery.py`仅重试事务开始，不重放业务事务体；另测短锁成功、COMMIT读锁失败回滚、归档后失败的已有ID与禁止重复上传提示、磁盘保存失败不报假保护、恢复副本篡改拒绝。锁失败轨迹保存在独立回执，不假称已写入被锁的agent_runs。
- 本批新增29项：18恢复unit、6真实SQLite integration、4评测负对照、1Chromium恢复流程。重点集成/浏览器12项通过12.93s；之前56项定向回归通过5.87s；随后完整449项通过。
- Chromium6个流程全部运行；新增上传→锁失败→原始CSV下载比对→刷新仍有恢复入口→解锁人工重试→仅1条归档→刷新清理入口。已查看成功重试后的截图；trace/截图在`output/playwright/test_browser_database_busy_download_reload_and_retry_without_duplicate/`。使用临时vault，没有向真实实验库注入故障，没有调用外部模型。
- 4项新增评测负对照分别污染失败状态、SHA、重试记录、假measurement ID，failure-003均能检出。当前trajectory/recovery适用分母各14；tool selection24、arguments15不变，离线通过不等于真实模型准确率。
- 静态Python compileall、node --check chat.js、git diff --check退出0。完整coverage/eval命令见EVALUATION_DESIGN；报告为`data/verification/engineering-audit/{pytest.xml,coverage.json,eval.json}`，中间报告`database-progress-eval.json`另保留。运行产物Git忽略。
- 同步工程32项CHECKLIST、24节原始映射及架构/教程/面试/真实性文档，补DATABASE_RECOVERY边界。没有增加教学提问。通用幂等、进程中途崩溃、跨介质原子性与全部模型错误传播仍未完成。
- 默认8765：确认旧PID74750和running/pending记录数为0后正常停止，启动当前代码PID90798（终端session88292）；health和新版chat.js返回200，实际提供recoveryCard/restoreUploadRecovery。当前浏览器无标签，新建一个应用标签并设为可见/保留，已核到输入框、历史会话和免费Lightning“未验证”状态。未修改API配置、未重写旧回答；本批没有真实provider请求，健康检查不算模型连通或内容质量验收。

## 历史工程复审（2026-09-12；模型错误与评测隔离）

本段优先于历史快照。教学继续暂停；工程仍有20个golden及开放质量等未验收项。

- 全量 **420 passed in 37.72s**；ResourceWarning/PytestUnraisableExceptionWarning作为错误。unit112、integration155、e2e15、scientific19、robustness13、agent_eval44、旧API62；0失败/跳过。
- Coverage：4305/4724语句＝**91.13%**，1205/1478分支＝**81.53%**，组合88.84%，80%门槛通过；JS和独立子进程未合并。
- Eval v3：65条，**45执行/45通过/0失败/20跳过**，执行覆盖69.23%；模型回放13、传输回放6，外部模型/网络调用0。dataset SHA-256 `e22d72e618ef9f2715068dd181222917fa81a019de219e36bccc7ff2ddeaa124`。本地adapter p50 6.019ms/p95 83.877ms，不是在线延迟。最后仅修正routing-005证据路径/离线边界说明后再次执行eval通过，prompt/expected未改。
- 修复普通问答开启模型仍被固定短答截走；关闭模型时明确local_reference，失败时unavailable，不给假模型回答。普通超时、429耗尽、认证/格式错误写入API、历史、DB、JSONL；尝试与输出修复分开计数，费用未知仍为null。
- provider_transport默认2次尝试，尊重Retry-After；超过2秒等待预算则停止而不提前请求。真实localhost urllib超时/429通过；工具模型失败也计入尝试/未知usage，父级领域错误仍有待统一。
- 本批45个新测试：28传输unit、11integration、4评测反例、1golden顺序独立性、1Chromium失败展示。全部5个浏览器流程通过；新增实际问题→限流/重试提示→刷新保留状态，未显示秘密或8篇无关来源。
- failure-001/002原prompt/expected保持不变；20秒延迟及Retry-After采用虚拟时钟故障注入。前者模拟12秒timeout×2＋0.2秒等待；该合约不冒充真实20秒联网压测。
- 评测修复每case隔离：第一次42/45暴露旧RAG资料污染后续case及旧context回放仍假设首轮无模型；改为独立DB/文件/probe状态，正序/逆序评分一致。保留progress失败报告。首次相关测试129/1也如实记录；旧断言已改为验证首轮与追问均调用模型。
- 完整命令与产物：EVALUATION_DESIGN、`data/verification/engineering-audit/{pytest.xml,coverage.json,eval.json}`；静态compileall、node --check、bash -n、git diff --check退出0。Git忽略运行数据。
- 默认8765：21:28确认旧PID56492及未完成run=0后正常停止，启动器以新PID74750运行（终端session98468），health与新版chat.js均200。现有应用标签已reload、设为可见并保留；实际UI仍恢复旧session191的科学结果/下载/来源，未回写旧结果。免费Lightning配置未改，重启后明确显示“未验证”；本批未调用真实外部模型，不把UI显示或本机健康检查冒充API/答案质量验证。新增限流提示的Chromium截图亦已实际查看。

## 历史工程复审（2026-09-12首批；教学暂停）

本段优先于历史快照。工程尚未全面验收，状态见COMPLETION_AUDIT。

- 全量375 passed in 29.74s，严格资源警告；unit84、integration144、e2e14、scientific19、robustness13、agent_eval39、旧API62。
- 4199/4631语句＝90.67%，1169/1442分支＝81.07%，组合88.39%，80%门槛通过。JS未统计覆盖；独立子进程未合并覆盖。
- Eval v3：65条、43执行/43通过/0失败/22跳过，执行覆盖66.15%；12模型回放、2传输回放，外部模型与网络调用0。dataset SHA-256 `d585e548ec7810128aac552e9b833584db0165b53c23d1e344aa4e8fd05e69a3`。
- 本轮修复：固定2023下界改为滚动三年窗口、精度/未来/边界日期过滤、模型不能丢原问题时间限制、空选择partial与持久stop_reason、Bio-Z同义词匹配、来源卡片数量/日期显示。
- Chromium 4/4已实际运行：7张来源卡与点击/刷新；论文→空结果→你好不复用来源；CSV上传→滤波→FFT1.2Hz→PNG→报告/CSV下载→刷新恢复；API验证切换→429失败保留→刷新。Playwright1.62.0/Chromium151，本地HTTP与临时vault，提供方回放。合成DOI点击后拦截到测试页，不是真实DOI在线解析。
- 测试依赖和Chromium已实际安装；CI增加安装步骤，未声称远端CI已运行。截图/trace在`output/playwright/`，已查看来源页面截图；不把截图本身当功能通过。
- 首轮日期集成116/117：Bio-Z→bioimpedance词项与标题写法不一致，修复同义匹配后121/121。首轮新eval42/43：误要求纯文本正文有Markdown链接；按实际产品的来源卡校验DOI/URL绑定，另补真正浏览器点击验收。首轮浏览器+eval测试24通过/2失败：7来源只显示6、测试未要求导出却找下载链接；前者修产品，后者补明确请求，随后浏览器4/4与全量375/375通过。
- 面试80题全文按代码/测试审核，修正不存在的macro/weighted统计、MRR/nDCG混淆、SQLite连接粒度、科学解释/执行器职责等；不是作者理解能力验证。
- 当前代码的独立服务HTTP启动/重启测试已通过；默认8765进程更新另见下方追加记录，不混同历史运行。

报告：`data/verification/engineering-audit/pytest.xml`、`coverage.json`、`eval.json`；完整命令见EVALUATION_DESIGN。未完成22个golden、真实数据库锁恢复、开放模型质量等不算通过。

## 历史工程复审（2026-09-11；教学暂停）

本段优先于下方同日较早快照。当前工程尚未全面验收，逐项状态见[COMPLETION_AUDIT](COMPLETION_AUDIT.md)。

- 全量316 passed in 23.41s；严格ResourceWarning/PytestUnraisableExceptionWarning，无失败。unit47、integration131、e2e10、scientific19、robustness13、agent_eval34、旧API62。
- 行覆盖4088/4537=90.10%；分支1130/1408=80.26%；组合87.77%，80%门槛通过。独立子进程未合并coverage，浏览器JS不在分母。
- Eval v3：65条、41执行/41通过/0失败/24跳过，执行覆盖63.08%；8次模型回放、2次传输回放，无外部模型/网络调用。dataset SHA-256 `159f4d884bb2f01c446c280aa367ae2a728ed4d5df17e295037dc7ce4ca266e3`。
- 实际修复：reference resistor/doing等词误触发文献搜索；413结构化错误；损坏PDF解析错误、无文本OCR_REQUIRED；检索重复ID重复计分；缺失成本误判零成本。
- 新增28项：5真实进程HTTP（CSV/filter/FFT/PNG/report/完成后重启，两页PDF/检索/引用/去重，3种错误上传），14评测器反例，9意图测试。Flask客户端5项仍明确标注，不冒充浏览器自动化。
- 保留失败：HTTP测试首次误用文档级接口字段，改用实际聊天chunk证据；随后原英文问题触发公网，定位并修复reference resistor路由。全量首轮315/1暴露评测上传临时流未关闭；修复初稿误用EnvironBuilder上下文产生315/1；改用closing并显式关闭wsgi.input后316/316。没有降低资源警告门禁。
- 文档：重写过时EVALUATION_DESIGN，纠正golden过时实现说明，file-008保留原expected并补实现/执行；暂停FINAL_DELIVERY中的教学入口。其余未完成合约不标通过。
- 静态检查：git diff --check、compileall、bash -n启动器、node --check chat.js均exit0。
- 默认窗口：确认旧进程48412及无未完成agent_runs后，正常停止旧服务，用启动器启动当前代码（终端session86691）；8765健康检查200，浏览器请求根页面/CSS/JS/会话/API状态均200。模型设置仍为Lightning免费版；重启后连接状态为unverified，本轮未调用真实模型，不把健康检查当API连接验证。窗口打开请求已提交；未宣称本轮浏览器视觉/交互E2E通过。

本地可复查产物：`data/verification/engineering-audit/pytest.xml`、`coverage.json`、`eval.json`。复现命令见EVALUATION_DESIGN第8节。报告目录已Git忽略，避免运行资料进入公开仓库。

## 以下为此前同日/历史运行证据

更新：2026-09-11。以下只证明列出的实际路径，不是全问题正确率、人体科研验证或生产 SLA。当前摘要优先；历史模型记录保留，不能当作当前配置。

## 当前配置与最新回归

- 已保存 `nvidia/nemotron-3.5-lightning:free`，OpenRouter，沿用本机密钥；没有收费自动兜底。切换探针 applied=true，实际型号一致，10.667 秒。
- 最终 288 项 pytest 在严格 ResourceWarning / PytestUnraisableExceptionWarning 下通过（16.28 秒）；4527 statements、445 missed，行覆盖 90.17%，范围 app.py + flexresearch。统计分层前为 90.19%；最终以此次 90.17% 为准。
- 最新离线 eval：65 条，40 executed / 40 passed / 25 skipped，执行覆盖 61.54%。8 次模型接口回放、2 次 transport 回放，真实外部模型/网络调用 0 次。每个指标仅按适用案例统计；hallucination_rate 的 passRate 是规则断言通过率，不是幻觉发生率为 100%。
- `python scripts/run_agent_eval.py --output /tmp/flexresearch-agent-eval-final-20260911.json` 已在共享工具适配器改造后运行。
- 完整测试命令：`python -m pytest --cov=app --cov=flexresearch --cov-report=term --cov-report=json:/tmp/flexresearch-coverage-final-20260911.json --cov-fail-under=80 -q -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning`。

## 新模型：科学和文献分别实测

| 任务 | 实际证据 | 结果与限制 |
| --- | --- | --- |
| 科学模型闭环 | session 185 / 实验 14；父 run `db22051417a546a19ac3711bc152729d`，科学 run `be12c8ba52174515af8227b6f6d56535` | 2 轮模型、2754 token、cost=0、10.086 秒；completed / selectionValidated=true |
| 共享适配器在线复验 | session 191 / 实验 15；父 run `53e6c11c155a4bc09410c50c73775dc7`，科学 run `3deb0ad2f7f34dd4a3e7baf74c3d144c` | 2 轮模型、2760 token、cost=0、13.066 秒；上述五工具和全部产物/隐私/来源检查再次通过；界面最近工具请求状态已核验 |
| Python 科学链 | load_csv → filter_signal → spectral_analysis → export_signal → plot_signal | ch4、100 Hz、0.5–3 Hz / 4 阶；主峰 1.2 Hz，1000 行派生 CSV、PNG、双哈希、上游滤波 ID 和报告通过；SYNTHETIC，不是人体数据 |
| 真实文献闭环 | session 186；run `2ffc08fee118447d9209641c52fe8f1e`；搜索 tool `49b45b0f80254d64bed1c8f45efed302` | 2 轮模型、1 次检索、3113 token、cost=0、115.892 秒；completed / selectionValidated=true。检索本身约 1.403 秒，多数等待来自模型 |
| 文献来源 | DOI `10.1097/00003246-200006000-00017` 与 `10.3390/jcdd12070237` | 真实 API 元数据匹配 Bio-Z pulse waveform；Crossref 核对 DOI/标题/期刊。第二篇亦在出版商及 PubMed 匹配；不是全文结论验证 |
| 普通跨轮追问 | session 189；run `bd1da02a532949e5b8a59ea74c495974` | 实际 Lightning，8.013 秒、cost=0；带入消息 423/424，来源为空，接口和上下文传递通过；**内容质量未通过人工检查** |

普通追问的真实回答把“光斩波法”作为暗电流常规测法，并引入“有效光斑面积”，却未明确暗态测量，表述容易误导。不能因为状态 complete 或脚本 `passedTransportAndContextChecks=true` 就称技术回答正确。对照 [Hamamatsu Si photodiode 技术资料](https://www.hamamatsu.com/content/dam/hamamatsu-photonics/sites/documents/99_SALES_LIBRARY/ssd/si_pd_kspd9001e.pdf) 与 [器件测量条件](https://www.hamamatsu.com/us/en/product/optical-sensors/photodiodes/si-photodiodes/S14605.html)：暗电流需在无光、明确偏置和温度条件下理解和测量。此失败保留，不回写旧回答、不用专门硬编码一句答案掩盖模型能力限制。

科学结果文件：`/tmp/flexresearch-live-science-lightning-20260911.json`；文献结果文件：`/tmp/flexresearch-live-paper-lightning-20260911.json`。浏览器已核验 session 185 的模型标记、参数、CSV/图/报告；保留会话直达链接 `http://127.0.0.1:8765/?session=185`。

模型免费与工具支持见 [OpenRouter 官方模型页](https://openrouter.ai/nvidia/nemotron-3.5-lightning:free)。免费端点的保密/使用条款需要单独核对；原始实验数组默认 local_only，不将免费推理视为保密实验室云服务。

## 为什么换模型前先修接口

1. Nex Mini 科学 run `432acefd58174e10af246561938f85ed` 返回 HTTP 400。最小普通工具 probe 成功；精确科学 schema 失败。上游将 schema 包进数组后错误解析 `#/$defs/...`，不是“没配 API”。
2. `model_schema.inline_local_refs` 仅在 schema 位置展开有限本地引用，保留字面值和约束；循环/外部/无效引用拒绝。9 项测试覆盖结构和边界，本地 Pydantic 不放宽。
3. 展开后 Mini run `6718cd79152c457dbe4b482c15a2b209` 漏传通道/滤波；要求所有确认字段后 run `52ec66e92c964b83b2cb0621a1cfdec8` 仍传 low_cut=0，随后不修复。均 partial；Python 兜底成功不能称模型成功。
4. 文献 Mini run `3970b499edbf4f6c909c61c1716ce20e` 协议通过，但 4 条中有 3 条注册/数据记录。增加注册、补充材料、类型和原问题模态过滤；过滤后 run `193ca0e70019436cb00919759e7a9541` 又未调用工具，记 partial。
5. 换 Lightning 前做了同参数工具 probe，然后保存免费型号，得到上述科学/文献成功。共享 `tool_model_client` 后科学和论文使用同一传输、首轮唯一工具约束及最近真实请求状态更新。连接 verified 只证明收到合法响应，不证明任务或科学内容已验收。

最后的模型边界整理把 `basic_stats` 从 Measured 移到 Calculated；第一次回归 286 通过/2 失败：旧文件-profile evaluator 和滤波失败测试仍断言旧字段位置。修复它们以检查新分层、mean=80 的真值以及“仅已有基础统计、没有滤波/FFT结果”，没有放松失败后禁算约束。最终 288 全过、40/40 executed eval 通过。旧运行快照不回写。

最终服务验证：确认旧模型任务已结束后，以新双击启动脚本启动最新代码，健康检查200；再次运行脚本直接打开已存在实例，不重复启动。session 192 / run `a37d0e36873047878ee1981fc5cc2ad6` 真实HTTP useModel=false 验证统计只在Calculated、主峰1.2Hz和completed；这是本地分层复验。重启后免费模型手动探针实际成功，型号一致、一次尝试、36.357秒；再次说明连通与低延迟不同。

文档结构核验：30个概念均有四字段；80道题均有四字段；13个软件组件齐全。JavaScript语法、启动脚本语法、git diff --check均通过。新启动器已实际验证启动和复用两条路径；不是持久后台服务。

## 历史运行记录（以下不是当前配置）

## 普通上下文与实际 API 状态

session 175：`scripts/live_conversation_context_smoke.py` 完成“暗电流为什么重要？”→“那它怎么测量？”。第二轮 run `4c3a2498c0a4459abdcb713b075b3675`，实际 Nex-N2.5-Mini 免费模型，2104 ms，cost=0，带入消息 389/390，旧来源/私有证据均未带入。

随后浏览器真实提交“那测量时为什么要保持温度稳定？”：run `c0861b9bbabd4cda981df4cd180b7e6d`，普通模型调用 2223 ms，单次尝试成功。回答承接暗电流的温度依赖，页面自动显示“nex-n2.5-mini · 已验证”；未显示论文来源。这个标记来自实际请求，不只是配置已保存。不是全问题正确率或工具循环成功证明。

## 报告可读结论与内容检查

`python scripts/live_report_content_smoke.py --experiment-id 10 --session-id 174` 已通过。新快照 run `ed4464be85a04c6e98827bcad5d240fa`；从已保存的合成数据运行转述 1 条质量标记结论，七项 rubric 为 pass，状态为 `supported_within_rubric`，但 `human_review_required=true`。未调用外部模型。浏览器已实际展开“报告内容检查”，确认七项文案与“不是科学或医学认证”边界；窗口已标记保留。

本轮启动前确认旧服务端口没有监听、旧执行句柄已不存在，随后启动新服务；没有仅因观察超时重启。18 个 `/api/tools` schema 已经真实 HTTP 验证。

## 原始信号质量检查

`python scripts/live_signal_quality_smoke.py` 已对运行中的 8765 服务完成合成 CSV 上传→对话追问→质量工具→来源/报告/历史恢复。session 174，父 run `1f0f6201466a4655979215f87297bc9c`，科学 run `aeb0c7a542f5484690a4f797f50d1d25`。注入区段 12–16 秒，实际标记 401 点、IoU 0.997506；来源中没有无关论文，未调用外部模型。浏览器已实际打开 session 174，确认简短回答、折叠质量卡和报告入口。

算法是非诊断性启发式，不是经人体标注验证的运动伪差识别器；未标记比例不是可靠性概率。服务重启后的 API“未验证”只表示本次启动尚未探测，不代表这次本地数值任务调用了模型或 API 故障。方法与限制见 `SIGNAL_QUALITY_METHOD.md`。

## 当前增量：Bio-Z 最近三次实验 → 比较 → 计划

执行 `python scripts/live_history_plan_smoke.py`。创建 SYNTHETIC 项目 4、实验 7/8/9；各有明确单位的两频点复阻抗，幅值分别为 5/10/15 Ω。先读取实验 9 建立项目上下文，再原样发“根据前 3 次实验结果建议下一次实验”。

- 会话 173；计划 run `fdbc3e4d08ca407c8d43c8ef8d4fca6a`，completed。
- 比较子运行 `53cee565f9f146fcbc33bace411addfc`、`d41f952655f04b8d81d1bb7ab49efc7c`；真实 compare_experiments 计算均值差 5/10 Ω，频点对齐，未自动插值。
- 每组比较绑定两个原始 SHA-256 和两个最新源分析 ID；每条建议有 source_run_ids。条件只变化 material，生成待审核单变量验证建议，不宣称因果或最佳材料。
- 真实界面已显示两组差值、条件差异、可下载来源报告和审核边界。发现重复建议后合并；比较存在时不再把三个实验都称为候选基线。
- 合并后的真实复测仍在 session 173，计划 run `cef8cf3d2469448d916c5603af7147e9`，比较 run `28e81dc580c54e52b86ef2b132040804` / `26d5b61c7c3c4c7d9edebe9f653ad583`。两组差异不变，建议缩为三条且仅一条材料验证建议；浏览器已确认最新回答。旧回答按历史快照保留，不回写篡改。
- 首次运行脚本早于服务监听，健康检查 ConnectionRefused，在任何创建操作之前退出。确认原服务会话已就绪后重试成功，没有因此另起服务。
- 此处外部模型调用 0 次。未匹配的单位/通道/频点或最新失败会返回 partial；其他分析类型的跨历史比较仍需实现。

## 当前增量：跨轮滤波参数，真实 HTTP 与界面通过

执行 `python scripts/live_processing_context_smoke.py`。脚本创建明确标注 SYNTHETIC 的 1000 点信号（100 Hz，1.2 Hz 正弦 + 12 Hz 干扰），先上传并完成 0.5–3 Hz 带通，再发“沿用刚才的滤波参数，分析主峰、导出CSV并画图”。

- 实验 6，会话 169；初次运行 `11b8bc37746240e78b13c553c75359b8`。
- 后续外层 `2d9649aa9297434aa7a08f8ef592d407`，科学子运行 `5682b7fd1903415082255167979c307a`，completed。
- load_csv → filter_signal → spectral_analysis → export_signal → plot_signal；主峰 1.2 Hz；CSV 双哈希、PNG 魔数、报告来源与历史恢复均验证。
- 浏览器实际显示 100 Hz、0.5–3 Hz / 4 阶、可点开的参数来源、CSV 下载、图和报告；无外部文献卡片。
- 外部模型调用 0 次；这不证明新模型工具编排已稳定。服务重启后 API 显示“未验证”是当前进程尚未重新探针，不等于已证明 API 离线。

## 当前模型切换证据

按用户要求保留免费端点，当前 `nex-agi/nex-n2.5-mini:free`。切换探针返回 applied=true、actualModel 与请求相同，1.345 秒；应用 session 168 的普通问答 1.39 秒且来源数为 0。短答成功与工具测试的 TLS SSLEOFError 分开记录；不能据此声称整条模型分析流程已经通过。未配置付费自动 fallback。

## 科学模型闭环：真实接口通过

运行命令：

```sh
python scripts/live_science_smoke.py --output /tmp/flexresearch-live-science-20260909-retest.json
```

脚本显式创建标注 SYNTHETIC 的本地实验。输入为 1000 点、100 Hz 采样、ch4=1.2 Hz 和 ch14=2.4 Hz 的正弦；不是真实人体/实验室数据。只向当前模型发送任务和受控工具状态。

| 证据 | 实际值 |
| --- | --- |
| experiment / session | 2 / 160 |
| 外层 run | `cf6d4429d61c4570a09e872732ab390f` |
| 科学子 run | `1d49f43bce6049beaeb307ba129d7afd` |
| 请求/实际模型 | `nvidia/nemotron-3-ultra-550b-a55b:free` |
| 模型请求 | 2 轮，两次均返回成功 |
| 工具 | analyze_experiment → load_csv → spectral_analysis → plot_signal |
| 科学真值 | ch4 FFT 主峰 1.2 Hz，通过误差 <0.01 Hz 检查 |
| PNG / 报告 | PNG 魔数通过；Markdown 含原始 CSV SHA-256 |
| 来源卡片 | 0 篇外部论文；没有套用 Crossref 八篇 |
| 耗时 / 用量 / 成本 | 32.076 秒 / 1859 token / 返回 cost=0 |
| 状态 | completed，selectionValidated=true，resultPrivacy=local_only |

首次实测失败 run `9bb8e67b0dd843108fec9e29147f8d0d`：模型传入数字 channel=4，旧 schema 只接受字符串；重复同一参数触发循环保护。随后明确接受非负整数通道 ID 并无损规范化，保留对小数、布尔、数组的拒绝。二次实测完整成功。失败记录保留，不能只展示成功的一次。

界面核验：`http://127.0.0.1:8765/?session=160` 展示短答、图、实验/文件/通道/fs 和报告下载；刷新后图仍存在。窄窗口 API 面板已可打开。所有这些是本地开发服务器上的验收，不是生产部署或并发稳定性测试。

## 离线测试与评测

```sh
python -m pytest --cov=app --cov=flexresearch --cov-report=term -q \
  -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning
python scripts/run_agent_eval.py --output /tmp/flexresearch-agent-eval-conversation-20260910.json
node --check static/chat.js
```

- 最新 272 项 pytest 全通过；4456 statements，459 missing，覆盖率 89.70%。报告 `/tmp/flexresearch-coverage-conversation-20260910.json`。
- 最新 65 条 golden，40 执行且通过，25 跳过；执行覆盖 61.54%。报告内容指标实测 1 案例，普通上下文传递实测 1 案例。报告 `/tmp/flexresearch-agent-eval-conversation-20260910.json`。
- 离线模型循环为确定性接口回放，不是在线模型质量测量。8 次 modelAdapterReplays，外部模型/网络调用均为 0；上面的两次真实追问单独列证。
- 24 通道均值案例逐通道构造：ch4 为 750+j1000 Ω，真值 1250 Ω；其他通道为 3+j4 Ω，防止误选通道仍碰巧通过。
- groundedness 当前检查来源绑定，不是完整语义蕴含评估；幻觉率仅在受控故障案例中计量。不能把局部通过率写成“全系统准确率 100%”。

## 新模型与派生文件：失败和成功分别记录

`python scripts/live_science_smoke.py --export-filtered --output /tmp/flexresearch-live-export-20260909.json`：Nex-N2.5-Pro 在 run `f7d9343ddfa445f59c9ebc786968e8af` 只返回文本，没有调用工具。74.419 秒，模型返回 728 token / cost=0；状态 partial。Python fallback 完成 1.2 Hz、PNG、1000 行 CSV、来源/派生双哈希和上游滤波编号。这里不能声称模型闭环成功。

随后首轮工具选择改为强制调用已确认范围的唯一科学工具（模型仍生成参数，服务端验参），提供方忽略要求时记录 missing_required_tool。复测的观察脚本在 120 秒超时，但服务器仍在工作，没有重启：最终 run `d07904424f604999a19df212984ebd0a` 于 141.045 秒结束，上游返回 HTTP 503、状态 partial，本地子 run `f6c1d378de434b448bbe0be4bf13dff7` 成功。此次费用未知，不能记成零。没有为了获得绿灯继续反复请求免费端点。

本地真实 HTTP 验收（非 Flask test_client）：聊天上传带 bindContext=true 的 SYNTHETIC 多通道 CSV，再直接问“帮我分析通道4，用0.5–3 Hz带通滤波后找主要脉搏频率，导出CSV并画图”。session `165`、上传资料实验 `5`、run `3092090159d144759de4d875bc023c1c`、科学子 run `ebcd95b8dcaa4fababa7073594536e8a`，completed。主峰 1.2 Hz，CSV 与 PNG 均可下载，CSV SHA-256 与归档元数据一致。此验收显式 useModel=false，只证明上传上下文和科学工作流，不证明模型质量。运行窗口因 Mac 锁屏未进行视觉复验。

## 尚未完成的验收

2026-09-09 方法卡增量：真实 HTTP 上传 `SYNTHETIC-method-demo.txt`（明确不是已发表论文），文档 2 → session 166 → run `305fee1bb66e4ab78bf9c9df45fa3608`，五类方法各一条原文摘录，completed，未调用外部模型。浏览器已打开 `http://127.0.0.1:8765/?session=166`，确认五个可展开分类、来源哈希与抽取式边界文案显示；引用接口的原文与哈希由集成测试验证。不是完整论文语义总结验收。

文献端到端在线成功、论文方法语义总结、脉搏特征历史规划、报告语义质量及真实实验室资料验证尚需推进。方法原文摘录、Bio-Z 比较驱动规则计划、按实验 ID 比较和派生文件已有实际运行证据；新模型完整在线验收需单独记录。仓库公开 CSV 是 demo，不能伪装成真实科研结果。更完整的需求核对见 COMPLETION_AUDIT.md。

