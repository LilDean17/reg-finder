# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- 新增 `form_actions` 提取：`probe._extract_forms` 现在收集页面所有 `<form>` 的 `action` 属性，纳入评分池

### Changed
- **XLSX 输出改为三档分段**：原 `high_score_above5.xlsx`（score>5）+ `register_signal_low_score.xlsx`（score<5 且命中注册关键词/表单）两文件，改为严格按分数归档的三个文件：`high_score_above5.xlsx`（score>5）、`score_0_to_5.xlsx`（0≤score≤5，含两端）、`score_below_0.xlsx`（score<0），无任何附加条件，三者合计无缝覆盖全部已评分条目；三个文件均为扫描中实时逐条写入；黑名单/内容重复/CDN/请求失败等非评分记录不进入分段文件（仅进 CSV/JSONL）
- `core/score.py` 取消 `max(total_score, 0)` 分数截断：排除规则扣分后允许出现负分，`score<0` 档才有实际意义
- **register_form 评分逻辑重构**：`type` / `name` / `id` / `value` / `action` 五个维度全部平铺到一个统一文本池，子串匹配时完全平等，每命中一个配置项独立计分
- 去除 `has_register_form` 阀门约束，register_form 始终参与评分
- 移除硬编码 fallback 输出 `"注册表单"`，无匹配时不产生 hit、不加分
- 清理所有 `debug_*.py` 调试脚本及 `test_portals.txt`、`urls.txt` 临时文件
