# Steam Deck 安装汉化

SteamOS 用户在 Release 选择 **Linux-Proton** 安装包，使用其中的 **`Install.sh`**；游戏通过 **Proton 运行 Windows 版**。纯汉化版和冒险记录版使用相同步骤。Windows 包单独提供 `.cmd` 入口。

《La-Mulana》也提供原生 Linux 版。汉化包含修改后的 `LaMulanaWin.exe`，安装前须让 Steam 下载 Windows 版。

## 在 Deck 上安装

1. 在游戏的 **属性 → 兼容性** 中勾选“强制使用特定 Steam Play 兼容性工具”，选择 Steam 提供的 Proton 稳定版。等待游戏下载完成，先从 Steam 启动一次，再正常退出。
2. 切换到 **桌面模式**，把安装包完整解压到下载目录或其他可写目录。
3. 打开解压后的文件夹，在空白处右键选择 **在此打开终端／Open Terminal Here**，运行：

   ```bash
   bash ./Install.sh
   ```

   安装器会读取 Steam 的游戏库，查找内置盘及已登记的 SD 卡。找到多个目录时按编号选择。
4. 安装成功后运行：

   ```bash
   bash ./Check.sh
   ```

   看到 `PASS` 后返回游戏模式，从 **原有 Steam 游戏条目** 启动。首页左下角应显示 `汉化版本 0.2.6 · 2026-10-27`。

安装使用 SteamOS 自带的 Python 3，无需 `sudo` 或安装系统软件。Windows 用户继续双击 `Install.cmd`。

朋友已有原生 Linux 版进度时，先备份原存档；切换到 Proton 后确认旧进度能加载，再继续保存。汉化安装器保留存档，存档迁移由 Steam 云同步或玩家单独处理。

## 手动指定目录

自动查找失败时，在 Steam 的 **属性 → 已安装文件 → 浏览** 中查看实际游戏目录，然后运行：

```bash
bash ./Install.sh "/实际游戏库/steamapps/common/La-Mulana"
bash ./Check.sh "/实际游戏库/steamapps/common/La-Mulana"
```

目录内必须存在 `LaMulanaWin.exe`。出现 `The Windows build is required` 时，先完成强制 Proton 和游戏下载。出现 `Proton prefix not found` 时，先用 Proton 从 Steam 启动游戏一次并退出。

高级入口可用 `--steam-root "/Steam目录"` 指定 Steam 根目录，用 `--config-path "/完整路径/config.ini"` 指定当前 Proton 配置；日常安装无需这些参数。

## 升级、切换版本和还原

升级或互切纯汉化版／冒险记录版：解压想用的新包，退出游戏后重新执行 `bash ./Install.sh`。最初原版备份继续保留，切回纯汉化版会移除补丁拥有的助手 DLL 和专用字体。

还原原版：

```bash
bash ./Restore.sh
```

安装包已删除时，在游戏目录打开终端，执行：

```bash
bash ./.lamulana-zh/Restore.sh
```

保留游戏目录下的 `.lamulana-zh`；它包含原版备份、安装记录和独立还原脚本。文件管理器按 `Ctrl+H` 可显示这个隐藏目录。安装中断后重新运行安装或还原入口，会先恢复到中断前版本，再完成所选操作。

安装器只调整当前 Proton 配置中的 `Language`，首次修改前备份配置；还原时保留当前设置与存档。它保留额外画面／音乐包，图像汉化使用原版画面包；检测到 EX Map Port 时会提示先准备干净原版。

若要回到原生 Linux 版，先执行 `Restore.sh`，再在 Steam 中取消强制 Proton，等待 Steam 完成版本切换。

## 冒险记录与验收

冒险记录跟随游戏当前按键绑定：暂停后按 **跳跃** 打开；确认键展开触发详情，返回键收起，再按返回键退出。页签和人物切换沿用游戏菜单动作，可通过 Steam Input 调整。

已验：Windows 主机隔离目录中的真实补丁安装、双向切换、Windows 安装记录接续、配置保留、中断恢复与独立还原，结果见项目验证记录。候选包的正文与字库继承 0.2.5，首页版本同步为 0.2.6。

待验：SteamOS 上实际执行脚本、Proton 加载、Deck 中文画面及实体手柄／Steam Input 操作。朋友首轮确认首页中文、载入存档、打开一段文本，以及冒险记录的进入／退出，即可反馈这四项结果。

参考：[Steam 官方 Proton 切换说明](https://help.steampowered.com/en/faqs/view/7DD4-C618-182E-0E49) · [Valve Proton FAQ](https://github.com/ValveSoftware/Proton/wiki/Proton-FAQ)。
