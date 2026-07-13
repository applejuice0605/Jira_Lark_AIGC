# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Changed
- `xxljob_fix_version_dev_finish_time.py`
  - 优化了报告排版格式：
    - 将原先独立的 "Key" 和 "Summary" 合并为了统一的 "Jira Ticket" 字段，内容展示为 `{Key}: {Summary}`，且整个文本被渲染成了可点击访问 Jira 详情的超链接，使推送信息更紧凑易读。
    - 去除了 `Jira Ticket` 前面的 `- `（连字符前缀），使版面更加整洁。
    - 调整了卡片和富文本中的字段展示顺序，将 `DevPIC` 移动到了 `DevStartTime` 字段之前。
    - 在总数 `COUNT Total` 字段下方新增了一行 `Query Version: {当前版本号}`，直观展示查询的版本范围。
  - 增加兜底文案展示：如果符合条件的数据为 0，则直接展示一条加粗的带有分割线的兜底文案 `"There's no Dev finished issue pending from QA in version {current_version}"`。
  - 提及（Mention）消息优化：根据实际查询结果动态展示版本号。脚本会提取**查询范围**（如 `v6.17, v6.18`）与**实际返回需求所属版本**的**交集**，以此作为 Mention 的标题展示，确保在包含历史/异常数据时展示的版本号绝对精准。

- 新增脚本：`xxljob_missing_qa_subtask.py`
  - 需求背景：用于检查指定版本下（当前自动匹配版本）的 `Story` 和 `Improvement` 类型的需求任务，过滤条件为状态处于 `"PRD APPROVED", "IN DEV", "DEV DONE"`。
  - 动态版本获取优化（奇偶数逻辑）：
    - 无论是配置为 `"AUTO"` 动态获取，还是**固定配置**为特定的版本号（如 `"v6.17"`），都会统一应用版本号奇偶性逻辑。
    - 解析获取到的当前版本号（如 `v6.17`）的最后一位数字，判断其奇偶性。
    - 如果是奇数（表示临时版本），则在查询范围中自动合并获取到的**下一个版本**（如 `v6.17, v6.18`）进行联合查询。如果是在固定配置模式下找不到下一个版本数据，则通过字符串加 1 的方式自动推算出下一个版本。
    - 如果是偶数（表示正常版本），则保持只查询当前版本的需求。
  - 核心逻辑：
    - 遍历上述需求的子任务，通过动态获取该父需求上填写的 `QAs` 字段对应的人员名单，来精确匹配子任务。
    - 增加更细致的异常场景判断并输出自定义提示信息 (`Warning`)：
      - 场景1：如果父任务没有分配QA，且也没有匹配到任何 QA 名单 (`QA_MAP_INLINE`) 内人员负责的子任务，给出提示：`No QA is assigned to this ticket yet`
      - 场景2：如果父任务没有分配QA，但却存在 QA 名单内人员负责的子任务，给出提示：`Please double confirm the QA assignee for this ticket`
      - 场景3：如果父任务分配了QA，但没有该QA对应的子任务，给出提示：`Missing QA subtask`
  - 推送机制：复用 `xxljob_fix_version_dev_finish_time.py` 的格式化逻辑，展示 `Jira Ticket`、`Status`、`Applicable Countries`、`QAs` 以及 `Warning` 字段。针对漏建子任务的情况，会自动发送带有 `Please create QA subtasks for the following issues：` 文案的 Mention 提及通知。
    - 艾特提醒的文案修改为 `"Please Pay Attention To The Dev Done Time："`。
    - Mention 推送的标题不再追加动态版本号，恢复为固定标题格式（如 `"Mention"`）。
  - 增加显式的日志输出，在动态匹配版本成功后输出“捕获当前版本号: {版本号}”，方便排查。
  - 启用了 QAs 艾特（Mention）功能：通过补充 `QA_MAP_INLINE` 中的开发人员飞书 ID 映射表，并在推送主报告后调用 `_send_mentions` 进行对应负责人的提醒。
  - 优化了动态版本号的匹配算法：改为调用 Release Management Board 接口，将获取到的所有版本根据 `releaseDate` 进行升序排序，随后找出第一个 `releaseDate` 大于或等于当前日期（`today`）的版本，以精确匹配当前正处于开发/测试周期的迭代版本。
  - 修复了动态版本匹配逻辑中意外使用了局部 `import datetime` 导致覆盖全局 `datetime` 类，从而引发后续计算时间范围时出现 `TypeError: isinstance() arg 2 must be a type...` 异常的严重 Bug。
  - 优化了艾特（Mention）消息的推送标题：将固定标题（如 `"2026-05-28 Mention"`）修改为携带当前迭代版本号的格式（如 `"2026-05-28 v6.16 Mention"`），提升了消息的辨识度。

### Added
- `xxljob_fix_version_dev_finish_time.py`
  - 新增获取需求“最晚结束开发时间（DevEndTime）”和“最早开始开发时间（DevStartTime）”的逻辑，分别读取子任务的自定义字段 `customfield_10109`（Target start）和 `customfield_10110`（Target end）。
  - 新增在报告卡片或富文本中显示 `Applicable Countries`（`customfield_10206`）、`Status` 等补充字段信息。
  - 新增 QA 审批状态校验功能，通过调用 workflow-wise approval 接口，根据返回判断 QA 是处于“(待Approve)”还是“(已Approve)”状态。
  - 报告展示的列表依据 `DevEndTime` 从近到远正序排列。
  - 添加了排除状态配置 `EXCLUDE_STATUSES`（例如：`"SIT Done", "IN SIT", "UAT Done", "IN UAT", "Open", "Closed", "Done", "On Hold"`）用于忽略不需要关注的需求。
- `xxljob_ready_to_brief_story_improvement.py`
  - 参考最新逻辑引入动态获取版本号（`FIX_VERSION: "AUTO"`），根据 Jira Board 接口的 `releaseDate` 自动匹配当前时间所属版本。
  - 在飞书推送内容（卡片/富文本）的 `Total` 字段下方新增一行 `Query Version: {当前版本号}`。
  - 优化报告排版格式：将原先独立的 "Key" 和 "Summary" 合并为了统一的 "Jira Ticket" 字段，渲染为 `{Key}: {Summary}` 的超链接格式，且去除了连字符前缀（`- `）。
  - 提及（Mention）消息优化：与其它脚本保持一致，提取查询版本与实际返回版本的交集来动态展示标题。Mention 的提示文案更新为 `"请相关方及时跟进 Please kindly follow up in time: "`。
  - QAs 名字后缀展示优化：基于审批状态面板，将待审批和已审批状态统一调整为首字母小写的英文形式，分别为 `(Pending approval)` 和 `(Already approved)`，并默认追加展示。
  - 新增兜底文案处理：当符合条件的需求数量为 0 时，使用 f-string 构建并在推送中展示无数据提示文案 `"There's no Ready to Brief Story/Improvement pending from QA in version {current_version}"`，且在其上方增加了分割线，同时将其设置为加粗样式以优化排版体验。
  - 为整个脚本增加全面的模块/函数/核心业务流程级别的中文文档注释（Docstrings），显著提升代码可读性与后期维护性。
