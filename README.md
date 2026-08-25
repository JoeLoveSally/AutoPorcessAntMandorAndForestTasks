# Ants Auto

在 WSL2 中通过 ADB 自动执行一次蚂蚁庄园 + 蚂蚁森林日常流程。项目按页面状态识别后再操作，不使用无人值守调度；任何资源不足、未知页面或验证失败都会安全停止，并保留截图、UI 树和结构化日志供人工处理。

## 已实现范围

- 庄园主页：逐个打赏、带小鸡回家、贴贴小鸡。
- 庄园家庭：签到、固定选择首个公益项目捐 1 颗蛋、请客、喂食，并检查完成标记。
- 领饲料：签到、两选一答题、视频/滑动广告、两类抽抽乐、芭芭农场、家庭/森林等点击即完成任务、小鸡厨房和列表刷新任务。
- 森林：收自己的能量、逐页一键收好友能量、两侧森林抽奖、真爱合种 100g、合种 520g、两轮天天能量雨。
- 安全机制：页面白名单、观测快照绑定、操作后置条件、未知页拒绝点击、SQLite 运行记录、JSONL 日志和失败现场截图。
- 能量雨：ADB `screenrecord` 原始 H.264 实时帧、持续 ADB 触控、目标跟踪与命中率统计；默认验收线为 80%。scrcpy 官方运行包保留用于环境诊断和备用验证。

不包含定时启动、无人值守重连和“运动捐步”任务。按当前约定，答题搜索不可用或结果不明确时固定选择第一项。

## 环境准备

环境为 WSL2 Ubuntu 24.04，手机需先从 Windows USB 共享并 Attach 到 WSL，且支付宝已登录。

```bash
./scripts/bootstrap
cp config/config.example.toml config/config.toml  # bootstrap 已在缺失时自动复制
adb devices -l
./scripts/ants-auto doctor
```

在 `config/config.toml` 的 `device.serial` 填入设备序列号。若要启用旧项目同类的 Bocha 搜索能力，把 API Key 放入环境变量 `WEB_SEARCH_API_KEY`；不配置时自动使用第一项。

`bootstrap` 下载 scrcpy 官方 Linux v4.1 包并校验固定 SHA-256，不安装系统级软件。真机验证发现 scrcpy 的容器录制文件不能稳定提供未封口的实时帧，因此正式能量雨通道改用 Android 原生 H.264 输出；scrcpy 不参与自动点击主链路。`config/config.toml`、运行日志、截图和运行时二进制均不会提交到 Git。

## 使用

```bash
./scripts/ants-auto doctor       # 设备与依赖检查
./scripts/ants-auto capture      # 仅读取并识别当前页面
./scripts/ants-auto probe        # 测量 ADB 观测延迟
./scripts/ants-auto stream-test  # 仅读取实时视频帧
./scripts/ants-auto manor        # 只执行一次庄园
./scripts/ants-auto forest       # 只执行一次森林
./scripts/ants-auto daily        # 依次执行庄园 + 森林
```

运行结果写入 `screenshots/runs/<run-id>/result.json`，逐步日志写入 `logs/<run-id>.jsonl`，本地步骤状态写入 `runtime/task_state.db`。

## 验证

```bash
./scripts/test
.venv/bin/python -m ruff check src tests
```

系统设计、开发阶段和实测记录分别见 [docs/system_design.md](docs/system_design.md)、[docs/dev_plan.md](docs/dev_plan.md) 与 [docs/validation_report.md](docs/validation_report.md)。
