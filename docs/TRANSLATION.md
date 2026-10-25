# 译文和中文古字数据

`translations/`保存主篇7095段和附加模式118段中文。每段用`resource_id`、`source_segment_index`和`stable_key`定位；`zh`是可编辑译文。源token锚点与`source_identity_requirements`保留数字、咒文及原符身份。

`readings/`保存5673段逐字读音。`units`依次拼回该段中文：`phonetic`使用带1—5调号的拼音；`source-copy`保留指定原符，token由该单位或同文件`source_symbols`给出；`source-token`及`literal`保留原字面编码。改译时同步检查读音、多音字和原符所在位置。

`phonetic/inventory.json`给出426基音与五调，`stroke-full-v1/`保存当前笔画部件、2130个音码和透明库存PNG。`preservation.json`记录表义符、数字和咒文保护规则；`source-components.json`记录部件坐标。普通同音同调共享古字，原符优先。`chinese_binding_proposals`的状态字段区分已用规则与候选。

从现有工作工程更新公开数据：

```bash
python scripts/export_sources.py --workspace "工作工程目录"
python scripts/check_sources.py --workspace "工作工程目录"
```

公开数据单独编辑后，运行`python scripts/check_sources.py`检查稳定键、7213／5673段计数、逐字拼接和映射结构。导出器保留中文与原符约束，输出UTF-8 JSON并清理PNG元数据；原版多语资源由本机游戏提取。

这些文件是便于审阅、修改和维护的公开源格式。完整补丁的游戏资源提取、字体编译和安装流程使用各自构建入口。
