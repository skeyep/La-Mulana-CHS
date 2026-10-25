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

助手编译输入还包括`catalog.generated.h`、`skin.generated.h`、`portraits.generated.h`，由本机文本和游戏资源生成。后续迁移资源生成与整包构建入口。

实际使用字体的OFL和版权说明在`licenses/`。
