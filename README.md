# AutoProcess Ant Manor and Ant Forest Tasks

支付宝蚂蚁庄园与蚂蚁森林的证据驱动 Android 自动化项目。

当前运行边界是人工触发的单次执行：手机连接电脑、解锁并完成 ADB 授权后，手动启动 Workflow。项目不包含后台常驻、定时调度或远程控制。

## 当前实现

已建立新仓库的基础运行时：

```text
Observation
  → PageDetector
  → Workflow
  → ActionExecutor
  → ADB
  → Evidence + Result
```

当前可离线验证：

- 支付宝主页识别；
- 庄园主页识别；
- 家庭页识别；
- 庄园 Canvas 中的家庭入口、好友喂食打赏、红点日记本视觉定位；
- 多个好友喂食提示的有限循环打赏与静默等待；
- 家庭签到成功和今日已签到状态判断；
- 家庭“每日捐蛋做好事”完整流程：首个项目、默认 1 颗、奖励页和安全返回；
- 家庭桌面红色“去喂食”及默认确认；
- 饲料每日领取、联网搜索答题、15 秒庄园视频和饲料满袋拒绝领取；
- 庄园两个抽抽乐的逛店任务、滑动保活、耗尽抽奖次数与奖励确认；
- 森林好友能量收取、森林寻宝任务与抽奖；
- 两轮能量雨实时视觉点击，第二轮固定赠送“小布”；
- 爱情合种每日浇水 100g；
- 通过任务文案 `(1/1)` 判断今日已捐蛋，重复运行不会再次捐蛋；
- 页面和元素安全校验；
- 有限等待、超时和 `UNKNOWN` 停止；
- 终端实时日志，以及 `logs/<started-timestamp>.log`、截图、XML、Observation 元数据和 `result.json`。

红点日记本的入口已经过真实截图验证，打开后通过 Android 返回键回到庄园主页并验证页面。

家庭捐蛋链路已在真机逐页取证并成功捐出默认的 1 颗爱心蛋；完整链路已加入离线回放，捐蛋完成后的幂等分支也已通过真机 Workflow 验证。家庭中的捐步、请客等其他任务尚未纳入当前流程。

饲料、轮盘、森林和能量雨部分已依据录屏与截图实现页面规则和有限循环，并通过离线单元测试；这些新增链路尚待下一轮连接真机逐页校准。

## 安装与运行

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev,vision]'
cp config.example.toml config.toml

.venv/bin/ants-auto --config config.toml doctor
.venv/bin/ants-auto --config config.toml manor-daily
.venv/bin/ants-auto --config config.toml forest-daily
.venv/bin/ants-auto --config config.toml daily
```

答题通过博查 Web Search 查询，并对搜索结果中的明确“正确答案/答案”表述打分；结果不唯一时会停止，不会猜选。密钥从 `[quiz].api_key_env` 指定的环境变量读取，也可让 `[quiz].env_file` 指向只存在于本机的 dotenv 文件。密钥不会写入证据、日志或缓存。

运行日志位于 `logs/<started-timestamp>.log`，文件名使用 Workflow 的开始时间；证据目录位于 `artifacts/<run-id>/`。排查时先查看对应日志和 `result.json`，再按日志中的 Observation 名称检查同名 `.png`、`.xml` 和 `.json`。

没有手机时可以直接运行测试：

```bash
.venv/bin/pytest -q
```

## 目录

```text
ants_automation/
  domain/       页面、观察、任务和结果模型
  device/       ADB 设备抽象
  perception/   UI Tree、Observation 和页面检测
  actions/      原子动作与安全校验
  workflows/    庄园/森林业务流程
  runtime/      配置、等待、错误
  evidence/     本地运行证据
tests/          XML fixture、单元测试和工作流回放测试
docs/           系统设计
```

`legacy/` 是历史 POC，不属于新仓库实现，也不会被提交到远端。
