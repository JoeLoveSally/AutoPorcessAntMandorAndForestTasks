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
- 页面和元素安全校验；
- 有限等待、超时和 `UNKNOWN` 停止；
- 本地截图、XML、Observation 元数据和 `result.json` 记录。

真实签到成功页面尚未取证，因此 Workflow 执行签到动作后会停止并返回 `unknown`，不会猜测成功状态。

## 安装与运行

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp config.example.toml config.toml

.venv/bin/ants-auto --config config.toml doctor
.venv/bin/ants-auto --config config.toml manor-daily
```

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
