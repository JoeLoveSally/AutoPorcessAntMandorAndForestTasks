# AutoFinishDailyTasks 系统设计文档

**版本：v0.2**  
**阶段：POC → 初始工程化设计（完善版）**  
**目标平台：Android / 支付宝 / 蚂蚁庄园与蚂蚁森林**

---

## 1. 背景

本项目用于自动完成支付宝中高度重复、规则相对固定的日常任务，当前主要覆盖：

- 蚂蚁庄园；
- 蚂蚁森林。

系统运行于电脑侧，通过 ADB 控制 Android 真机，根据手机当前真实页面状态执行确定性操作。

新仓库实现前需要单独验收以下运行前提：

- 电脑可以通过 ADB 连接并控制 Android 真机；
- 可以启动支付宝、截图并 dump UIAutomator Tree；
- 可以从页面观察结果中提取稳定的页面标识和可执行元素；
- 可以保存截图、XML、动作和运行结果作为本地证据。

因此项目进入系统设计阶段。

---

## 2. 设计目标

当前版本的核心目标是构建一个：

> **可观察、可验证、可扩展、以确定性 Workflow 为核心的 Android 自动化运行时。**

系统遵循统一执行模型：

```text
Observe
  ↓
Recognize
  ↓
Decide
  ↓
Act
  ↓
Verify
```

即：

1. 获取手机当前状态；
2. 识别当前页面；
3. 根据 Workflow 决定允许执行的动作；
4. 执行动作；
5. 重新观察页面并验证结果。

禁止采用单纯的：

```text
点击 → 等待 → 点击 → 等待
```

方式串联业务逻辑。

### 2.1 运行边界

当前运行方式是**人工触发的单次执行**：用户到公司后，将手机连接到电脑，确认设备已解锁并完成 ADB 授权，然后手动启动一次 Workflow。

v0.2 不设计定时调度、后台常驻、远程控制、跨设备编排或断点续跑。一次运行只负责当前设备上的一次任务执行，并输出完整结果；下一次运行重新从设备当前状态开始识别。

---

## 3. 非目标

v0.2 暂不实现：

- 通用 Android Agent；
- LLM Planner；
- 多 Agent；
- 通用支付宝自动化平台；
- 微服务；
- 分布式任务系统；
- 数据库；
- 通用 Workflow DSL；
- 大规模视觉模型推理；
- 风控绕过、验证码绕过或反检测机制。

当前优先保证单机、单设备、固定业务 Workflow 的稳定性。

---

## 4. 总体架构

```text
┌─────────────────────────────────────────┐
│              Application                │
│                                         │
│              main.py                    │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│               Workflow                  │
│                                         │
│  ManorDailyWorkflow                     │
│  ForestDailyWorkflow                    │
└────────────────────┬────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌─────────────────┐   ┌─────────────────┐
│   Perception    │   │ ActionExecutor  │
│                 │   │                 │
│ Screenshot      │   │ Tap             │
│ UI Tree         │   │ Swipe           │
│ PageDetector    │   │ Back            │
│ Future: CV/OCR  │   │ Launch          │
└────────┬────────┘   └────────┬────────┘
         │                     │
         └──────────┬──────────┘
                    ▼
            ┌───────────────┐
            │ Device        │
            │ Controller    │
            │               │
            │ ADB           │
            └───────┬───────┘
                    │
                    ▼
              Android Phone
                    │
                    ▼
                 支付宝

旁路能力：

┌─────────────────────────────┐
│ Evidence / Runtime          │
│                             │
│ Screenshot                  │
│ XML                         │
│ Result JSON                 │
│ Retry / Timeout / Logging   │
└─────────────────────────────┘
```

---

## 5. 核心设计原则

| 原则 | 约束 |
| --- | --- |
| 真实页面优先 | 页面规则和动作必须来自截图、UI Tree 或真机结果；未知页面先取证。 |
| 感知分层 | UI Tree 优先，必要时再用 CV/OCR/VLM；复杂能力按需引入。 |
| 职责分离 | PageDetector 只识别页面和元素；Workflow 决定业务动作。 |
| 动作可验证 | 每次动作后重新 Observe，并验证预期页面或结果。 |
| 尽量幂等 | 根据当前状态判断“待执行”或“已完成”，避免重复操作。 |

---

## 6. 核心领域模型

### 6.1 Observation

表示一次完整的手机状态观察。

建议结构：

```python
@dataclass
class Observation:
    timestamp: datetime

    device_serial: str | None
    package: str | None
    activity: str | None

    screenshot_path: Path
    ui_tree_path: Path | None

    ui_tree: UiTree | None
    visible_labels: tuple[str, ...]
    errors: tuple[str, ...]
```

Observation 是 PageDetector 的输入，也是运行证据的基础对象。

Observation 必须代表同一时刻采集的状态。截图、UI Tree、package 和 activity 不能来自不同的采样周期；如果其中一项采集失败，应在 Observation 中记录失败原因，而不是伪造完整状态。

---

## 7. Page

Page 表示系统对当前页面的确定性判断。

初期可定义：

```python
class PageType(Enum):
    ALIPAY_HOME = auto()

    MANOR_HOME = auto()
    MANOR_FAMILY = auto()
    MANOR_DONATION = auto()

    FOREST_HOME = auto()

    UNKNOWN = auto()
```

不要一次性定义所有未来页面。

只有经过真实取证后，才增加 PageType。

---

## 8. PageDetector

职责：

```text
Observation
    ↓
PageDetector
    ↓
DetectedPage
```

建议：

```python
@dataclass
class DetectedPage:
    type: PageType
    observation: Observation
    elements: dict[str, UIElement]
    evidence: tuple[str, ...]
    confidence: float
```

例如：

```python
DetectedPage(
    type=PageType.ALIPAY_HOME,
    elements={
        "manor": ...,
        "forest": ...,
    },
)
```

PageDetector 必须同时返回“识别结论”和“识别依据”。`confidence` 不是允许 Workflow 猜测操作的授权，而是用于判断是否达到该页面的最低识别阈值；低于阈值时统一返回 `UNKNOWN`。

页面识别至少应校验：

```text
package / activity 是否符合页面范围
AND
存在页面稳定标识
AND
关键元素没有被未知弹窗遮挡
```

---

## 9. 页面识别策略

页面不能仅依赖单个按钮判断。

例如支付宝主页可以使用：

```text
package == com.eg.android.AlipayGphone

AND

存在：
    蚂蚁庄园

AND

存在：
    蚂蚁森林
```

庄园主页未来可能使用：

```text
存在：
    蚂蚁庄园
    家庭
    去捐蛋
```

具体规则必须经过真机验证后确认。

---

## 10. UI Element

统一封装 UI Tree 中可执行的元素。

例如：

```python
@dataclass
class UIElement:
    text: str | None
    bounds: Bounds
    clickable: bool
    enabled: bool
    source: str
    observation_timestamp: datetime
```

支持：

```python
element.center
element.enabled
element.clickable
```

`UIElement` 只在创建它的 Observation 仍然有效时可执行。页面重新 Observe 后，旧元素必须失效，不能跨观察周期复用坐标。

现有：

> 根据文字节点寻找最近的 clickable 父容器

逻辑继续保留在 UI Tree 层，不泄漏到业务 Workflow。

---

## 11. Action

Workflow 不直接调用：

```python
adb.shell("input tap ...")
```

统一通过 ActionExecutor。

基础动作：

```text
LaunchApp
Tap
Swipe
Back
Wait
```

例如：

```python
actions.tap(element)
```

内部由 ActionExecutor 转换为 ADB 指令。

---

## 12. ActionExecutor

负责：

- 参数校验；
- 转换坐标；
- 调用 ADB；
- 保存动作记录；
- 统一异常处理。

例如：

```text
Workflow
   ↓
Tap(UIElement)
   ↓
ActionExecutor
   ↓
ADB shell input tap
```

Workflow 不依赖 ADB 实现细节。

ActionExecutor 必须使用统一的设备坐标系。视觉匹配得到的坐标在传给 ADB 前，必须经过屏幕尺寸校验；超出当前屏幕边界、元素已失效或页面前置条件不满足时，动作不得执行。

每次动作都返回结构化结果：

```python
@dataclass(frozen=True)
class ActionResult:
    name: str
    status: str  # executed / rejected / failed
    point: tuple[int, int] | None
    error: str | None
```

---

## 13. Workflow

Workflow 是业务核心。

当前至少包括：

```text
ManorDailyWorkflow
ForestDailyWorkflow
```

v0.2 优先实现 ManorDailyWorkflow。

---

## 14. ManorDailyWorkflow

当前已确认目标：

```text
START
  ↓
支付宝主页
  ↓
蚂蚁庄园
  ↓
庄园主页
  ↓
家庭
  ↓
立即签到
  ↓
签到后页面
  ↓
返回庄园主页
  ↓
每日捐蛋做好事
  ↓
如果“去捐蛋”可执行
  ↓
捐蛋页面
  ↓
DONE
```

尚未取得真实证据的流程不能提前实现。

---

## 15. Workflow Step

建议一个 Step 遵循统一形式：

```text
Precondition
    ↓
Action
    ↓
Wait
    ↓
Observation
    ↓
Postcondition
```

例如：

### EnterFamily

Precondition：

```text
Page == MANOR_HOME
AND
存在 enabled FAMILY
```

Action：

```text
Tap FAMILY
```

Postcondition：

```text
Page == MANOR_FAMILY
```

失败：

```text
Retry / Capture / Abort
```

---

## 15.1 Task Contract

每个业务任务先定义契约，再实现 Workflow：

```python
@dataclass(frozen=True)
class TaskSpec:
    name: str
    entry_page: PageType
    preconditions: tuple[str, ...]
    action: str
    success_conditions: tuple[str, ...]
    already_done_conditions: tuple[str, ...]
    unknown_conditions: tuple[str, ...]
```

任务状态统一为：

```text
SUCCESS / ALREADY_DONE / SKIPPED / UNKNOWN / FAILED
```

未完成取证的任务只能登记为规划项，不得直接加入 Workflow。

| 任务 | 入口页面 | 当前阶段 | 最终验证要求 |
| --- | --- | --- | --- |
| 进入蚂蚁庄园 | `ALIPAY_HOME` | 已验证 | 识别 `MANOR_HOME` |
| 进入家庭 | `MANOR_HOME` | 已验证 | 识别 `MANOR_FAMILY` |
| 家庭签到 | `MANOR_FAMILY` | 首个闭环 | 识别成功提示或已签到状态 |
| 庄园其他任务 | `MANOR_HOME` | 规划中 | 识别任务完成状态 |
| 森林收能量/浇水 | `FOREST_HOME` | 规划中 | 识别任务完成状态 |

---

## 16. 页面状态转换

Workflow 本质上可以视为有限状态转换：

```text
ALIPAY_HOME
    │
    │ open_manor
    ▼
MANOR_HOME
    │
    │ open_family
    ▼
MANOR_FAMILY
    │
    │ sign_in
    ▼
MANOR_FAMILY_SIGNED
```

正常路径之外，Workflow 必须显式处理以下分支：

| 当前状态 | 条件 | 处理 | 结果 |
| --- | --- | --- | --- |
| 任意已知页面 | 出现已确认且安全的业务弹窗 | 执行唯一的关闭动作，重新 Observe | 继续当前任务 |
| `MANOR_FAMILY` | 存在 enabled 的“立即签到” | 点击并验证签到结果 | `SUCCESS` 或 `UNKNOWN` |
| `MANOR_FAMILY` | 不存在签到按钮，但存在已签到标记 | 不点击 | `ALREADY_DONE` |
| `MANOR_FAMILY` | 没有签到按钮，也没有已签到标记 | 保存证据并停止 | `UNKNOWN` |
| 任意状态 | 页面跳转到 `UNKNOWN` | 保存证据，不执行业务点击 | `UNKNOWN` |
| 任意状态 | 设备断开、ADB 超时或动作失败 | 保存可用证据并终止本次运行 | `FAILED` |

同一状态下不得依赖条件判断的排列顺序来隐含这些分支。每个分支都应有明确的预期页面、允许动作和终止状态。

v0.2 不需要引入专门 FSM Framework。

普通 Python 代码即可。

但状态转换必须明确，而不是散落的条件判断。

---

## 17. Unknown 页面策略

任何无法可靠识别的页面：

```text
PageType.UNKNOWN
```

不能尝试猜测操作。

默认处理：

```text
UNKNOWN
   ↓
Capture Evidence
   ↓
保存 screenshot
   ↓
保存 XML
   ↓
保存 package/activity
   ↓
Abort Current Workflow
```

开发阶段再人工分析该证据。

未来可以扩展：

```text
UNKNOWN
   ↓
CV / OCR
   ↓
VLM Recovery
```

但不属于当前 v0.2 核心链路。

---

## 18. Retry 策略

页面加载和动作验证统一使用有限等待，不使用无限循环或单次固定 sleep：

```python
wait_until(
    observe: Callable[[], Observation],
    predicate: Callable[[Observation], bool],
    timeout_seconds: float,
    interval_seconds: float,
) -> Observation
```

返回满足条件的最新 Observation；超时抛出 `TimeoutError`，由 Workflow 选择有限重试、保存证据停止或标记 `UNKNOWN`。等待期间不得复用旧元素。

---

## 19. Timeout

所有等待外部状态的操作必须配置上限，例如：

```python
PAGE_LOAD_TIMEOUT = 10
ACTION_VERIFY_TIMEOUT = 5
```

具体数值应通过真机测试确定。

---

## 20. Evidence

Evidence 是运行结果的一部分。每次运行创建独立目录：

```text
artifacts/
└── 20260814-xxxxxx/
    ├── <step>.png / <step>.xml
    └── result.json
```

每个关键动作保留 Before、Action、After、Result；`result.json` 能反向定位 Observation、Action 和页面转换，并至少记录：

```text
timestamp / device / package / activity
screenshot / UI XML / page evidence
```

Evidence 只用于复盘当前运行，不作为下一次运行的状态库；默认只保存在本机。

---

## 21. Result

运行结果至少包含：

```json
{
  "workflow": "manor_daily",
  "status": "success",
  "started_at": "...",
  "finished_at": "...",
  "device": "...",
  "steps": [],
  "tasks": [],
  "actions": [],
  "error": null
}
```

失败时补充：

```json
{
  "status": "failed",
  "workflow": "manor_daily",
  "error": {
    "type": "page_not_recognized",
    "expected": "MANOR_FAMILY",
    "actual": "UNKNOWN",
    "step": "enter_family"
  },
  "evidence_directory": "..."
}
```

运行级和任务级状态统一为：`success`、`already_done`、`skipped`、`unknown`、`failed`。

---

## 22. Error 分类

| 类型 | 典型原因 |
| --- | --- |
| `DeviceError` | ADB 断开、未授权或 shell 失败 |
| `LaunchError` | 无法解析或启动 Launcher |
| `RecognitionError` | 页面或关键元素无法识别 |
| `ActionError` | 目标 disabled、坐标无效或动作失败 |
| `TransitionError` | 实际页面不符合预期转换 |
| `TimeoutError` | 页面加载或动作验证超时 |
| `SafetyStop` | 敏感页面、未知遮罩层或过期元素 |

---

## 23. 安全边界

Workflow 只允许处理明确识别的庄园或森林页面。检测到以下内容立即终止：

```text
支付 / 付款 / 转账 / 订单确认 / 密码输入 / 生物认证
```

未知页面默认不点击。每次业务动作前检查：

```text
设备在线且已解锁
package/activity 和 PageType 在允许范围
目标元素来自最新 Observation，且 enabled/clickable/bounds 有效
没有未知弹窗或敏感操作页面
```

任一检查失败都执行 `SafetyStop`，不通过固定坐标或模糊匹配恢复。

---

## 24. 模块与职责

```text
domain/       Page、Observation、TaskSpec、Result 等模型
device/       ADB、截图、UI dump、启动应用
perception/   Observation、UI Tree、页面检测器
actions/      Tap/Swipe/Back 等原子动作及校验
workflows/    庄园和森林业务流程
runtime/      等待、超时、错误和结果汇总
evidence/     截图、XML、动作记录和 result.json
```

依赖方向固定为：

```text
Workflow → Perception / Actions / Runtime
Perception → Device
Actions → Device
Evidence → Device / Runtime
```

Workflow 不直接调用 ADB；PageDetector 不决定业务顺序；Domain 不读取设备或执行动作。

感知实现统一输出 `DetectedPage`。优先使用 UI Tree；目标元素缺失时才使用已登记的 CV 模板；匹配不确定、候选冲突或坐标越界时返回 `UNKNOWN`。OCR/VLM 仅作为显式登记的恢复步骤，不参与正常流程的自由决策。

日志至少记录：`timestamp`、`workflow`、`step`、`page_before`、`action`、`page_after`、`duration`、`result`。

---

## 25. 测试策略

### 单元测试

继续覆盖：

- Launcher Activity 解析；
- XML 解析；
- 元素定位；
- clickable parent；
- enabled 判断；
- PageDetector；
- Workflow 状态判断；
- Task Contract 的 success/already_done/skipped/unknown 分支；
- SafetyStop 和过期 UIElement 拒绝执行。

### XML 回放测试

真实手机获取的 XML 应保存为测试 fixture。

例如：

```text
tests/fixtures/
├── alipay_home.xml
├── manor_home.xml
└── manor_family.xml
```

PageDetector 可以在没有手机的情况下回放真实页面。

这是后续最重要的测试方式之一。

每个已知页面至少需要一份正常 fixture 和一份关键异常 fixture，例如：

```text
manor_family_normal.xml
manor_family_popup.xml
manor_family_already_signed.xml
unknown_page.xml
```

回放测试必须覆盖“识别页面 → 选择任务分支 → 生成允许动作或安全停止”，不能只验证字符串查找。

### 真机测试

真机测试主要验证：

```text
ADB
→ Observation
→ Recognition
→ Action
→ Transition
```

不要把所有测试都依赖真实手机。

---

## 26. 当前已知页面

| 页面 | 已知标识 | 可规划动作 |
| --- | --- | --- |
| `ALIPAY_HOME` | 蚂蚁庄园、蚂蚁森林 | 进入庄园/森林 |
| `MANOR_HOME` | 蚂蚁庄园、家庭、去捐蛋 | 进入家庭或任务 |
| `MANOR_FAMILY` | 欢乐全家桶、立即签到 | 签到 |

页面规则必须经过真实取证后才可执行。

---

## 27. 当前未知状态

签到结果、亲密度任务、捐蛋、小鸡状态和森林页面均属于未知状态。
处理流程：`Capture → 分析 → 增加规则 → Replay Test → 真机验证`。

---

## 28. v0.2 开发顺序

1. `ALIPAY_HOME → MANOR_HOME`
2. `MANOR_HOME → MANOR_FAMILY → SIGN_IN → Verify`
3. 增加捐蛋及其他庄园任务
4. 处理小鸡雇佣和召回
5. 开始 Forest Workflow

---

## 29. v0.2 成功标准

系统设计阶段后的第一个里程碑定义为：

运行前置条件：设备已通过 ADB 连接并授权、手机已解锁、支付宝可以正常打开。该里程碑不要求后台常驻或定时触发。

```text
用户手动启动程序
    ↓
自动启动支付宝
    ↓
识别支付宝主页
    ↓
进入蚂蚁庄园
    ↓
识别庄园主页
    ↓
进入家庭
    ↓
执行签到或判断已签到
    ↓
验证最终状态
    ↓
输出完整 Evidence + Result
```

要求：

- 不依赖固定绝对坐标作为页面元素定位依据；
- 不依赖未经验证的页面文案；
- 不产生无限重试；
- 任一未知状态安全退出；
- 所有失败均保留可复现证据。

---

## 30. 核心不变量

整个系统后续开发应保持以下不变量：

| 编号 | 不变量 |
| --- | --- |
| INV-01 | 业务动作执行前必须存在可验证的页面状态。 |
| INV-02 | 动作执行后必须重新 Observe，不能假设动作成功。 |
| INV-03 | `UNKNOWN` 页面不可执行业务点击。 |
| INV-04 | 页面规则必须来自真实页面证据。 |
| INV-05 | Workflow 不直接依赖 ADB 命令。 |
| INV-06 | PageDetector 不负责业务决策。 |
| INV-07 | 等待和重试必须有明确上限。 |
| INV-08 | Evidence 必须足以复盘失败运行。 |
| INV-09 | 禁止自动执行支付、转账等非目标功能。 |
| INV-10 | 复杂感知能力按需增加。 |
| INV-11 | UIElement 只在其 Observation 周期内有效。 |
| INV-12 | 任务必须区分成功、已完成、跳过、未知和失败。 |
| INV-13 | 动作前必须通过设备、页面和敏感操作安全检查。 |
| INV-14 | 感知冲突或视觉匹配不确定时进入 `UNKNOWN`。 |

---

## 31. 总结

AutoFinishDailyTasks v0.2 采用：

> **单进程 Python + ADB + UI Tree 优先 + 确定性 Workflow + Evidence 驱动开发**

作为基础架构。

核心链路为：

```text
Observation
    ↓
PageDetector
    ↓
Workflow
    ↓
ActionExecutor
    ↓
ADB
    ↓
Observation
```

当前最重要的不是继续增加框架能力，而是让该架构通过真实支付宝页面逐步完成：

```text
UNKNOWN
→ 取证
→ Known Page
→ Known Transition
```

的收敛过程。

视觉识别、OCR 和 VLM 均保留扩展位置，但只有在真实证据证明 UI Tree 不足后才引入。
