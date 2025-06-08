README (详细算法原理版)
🚀 Auto-Programmer (核心算法详解)
核心设计哲学
Auto-Programmer的核心思想是模拟一个高度协同的、基于测试驱动开发（TDD）原则的软件开发团队。它将大型语言模型（LLM）在软件工程中的角色进行了功能分解，使其在不同阶段扮演不同角色（如产品经理、架构师、开发者、测试工程师），并通过一个结构化的工作流（Workflow）将这些角色串联起来，从而实现从一个模糊想法到最终交付可用代码的全自动化流程。

整个工作流被设计为一个“智能体”（Agent）系统，其核心驱动力是通过不断地生成、测试、审查和修正来逐步逼近最终目标。

算法工作流详解
系统的主要工作流程在 WorkflowController 中进行协调，可以分为三个主要阶段：规划与定义、执行与迭代、收尾与交付。

阶段一：规划与定义（PM与架构师阶段）
这个阶段的目标是将用户模糊的自然语言需求，转化为一份结构化、可执行的开发蓝图。

需求澄清 (run_clarification_phase):

输入: 用户的一句初始构想（例如：“我想做个股价提醒工具”）。
过程:
系统使用 clarification_questions.txt 模板，让LLM扮演一名“软件架构师”。
LLM会分析用户的初步构想和其开发环境信息，生成不超过5个关键问题，以澄清核心功能、技术选型、输入输出和特殊依赖等。
输出: 向用户展示这些问题，并收集用户的回答。
初始方案细化 (run_initial_refinement_phase):

输入: 用户的初始构想 + 对澄清问题的回答。
过程:
系统使用 initial_refinement.txt 模板，让LLM结合所有已知信息，生成一份高层次的Python项目技术方案。
输出: 一份结构化的JSON文件 (project_definition.json)，其中包含：
建议的项目名称 (project_name) 和核心目标 (project_goal)。
项目的主要功能模块/类 (main_components) 及其职责。
需要安装的第三方库 (third_party_libraries) 和将用到的标准库 (standard_libraries_used)。
描述数据流和组件交互的主要工作流程 (main_workflow)。
迭代式确认 (run_project_definition_iteration_phase):

输入: 上一步生成的 project_definition.json。
过程:
系统向用户展示技术方案，并询问是否满意。
如果用户不满意并提出修改意见，系统会使用 refinement_iteration.txt 模板，将“当前方案”和“用户反馈”一同提交给LLM，让其生成一份更新后的方案。
此过程循环往复，直至用户确认为止。
输出: 一份经过用户最终确认的 project_definition.json。
任务分解 (run_task_decomposition_phase):

输入: 最终版的 project_definition.json。
过程:
这是规划阶段最核心的一步。系统使用 task_decomposition.txt 模板，要求LLM扮演一名信奉“测试驱动开发”（TDD）的“技术项目经理”。
LLM将整个项目分解为一个有向无环图 (DAG)，其中每个节点都是一个逻辑独立的开发步骤。
每个步骤都包含明确的 step_number, step_title, step_type (如 feature_development, refactoring, integration_test), 详细描述, 产出物 (deliverables) 和它所依赖的前置步骤 (dependencies)。
关键原则：起始步骤（依赖为空）必须是建立项目骨架、requirements.txt 和一个简单的“Hello World”级别测试。后续步骤必须是增量式的。
输出: 一份包含所有开发步骤及其依赖关系的 task_steps.json 文件。
阶段二：执行与迭代（开发者与QA阶段）
系统根据任务依赖图（DAG），通过拓扑排序算法来逐一执行开发步骤。每个步骤都遵循一个“生成 -> 审查 -> 构建 -> 测试 -> 修正”的内部循环。这个循环由 StepHandler 控制。

代码生成 (_execute_..._step):

首次生成 (Step 1): 对于没有依赖的初始步骤，使用 code_generation_step1.txt 模板，要求LLM生成项目的完整初始文件结构和内容。
增量修改 (后续Steps): 对于后续步骤，使用 code_modification.txt 模板。系统会将上一个成功步骤的完整代码、当前步骤的任务目标、架构笔记以及历史错误反馈，全部作为上下文提供给LLM，要求其生成精确的代码修改指令（例如：新增文件、删除文件、替换文件、或精准到行的 line_diff）。
代码审查 (_run_inspection):

在代码被编译或测试之前，它首先会被提交给一个“代码审查员”AI。
使用 code_inspector.txt 模板，该AI会从功能符合性、架构健康度（是否遵循已有模式、是否冗余）和测试覆盖度三个维度进行审查。
如果审查不通过，其反馈意见将成为下一次修正尝试的输入。如果审查通过，且AI在过程中产生了新的架构决策，这些决策会被记录到 architecture_notes.md 文件中，作为项目的“长期记忆”。
构建与验证 (_build_and_verify):

环境构建: EnvironmentManager 会读取 requirements.txt，并在项目专属的Conda/Venv环境中安装所有依赖。
自动化测试: CodeRunner 会执行步骤中定义的单元测试（例如 pytest tests/）。如果测试失败，详细的错误日志（stdout/stderr）会被捕获，并作为反馈信息提供给LLM用于下一次修正。
手动验证: 如果自动化测试通过，系统会向用户展示AI提供的操作指南，并提示用户在新终端中手动运行程序，以进行最终的功能确认。用户可以选择确认成功 (y) 或报告失败并提供反馈 (n)。
循环与自愈:

上述 生成 -> 审查 -> 测试 -> 验证 的循环会持续进行，直到步骤被用户确认为成功，或者达到最大尝试次数（在 config.ini 中配置）。
一旦步骤成功，ProjectState 会将其代码快照保存到 successful_steps 目录，并更新 latest_successful_code 目录，作为下一个步骤的基础。
同时，系统会调用LLM对成功的代码进行总结（使用 code_summary.txt 模板），这份总结将作为未来步骤的上下文，帮助AI更好地理解现有代码库。
阶段三：收尾与交付
当所有任务步骤都成功完成后，系统进入收尾阶段。

环境清理: 询问用户希望保留、重命名还是删除为本项目创建的虚拟环境。
项目归档: 在工作区生成一份清单文件，列出所有重要的产出物。
交付指南: 在控制台清晰地展示最终代码的存放路径和建议的运行命令，方便用户直接使用。