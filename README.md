# La-Mulana-CHS

《穆拉纳秘宝》Windows Steam 重制版简体中文汉化。  
汉化：**Skeyep_目目** · 当前版本 **0.2.6**

## 下载与安装

| 平台 | Translation Only（纯汉化） | Translation + Adventure Log（含冒险记录） |
| --- | --- | --- |
| Windows | [Download](https://github.com/skeyep/La-Mulana-CHS/releases/download/v0.2.6/La-Mulana-CHS-0.2.6-Windows-Translation-Only.zip) | [Download](https://github.com/skeyep/La-Mulana-CHS/releases/download/v0.2.6/La-Mulana-CHS-0.2.6-Windows-Translation-Adventure-Log.zip) |
| Steam Deck / Linux（Proton） | [Download](https://github.com/skeyep/La-Mulana-CHS/releases/download/v0.2.6/La-Mulana-CHS-0.2.6-Linux-Proton-Translation-Only.zip) | [Download](https://github.com/skeyep/La-Mulana-CHS/releases/download/v0.2.6/La-Mulana-CHS-0.2.6-Linux-Proton-Translation-Adventure-Log.zip) |

Windows安装：

1. 退出游戏，解压下载的Windows安装包。
2. 双击 **Install.cmd**，自动查找 Steam，必要时手选游戏目录。
3. 启动游戏即可使用简体中文，首页左下角显示汉化版本与日期。

新版直接覆盖安装；两个版本也可以直接切换。双击 **Restore.cmd** 恢复原版。

**Steam Deck / Linux**：先在Steam中强制Proton、启动一次并退出，再在桌面模式解压Linux-Proton包，终端运行 `bash ./Install.sh`；检查用 `bash ./Check.sh`，还原用 `bash ./Restore.sh`。[完整教程与待验范围](docs/steam-deck.md)。Deck画面和实体手柄待实机确认。

## 中文穆拉纳文字

普通汉字按 **声母＋韵母＋声调** 拼成一格，例如「看 kàn」由 `k＋an＋第四声` 组合。同音同调共用字形，多音字按句中的读音选择，调号记本调。

与谜题相连的数字、表义符号、印章和咒文保留原作的对应关系；旧文字沿原作规则，逐格左右镜像。玩家可以结合部件规律和上下文自行识读。

[设计过程与图解：中文穆拉纳文字，我的做法](https://www.xiaoheihe.cn/app/bbs/link/194788616)

## 汉化独占功能：冒险记录

- 查阅穆尔、长老的对话与邮件，查看已听、可触发、暂不可及已错过状态。
- 查看流程点数、收集进度（含泡温泉次数）、通关挑战和结局同行角色。
- 暂停后按 **跳跃键** 打开；确认键展开触发详情，返回键收起，再按返回键退出。

[独占功能介绍与演示](https://www.xiaoheihe.cn/app/bbs/link/194922739)

## 反馈

请在 [Issues](https://github.com/skeyep/La-Mulana-CHS/issues) 附上版本号、出现位置和截图；译文建议可以同时写出原句与修改意见。

## 使用许可

免费使用，允许保留署名与来源的非商业转载和修改；禁止收费售卖、付费捆绑、付费代装及冒名发布。修改版须注明改动并沿用相同许可，详见 [LICENSE](LICENSE)。正常游戏直播、攻略与评测视频及其平台收益允许。

本项目为非官方玩家汉化，原作内容归各自权利人所有；第三方字体继续适用 [原许可](licenses/)。
