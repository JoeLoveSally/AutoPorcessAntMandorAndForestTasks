# 真机校准记录

## 2026-10-09：红日记本无提示日的定案与放行

- run `3a6860`（10-09 第 1 跑，全链累计第 10 跑）——冷启无更新弹窗（App 未更新，
  用户确认），reward SKIPPED、bring_home SKIPPED（小鸡在家），diary 首次尝试
  `小鸡日记|^日记$: found 0` 再次失败——与 10-08 同点位连续第 2 天。
- 缺位定案（双通道 + 对照裁剪）：OCR 无文本，`manor_diary_entry` 校准带视觉
  检测返回 None（09-30 对照帧命中 (1028,1686)、红像素 96003 vs 9864）；同区域
  裁剪并排对比确认书位只有树干水面，好友小鸡在左侧未遮挡；两日均为**当天首个
  尝试**即缺位，用户确认 10-08 晚未手动做任何任务、App 未更新 → 属"当天无
  日记内容、服务端不生成提示"，非读过、非遮挡、非版本变更。
- 处置（用户指令 2026-10-09："没有提示就不做，不用纠结"）：`d3b9006` 将
  diary 的 fail-closed 改为**无锚即 SKIPPED 终态放行**——有锚 → 照常全验证
  提交；无锚 + 当天已验证记录 → ALREADY_DONE（`de17f44` 分支保留）；无锚 +
  无记录 → SKIPPED，链路继续；非 manor 帧先 `ensure("manor")` 再判，防止串页
  误判成"无提示"。测试：fail-closed 用例替换为 SKIPPED 用例 + 串页路由用例
  （ruff clean，213 passed）。
- run `e81885`（第 11 跑）——**diary SKIPPED 放行首验通过**（13:49:36→38，2 秒
  终态，链路首次走通任务 3），随后死于 `^家庭$`：新上线**秋日美满全屏促销
  弹窗**自 13:49:10 首帧起全程在场——背景压暗（左边带灰度 34 对干净主页 172）、
  底部导航在暗层下仍可读 → 页面仍判 manor、弹窗文案不在任何规则 →
  `overlays=[]`，tap (627,3037) 落在弹窗全屏触摸层被吞，8 帧后置刷新全滞留
  manor 零转场；reward/bring_home/diary 三项 SKIPPED 均系弹窗下盲判（run 10
  11:12 干净帧已有同日真凭据，业务终态不受污染）。修复 `a0d86f6`：
  `costume_promo` overlay——文案门（秋日美满|主题装扮来[拉啦]|去抽装扮）+
  dim<140 物理门 + Hough 扫 .62-.86h band（真帧命中 ✕ (720,2450) r47 正中），
  dismiss 走圈关闭绝不 Back；+2 fixture（弹窗帧/干净帧）+3 测试（216 passed）。
- 午后 WorkBuddy 接手（14:28-16:59 共 14 跑）：`e8f6d81` reward 比对收窄到
  `REWARD_CARD` 行（页面漂浮"请客吃饭啦"横幅致重复点击 STALE）、`3a6b3ff`
  首页券卡压暗丢签名时允许 page UNKNOWN 并在圈验证后恢复 alipay；
  **大号当日终态 19 SUCCESS + 4 SKIPPED + 1 ALREADY_DONE 全绿（0 FAILED）**——
  manor 段 `75b3a0` 单跑 24 项走完（19+5），森林段 `forest.self` 两败
  （return 后置 UNKNOWN、前台被切）后由 `e5dbe4`（debug --module forest）补完。
- 小号接入：`50566f4` 进度命名空间 `<serial>#<account>`（run lock 仍锁裸
  serial，双号永不并驱）+ `config/config.xiao.toml`（account=xiao、
  forest_owner=小布）；分身 = Android user 999 同包名双实例，分身前台时
  package 判据同名、链路不重复拉起。15:41-16:59 十跑完成 20 项
  （7 SUCCESS + 9 ALREADY_DONE + 3 SKIPPED）：踩坑修复 `daf773b`（打赏行
  去掉图章数字比对）、`c9f40c3`（成就解锁弹窗圈关闭）、`8f86465`（来日再试
  pill 明/朋 OCR 变体）；farm 淘宝绑定落地页（run `9282ac`，小号芭芭农场开在
  "去绑定淘宝账号"页、page UNKNOWN）修复 `0c2af17`（落地页视为打开完成 +
  卡片可领即 already，测试绿、设备验证排 10-10 小号跑）。
- 当日 DB 终态：大号 24/24 全绿；小号 20 项全绿 + forest.self FAILED
  （USB 掉线 device not found，16:59——设备断连非业务失败），森林 5 项未执行。

## 2026-10-08：版本更新弹窗与红日记本缺位（隔周续跑）

- 背景：09-30 后隔周续跑（10-01~10-07 账号零活动）。当日两跑 + 两项修复落码
  （`5947b04` 丰收礼包、`d1891aa` 版本更新弹窗）。
- run `1ed031`（第 8 跑）——启动 3 帧即死 `^蚂蚁庄园$: found 0`：隔周冷启弹出
  **原生"版本更新"弹窗**（支付宝最新尝鲜版，CTA `立即更新`），卡片盖住首页
  图标带，把标签裁成 庄园/芭芭/市民（"蚂蚁"半边入卡），页面仍按暴露头部判
  alipay、无 overlay 规则认领 → 三帧全灭，run 死于第一个任务。取证（帧
  0003/0002）：✕ 实测中心 (1183,1138)、**无环**（HoughCircles 在同窗只返回
  卡片自身圆角弧）；dim 带 82.5 对干净帧 172.5 → home_promo 的文本+dim 双门控
  同帧满足、仅圈扫描落空。修复 `d1891aa`：`app_update` overlay——门控
  `版本更新`+`支付宝最新尝鲜版`，以 OCR 标题 `版本更新` [564,1562,872,1640]
  中心 +（+465,−463）锚定 ✕（±60 盒，source=vision.ocr_anchor，pixel_guard
  默认 28）；recovery 分支把 `app_update` 排在 `home_promo` **之前**（关弹窗
  即去遮罩、反而解除其 dim 门控），绝不点 `立即更新`、绝不 Back；测试 +3
  （208 passed）。规则前置于 home_promo 扫描，同帧分类实测 `overlays ==
  ["app_update"]`。
- run `133fc5`（第 9 跑）——**`close-app-update` 真机首验通过**（20:56:10
  intent → 20:56:14 verified，随后 `^蚂蚁庄园$` verified），链路续行：
  `close-home-promo` 第 2 次真机闭环（关后回首页，券卡再次现身即关、再次进
  庄）、reward_friends SKIPPED、bring_home SUCCESS（`马上去找` →
  `bring-chicken-home` verified）。死于 `manor.home.diary`：**红日记本首个
  尝试即缺位**——20:57 首帧、21:05 复查均无（小鸡在家、非遮挡；与 09-30
  首跑帧 diff 庄园结构无变更，仅内容态差异），用户确认当日未手动做过贴贴
  小鸡 → 属服务端未生成。`de17f44` 的 fail-closed 如设计生效（无当天验证
  记录 → 首次尝试必须失败），非代码缺陷，不做改动。
- 机制推测（未验证）：09-28/09-29/09-30 连续活动、三日红本均在；本周零活动 →
  10-08 红本未生成。若成立，10-09 晨恢复。
- 当日终态（DB day=2026-10-08）：reward_friends SKIPPED（第 8 跑的 FAILED
  已被第 9 跑翻转）、bring_home SUCCESS、diary FAILED。
- run `95ece9`（farm 单任务 debug 跑，21:21）——diary 阻断全链期间单独真机
  锻炼 farm 尾段，死于 `drawer-close`，**点 X 的 tap 其实成功**（:54 抽屉关、
  落 farm 主页），三连碰撞杀掉了 postcondition：
  ① 本周主页新增底栏 `做任务集肥料`（[535,3053,908,3117]，.95h；抽屉标题
  在 .34h，列表只向上滚）撞上纯文本 `farm_tasks` 页规则 → 关后主页被判回
  `farm_tasks`，`page=="farm"` 永不真；
  ② 主页持久卡 `参与施肥挑战赢大额奖励`（新事件卡）命中 reward 规则的
  `施肥挑战` 臂 → 无 CTA → else 分支按 Back → **容器出栈落 feed**（帧
  0037→0038，动作名 `return`——`back_observation` 固定名，链路定论）；
  ③ 单修页判不够：`^施肥$` 的 before 帧仍带 reward → 还是 else-Back 出栈。
  同跑真机闭环：`close-farm-promo`（礼遇卡圈关闭）、farm-jump、claims 两行
  缺席（optional 正常跳过）。修复 `ba91630`：classify 位置修正（底栏独占 →
  回判 farm）+ reward 在 farm/farm_tasks 上无 `开心收下|我知道啦|
  去蚂蚁森林收能量` 即不分类（卡片/toast 是内容非弹窗；施肥挑战弹窗走 L352
  文本直关不依赖 overlay；spec L67 森林互推弹窗保留 else-Back 模态关闭），
  测试 +4（212 passed）。
- farm 第 2 跑因用户用机 + 支付宝后台被杀顺延至 10-09。

## 2026-09-30：抽奖第四拼写与丰收礼包 Back 出栈

- 全天两跑均止于庄园链（森林链未执行），根因同属**产品弹窗的关闭拼写/方式
  未跟上**：`573250` 的修复当日落码（`0183523`），`f427d5` 的修复 10-08
  落码（`5947b04`）。09-30 终态 **3 SUCCESS + 7 ALREADY_DONE + 2 SKIPPED +
  1 FAILED**（farm）。
- run `573250`（第 6 跑）——`manor.feed.lottery` FAILED：立即抽奖抽中
  "恭喜抽中 6件奖品 永久套装"，结果视图 CTA 换成 `穿上装扮`——继 开心收下
  （spec L56/L63）→ 做任务继续抽（09-23）→ 我知道了（09-24 装扮奖品）之后
  的**第四种拼写**——三词锚 found 0 ×3 帧。修复 `0183523`：锚点加第四种
  拼写（后置谓词不变），测试 `test_result_view_close_takes_the_suit_cta_
  spelling`（201 passed）。本轮 10 任务完成，diary 首跑走**正常路径**
  SUCCESS（新未读红本 + `diary-entry` 锚点探测——`de17f44` 的正常分支）。
- run `f427d5`（第 7 跑，12/13）——`manor.feed.farm` FAILED：三项真机首验
  成功后死在丰收礼包**已领取**态的 `back(("farm",))`：一次 Back 关掉整个
  芭芭农场容器落 feed（抽屉 Back 同构，09-27/09-29/09-30 第三次同证），
  8 次 return 轮询饿死。首验成功 = `close-home-promo`（dim 门控闭环）、
  `drawer-close`（抽屉 X，`0731575` 首次真机走通）、`^施肥$` 施肥动作
  （意图+验证走通，施肥尾段首次真机执行）+ 立即领肥 + 丰收礼包立即领取。
- 丰收礼包取证：待领取/已领取两态帧 `0157`/`0158` 的 ✕ 同位
  (0.50w, 0.726h) r≈56、HoughCircles 唯一命中（同 run 干净 farm 帧 8/8
  零命中）；OCR 对同一弹窗 0155 读"丰"、0157 读"半"→ 门控 `[半丰]收礼包`；
  dim 带与干净帧重叠（50-126）故不作物理门控。修复 `5947b04`：`farm_gift`
  overlay 圈检测 + recovery 关闭分支 + claim 骑 `overlay=True`（session.tap
  见 overlay 先关会丢目标）+ `dismiss(s, s.obs)` 替代 Back（spec L67
  "点击 X 关闭丰收礼包页面"），测试 +4（205 passed）。
- 调度侧记：run 7 中 diary/lottery 以 ALREADY_DONE 短路——diary 走的正是
  `de17f44` 的**锚缺失 + 当天页面验证记录**分支（run 6 读掉红本后二跑无锚），
  lottery 是 run 6 已消耗当日机会——均页面证据短路的设计行为。

## 2026-09-29：五连败的帧级根因与五项修复

- 全天终态：**8 SUCCESS + 2 ALREADY_DONE + 2 SKIPPED + 1 FAILED**（diary，
  修复在其后提交、设备断连前未复跑），森林链两度被阻未执行。五次 daily
  失败的根因全部定位并落码（`dev` 分支，门禁 ruff clean + 200 passed）：
- run `b8d5e5`——**高版弹窗 crop 未覆盖**：09-29 版"广州生活卡"弹窗 CTA ✕
  圈落在 y=.85h，扫带止于 .60h → found 0。修复 `d81fc74`：扫带扩至 .90h +
  选圈判据"水平居中(≤.07w)中取 y 最大"，fixture `home_promo_0929.jpg`。
- run `4374cb`——**banner 文案污染门控**：tap#1 已关弹窗，主页自身 banner
  命中文本门控 → 第二轮假圈 tap → 页面点坏 → Back 退出支付宝 → 9 次
  return 轮询 TIMEOUT。修复 `92d0759`：backdrop dim 物理门控（弹窗帧条带
  灰度≈64-66、干净主页≈220、阈值 140），fixture `home_clean_banner_0929.jpg`。
- run `184e67`——**频道页遗留饿死 launch**：上轮 Back 退 app 后进程存活，
  relaunch 恢复闪购外卖频道页（三词规则外）→ `wait(page!=UNKNOWN)` 饿死，
  而 09-23 起注释承诺的 fall-through 只覆盖 recognize 分支。修复 `cb37b0f`：
  launch 等待超时同路径落入路由循环 back 兜底。
- run `5742c4`——**farm 抽屉 Back 出栈**：冷启动弹窗闭环首次真机走通
  （close-home-promo intent+verified），13 任务 12 完成；farm 领完肥料后
  `back(("farm",))` 一次 Back 直接退出芭芭农场容器落 feed（09-27 `80393d`
  同证），后置饿死。spec L67 明示抽屉应"点击右上角 X 关闭"。修复
  `0731575`：X 圆钮锚定（标题 bounds 23 帧稳定 [533,1085,906,1150] +
  中心偏移 (+535,−28)、r≈57），`drawer-close` 替代 Back。
- 单任务 `32ef49`——farm 走 **ALREADY_DONE 短路**：5742c4 的抽屉领肥料
  （fertilizer-claim VERIFIED）+ 逛一逛已让服务端把卡片翻成"领取"
  （spec L68 验证方式），当日施肥尾段未执行（单测覆盖，待 09-30 链首跑）。
- run `97e388`——**日记入口随读取消失**：09:31 读掉未读后，红日记本浮标
  从 manor 消失（四帧零 `小鸡日记`，对照 0016 帧 bounds 处已空），调度的
  always-reprobe 二跑 found 0。修复 `de17f44`：锚缺失 + `verified_status`
  当天页面验证记录 → ALREADY_DONE；无记录则保持 fail-closed。
- 调度确认：TaskManager 每次全量重探（"previous successful record never
  authorizes skipping page probing"），任务由页面证据短路——reward_friends/
  bring_home 二跑按页面证据落 SKIPPED 属设计行为。
- 期间 USB 转发断连（Windows PnP 全 Unknown），09-30 恢复后续跑。
- 待 09-30：launch fall-through、dim 门控闭环、farm 抽屉 X 与施肥尾段、
  diary 正常/跳过两分支、森林链的真机锻炼。

## 2026-09-28：四失败复跑收口与彩票悬挂对账

- 全天终态：08:56-09:42 链 24 项初值 **15 SUCCESS + 5 SKIPPED + 4 FAILED**
  （donate_egg/farm/kitchen/friends），复跑后终值 **16 SUCCESS +
  3 ALREADY_DONE + 5 SKIPPED + 0 FAILED**。CLI JSON 的 SUCCESS 只表流程走完，
  真值一律读 `runtime/task_state.db`（本轮 donate/farm/kitchen 复跑 CLI 报
  SUCCESS、DB 实为 ALREADY_DONE 再次印证）。
- 09-27 修复真机生效：member 落点路由（`manor.feed.member` SUCCESS）、rain
  候选遍历（`forest.rain` SUCCESS）、diary 书服务端状态回归（SUCCESS）、
  farm 欢迎卡 reward 守卫与 kitchen 模态分类——后两项把失败推进到流程更深处
  才暴露出本轮新根因。
- `manor.family.donate_egg` FAILED `d1da54`——**Back 出发帧瞬时 UNKNOWN**：
  捐赠后回读详情页重渲染中途（0022 donate_detail → 0023 UNKNOWN），ensure
  parents 的 Back 谓词拒绝按压。修复 = 该 Back `allow_unknown=True`（谓词仍
  排除落点 UNKNOWN，非破坏导航与 UNKNOWN 分支同立场）。复跑 ALREADY_DONE
  （入口对账放行），逻辑由 `test_ensure_navigation` 覆盖，待 09-29 链锻炼。
- `manor.feed.farm` FAILED `77dae5`——两根因：① 抽屉轮播横幅每帧改写签名，
  no_progress 永不到 2，滚动预算在循环头耗尽却硬抛（行真缺席与两条已确认
  路径同判）→ `row()` 预算耗尽尊重 `required=False`；② 欢迎卡倒计时自动
  签到（签到领肥 3s→1s），抽屉签到条渲染 已领取、**每日签到行整行缺席**（34
  帧零出现），而原认领谓词 `has("已领取")` 被常驻已领取架空 → 领取顺序改为
  肥料行先行 + 每日签到 `required=False` + 认领谓词改药丸消失（±20px 配对）。
  复跑 ALREADY_DONE；`fertilizer-claim`/`fertilization` 在全部 284 个历史日志
  零命中——抽屉领取+施肥序列从未走通，待 09-29 链验证。
- `manor.feed.kitchen` FAILED `b2acc0`——**cook-back 整页落 feed**：一次 Back
  从结果模态直接退出 H5 到 feed（0029 模态在屏 → 0030 page=feed），模态专用
  谓词在它自己产生的落点上饿死。修复 = 后置谓词放宽 `kitchen|feed`、循环内
  非 kitchen 时经 feed 行重进（`kitchen-reopen`，行已领取/已完成则收口）、
  末尾 `page != "feed"` 才按 Back（防止在已满足目标上二次 Back 退出整个应用）。
  复跑 ALREADY_DONE，单测覆盖，待 09-29 链锻炼。
- `forest.friends` 三根因链，复跑 `1a0a44` FAILED → `cd89c9` **SUCCESS**：
  - **签后分类缺口**（84c8a6）：签到一刷新移除 每日签到 卡与其按钮，面板仅剩
    市集行标题与翻转的机会徽标——group2 旧锚全失，后置在已成功的签到上饿死。
    修复 = 锚追加 `森林市集|还有\d+次机会`（tap 前后帧均携带）。
  - **lottery-sign 悬挂**（84c8a6 → fc7b38）：签到实际生效但后置星帧读
    RESULT_UNKNOWN，fc7b38 首个 spend（lottery-ad-claim）被 intent 守卫拒。
    修复 = sign 循环入口对账：卡已消费 ⇒ VERIFIED、卡仍在供给 ⇒ CANCELLED
    重签——与 kitchen 领食材、兑换确认同构的状态锚定对账。
  - **lottery-ad-claim 后置饿死**（1a0a44）：claim 实际生效（0019→0020
    还有1次→2次机会、领取药丸消失），但当期面板不再弹 领取成功 toast（六次
    采样零命中）、标题 (N/2) 只计浏览数不随 claim 变——两个旧替代证据全空，
    历史 VERIFIED（bd69ed/59771b）靠的正是已不渲染的 toast。修复 = 药丸从
    配对 title_y+35 槽位消失（±20px，0018 帧 2450→2485 实测）作为完成证据 +
    入口 ad-claim 对账（药丸仍在 ⇒ CANCELLED 重领）。
  - `cd89c9` 全程取证：入口对账放行 → 广告浏览 + **lottery-ad-claim 首次真机
    VERIFIED** → 右/左双侧面板 44 帧全部正确分类、签到与两侧抽奖、结果视图
    关闭逐项 verified → DB SUCCESS、当日悬挂清零。
- 复跑中 donate/farm/kitchen 走 ALREADY_DONE：入口 already 分支不点行
  「领取」即收口——对照 spec L21「领饲料任务仅需完成任务，不需要领取完成任务
  后的奖励」，属规格既定设计而非漏领。
- 帧回放回归：`classify_scan.py` 双进程重建 5774 帧重分类，仅 25 帧变化、
  全部 `UNKNOWN → lottery`、既有识别页零抢页，抽查均为真实抽奖面板。
- 门禁：ruff clean，**184 passed**（+11：row 预算 ×2、农场缺席签到、厨房
  feed 落点守卫、瞬时 UNKNOWN、签后面板分类、sign 对账 ×2、ad-claim 药丸
  谓词与对账 ×3）。
- 待 09-29：farm 抽屉领取+施肥段、kitchen 重开路径、donate Back 路由在全链
  中的真机锻炼（fertilizer-claim/fertilization 历史零命中）。

## 2026-09-27：五个失败的帧级根因与四项修复

- 全天终态（12:15-13:17 链）：**17 SUCCESS** + 2 SKIPPED（reward_friends 条件
  缺席、bring_home 鸡在家）+ 5 FAILED（diary/farm/kitchen/member/rain），退出码
  只表终止、真值读 `runtime/task_state.db`。
- `manor.feed.farm` `80393d` FAILED——**欢迎卡标签行的 reward 误报**：入场欢迎卡
  （欢迎来到芭芭农场/2100肥料待领取/签到领肥 CTA/×）标签行 OCR 合并成
  `明日肥料获得奖励每日签到`，命中 reward 规则 → overlays=[reward] → ex.wait
  中断处理进 dismiss()，其 reward 支找不到 开心收下|我知道啦 锚、落到 **Back**，
  0012 帧 12:37:46（倒计时归零、自动跳转前 1 秒）被打出农场回 feed，
  `farm-jump` 等待在 page=feed 上饿死。9d8f76（09-25）对照帧证明跳转本就在
  欢迎卡仍屏时触发——卡是自管理状态，不是可解散奖励。修复 = classify 对含
  `欢迎来到芭芭农场` 的帧跳过 reward；表象是误报，根治在分类层而非 Back 兜底。
- `manor.feed.kitchen` `a520fb` FAILED——**结果模态帧分类饿死**：烹饪已成功
  （橄榄烤彩椒制作成功/厨余生成了58肥料/新解锁+1），但新 pity 横幅
  （5次内必解锁一道新的美食哦）挤掉 普通美食、领取行 OCR 成无今日的 领食材、
  店铺按钮被遮——group1 三锚全失，唯一幸存是事件头 秋食风味录 →
  page=UNKNOWN → `s.back` 前置校验拒绝 `Cannot act on unknown page`，做完了
  关不掉。修复 = kitchen group1 追加 秋食风味录（09-24..27 全帧扫描仅厨房与
  厨房模态帧携带：76 kitchen + 36 模态、零外部页面）。
- `manor.feed.member` `e7673b` FAILED——**返回落点栈深与昨日不同**：广告任务
  中心签到成功后一次 Back 落在支付宝会员首页（小组件推广层 领积分兑好礼更方便/
  添加会员小组件到桌面/待领积分），该页无分类 → page=UNKNOWN，`("feed",)` 落点
  等待饿死。09-26 `0a42ca` 同一步一次 Back 直达 feed（栈里没有会员首页层）。
  修复三件套：classify 新增 member 规则（group1 待领积分|领积分兑好礼|
  添加会员小组件，group2 会员|积分）+ `parents["member"]="feed"` 入路由表 +
  browse 返回收 `("feed","member")`、非 feed 时 `ensure("feed")` 兜底走规范
  路由。首版锚含 会员中心，在帧回放中暴露 699443 森林任务行
  `逛支付宝会员中心` 子串假阳 10 帧——移除该锚后归零。
- `forest.rain` `c59b7f` FAILED——**同文按钮的死点抽奖**：礼物面板三个同文
  送TA机会（手型指引贴最左、OCR 成 送T 不入选择集），min-by-(y,x) 选中中间
  (655,1807) 死等 40s；09-26 `06fb5b` 选右侧 (936,1807) 应答成功。两日中/右
  按钮像素均值完全一致（[87.7,203.3,145.9]/[87.9,203.3,146]），非置灰——朋友
  列表每日轮换，任一按钮都可能是死点。修复 = 候选遍历（右按钮优先，证据即
  右侧曾应答）+ 超时对账（面板仍供给 affordance ⇒ 提交从未生效 CANCELLED，
  换下一按钮；面板已关 ⇒ 慢成功放行）+ 全部死点 fail-closed 重抛 TIMEOUT。
- `manor.home.diary` `854b77` FAILED、`7b5156` 13:33 复跑仍 FAILED：4 帧模板分
  全背景级（0.548-0.572）、60s×20 高频采样无闪现——书服务端状态缺席（延续
  09-26 假说，非采样漏）。
- 修复验证 = **HEAD vs 工作区隔离回放 4010 帧**（09-24..27 真机帧重建
  Observation 重分类）：UNKNOWN→kitchen 30、UNKNOWN→member 11（全部真会员首页）、
  0 抢页（既有识别页零漂移）、reward 摘除恰 2 帧（9d8f76/0014、80393d/0012，
  均为欢迎卡）——用历史全量帧当回归集，比单测更早揪出 会员中心 假阳。
- 门禁：ruff clean，**173 passed**（+7：厨房模态/会员首页/森林行防假阳/欢迎卡
  reward、browse 会员落点、rain 候选回退 ×2）。
- 晚间基础设施：USB 掉线（usbipd 仅 persisted 无 Connected、WSL 只剩 root hub，
  15s 轮询不恢复）需手机侧重插；期间用户取走手机复还、支付宝进程被杀
  （monkey 注入无窗口，`am start -n com.eg.android.AlipayGphone/.AlipayLogin`
  恢复）——真机复跑顺延至 09-28。

## 2026-09-26：厨房真机结果模态、外出木牌双变体与日记本全帧取证

- 全天终态：**18 SUCCESS** + 3 ALREADY_DONE（sign/farm/kitchen）+ 2 SKIPPED
  （reward_friends 无打赏落账属条件语义；bring_home 的 SKIPPED 是缺陷，见下）+
  1 FAILED（diary）。
- `manor.home.bring_home` `6b3fa4` **SKIPPED 而鸡实际外出**：旧判定式
  `马上去找|小鸡外出` 不含雇主木牌 `小鸡出去工作啦`，入口漏检→落"确认在家"支、
  同式再漏检→以 SKIPPED 收场。修复三件套：`CHICKEN_OUT = 马上去找|小鸡外出|
  小鸡出去工作啦` 统一三处；CTA 缺失时改点木牌文本（130950 实测 (794,1739)
  直跳好友庄园）；好友页无指向手线索时回退 `own_chicken_label_target()`——
  y 带 .52-.65h 内取不以"的小鸡"结尾的标签（我的 不理鸡），标签中心 +75px =
  实测点击位，cx 窗口排除 .92w 的蚂蚁新村牌。13:11 人工带回家时先误点右侧
  客鸡给茵茵发了"提醒"，后按左槽标签带回家。test_roaming_chicken +2。
- `manor.feed.farm` `7d8d95` FAILED：自动跳转的"做任务集肥料"抽屉开约 2 拍后
  限时卡（领3000肥料/玩寻道大千砍树20次即得）全屏模态弹出，背景模糊抹掉抽屉
  头，帧仍凭导航标题分类 farm，`ensure("farm_tasks")` 无路回旋至预算尽。修复 =
  classify 新增 `farm_promo`（`page=farm ∧ 领\d+肥料` 文字门 + 62%-86% 高度带
  Hough 圆 + 期望位距 ≤ .07w），dismiss 加入 farm_promo **只走圆点绝不 Back**
  （抽屉仅自动跳转可达）；文字门保证入场欢迎卡（1100肥料待领取）永不误触。
  test_page_classification +2（含真机帧 farm_promo/farm_welcome 固定证据）、
  test_executor_recovery +1。`f250cf` 复跑 ALREADY_DONE。
- `manor.feed.kitchen` 六轮收官（`e480ea`→`4a78d9`→`6bafea`→`780c45`→
  `d6fba9`→`756696` **ALREADY_DONE**），四个独立根因：
  1. `e480ea` 撞近满食材确认框（食材快放不下啦/仅能装下50g + `^确认$`），
     postcond 等 not-has 饿死；其 RESULT_UNKNOWN 留存又让 `4a78d9` 被 intent
     守卫拒发首点。修复 = 入口 affordance 对账（领今日食材仍供给 ⇒ 当时提交
     未生效 CANCELLED；consumed ⇒ VERIFIED）+ 确认框支（锚 `^确认$`，同签到
     近满支）。做美食 stale 同入口解决：out-bubble 取消（before 帧记录点击时
     气泡）→ own-run proof（`_load_run_proof()` 按帧序取首个后帧匹配
     `制作成功|厨余生成|查看图鉴`，780c45 的提交以 after=0020-5016a6 VERIFIED）
     → 否则 fail-closed。
  2. `6bafea` 撞 300g 满袋 toast（食材袋放不下啦，使用后再领取吧）——按钮仍
     OCR 可见饿死 postcond。修复 = 接受 toast 为应答，置 shop_refused，两轮
     烹饪后按 toast 自己的建议重试一次领取，二次拒绝同样照单全收。
  3. `780c45` 根因：**真机不渲染 spec 的 美食图鉴 画廊**——点 做美食 直接出
     结果模态（金枪鱼海苔卷制作成功 + 厨余生成了60肥料 + 查看图鉴，帧 0031）。
     修复 = postcond 双收（`美食图鉴` or `制作成功|厨余生成|查看图鉴`）；back
     谓词同步排除模态——模态帧也分类 kitchen 且无 美食图鉴 文本，旧谓词会放行
     留着模态吞掉下一点。
  4. `d6fba9` 败 `Postcondition failed: launch; page=UNKNOWN`：14:11 静默唤醒
     未验证、屏已锁（末帧仅时钟），launch 只拉支付宝不解键盘锁。教训固化 =
     任务前 `WAKEUP → dismiss-keyguard → mWakefulness=Awake` 三步验证，并加
     `svc power stayon usb` 防跑批中段落锁。
  最终 `756696`：行已呈 领取（单次烹饪后，device truth > spec 两次演示），
  id=109 经 own-run proof VERIFIED、id=108 经 executor VERIFIED，全任务 0 未决；
  行 领取 不点（L21）。kitchen 部分实机全链走通。
- `manor.home.diary` 两轮 FAILED（`13f996` 鸡外出 / `61530c` 鸡在家），全帧取证：
  1. **书真不在**：真书模板（取 09-24 成功帧书像素）匹配成功日 1.000/0.937，
     当日 10:55/11:12/13:16/14:20×2/14:42 全 ≤ 0.58 背景级；松红全帧扫描
     （HSV S≥80）在预期位 [955,1665,1101,1740] 无候选；三时刻裁剪目视为空
     草地。11:12 与 09-25 21:26 的 vision 命中是**红心道具误检**（元素
     [1075,1937,1193,2035]，质心 y≈1986 贴 y 带 .62h=1984 边缘，滚动差 2px
     决定过门）——09-25 21:26 那轮点心无果、postcond 空转的败因即此。
  2. **书会十秒级闪现**：09-21 09:25 `662f0d` 0001 帧书在（模板 0.953 + 红点）
     且 vision 命中 `小鸡日记`，10 秒后 before 步 0002 无遮挡消失（0.543）→
     found 0 败；09:27 `3e9972` 复现并成功。
  3. **历史相关性**：鸡在家 ⇔ 书在（09-20/21/24 全部观测），鸡外出 ⇒ 书不在
     （09-25 ×3、09-26 10:55、09-24 10:44 带回前帧）；09-24 10:45 带回后
     10:46 书在，demo 视频同语义（t32 回家 → t34 书现）。
  4. **异常未解**：09-26 13:11 人工带回家（页面开着、与 09-24 同机制）后
     13:16 书未生成，此后全缺；用户确认未做贴贴，fail-closed FAILED 挂起。
     假说（未证）：书以"昨日日记条目"服务端生成为前提，09-25 全天外出/外宿
     可能无条目。09-27 12:16 复跑仍 4 帧全无、60s×20 高频采样无闪现（续诊）。
- 晚间 USB 掉线（usbipd 总线 1-2 消失、adb 空），次日重插 + detach/attach 恢复。
- 门禁：ruff clean，**166 passed**。

## 2026-09-25：日记本缺位、锁屏窗口与全天 24 项收官

- 当日首批：`faeeca` `manor.home.reward_friends` **SKIPPED**（区域内 0 个 `^打赏$`，
  absence-confirm 通过）；`8acd32` `manor.home.bring_home` **SKIPPED**（无
  `马上去找|小鸡外出`，chicken-home-confirm 通过）。两项均按 spec L8-9 的条件语义
  "无触发即无动作"落账，非失败。
- `b1d1a6` `manor.home.diary` 败 `Expected unique target 小鸡日记|^日记$: found 0`
  ——spec L10 日记本是**条件浮标**（"小鸡头上（右上方）出现一本红色的日记本"），今日
  17:12 两鸡上方无标、右侧栏仅 4 图标（更多/装扮/道具/小鸡乐园），历史 20/21/24 三次
  跑该浮标均在。用户确认**今日未手动做贴贴**；主页立着"小鸡出去工作啦"木牌，与
  "小鸡不在家 → 浮标无承载点"假设吻合（未实证）。`ensure("diary")` 的路由步即入口，
  无浮标既进不了页也无从区分"已完成"与"未触发"——挂起待浮标出现补跑，fail-closed
  可见。
- `77664d` `manor.family.donate_egg` 首败 `Postcondition failed: launch;
  page=UNKNOWN`——诊断间隙 ~9 分钟屏幕超时**落锁**，末帧仅大时钟 `17/22 +
  9月25日星期五`；`launch` 只重拉支付宝、不解键盘锁，15 次对锁屏刷新全 UNKNOWN。
  处置=`input keyevent 224` + `wm dismiss-keyguard` 人工唤醒，解后落回庄园主页 ✓；
  之后凡跑批前有空窗先醒屏。昨日未踩是因为空窗期用户正在用机。
- `0c01e7` `manor.family.donate_egg` 第 2 败 `Expected unique target
  [立三主]即签到|^攒亲密度$: found 0`——家庭页开屏促销层 **`家庭家具上新啦`**
  （09-20 未提交改动里写进 reward 叠层表的那串，当日三轮全 FAILED、从未验证过绿）：
  今日实测它是**全屏模态**（帧均值 88 vs 干净家庭帧 164，四条采样带 30 上下 vs
  130-170，卡片 y≈540-2440）。链路=检出 reward → 拒点签到 → `dismiss()` 的 reward
  分支只认 `开心收下|我知道啦` → 落 else 走 **Back 把家庭 H5 整页退出**（0005→0007
  回 manor）→ 阻塞步在错页找签到 → found 0 搁浅。修复=recovery 新增
  `dismiss-furniture` 分支：× 无 OCR 文本，锚卡内 OCR CTA `去看看` point +
  (-2,+293)（帧 0004：CTA (720,2372)，圈心 (718,2665) r≈41，与 farm 礼遇卡同款
  卡下居中几何），box ±90，后置 `removed_or_replaced("reward")`；锚缺失/歧义直接
  AMBIGUOUS fail-closed，绝不落回 Back。ruff 干净、pytest **130 passed**（新增
  关卡位断言 + 锚缺失 fail-closed 两条）。
- `821f2c` `manor.family.donate_egg` **SUCCESS**（第 3 轮）——但日志 0 命中
  `dismiss-furniture`：**模态第二次进入时未再出现**，绿来自缺席而非 × 路径；
  × 关闭分支**单测覆盖、实机待下次模态自然复现时验证**（fail-closed：锚漂移会以
  OVERLAY 可见失败而非静默）。09-20 模态连续三轮在场 vs 今日二进即消，出现节律
  未知（疑似每会话/每日首进一次）。
- `manor.feed.sign` 三轮才绿（`7ecb00`→`e5bb6b`→`8d2ee5`），近满确认框的三个缺陷
  逐个暴露逐个修：
  1. `7ecb00` 败 `Postcondition failed: daily-sign; page=UNKNOWN`——60g 余量时领
     20g 签到弹**近满确认框**（`饲料袋快满了 / 现在饲料袋只能装下60g，确认领取吗？`
     + `去帮好友喂食`+`确认`，无"知道了"），文案不在 overflow 模式表 → 叠层不标、
     页面规则被 brush 字 `饲料千务` 打断 → page=UNKNOWN、overlays=[] → 后置干等
     12 帧超时。修复：overflow 模式加 `|饲料袋快满|只能装下`（7ecb00 实测文）。
  2. 硬拒分支旧键 `先消耗一些饲料|去帮好友喂食` 与近满框**按钮撞键**（今天也带
     `去帮好友喂食`）→ 会误入硬拒支去点不存在的"知道了"。修复：改键
     `先消耗一些饲料|^知道了$`（框体文案/自家按钮）。确认支同时补
     `allow_unknown`（对话框帧 UNKNOWN）+ `recover=False`（点击后残帧会撞
     dismiss 的 overflow 任务守卫直接抛错）。
  3. `e5bb6b` 败 `Expected unique target 确认|继续领取: found 2`——未锚定时框体
     正文（含"确认"子串）与按钮双双命中。修复：锚定 `^确认$|^继续领取$`
     （与家庭确认支 `^确认$` 同款）。
  中间人工清理：× 关闭对话框两轮（(1177,1215)，对话框自带 ×，关闭后签到条仍
  `第5天/领取` 未领），保证每轮验证走全链而非 already 支。最终 `8d2ee5`
  **SUCCESS**，日志 `daily-sign verified → ^确认$|^继续领取$ verified` 全链实机
  走通。pytest **132 passed**（+overflow 文案分类、近满支防撞键两条）。
- `manor.feed.video` 三轮才绿（`f4b926`→`184a5a`→`b4ac94`），两个独立根因：
  1. `f4b926` 败 `Cannot act on unknown page`——**广告完成视图竞态推进**：browse()
     收尾观测还是 `ad`（`浏览完成`），1s 内视图自动推进为 `任务已完成/看更多视频>`
     （无 ad 规则标记 → UNKNOWN），而 L197 的 `allow_unknown=instant or
     s.obs.page=="UNKNOWN"` 用的是**旧观测**算标志 → back 新观测已 UNKNOWN 被
     fail-closed 拒绝。修复：post-browse back **无条件 `allow_unknown=True`**
     （back 非破坏性、落点由 target 谓词守卫，与同函数 TIMER_MISSING 支 L185 同策
     略）；`shared.lottery` L70 同款隐患一并修。+成功路径竞态测试，pytest 133。
  2. `184a5a` 败 `Overlay requires task-specific handling`——**row 配对容差击穿**：
     视频行两行描述使 `领取` 按钮中心比标题中心低 **113.5px > .035×3200=112px**
     （仅差 1.5px）→ 列内配对 0 → 刷新×3 后落 **button-column 合成回退**
     （标题y+35=(1230,2006)）→ 文本 `看庄园小视频 [button-column]` 不匹配 L166 的
     `领取` 判断 → 走 browse-open **盲点进行内真认领药丸** → 领 90g 撞 1800g 满仓
     （quiz 领完 180g 后满）→ 弹 `饲料袋已满` 硬拒框 → browse 的 dismiss 守卫
     fail-closed。该行昨日也贴线摆动（.035 是阈值抖动区）。修复：
     `row_tolerance .035→.05`（160px）——观测最小行距 330px > 2×160，邻行按钮
     （±259/443px）仍唯一排除，未来双配对也只会 AMBIGUOUS 可见失败；+视频行几何
     红绿测试。人工清框（`知道了` (959,1883)）后第 3 轮 `b4ac94` **SUCCESS**：
     零 browse-open/零合成按钮，纯「真按钮配对 → 领取证据 → done」路径。
  顺带说明：video 注册 `claim=False`——`领取` 行即完成证据，任务本不要求点认领；
  满仓拒领对 claim=False 任务无感。pytest **134 passed**。
- `manor.feed.ip_lottery` 四轮才绿（`adde3c`→`b8fdaf`→`bb1540`→`b5628f`），三层根因：
  1. `adde3c` 败 `Postcondition failed: 确认兑换`——**无提示条变体**：点击正中
     确认按钮、兑换实际成功（`还剩4→6次`、行塌缩于第二抓帧 ~8s），但 IP 变体 6
     帧全程无 `领取成功|已兑换` 提示条，谓词只等它 → 超时。修复：谓词改「提示条
     **或**（行消失 + 次数可读）」，与 6b2c7c 行塌缩证据同标准；失败确认行仍在
     仍可见超时。+ 流程测试（0055 中间帧拒真、UNKNOWN 帧 page 守卫拒伪）→136。
  2. `b8fdaf` 败 `Unresolved submission '确认兑换' awaits evidence`——**悬置提交
     死锁**：attempt 1 超时的确认提交留 `RESULT_UNKNOWN`，`store.intent()` 对同
     任务一切新 intent 前置拦截；attempt 2 正确跳过已完成后项，死在**抽奖**
     intent。修复：换机会行 skip 分支用同标准证据**就地核销**该笔 `确认兑换`
     （其余悬置保持阻塞至 done()）。+ 复刻 intent 拦截的红绿测试 →137。
  3. `bb1540` 同错——**行并非塌缩而是渲染成 `(1/1)`**（0056-0060 消失是刷新瞬
     态；`每日签到(1/1)` 同款 = 面板稳定完成态，正是 row() 自认的完成标记），
     守卫 `not has("消耗饲料换机会")` 被 (1/1) 文本挡住。修复：守卫加
     「行带 (1/1) 计数」析取。+ (1/1) 测试 → **138 passed**。
  4. `b5628f` **SUCCESS**：核销 → 一键抽 6 次（`^[立三主]即抽奖$` VERIFIED）→
     `dismiss-reward` 关结果页 → back。谓词修复因分支已跳过为单测覆盖（下周期
     首跑实机），核销/抽奖/结果页全链本轮实机验证。**12/24**。`ruff` 干净。
- `manor.feed.market` `64944c` 与 `manor.feed.lottery` `c0f469` 均一次过
  **SUCCESS**（收口帧均见饲料任务列表 `已领取` 态）。
- `manor.feed.farm` 两轮落账（`9d8f76`→`f7d3b5`）：
  1. `9d8f76` 败 `Expected unique target ^施肥$: found 0`——**spec L67 自动跳转
     晚一拍**：进场帧 0012 农场主页 `施肥` 在 OCR，0013 过渡帧已消失，0014
     `做任务集肥料` 抽屉已开——旧码的 farm_tasks 即时检查跑在跳转前，
     ^施肥$ 的刷新循环又拒绝跨页动作。修复：`wait(page=="farm_tasks",
     "farm-jump")` 等 spec 保证的跳转 → 领抽屉两行（每日签到/蚂蚁庄园小鸡
     肥料）→ back → 家主页连施两次肥（`即领肥/丰收礼包` 链）→ `complete_row`。
     +`test_farm_flow.py` 时序红绿（先领后施、跳转等待）。
  2. `f7d3b5` **ALREADY_DONE**——第 1 轮进场已使命中的行转 `领取`（browse 即
     完成，spec「父卡可领即完成证据」），第 2 轮入口直判幂等；**跳转新流仅
     单测覆盖，实机待 fresh 入口**（次日首跑验证点）。
- `manor.feed.family` 两轮才绿（`8f3a63`→`3932e5`）：`8f3a63` 败
  `Required task missing after complete scan: 去家庭逛一逛`——活动期行标题
  改名 `家庭×阿福新活动上线`（分隔符 ×/入/X 在 OCR 间摆动），描述尾仍
  `去家庭还可获得90g饲料哦`，旧裸锚 16 次拖拽扫尽 0 命中。修复：注册表模式
  `去家庭逛一逛|家庭.{0,2}阿福新活动上线`（描述尾双保险不可命中）。
  `3932e5` **SUCCESS**：命中改名行 → browse 进 `欢乐全家桶` H5 → back →
  二段扫描取行完成证据 → done。+`test_family_row_pattern.py` 红绿。
- `manor.family.meal` `244530` **ALREADY_DONE**（入口按钮 `明天再来` 非就餐
  窗口，按终态幂等收口）；`manor.family.feed` `de4161` **SKIPPED**
  （`帮喂家人小鸡(0/1)` 旁 `暂无小鸡`，条件缺席 → absence 通过）。
- `manor.feed.kitchen` 六轮才落账（`697d65`→`d9fb5d`→`3496e7`→`295962`→
  `b28f55`→`88e545`），四层根因 + 诚实阻塞：
  1. `697d65` 败 `Postcondition failed: kitchen-open; page=UNKNOWN`——**活动期
     标题塌缩**：秋食风味录期间厨页 `小鸡厨房` 标题从 OCR 消失（kitchen-open
     后 6 帧稳定捕获标题槽空、页眉 `秋食风味录`），而 `做美食`/`领今日食材`/
     `爱心食材店` 均在。修复：kitchen 规则一组收 `小鸡厨房|爱心食材店|
     领今日食材` + `做美食|食材`。
  2. `d9fb5d` 败 `Postcondition failed: 爱心食材店; page=kitchen`——**子页被
     父页规则抢注**：献爱心得食材子页自带 `爱心食材店` 店头，kitchen 规则
     先匹配恒判 kitchen。修复：`ingredient_shop`（`献爱心`+`食材`）提到
     kitchen 之前（kitchen 主页永不含 `献爱心`）。+
     `test_page_classification.py` 两条。
  3. `3496e7` 败 `Postcondition failed: 做美食; page=kitchen`——**出走 toast
     竞态**：两笔领食材已 VERIFIED，cook 点击后 `小鸡不在家哦，等它回来`
     仅存活 2-3s < 4s 采集节律，后置帧只见家页超时。`295962` 随之把该 cook
     悬置为 `Unresolved submission ... awaits evidence`（intent 前置拦截
     fail-closed，形成死锁）。
  4. `b28f55` **SKIPPED**——修复=**帧锚定核销**：仅当悬置 cook 自己的
     before-frame（`store.pending_frames()` + `_load_frame_texts()` 锚
     `0032-b9750b`）含出走气泡才核销；实机出走态 → 跳过 cook；干净帧悬置
     保持阻塞；帧记录缺失不核销。+`test_kitchen_guard.py` 5 条红绿
     （57/58 VERIFIED、59 CANCELLED）。
  5. `88e545` 复跑 **SKIPPED**：21:25 证据帧 `0026` 出走气泡 `主人，我出去啦`
     在场、`明日可领食料` 证两笔已领——小鸡全天外出，cook 合法阻塞，
     待回窝补跑。
- `manor.feed.forest` 两轮落账（`7a53ce`→`05cf7e`）：`7a53ce` 败
  `Cannot confirm complete scan for 去蚂蚁森林逛一逛`——扫到底却缺**列表尾标**，
  无法区分「行缺席」与「没扫到底」，fail-closed。修复：`row()` 页脚标记补
  `完成任务后会获赠饲料`（末行之后的固定尾文）。`05cf7e` **SKIPPED**：全扫
  可确认 → 行真缺席 → absence-confirm 通过。+尾标红绿（test_list_scanning.py）。
- `manor.feed.sesame` 两轮才绿（`e22b56`→`ac3440`）：`e22b56` 败
  `Task completion not verified: 去芝麻攒粒攻略逛一逛`——**底摺行够不着**：
  行标题 y > 视高 .93，配对失败后既不滚动也进不了回退，refresh 空转到底。
  修复：`session.row()` 新增**底摺提升**——配对失败且标题在 y>.93 → 先
  `scroll()` 一次再重找重配，其后才走 refresh/回退。+
  `test_bottom_clipped_row_is_lifted_before_pairing` → **149 passed**；
  `ac3440` 实机 attempt 2 SUCCESS（`required-reward` 领取 VERIFIED）。
  `manor.feed.village` `95be9a`、`manor.feed.member` `347a58` 均一次过
  **SUCCESS**——可选×4 全落账。
- `forest.self` 两轮才绿（`41640d`→`dcef7e`）：`41640d` 败
  `Expected unique target ^蚂蚁森林$: found 0`——**首页推广弹窗遮挡**（不是
  图标轮换）：`广州生活卡/支付打车外卖组合券包/400` 卡片（x≈429-1041）正盖
  常用行中段，`蚂蚁森林`/`游戏中心`（x347-816）在其后，底部导航仍可读 →
  页面照常分类 alipay、`overlays=[]` → ensure 直接点入口 found 0（3 张刷新帧
  + 手工帧全带弹窗文案，OCR 看见了但没人把它标成 overlay）。修复：classify
  新增 `home_promo`——文本签名 `广州生活卡|组合券包` 门控 + HoughCircles 找
  卡下悬浮关闭圈（真帧稳定检出 (719,2198) r56，param2 35-60 不变；干净首页
  的圆形图标因文本门在前绝不误触发）；dismiss 关闭圈分支收编该类型（首页按
  Back 会退出 app，绝不落回）。fixture `home_promo.jpg` +3 测试 →
  **152 passed**。`dcef7e` 实机全链：`close-home-promo` 点击 [719,2198]
  VERIFIED → 图标重现 → `^蚂蚁森林$` (440,1590) 入场 → 收能量幂等收口 SUCCESS。
- `forest.friends` `fb4564` **SUCCESS**；`forest.love` `0ea576` **SUCCESS**
  （真爱合种 100g）。
- `forest.cooperate` 两轮才绿（`d04112`→`1e67f2`）：`d04112` 败
  `Expected unique target ^合种$: found 2`——**同卡双字**：`合种` 卡面浮标
  `合种>`（[882,2569] y=.808）与卡下标签（[917,2625] y=.829）双双全匹配
  `^合种$`（真爱合种卡浮标仅 `真爱>` 故 love 无恙，现场目视帧复核）。修复：
  新增 `PLAZA_ENTRY=(0,.816,1,.845)` 标签行带——`has()` 滚动断点与 `tap()`
  region 同带收口（断点改等标签，顺带免疫底摺同款风险）。+同卡双字红绿
  （带内 find 唯一 + 走线断言 region 传参），两个旧夹具按真机几何修正 →
  **153 passed**；`1e67f2` 实机 SUCCESS（520g）。
- `forest.rain` `79cf1b` **SUCCESS**（`恭喜获得68g绿色能量` 证据）。
- `manor.home.diary` 边界补跑两轮仍挂（`31d07e`→`e45e84`）：`31d07e` 败
  `Postcondition failed: 小鸡日记|^日记$; page=manor`——**书闪现一帧死热点**：
  0012 帧真书 `小鸡日记 [1075,1936,1193,2034]` 被正中点到 (1134,1985)，其后
  8 帧书消页不开（出走日无日记承载，未实证）；`e45e84` 回到 `found 0`。
  两小时仅现一帧 → 维持挂起 FAILED（段首条已述）。
- `manor.home.bring_home` 19:48 复跑 `02d79c` 仍 **SKIPPED**——木牌
  `小鸡出去工作啦` 非条件词（`马上去找|小鸡外出`），条件语义二次确认。
- 中途 USB/IP 断连无感恢复：`PATH="$PATH:/mnt/c/Program Files/usbipd-win"` →
  `usbipd.exe list`（busid 可漂移，当日 1-2）→ `usbipd.exe attach --wsl
  --busid 1-2`，免插拔；repo 零串号硬编码保持不变。
- **收官：24 项全部落账**——SUCCESS 16（donate_egg/sign/quiz/video/market/
  lottery/ip_lottery/family/sesame/village/member/forest.self/friends/love/
  cooperate/rain）、ALREADY_DONE 2（family.meal/feed.farm）、SKIPPED 5
  （reward_friends/bring_home/family.feed/feed.forest/feed.kitchen，全为条件
  缺席）、FAILED 1（diary，条件浮标缺位挂起）。`ruff` 干净，pytest
  **153 passed**。

## 2026-09-24：数量带遇月历、动画 CTA 卫兵与 love 返回态后置

- `forest.love` 昨日败因（`20260923-121403`）：浇水实机已成功——面板 8×`+` →
  `攒能量` → 合种总量 42700→42800g（+100g），但后置锁死旧时代文案
  （`已为爱攒100g`/`成功…100g`/`获得奖励`弹窗一个都没出现）超时成
  `RESULT_UNKNOWN` id12，凭证据帧 `0035-9a49dd` reconcile；`unresolved()`
  按 day 过滤，跨天残留不阻塞今日。
- 新返回态后置 `_water_submitted`：面板收回（`为爱攒能量` 回归、`你当前有`
  消失）**且** 合种总量 ≥ 浇前基线+克数（总量升是 spend 唯一地面真值），
  基线读不到 fail-closed。`090517` 实机证实：基线 42900g、8×`+` 全过、
  提交后 `0037` 帧总量 **43000g** 面板收回。当日 `forest.self`
  （`081348`）、`forest.friends`（`085036`，空牌组直落 summary 零次跳）
  同日三绿，DB 未决 0。
- `085605` `Water quantity is ambiguous`：数量区 (.15,.4,.85,.95) 同时命中
  面板数量 `20`(y=.549) 与真爱合种页**月历日号 `12`**(y=.909)——日号位置随
  月历排版逐日漂移，前一日恰在区外。数量带收窄 `QUANTITY_REGION=(.15,.4,.85,.72)`
  （数量/`+`/确认按钮全在内，月历自 .765 起排除），`+` 后置同带，否则 9 月
  日历的 `30` 会把未跳数的点击误判成功（`test_water_quantity_band_excludes_the_calendar_days`）。
- `081743` `Target changed since observation`：开奖结果页 `做任务继续抽` CTA
  自带动画（裁片区 mean absdiff 39.3 ≫ 阈值 28），像素卫兵首跳、重找后二次
  连败，第二次重试不在 try 内原样传出。重找已用新鲜帧 OCR 复核文字与位置
  → `validate/tap` 增 `pixel_guard` 开关，两处 STALE-retry 重试点关掉冗余
  diff（首跳语义不变，`test_stale_tap_retry` 三例）；该轮抽奖机会已耗尽，
  关闭点击的实机复证待下次抽奖。
- `084622` Back 的 `input keyevent 4` ADB 超时 20s：设备随即 `echo ok` 正常、
  超时按键迟到送达（下轮入口落回 alipay 主页可证），判瞬时连接抖动直接重跑；
  不加盲重试——超时按键可能已送达，补按会连退两级。
- `091908` `forest.cooperate` 假 `ALREADY_DONE`：幂等检查是帧级
  `刚刚|分钟前|今天|今日`，被页面固定标题 `今日排行）` 满足，而最新 feed 行
  实为 `昨天12:19` → 今日 520g 未浇却记已完成。feed 文本与时间戳是同行两
  元素，改行级绑定（同行 ≤.04×屏高，下一 feed 行在 ~.046 外被排除，
  `test_cooperate_completion_ignores_freshness_outside_the_feed_row`）；
  两表假记账清除（evidence 自带 `昨天12:19` 留档）。
- `090814` 广场入口卡横滑 no-op：旧滑带 (.85,.67,.2,.67) 压在**固定图标行**
  y=.67（滑动前后文本不变），卡片区实际在 y≈.81 → `PLAZA_SCROLL=(.85,.81,.2,.81)`
  （`test_cooperate_entry_drags_the_plaza_card_row_not_the_icon_row`）。
- `092325` rain 入口 5 滑找 0：卡面文案是 **`能量雨`**（spec L103 的
  “天天能量雨”是功能名、非卡面字），锚定改
  `RAIN_ENTRY="^(?:天天)?能量雨$"` 兼容两种拼法
  （`test_rain_entry_accepts_the_short_energy_rain_card_label`）。
- `093245` 确认钮 `found 2`：弹窗是**中部对话框**——确认 `浇水` 在
  (0.691,0.621)，主页右下角 `浇水` (0.865,0.969) 根本没被盖住，旧区
  (0,.6,1,1) 双命中。`QUANTITY_REGION` 更名 `WATER_DIALOG` 复用为整个确认
  弹窗带（数量 .537/`+` .550/确认钮 .621~.667 在内，主按钮与月历日号在外），
  `test_confirm_tap_picks_the_dialog_button_over_the_page_button`。
- `9002e4` cooperate 提交后置超时（实已浇成）：feed 是**两行轮播动态**——新
  owner 行整个等待窗内没轮到（可见戳全为 昨天/09-xx），时代 toast 是 `+520g`
  而非 `成功…520g`；唯一地面真值是总量 **101870→102390（+520）**、`暂不`
  消失且 `今天在本合种还能浇520g` 配额提示消失。`_water_submitted` 扩至
  cooperate 路径（弹窗 `暂不` 收回 **且** 总量 ≥ 基线+克数），基线 fail-closed
  两路共用（`if base <= amount`，`test_cooperate_water_submit_accepts_the_total_rise`）；
  `RESULT_UNKNOWN` id20 以 `0016-61c250` reconcile、tasks/verified_tasks 记
  `SUCCESS`、未决归 0。同轮入口帧显示 093245 遗留的残留弹窗由 Back 重规划自愈。
- `095330` rain 入口点击成功却后置超时 `page=UNKNOWN`：卡片开的是**闪屏页**
  ——大标题 `天天能量雨`、副题 `拯救绿色能量`、CTA OCR 成 `主即开启`（`立/主`
  已知混淆，spec L103 称该按钮"立即开始"），而 rain 规则第二组要
  `[立三主]即开始|送TA机会|…` 全不存在 → 规则落空。补
  `[立三主]即开[始启]|拯救.*能量`，`rain()` 开始守卫与 `play()` 开始锚点、
  gift 返回后置三处同改（`test_rain_splash_is_recognized_but_the_plaza_card_stays_forest`
  双向断言：闪屏→rain、广场卡单独→forest）。该轮无 actions 残留（导航点击
  失败不留未决），免对账直接复跑。
- `100043` `forest.rain` **SUCCESS**：闪屏过后置 → 两轮游戏各 ~23.4s、
  1035/1036 视频帧、检出 4134/4238、实点 **155/148 次**，首轮 `送TA机会`
  spend 已 verify，末帧 `0015-5ab576` `恭喜获得 62g 绿色能量`。森林链当日
  self/friends/love/cooperate/rain **五绿**，未决 0。
- `100434` `manor.feed.sign` 入口点击 30s 无响应 `page=alipay`：支付宝首页
  处于 **`加载首页栏目` 楔死态**——页面渲染完整、时钟在走、输入焦点就在
  AlipayLogin 自身，但网格 `蚂蚁庄园` [1274,1326]（与 09-08 成功轮同坐标）、
  底部 `我的` 标签、手动补点 **三次全部无响应**；该标记全史仅见 085036 与
  本轮。栈顶 `hello.litiaotiao.app` 1×1 `NOT_TOUCHABLE` 无障碍锚点是红鲱鱼，
  `XRiverActivity` 焦点为事后 Back 才出现。`am force-stop` + 冷启重建后标记
  消失、同坐标点击立即开出 `page=manor`（`manor_ad` 同帧在位）。恢复手段=
  应用级重启；楔死态自动预检/自愈重启留作后续增强，先记档。
- `386e27` `manor.feed.sign` 二败 `Postcondition failed: return`：关掉广告层后
  叠出二层 `恭喜获得七日礼包` 弹窗（reward overlay），Back 关它时连整个 manor
  H5 一起退回首页；随后芭芭农场图标旁**瞬态角标 `领肥料`**（含"肥料"）把首页
  误判成 `farm`，ensure 按 `(farm,…)` 规划 Back、执行前帧虽已是 `alipay` 仍
  照发 → **退出到桌面**；桌面不在 PAGE_RULES → UNKNOWN →
  `page != start && != UNKNOWN` 永假超时。修复：**首页签名（扫一扫+收付款+
  我的——H5 子页绝不共有的三元组）提至 PAGE_RULES 首位**，任何图标角标都压
  不过首页身份（`test_home_signature_outranks_child_icon_badges` 双向断言：
  角标首页→alipay、真实 farm 页仍→farm）；冷启首页实机复验 `page=alipay`。
- `0ace75` `manor.feed.sign` 三败 `确认|继续领取: found 0`：入口/广告/签到条全
  过（首页签名修复实机生效：alipay→manor→feed→签到条→`领取` 点中），但仓库
  袋存已满 **1800g**，应用弹的是 spec L29 未覆盖的**零余量硬拒**——
  `饲料袋已满 / 先消耗一些饲料再来领取吧~`（`知道了` / `去帮好友喂食`），
  而非"领了会超→确认丢弃"框（那需要有余量），代码按 spec 找 `确认|继续领取`
  必然 0。袋值轨迹 1360g(09-20)→1765g(09-21)→满格（09-22/23 未跑 feed 阶段，
  手动领取堆满）。**解法=spec 顺序本身**：`主页-家庭-领饲料` 中
  `family.feed` 确认框原文 `将消耗180g饲料`（09-21 `f81adb` 真机 SUCCESS），
  家庭段先耗 180g→袋 1620→签到 +90→1710≤1800 连确认框都不弹；调试序改回
  spec 序逐任务推进。**代码兜底**：`sign()` 按 `先消耗一些饲料|去帮好友喂食`
  识别拒领变体→`知道了` 关框→`BLOCKED` 明确报错（fail-closed，不进好友列表
  摸喂食——行内无喂食钮、依赖好友小鸡挨饿，spec 未覆盖不保底，探路实证
  `去帮好友喂食`→"我的好友"列表）；overflow overlay 模式扩容
  `饲料袋[已巴]满|先消耗一些饲料`（刷新帧 OCR 将"已"读作"巴"，否则
  daily-sign 后置条件靠帧间骰子）。测试 +2=113 通过。
- `c47f25` `manor.family.donate_egg` 首败 `即签到|攒亲密度: found 2`：进家庭页
  底部 `主即签到` 按钮在位（0005 唯一命中），但 tap 前帧（0006）瞬态"暂不符合
  领奖条件"卡片冒出 `快攒亲密度昨天18:53`——子串 `攒亲密度` 与按钮 OCR 变体
  `三即签到` 双命中 → AMBIGUOUS（导航 find 阶段即抛，无动作行残留）。修复：
  route 锚点 `(family→family_tasks)` 中 `攒亲密度` 改**全串锚定** `^攒亲密度$`
  （`re.search` 语义下排除带前后缀的卡片文案），按钮保留宽松
  `[立三主]即签到`（容忍 主/三/立 OCR 漂移）。回归
  `test_family_route_ignores_the_encouragement_card_phrase`（真机 0006 坐标）。
  114 通过。
- `17b8ff` `manor.family.donate_egg` 二败 `Postcondition failed: first-project;
  page=UNKNOWN`：导航全通（route 修复实机生效：`即签到` 单命中进
  family_tasks ✓、`open-donation`→`donate_projects` ✓、项目行点中→详情页 ✓），
  但 `donate_detail` 规则是 demo 期产物（锚 `项目介绍|本期目标|我的约定 +
  立即捐蛋`），真机详情页四个标记**全没有**——实身为 `活动截止时间2026/10/25`、
  `筹集中`、`爱心值奖励` 标签栏、底部居中 **`去捐蛋`**（3 字，spec L14 写的
  "立即捐蛋"与 UI 不符）→ 详情页 classify 恒 UNKNOWN → 后置永假超时。修复：
  规则组1 换真机标记（组1 判别保证列表页不误入：列表是 `活动剩余时间/正在
  筹集第/焕新乐园`）、组2 与 L27 点击锚同补 `去捐蛋`（否则分类修好下轮必撞
  found 0）。`parents` 已含 `donate_detail→donate_projects→manor` 链，设备停
  详情页由 ensure 自行 Back 退出。测试 +2（detail-vs-list 分类 + 捐物流程
  全链 Fake 首覆盖，`re.fullmatch` 断言真机标签）=116 通过。
- `ed9ed9` `manor.family.donate_egg` 三败 `Task completion not verified`——**捐物
  流程本身全链真机打通**：退出重建（详情→列表→manor→家庭→签到重入）、
  `donate_detail` 分类 ✓、`去捐蛋` 锚进数量页 ✓、`/颗`+`5颗`+`当前有86颗` 一蛋
  校验 ✓、捐出成功页 `主人，你已成功向…捐出了/颗爱心蛋` ✓（`本周已捐 2→3 颗`
  真实生效）、ensure 长链 Back 重规划回 `family_tasks` ✓——**0044 帧
  `每日捐蛋做好事(1/1)` 已在位**。败于最后 `complete_row`：该行在列表最末
  （cy .988），OCR 只回标题不回侧边按钮 → `row()` 按 L289 的 (1/1) 保障以标题
  本身充当 button → `complete_row` 标记集只有 `领取|明天再来|已完成|已领取|点后`
  不含 (1/1) → 恒判未完成。修复：标记集补 `[（(]1/1[）)]`（与 row() 回退语义
  闭环——row() 返回锚点当 button 当且仅当标题含 (1/1)）。回归
  `test_complete_row_accepts_the_done_title_when_ocr_missed_the_side_button`
  （完成收绿 + 待办行仍 fail-closed 双向断言）。117 通过。
- `3b0d9e` `manor.family.meal` 首败 `Postcondition failed: ^确认$`——**请客动作
  真实成功**：0005 出 `请客成功`、行文案 0/3→**1/3**、按钮变 `16点后可来请客`
  （spec L17 的"11点后"随餐段浮动，真机为 16 点）。败因=`^确认$` 点后谓词
  `page==family_tasks and not o.has("美食")`——`prompt="美食"` 子串匹配，而列表
  行标题 `请家人吃一顿美食(1/3)` **本身含"美食"** → 关层回列表后谓词结构性永假
  （0006-0011 帧恒超时）。该分支 09-21 走了 already 从未真机执行。证据：弹层
  开着时 page 恒 `UNKNOWN`（标题 OCR 成 `已选4份美食...`，不中任何页规则与
  confirm overlay），故 `page==family_tasks` 单独即足以证明关层；feed 变体同形
  （f81adb：确认喂食框开着=UNKNOWN ✓）。修复=删除 `not o.has(prompt)` 半句
  （`complete_row` 在后段 fail-closed 复核）。回归
  `test_meal_confirm_survives_a_row_title_that_contains_the_prompt`（后置帧行
  标题含美食、旧谓词必红）。118 通过。
- `974051` `manor.family.feed` 首败 `Postcondition failed: family-feed`——业务
  **禁用态**：行右侧按钮槽渲染两行灰字 `暂无小鸡`(y2877)+`可喂`(y2940)
  ="暂无小鸡可喂"，此刻**无家人小鸡可喂**（挨饿周期未到/已被喂过）。二者均不在
  `TASK_BUTTON` 集 → row() 三次 row-refresh 无配对 → 列位兜底合成点
  [1230,2921] 落在禁用字上 → 空点，0005-0012 帧恒 family_tasks 超时。对比
  09-21 `f81adb`：同槽位可点 `去喂食` → `小布的小鸡喂食/将消耗180g饲料/确认`
  （当时可喂）。处理=同木牌类条件态思路：识别 `暂无小鸡` → `done(skipped=True)`
  诚实跳过（终端态链不停；(0/1) 本轮无法推进）。**连带影响**：−180g 解袋今日
  落空，袋仍 1800，sign 重跑将被拒领分支 BLOCKED 拦下——解袋改走 spec 自带的
  抽抽乐"消耗饲料换机会"（L51 每日子任务）路径（待标定）。回归
  `test_feed_skips_when_no_family_chicken_is_feedable`。119 通过。
- `64972f` `manor.family.feed` 重跑败于 `device '10AD4419NX0029Z' not found`——
  **基础设施断连**（非业务）：WSL `lsusb` 只剩 root hub，Windows PnP 里
  `vivo X90 Pro+`/`Android ADB Interface` 全 `Status=Unknown`（不在场），usbipd
  列表无 ADB 条目。恢复：手机侧重插（USB 用途=传输文件+解锁授权）→ usbipd
  **persisted 绑定自动 Attached**（busid 可漂移，1-2→3-1）→ `adb devices` 见
  `10AD4419NX0029Z`。诊断三板斧：`adb devices -l` → `lsusb` →
  `usbipd.exe list`（WSL interop 直达 `C:\Program Files\usbipd-win`）。
- `866f6a` `manor.family.feed` 三败 `Postcondition failed: ^蚂蚁庄园$;
  page=donate_detail`——入口链路本身正确（0001 支付宝首页 → 0002 点
  `^蚂蚁庄园$` [1274,1327] → 0003 加载），但**庄园首页被误分类成
  `donate_detail`**：首页新亮出的"第2间房 正在筹集中"卡片命中
  `donate_detail` group1 `筹集中` 子串 + 底部导航固定 `去捐蛋` 命中 group2 →
  抢在 `manor` 规则（L72，三组标记本帧全齐）之前匹配 → 入口后置谓词恒假超时。
  10:44-11:18 各轮入口正常 = 该筹款卡为午间新出现（或被请客+亲密度推进触发），
  0005-0010 帧稳定 OCR 到 → 确定性失败。修复=group1 摘除 `筹集中`，详情页留
  `活动截止时间|爱心值奖励|项目介绍|本期目标|我的约定` 五个专属标记兜底（17b8ff
  与全部既有测试帧均含其一）。回归
  `test_manor_home_is_not_misclassified_by_the_fundraising_card`。120 通过。
- `adb4b0` `manor.family.feed` **SUCCESS（真绿）**——分类修复后入口命中 `manor`
  正常进家；**小鸡恢复可喂**（重插后挨饿周期推进），走真实分支：`将消耗180g饲料`
  确认框 → 行 `(0/1)`→`(1/1)`，**袋 1800→1620g**。974051 条目里"解袋改走抽抽乐"
  的预案作废——原计划的 −180g 链路自动恢复：1620+90=1710 ≤ 1800，sign 头部空间
  就位；`暂无小鸡` 禁用态分支（119/120 两测）留作未来禁用轮的防护。
- `3b679e` `manor.feed.sign` **SUCCESS（真绿）**——袋 1620+90=1710 ≤ 1800 **直接
  领取**，全日志 `先消耗一些饲料|饲料袋已满|饲料袋巴满` 计数 0（拒领分支未触），
  09-21 的顺序解袋方案（feed −180g → sign +90）当日闭环，spec L29 超额确认层
  无需出场。7/15。
- `a8c506` `manor.feed.quiz` 首败 `Cannot identify exactly two quiz options`——
  入口/开页全通（0005 已在 `quiz` 页 `题目来源一答答星球`），挂在
  `quiz_options()`：该实现按 **HSV 饱和度 ≥35 的彩色轮廓**框按钮，今日
  答答星球主题把两选项渲染成**白底浅灰药丸**（饱和度≈0）→ 0 框恒败，而 OCR
  干净读到 `吸收热辐射`(y.59)/`反射热辐射`(y.68)。修复=**主路径改 OCR 文本带**
  （y(.42,.88) 居中带=题目下方、`题目来源` 脚注上方；容 `对/错` 单字判断题），
  彩色轮廓降为兜底（带≠2 且有图时），两者都非 2 则原样返回给调用方的
  exact-two fail-closed 守卫；`image is None` 时不再炸 cvtColor。回归
  `tests/test_quiz_options.py` 三例（白底帧/单字判断题/带内杂项透传）。123 通过。
- `add4f1` `manor.feed.quiz` 二败 `Postcondition failed: quiz-answer;
  page=UNKNOWN`——**OCR 带修复生效**（0009 选项定位 [719,1890]，点击已发出），
  答后解析页 `回答错误; + 解析 + 去领取饲料` 被拍全，谓词文本半边（`回答错误`
  子串）已命中，**只差页面半边**：解析页丢光 `庄园小课堂|题目来源|答答星球`
  三标记 → `quiz` 规则不中 → UNKNOWN 恒假。spec 核对：L34 验证=“弹出答案解析→
  返回后去答题按钮变**领取**”（不点解析页 `去领取饲料`、不点行内领取，现有
  `claim=False` 合规）；L35 答错也算完成（选 index 0 符合 spec“只选一个答案”）。
  修复=quiz 规则组1 补结果页专属标记 `回答错误|回答正确|去领取饲料`（后者正反
  结果兼有）。回归 `test_quiz_result_view_is_recognized_as_the_quiz_page`。
  124 通过。
- `d81a5a` `manor.feed.quiz` **SUCCESS（真绿）**——解析页分类生效，答题闭环，
  行按钮按 spec 停在 `领取`（claim=False 验证即止）。8/15。
- `19d92f` `manor.feed.video` 败 `Postcondition failed: browse-open;
  page=feed`——**双根因**：① attempt 0 视频实看满 15s 但右上角计时器 OCR 无字
  （帧里只有广告字幕 `视频肖像露出已获授`）→ `browse()` 抛 `TIMER_MISSING` 进
  重试；② **重试 L174 重新 row 了却没重查 `领取|已完成`**（该检查只在循环前做
  一次）→ attempt 1 把已翻 `领取` 的行当入口点 → **误领 90g（袋 1710→1800 封
  顶）、行从列表消失**（0021 起，两侧锚行原位=行真移除），`browse-open` 谓词要
  ad 页 → 恒 feed 超时。0014 帧 `看庄园小视频→领取` 已实机满足 spec L38 验证态
  → **经 `Store.task` 正规通道补记 SUCCESS**（run 挂 `19d92f`，evidence 注明
  手工账+误领事实；同日重跑会因行消失 fail-closed 属预期，次日列表刷新自然消
  失）。修复=重试重查后命中 `领取|已完成` 即 `complete_row` 直返，不再点；
  计时器 OCR 脆性留观（重试兜底已闭环，市场任务若复发再定点治）。回归
  `test_browse_retry_completes_instead_of_tapping_the_claim_button`
  （恰一次 tap 断言，未修复时第二次调用必红）。125 通过。9/15。
- `c29025` `manor.feed.market` **SUCCESS（真绿）**——滑动起计时 15s 流程一轮
  走通。10/15。
- `bc2b84` `manor.feed.lottery` 首败 `Ambiguous task identity
  ^(?!.*IP).*抽抽乐`——行身份歧义 fail-closed（row() 设计行为，防错点）：
  抽抽乐行**双文本**：主标题 `【抽抽乐】 丹桂秋光来啦`(cy .741) + 行左下角裸
  游戏 logo `抽抽乐`(cy .774, x112)，旧模式只锚"开头且无 IP"**无右界**→两串
  同中。修复=改**方括号右界** `^【?抽抽乐\s*】`（`\s*` 容 `【抽抽乐 】` 空格变体、
  容丢左括号；logo 无 `】` 必排除；`【IP` 开头自然不中，负向前瞻一并删），
  IP 侧镜像 `^【?IP抽抽乐\s*】`（旧子串模式同样会中 IP logo 双胞胎）。回归
  `tests/test_lottery_patterns.py` 从 `build_tasks().partial.args` 取真模式
  断言 7 正反例。126 通过。
- `9828af` `manor.feed.lottery` 二败 `Cannot act on unknown page`——主体全打完：
  开页 ✓、每日签到领取 ✓、**3 轮广告全看全领**（(0/3)→(3/3)，`还剩0→4次机会`，
  guess 弹层正确处置），挂在 0055 领后收尾：页面仍是抽抽乐（`装扮抽抽乐/还剩4次
  机会/立即抽奖/消耗饲料换机会` 同帧在），但 `lottery` 规则 group2 只认
  `每日签到|抽奖机会|去逛逛|杂货铺`——**签到卡领完消失、(3/3) 广告行收起**（与视频
  行移除同款行为）→ group2 全灭 → `UNKNOWN` → ensure 恒不认，恢复逻辑**从想留的
  页面上往外 back**，feed→UNKNOWN→farm 螺旋直到硬守卫拒盲退（386e27 教训正确兜
  底，fail-closed 无副作用）。修复=group2 补领后仍存活的页专属标记
  `消耗饲料换机会|还剩\d+次机会|装扮抽抽乐|做任务得机会`。回归
  `test_lottery_panel_after_the_ad_claims_still_classifies`。127 通过。
- `0ce9ab` `manor.feed.lottery` 三败 `Postcondition failed: return;
  page=UNKNOWN`——**入口即 UNKNOWN**：0001 帧实为支付宝首页、OCR 健康（59 元素，
  `收付款/我的/蚂蚁庄园` 全干净），唯独手写体皮肤把 `扫一扫` 读成 **`拉一拉`**
  （已容错的 `扫一拉` 之外的新变体），alipay 规则组1 `扫一扫|扫一拉` 三识别全不中
  → 组2/3 再干净也 UNKNOWN → 恢复逻辑连按 9 次 return **把支付宝退出到了手机桌面**
  （0014 = vivo 桌面，386e27 同类出栈隐患第二现）。修复=组1 补 `拉一拉` +
  **字体无关锚 `市民中心`**（首页网格常量字，未来任何手写变体都能兜住；另两组
  结构仍约束防误报）。人工 `am start .AlipayLogin` 把设备从桌面拉回支付宝。
  回归 `test_brush_font_home_survives_the_sweep_label_misread`（本帧变体 +
  扫一扫家族全缺两例）。128 通过。
- `6b2c7c` `manor.feed.lottery` 四败 `Expected unique target 做任务继续抽:
  found 0`——**主体再全绿**：新 alipay 规则入口 ✓、`【抽抽乐 】` 空格变体被
  `\s*` 接住 ✓、**兑换完成**（`确认兑换`→`抽奖机会领取成功`，还剩 4→**6 次**，袋
  −180g）、**抽奖完成**（`立即抽奖`→结果页 `恭喜抽中 6件奖品`，6 次全消耗）。卡在
  关结果页：**装扮中奖变体的 CTA 是 `我知道了` 而非 `做任务继续抽`**（0027-0031 恒
  定，refresh ×2 均 0 命中；森林侧 09-23 是做任务继续抽文案）。修复=①关闭目标与
  进入判定改双 CTA `做任务继续抽|我知道了`；②**兑换行同款消失容错**——`确认兑换`
  完成后兑换行收起（0024 实证，与签到条/广告行移除同款），`row(required=False)` +
  `button is not None` 守卫防 rerun 撞 `Required task missing`（attempt 5 必踩，提
  前治）。手动 `input tap` 关掉滞留结果页后第 5 轮重跑；CTA 修复当日路径因
  `还剩0次` 早退不经过，留待次日新鲜抽奖验证。128 通过。
- `cb4c6f` `manor.feed.lottery` **SUCCESS（真绿）**——5 轮收敛：兑换跳过 → 0 次
  早退 → 回 feed 验行（每日抽1次→`领取`）收绿。11/15。签到+广告×3+兑换+抽奖全
  部实机完成，袋 −180g（1800→1620）。**6 项修复**：logo 歧义/领后规则/入口手写
  体/CTA 双拼/兑换容错/…当日全数落地。
- `ffc3ae` `manor.feed.ip_lottery` 首败 `Required task missing after complete
  scan: ^【?IP抽抽乐\s*】`——**行在场，是 bc2b84 的修复误伤**：完整扫描 29 帧里
  有本期真实标题 `IP抽抽乐江苏文旅装扮`（**无方括号**）+ 左标签 `限定IP`（**非**
  裸 IP logo 双胞胎——抽抽乐侧的 `】` 判别假设不成立于 IP 侧）。IP 模式改
  `^【?IP抽抽乐`（前缀锚容未来括号变体与主题后缀，仍排除普通抽抽乐标题）。顺带
  预置**结果页第三变体**：spec L56/L63（视频 02:03/03:54）载 IP 页弹 `获得奖励`+
  `开心收下`，draw 判定 L113 早已收（`获得奖励|开心收下`在列）而关闭分支没收——
  L115 进入判定与 L120 关闭目标扩为三拼 `做任务继续抽|我知道了|开心收下`（+`获得
  奖励` 判定），防 attempt 2 撞 6b2c7c 同款关不掉。回归同步换实证断言（真实标
  题正例、`限定IP` 负例、跨行互斥负例）。128 通过。
- `10b0f5` `manor.feed.ip_lottery` 二败 `Cannot act on unknown page`——**主体
  全绿**：行 `IP抽抽乐江苏文旅装扮` 归局（模式修复 ✓）、IP 页正确归类 `lottery`
  （组1 `立即抽奖`+组2 `还剩0次机会`）、签到领 ✓、**广告×3 全看全领**（还剩
  0→4 次，(0/1)→(1/1)）。卡在**展开兑换层上的 `确认兑换`**：IP 页兑换层**遮住
  `立即抽奖`**（0064 无此字）→ 组1 必中项缺席 → `UNKNOWN` → 执行器守卫拒点
  （`code=UNKNOWN`）。主抽抽乐页当天展开时 `立即抽奖` 仍露（0020=lottery）故未暴
  露。修复=该点击加 `allow_unknown=True`——CTA 文本 OCR 验证 + 后置条件仍要求
  `page==lottery` 且 `领取成功|已兑换`，即 L120 结果页 run 115920 已实证的白名单
  语义（不改分类语义，面最小）。128 通过。
- `7798c6` `manor.feed.ip_lottery` 三败 `Cannot act on unknown page`——allow_unknown
  修复生效且**兑换真绿**（`确认兑换`→`抽奖机会领取成功`，还剩 4→**6 次**），**抽奖
  也真发**（0029 结果页 `恭喜抽中+开心收下+去兑换`，overlay 视觉判定 `reward` ✓）。
  卡在 `recovery.dismiss` 的 **reward 分支**：其 `dismiss-reward` 点击只传
  `overlay=True` 未传 `allow_unknown`，而结果层压暗使全部规则标记消失 →
  `page==UNKNOWN` → 执行器 validate L24 **派发前拒击**（intent 未出，与日志吻合）。
  6b2c7c 当时该层 vision 未判出 reward（overlays=[]）走 L120 路径才没暴露此处。
  修复=reward 分支补 `allow_unknown=True`（CTA 本帧 OCR 验证 + overlay 消失后置判
  定，与 shared.lottery 结果层 CTA 同白名单语义）。128 通过。
- `c0f8a8` `manor.feed.ip_lottery` **SUCCESS（真绿）**——4 轮收敛：入口
  `dismiss-reward` 关残留结果层 ✓，子任务幂等跳过（签到/广告×3/兑换均完成态、抽
  奖 `还剩0次` 早退），回行 `IP抽抽乐江苏文旅装扮→领取` 收绿。12/15。本期 IP
  （江苏文旅，9.7-10.5）全子任务实机完成：袋 −180g、抽奖 6 次全消耗。
- `e2c7d1` `manor.feed.farm` 首败 `Ambiguous task identity 芭芭农场`——行自身描述
  `和小鸡一起去芭芭农场逛一逛，完成即可` **完整内含标题串**，裸 `芭芭农场` 双命中
  （其他行 desc 均不含完整标题故未踩，与抽抽乐 logo 歧义同族）。修复=`row`/
  `complete_row` 同改锚 `^去芭芭农场`（标题首字"去"、desc 首字"和" → 单命中）。
  128 通过。
- `ae2e4d` `manor.feed.farm` 二败 `Expected unique target ^施肥$: found 0`——行锚
  修复 ✓（入农场、`farm` 归类正确），但开屏被**每日礼遇卡**挡住：`领1000肥料奖励/
  浏览精选好物15s即可得 + 领肥料 CTA`，× 无 OCR 文本、悬于**卡片正下方居中**；卡片
  盖住 `施肥`（3 次 refresh 找 0）。vision 未标该层为 overlay（`overlays=[]`），
  `dismiss()` 不介入；开屏时序 = 欢迎层（欢迎来到芭芭农场/签到领肥 3s 倒计时）→
  礼遇卡上滑，spec L65 的"自动跳转做任务集肥料"被压住。修复=`farm-open` 后、
  `farm_tasks` 分支**之前**内联关卡：OCR 标题锚定 ×（帧 0017 标题 [406,1638,
  1023,1724] 中心 (714,1681)、× 实测 (724,2400) r≈45 → 标题中心 +(+10,+719)，
  容差 ±90 方框 + pixel_guard），后置 = 卡消失且仍在 farm/farm_tasks；检测式
  `领\d+肥料奖励` 容数字变体。128 通过，待实机验证。

## 2026-09-22：蚂蚁森林收能量自校准至 +82g

- 当日 `forest.self` 三败一成（`logs/20260922-*.jsonl`）：
  - `092723` `Postcondition failed: swipe; page=forest`——主页滑动前后 OCR 文本
    完全一致（收好友/g被好友收 悬浮条不随滑动变化），滑动后置条件永不成立；
  - `093232` `Postcondition failed: return; page=alipay`——Back 落支付宝首页，
    与 09-21 同族问题在真机复发 → ensure 改为接受任何新识别非 UNKNOWN 页并重规划；
  - `094737` `No verified navigation from UNKNOWN to forest`——入口帧被
    `收付款`+能量通知横幅干扰识别为 UNKNOWN（`扫一扫` 还被读成 `扫一拉`）→
    ensure 增加包名匹配时的 recognize 等待（8s），仍不可读则 Back 出去重规划
    （`tests/test_ensure_navigation.py::test_ensure_survives_one_unrecognized_entry_frame`）。
- 同批真机标定的系统性 OCR 混淆（设备对花体/手写字的稳定误读）：`立→主`
  （`立即领取/立即签到` → 全仓统一 `[立三主]即*` 字符类，覆盖 PAGE_RULES、
  forest、manor、共享 lottery、energy_rain、campaign-modal）、`答←签`
  （能量签到 → 锚定 `能量[签答]到`）；森林广场入口卡与宝贝庄园页同名锚点
  分离（home-as-treasure），好友悬浮条不做结构性排除、右上累计徽标与
  `能量签到` 气泡按 09-21 策略隔离。
- `094932` SUCCESS：`forest.self` +82g（气泡 → `delayed-energy` 延迟等待 →
  能量签到 5g 独立路径全通），翌日 `083805` 复跑干净通过。

## 2026-09-23：好友遍历与抽奖链路 19 轮逐败修复

- 里程碑：`084117` 起 14 个好友页逐页 `一键收`+滑动遍历稳定通过；
  `103757` claim1 实机 `领取成功`、机会 1→2（"能立即领取的没领"修复首次实机证实）；
  `105813` 猜价格弹窗 `dismiss-guess` 实机命中。
- 入口/导航：
  - `083419` 遗留好友页 → `parents` 增 Back 出口（forest_friend/treasure/
    forest_summary/lottery 依次 Back，落点任意接受重规划）；
  - `083902`/`092726` 找能量入口 chevron 变体 → `FRIEND_ENTRY = "^找能量>?$"`；
  - `090232`/`090652` 灭屏导致 launch/swipe 全 UNKNOWN → 启动前解锁 +
    `svc power stayon true`；
  - `091751`/`091940`/`092242` deck 促销卡钉住 UNKNOWN 页 → ensure 的
    recognize-wait 超时后走 Back 分支、`allow_unknown` 白名单护栏
    （`Cannot act on unknown page` 不再放行盲点）；
  - `105813` 崩溃遗留广告页 `No verified navigation from ad to forest` →
    `parents` 增 `"ad": "lottery"`（广告完成运行均验证过 Back 可回）。
- 任务行与按钮：
  - `084117` 每日签到行多按钮不唯一 → `TASK_BUTTON` 白名单 `|^签到$|^已签到$`；
  - `095553`/`100224` 市集行 `去逛逛` 药丸视觉在、OCR 连续 5 帧全漏 →
    `row()` 三次重拍 + 几何兜底（按钮列 x≈1219、y=title cy+35，兄弟行钉列）；
    同期发现任务清单按周期轮换（去杂货铺⇄去森林市集）→ 侧别判别弃任务集假设，
    改用 `装扮` 橙色胶囊（mean(R-B)>40）定位当前激活侧；
  - `094953` 签到后整卡离场导致后置永假 → 署名后置接受"徽标翻转 + 卡片缺席"，
    入场即缺席视为已签（`lottery-sign` 的 RESULT_UNKNOWN 已凭证据帧 `0017-e501fb`
    手工 reconcile）；
  - `101245` claim 卡死后续 spend → `store.intent()` 报错指名卡点动作，
    只有 `reconcile()` 能解（防重复支出，不自动放宽）。
- 抽奖/弹窗/滑动：
  - 好友能量耗尽后 `找能量` 落**找能量汇总页**（新页 `forest_summary`）→
    `去抽奖` 直落**左侧**（仲夏活动侧）、宝箱 `立即抽奖` 落右侧（探针 3 连证实）→
    friends 流程改为右先抽完再 `装扮` 切左（`switch()` 橙胶囊验侧）；
  - `103229` 动画 chevron 被 OCR 成 `去抽奖>` 触发像素卫兵 STALE →
    `s.tap()` 换帧重找（同页同遮罩、位移 ≤10%）；
  - `103757`/`105105` 猜价格弹窗 `放弃奖励` 手写体 5/5 帧读成 `教弃奖励`、
    弹窗 3 滑零位移（不滚动）→ `[放教]弃奖励` 字符类 + 全漏时直点底部中央
    (0.496w, 0.878h)，后置"弹窗消失"兜底盲点；
  - 下滑频率（用户反馈"下滑频率太低"）：实测单帧捕获 2.7-4.0s，旧 `browse`
    每滑 3 帧 + 1s 死等 = **10.6s/滑** → 滑后帧直接喂下轮 overlay/完成检查、
    去掉死等与 before 重拍（复用帧仍在 12s 新鲜窗内，滑动不走元素像素比对），
    一滑一捕 ≈3.3s/滑（`tests/test_ad_browse.py`）；
  - `110428` 单好友栈收完再滑落汇总页，`_friend_advance`/`_deck_advance`
    不认 `forest_summary` 超时 → 两谓词都把汇总页作为遍历终态接受；
  - `111049` 右侧绘制实机成功（`恭喜抽中` + 66g/20g/10g、3 次一次耗尽，与
    规范"点一次弹结果页即完成"一致）但后置锁死旧时代 `获得奖励|开心收下`
    超时 → 扩 `恭喜抽中|做任务继续抽`；压暗结果页丢光抽奖页规则标记、顶部
    `装扮` 标签滑出屏 → 绘制后经 OCR 实证的 `做任务继续抽` 关闭结果页、
    `switch()` 缺双标签时向顶滑最多 6 次（入口首帧即有标签，no-op）；
    显式 `还有0次` 徽标 = 当日已抽完 → 跳过绘制保重跑幂等（零判定位于幂等
    签到/广告之后）；绘制 spend 未决 id9 凭证据帧 `0048-dfabdc` 核销；
  - `115920` 关结果页的 `做任务继续抽` 被执行器"Cannot act on unknown page"
    护栏拦下（压暗视图确实判 UNKNOWN）→ 该点击透传 `allow_unknown=True`：
    目标文本 OCR 实证、后置仍要求回可识别 lottery 页，正是白名单语义；
  - `120551` **`forest.friends` 全链路首次 SUCCESS**：入口结果页 Back→汇总→
    `返回森林首页`→找能量（好友栈已空直落汇总）→`去抽奖`→右侧零次跳抽→
    `left-lottery` 切左→左签到/绘制已完成零次跳→`返回森林首页` 收尾，
    DB 未决 0；证据帧含今日 `收好友178g`，与 `103757`/`111049` 两轮
    `领取成功` 一起构成"好友能量一个没领取""能立即领取的没领"两条投诉的
    实机反证。

## 2026-09-21：蚂蚁森林全屏活动弹窗挡住收能量

- 设备：`10AD4419NX0029Z`，`1440x3200`；运行 `forest.self` 两次均超时
  （`logs/20260921-101347-1d5f62.jsonl`、`logs/20260921-101558-8911fc.jsonl`）。
- 进入森林约 10 秒后自动弹出“广东瑰宝季 PK赛”整屏模态（证据
  `screenshots/runs/20260921-101558-8911fc/0006-24272a.png`）：深色遮罩压暗场景，
  但页面标题“蚂蚁森林”“森林广场”仍可 OCR，页面被误判为正常 `forest`，
  气泡被模态挡住 → 点击后置条件永远不成立 → `Postcondition failed: collect-energy` 超时。
- 标定（半分辨率夹具同结论）：四条边缘带灰度均值 弹窗 ≈88 / 正常 ≈195，
  中央区域 171 / 184；判定门槛 `ring < 115 且 center > ring + 25`。
  关闭圆圈位于裁剪带 `y∈[.78,.93]、x∈[.28,.72]` 内、相对 (0.5w, .58 带高) 距离
  ≤ `0.07w`（实测 (0.498, 0.869)、r≈50px）；正常主页上最近圆圈距离 >200px，不会误检。
- 策略：`classify()` 只在 `page == forest` 且暗度门槛通过且圆圈命中时追加
  `forest_campaign` overlay 与“广告关闭”控件；`recovery.dismiss` 复用庄园广告的
  关闭圆形流程，关闭后重新截图确认遮罩消失。

## 2026-09-21：幻影 `21563g` 气泡与收能量边界

- 右上角累计徽标 OCR 为 `21563g`（(.851, .141)），命中旧的 `^\d+g$` 气泡规则；
  真实点击日志 `action.intent collect-energy point [1226,450]` 正落在徽标上，
  徽标点击后不消失 → 后置条件永不成立。同时“森林广场”入口卡自带 `260g/150g`
  角标（y≈.78/.81），左上角另有任务书定义的“5g 能量签到”特殊气泡。
- 策略：`Forest._bubbles()` 限定 `^\d{1,4}g$`、树冠带 `(.05,.14,.95,.52)`、
  排除右上角 (x>.68 且 y<.17) 徽标位、并与“能量签到”文本 240px 内的气泡分离
  （签到气泡走独立奖励流）；连续点击无效果最多重试 3 次（TIMEOUT/STALE/OVERLAY），
  每次用新观测证明点击确实无效，否则失败关闭。

## 2026-09-21：Back 落点与签到条识别

- `run 20260921-101347`：从“饲料任务”页 Back 落回支付宝首页而非森林，
  旧 `ensure()` 只接受硬编码目标页 → `Postcondition failed: return; page=alipay`。
  现策略：接受任何新识别到的非 UNKNOWN 页面并重新规划路线
  （`tests/test_ensure_navigation.py` 回归）。
- 庄园签到条整条不存在独立“签到”文案、OCR 常把“今天”读错、领取后整条消失；
  改为锚定“饲料任务”表头 + `第[2-5]天` 格子，两次连续观测证明缺席后记
  `ALREADY_DONE`，领取后必须在同一区域看到“已领取”（`tests/test_sign_strip.py`）。
- 列表滑动统一为 700ms 短距，避免跳过任务卡。

## 2026-09-08：庄园主页连续弹窗

- 设备：`V2227A`，Android 16，`1440x3200`，USB ADB。
- 底层页面：蚂蚁庄园主页；底部仍可见“好友、领饲料、家庭、去捐蛋”等入口。
- 弹窗顺序：`玩游戏得现金` -> `七日礼包` -> `含羞草来串门`。
- 三层弹窗均在屏幕下方中央提供圆形 `X` 关闭控件；关闭一层后可能立即出现下一层。
- 弹窗关闭后必须重新截图确认遮罩消失，不能依据 ADB 点击返回码判定成功。

### 自动化策略

1. 先识别底层页面仍为庄园主页，再识别整屏变暗、中央模态区域和关闭圆形。
2. 将关闭圆形绑定到当前观测，点击前校验观测未过期；不点击广告主体或“立即领现金”。
3. 每次只关闭一层，重新采集并继续处理，最多受弹窗层数、无进展次数和总恢复预算限制。
4. 关闭控件无法识别、页面变为未知或出现未决不可逆动作时立即停止并保存截图。

这类主页弹窗是通用页面中断，不属于庄园业务任务；后续任务 Workflow 在任何入口前先调用同一套 overlay recovery。
