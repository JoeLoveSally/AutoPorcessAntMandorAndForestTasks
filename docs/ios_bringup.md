# iPhone 联调准备（无 Mac 路线）

iOS 迁移（`feature/ios-support`）已完成接口层：`platform = "ios"` 的配置经
`runtime.cli.build_device` 构造 `device_bridge.ios.IosDevice`，通过
WebDriverAgent（WDA）的 REST 协议驱动 iPhone。本文档是**真机联调前**要完成
的部署清单与联调步骤；所有 WDA 端点以联调首日实测为准（客户端把每个端点都
收在 `IosDevice._call` 一处，改名成本一行）。

## 0. 现实约束（先读）

- iOS 不提供公开的触控注入 API，不越狱情况下唯一注入面是挂在 XCTest 上的
  WebDriverAgent。
- WDA 是 Xcode 工程，**首次构建需要一台 macOS**（一次性，产物可反复用）。
- 签名后的 ipa 用免费 Apple ID 安装有效期 7 天（AltServer/Sideloadly 联网可
  续）；付费开发者账号（$99/年）签名为 1 年。
- 联调机（Windows/WSL2）与 iPhone 通过 usbmuxd（iOS ≤16）或 RemoteXPC 隧道
  （iOS ≥17）连通，不需要 Mac 参与日常运行。

## 1. 构建 WDA（无 Mac 时）

任选其一：

- **借一台 Mac 一次性构建**：Xcode 打开
  [facebook/WebDriverAgent](https://github.com/facebook/WebDriverAgent)（或
  appium 维护的 fork），改 bundle id 为自己的 Team 前缀，直接 Run 到手机上
  （手机开开发者模式），随后可取 ipa 归档。
- **GitHub Actions 云构建**（macos runner 免费用）：`.github/workflows/wda.yml`
  修改自身即自动触发，也可手动 workflow_dispatch（默认
  `appium/WebDriverAgent@master`）。流程为
  `xcodebuild -project WebDriverAgent.xcodeproj -scheme WebDriverAgentRunner
  -destination 'generic/platform=iOS' -archivePath wda.xcarchive archive`
  → 打包 unsigned ipa 并挂到仓库 Releases（公开直接下载，job Artifacts 里
  也有一份）；签名留给第 2 步。构建失败时各阶段日志会推到 `ci/wda/`
  目录，可直接从 raw.githubusercontent 查看。

## 2. 签名并安装到 iPhone（Windows 可完成）

- [Sideloadly](https://sideloadly.io/) 或 AltStore：载入预编译/云构建的
  WDA ipa + Apple ID 签名安装；或 3uTools/爱思助手的自签安装。
- 手机：设置 → 隐私与安全 → 开发者模式 打开；首次启动 WDA 的
  `WebDriverAgentRunner-Runner` 后在 通用→VPN与设备管理 信任证书。
- 验证安装：`pymobiledevice3 apps list | grep -i webdriveragent`（或
  `tidevice app list`）。

## 3. 建立端口转发（联调机侧）

WDA 启动后监听手机上的 8100 端口，联调机需要把它转到本地：

- **iOS ≤ 16**（usbmuxd 直连）：
  `tidevice -u <udid> forward 8100 8100`，或
  `pymobiledevice3 remote` 生态的等价 forward。
- **iOS ≥ 17**（RemoteXPC 隧道）：
  `sudo pymobiledevice3 remote tunneld` 起隧道后，用 pymobiledevice3 的
  forward 能力映射 8100。
- **启动 WDA 的 xctest**：`tidevice -u <udid> xctest -B
  com.WebDriverAgentRunner.xctrunner`（或手机上手动点开 runner 图标；
  iOS17+ 的启动方式以联调时 pymobiledevice3 版本为准）。
- 快速验证：`curl http://127.0.0.1:8100/` 返回
  `{"value":{"name":"WebDriverAgent",...}}` 即通。

> 若手机与联调机同 Wi-Fi 且 WDA 以网络模式启动，也可直接
> `wda_url = "http://<手机IP>:8100"` 跳过转发。

## 4. 配置并自检

复制 `config/config.example.toml` 为 `config/config.ios.toml`：

```toml
platform = "ios"
serial = "<iPhone udid>"          # pymobiledevice3 usbmux list / tidevice list
package = "com.alipay.iphoneclient"   # 联调首日确认实际 bundle id
wda_url = "http://127.0.0.1:8100"
```

然后：

```bash
./scripts/ants-auto doctor --config config/config.ios.toml   # platform=ios 输出 + WDA 信息
./scripts/ants-auto capture --config config/config.ios.toml  # 截图+OCR 分页，验证观测链
```

## 5. 端点校准清单（联调首日逐项过）

| 客户端方法 | WDA 端点 | 校准命令 |
| --- | --- | --- |
| `foreground()` | `GET /wda/activeAppInfo` | 打开支付宝后 curl，确认 `value.bundleId` |
| `frame()/screenshot()` | `GET /screenshot` | 确认 base64 PNG 与屏幕同分辨率 |
| `tap()` | `POST /wda/tap` | body `{"x","y"}` 点击落点校准 |
| `swipe()` | `POST /wda/drag` | body `{"fromX","fromY","toX","toY","duration(秒)"}` |
| `back()` | drag（左边缘右滑） | 小程序页返回行为验证 |
| `launch()` | `POST /wda/apps/launch` | body `{"bundleId"}` |
| `window_size()` | `GET /window/size` | 与截图分辨率一致性 |

## 6. 已知降级与待定项

- **观测为纯 OCR**：iOS 无 uiautomator dump，`tree()` 显式抛 UI_TREE，
  Observer 记 `tree.unavailable` 后仅 OCR 分页——现有页面规则全部基于 OCR
  文本，理论适配，但元素合并（ui_tree+ocr 双源校验）缺失，精度以联调实测
  为准。
- **能量雨不支持**：实时通道（screen_stream/touch_channel）在 iOS 抛
  REALTIME，`forest.self` 的能量雨步会 fail-closed；方案（WDA 连续截图轮询 /
  ios-webkit-debug-proxy 等）留待联调阶段评估。
- **支付宝 iOS 与 Android 功能面差异**：庄园/森林入口位置、活动弹窗族、
  文案均可能不同，页面规则（PAGE_RULES）与恢复分支需按 iOS 真帧逐个校准——
  建议联调首日先跑 `capture` 采一批真帧，再 `debug --task` 单任务推进。
- `package` 的 bundle id、WDA 启动方式、iOS17+ 隧道细节均为待实测项，
  以联调当日的 pymobiledevice3/tidevice 版本为准。
