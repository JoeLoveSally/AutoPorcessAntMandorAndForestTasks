# 支付宝蚂蚁庄园 Android 自动化 POC

本项目采用证据驱动的开发方式：程序自动走到当前已知边界，保存 screenshot、UIAutomator XML、当前 Activity 和动作记录；遇到未知页面后停止，人工确认稳定特征，再增加下一步规则。

当前阶段不引入 OCR、VLM、Agent 或复杂工作流框架。

## 当前真机进度

测试设备：vivo X90 Pro+（ADB model `V2227A`），序列号由本地配置或 ADB 自动选择。

截至 2026-08-14，以下链路已在支付宝被彻底杀掉、手机已解锁的条件下完成真机验证：

```text
ADB 发现设备
  → 动态解析并冷启动支付宝 Launcher Activity
  → 等待并识别支付宝主页
  → 通过固定文字“蚂蚁庄园”找到可点击父容器
  → 自动点击并进入蚂蚁庄园
  → 等待庄园主体加载
  → OpenCV 匹配固定文字“家庭”
  → 自动点击并进入家庭页
  → 保存家庭页证据后停止
```

验证结果：

| 阶段 | 状态 | 实际依据 |
| --- | --- | --- |
| WSL USB/ADB | 已验证 | `adb devices -l` 返回 `device` |
| 支付宝冷启动 | 已验证 | 动态解析 Launcher，前台为 `com.eg.android.AlipayGphone/.AlipayLogin` |
| 支付宝主页识别 | 已验证 | UI Tree 同时出现“蚂蚁庄园”和“蚂蚁森林” |
| 庄园入口点击 | 已验证 | 文字子节点提升到可点击父容器后点击成功 |
| 庄园页面识别 | 已验证 | 前台为 `XRiverActivity`，原生标题栏出现“蚂蚁庄园” |
| 庄园主体 UI Tree | 已确认不足 | 主体只有全屏 `android.webkit.WebView`，没有“家庭/去捐蛋”等节点 |
| “家庭”视觉定位 | 已验证 | 真实截图模板匹配分数 `1.0`，点击后进入家庭页 |
| 家庭页识别 | 已验证 | UI Tree 出现“欢乐全家桶”等页面文字 |
| “立即签到” | 尚未执行 | 本次进入后出现“家庭家具上新啦”弹窗，遮挡签到按钮 |

本次完整产物位于：

```text
artifacts/20260814-094226-140578/
```

其中 `result.json` 记录了两个真实动作：

- `open-manor`：`ui-tree-clickable-parent`；
- `open-family`：`opencv-template`，匹配分数 `1.0`。

家庭页截图中出现了新的实际状态：“家庭家具上新啦”弹窗，包含“去看看”和关闭按钮。程序没有猜测或越过该弹窗，而是在保存证据后停止。

## 下一步唯一目标

基于已采集的弹窗截图/XML，增加合法的关闭动作，然后完成：

```text
进入家庭
  → 识别并关闭已知弹窗
  → 重新观察家庭页
  → 定位“立即签到”
  → 点击签到
  → 立即保存签到后 screenshot + XML + Activity + result.json
  → 根据真实结果定义“签到成功”判据
```

在签到闭环完成前，不继续实现捐蛋、亲密度任务、小鸡召回、其他庄园任务或蚂蚁森林。

## 环境

项目使用 WSL/Linux 版 ADB。Scrcpy 不是自动化依赖，可在 Windows 侧作为人工看屏工具。

手机每次拔线、重启 WSL 或重新连接后，`usbipd list` 可能只显示 `Shared`，需要在 Windows 侧重新执行：

```powershell
usbipd attach --wsl --busid <当前BUSID>
```

WSL 中应确认：

```bash
lsusb
adb devices -l
```

vivo 的 USB 厂商 ID 是 `2d95`，本机已通过 udev 规则将设备权限授予 `plugdev` 组。

Python 使用项目独立虚拟环境：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[vision,dev]'
```

## 安全实验命令

```bash
.venv/bin/python -m ants_automation.cli --config config.toml doctor
.venv/bin/python -m ants_automation.cli --config config.toml inspect-home
.venv/bin/python -m ants_automation.cli --config config.toml inspect-manor
.venv/bin/python -m ants_automation.cli --config config.toml inspect-family
```

- `inspect-home`：自动启动支付宝并采集主页，不点击入口。
- `inspect-manor`：自动进入庄园，采集庄园页面后停止。
- `inspect-family`：自动进入庄园，通过真实“家庭”模板进入家庭，采集后停止。
- `snapshot`：只采集手机当前页面，适合未知状态取证。

`daily --execute` 尚未完成当前阶段的逐步真机验收，不应作为现阶段实验入口。

## 定位策略

支付宝主页继续优先使用 UIAutomator：

```text
固定文字节点
  → 最近的 enabled + clickable 父节点
  → 使用父节点 bounds 点击
```

这样可以区分主页应用入口和消息区内同名的“蚂蚁庄园”。

庄园主体已经由真实 XML 证明不暴露内部控件，因此主体动作使用 OpenCV 模板匹配。模板只截取已确认稳定的“家庭”文字，不包含会变化的小鸡、衣服和庄园场景。模板文件：

```text
templates/manor_family.png
```

每个视觉动作必须记录模板、阈值、实际分数和点击点；匹配不足时停止，不使用兜底固定坐标。

## 产物

每次运行在项目的 `artifacts/<时间>/` 保存：

- 各阶段截图 `*.png`；
- UIAutomator Tree `*.xml`；
- UI dump 错误 `*-ui-error.txt`；
- 当前 Activity；
- UI 可见文字；
- 动作定位方式、点击点和视觉匹配分数；
- 汇总结果 `result.json`。

## 代码结构

```text
ants_automation/
  adb.py                   # 设备、启动、点击、滑动、返回、截图、UI dump、Activity
  ui_tree.py               # 精确文字识别与可点击父节点解析
  vision.py                # OpenCV 模板匹配
  artifacts.py             # 分阶段证据采集
  pages/manor.py           # 已知页面检测器
  workflows/manor_daily.py # 当前 POC 探索流程
templates/
  manor_family.png         # 由真机庄园截图提取的“家庭”模板
```

## 开发原则

```text
UNKNOWN 页面
  → 保存 screenshot + XML + Activity
  → 人工确认稳定特征
  → 增加 Page Detector
  → 增加唯一合法 Action
  → 真机验证
  → 成为 KNOWN 页面
```

没有真实证据的喂食、成功提示、确认弹窗、捐蛋状态、小鸡召回等规则不提前实现。
