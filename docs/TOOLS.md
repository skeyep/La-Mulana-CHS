# 已公开工具

`tools/patch/`保留当前离线安装器的五个入口。它们在Release解压目录中与`manifest.json`、`payload/`一起使用，支持安装、检查、直接覆盖升级和还原。

`tools/lm1_phonetic_stroke_full_v1.py`是当前2130个音调古字的有限部件编码；`lm1_phonetic_stroke_v1.py`保留变宽笔锋、平滑插值、12倍面积采样和18个样例接口。两者读取`phonetic/stroke-full-v1/mapping.json`中的定稿几何配方，生成字格与完整图集。

Python需要Pillow，在仓库根目录运行：

```powershell
python -m pip install Pillow
python tools/lm1_phonetic_stroke_full_v1.py kan4 --output kan4.png
python tools/lm1_phonetic_stroke_full_v1.py --catalog --output catalog.png
```

`--mapping`可指定另一份同结构配方。输出是原生21×21灰度alpha PNG，五调按末尾1–5选择。Python接口`Codec().encode("kan4")`返回合成字格、分层和读音特征。

`tools/achievement_assistant/assistant.cpp`和`roster.h`保留冒险记录界面、输入、判定和结局同行逻辑。目标为本项目所支持的Windows Steam x86版本，需要C++17、Win32／Direct3D 9／XInput头文件及库。

收集页的泡温泉进度读取当前存档flag3027，按100次目标显示。地上温泉的原生检测器要求在池内范围连续累计61次更新；上方或右侧离池区域重置当次计数锁。小跳可能未触及重置区，离池后回池还需等待约1秒；满血也可计次。

`build_catalog.py`与`trigger_hints.py`按当前中文、原选择器及RCD容器生成对话与邮件目录。房间范围和屏幕范围分别处理；随机区间扣除固定对白覆盖，保留流程点数的原始边界。这两个生成器需要本机提取的源资源与上下文。

助手编译输入还包括`catalog.generated.h`、`skin.generated.h`、`portraits.generated.h`，由本机文本和游戏资源生成。后续迁移资源生成与整包构建入口。

实际使用字体的OFL和版权说明在`licenses/`。

`tools/build_lm1_title_version.py`读取`docs/release.json`，把版本与日期绘制到首页左下角，保留右侧署名。输入为已汉化的纯版候选目录，另需Pillow、pefile、keystone-engine及现用臻楷字体；通过`--base`、`--output`和`--font`指定。

每批交付改动都递增版本号，不再覆盖同版本附件。发布时同步`docs/release.json`、README、两个安装包与Release，并用同一份版本／日期元数据更新游戏首页。日期按实际发布日期填写。


`dialogue_timing.py`只补13项缺少关键前置或截止信息的对话提示，其余98项保持原样。简要使用正常短句，具体操作放在详情中。
