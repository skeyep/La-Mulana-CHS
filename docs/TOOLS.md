# 已公开工具

`tools/patch/`保留两种平台的离线安装器源码。Windows使用`Install.cmd`／`Check.cmd`／`Restore.cmd`及PowerShell；Steam Deck／Linux使用对应`.sh`入口和`Patch.py`，通过Proton运行Windows版游戏。Linux安装器使用Python 3.8以上的标准库。每个平台的Release包分别携带自己的入口，与`manifest.json`、`payload/`一起支持安装、检查、直接覆盖升级和还原。

Linux安装器的生成数据回归可在仓库根目录运行`python -B tools/patch/test_portable.py`。它覆盖升级互切、配置失败回滚、安装／还原中断、文件改动保护、SD卡库与Proton配置定位、子路径符号链接、互斥锁及Linux运行中检测；无需游戏资源。

`tools/lm1_phonetic_stroke_full_v1.py`是当前2130个音调古字的有限部件编码；`lm1_phonetic_stroke_v1.py`保留变宽笔锋、平滑插值、12倍面积采样和18个样例接口。两者读取`phonetic/stroke-full-v1/mapping.json`中的定稿几何配方，生成字格与完整图集。

古字绘图脚本需要Pillow，在仓库根目录运行：

```powershell
python -m pip install Pillow
python tools/lm1_phonetic_stroke_full_v1.py kan4 --output kan4.png
python tools/lm1_phonetic_stroke_full_v1.py --catalog --output catalog.png
```

`--mapping`可指定另一份同结构配方。输出是原生21×21灰度alpha PNG，五调按末尾1–5选择。Python接口`Codec().encode("kan4")`返回合成字格、分层和读音特征。

`tools/achievement_assistant/assistant.cpp`和`roster.h`保留冒险记录界面、输入、判定和结局同行逻辑。目标为本项目所支持的Windows Steam x86版本，需要C++17、Win32／Direct3D 9／XInput头文件及库。

收集页的泡温泉进度读取当前存档flag3027，按100次目标显示。地上温泉的原生检测器要求在池内范围连续累计61次更新；上方或右侧离池区域重置当次计数锁。小跳可能未触及重置区，离池后回池还需等待约1秒；满血也可计次。

`build_catalog.py`、`trigger_hints.py`与`dialogue_routes.py`按当前中文、原选择器及RCD容器生成对话、邮件与实际入口目录。房间范围和屏幕范围分别处理；随机区间扣除固定对白覆盖，保留流程点数的原始边界。这两个生成器需要本机提取的源资源与上下文。

助手编译输入还包括`catalog.generated.h`、`routes.generated.h`、`skin.generated.h`、`portraits.generated.h`，由本机文本和游戏资源生成。后续迁移资源生成与整包构建入口。

实际使用字体的OFL和版权说明在`licenses/`。

`tools/build_lm1_title_version.py`读取`docs/release.json`，把版本与日期绘制到首页左下角，保留右侧署名。输入为已汉化的纯版候选目录，另需Pillow、pefile、keystone-engine及现用臻楷字体；通过`--base`、`--output`和`--font`指定。

每批交付改动都递增版本号，不再覆盖同版本附件。发布时同步`docs/release.json`、README、四个安装包与Release，并用同一份版本／日期元数据更新游戏首页。四包为Windows／Linux-Proton各自的Translation Only和Translation + Adventure Log，同一内容版本的游戏payload保持相同。日期按实际发布日期填写。


`dialogue_timing.py`维护已核实的具体地点、前置与截止提示。0.2.5统一穆尔56条、长老57条的状态：已听优先，再判断明确错过、当前入口和选择器优先级；剧情、未展示装备、固定点数和随机池依次选择。未来点数及前置未满足均显示“暂不可”，随机提示列出完整的下一窗口。查询本身保持旗标与随机数状态。

## 仓库维护

提交到`main`、向`main`提出Pull Request或手动运行工作流时，GitHub Actions会在Ubuntu上使用Python 3.14执行`python -B scripts/check_sources.py`，检查译文稳定键、颜色范围、逐字读音、原符绑定和古字数据，并执行`python -B tools/patch/test_portable.py`检查Linux安装器。两项检查使用Python标准库，可在公开仓库内独立运行。

`main`允许正常提交，禁止强制推送和删除；自动检查暂不设为发布硬门槛，现有GitHub API发布入口继续使用。`v*`标签禁止更新和删除，管理员保留例外，用于现有草稿发布流程及必要恢复。已正式发布的版本继续沿用逐批递增版本号的约定。

反馈入口提供“翻译问题”和“安装或运行问题”表单，分别收集文本位置与上下文，以及安装包、运行环境和复现步骤。
