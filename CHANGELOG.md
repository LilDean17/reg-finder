# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- 新增 `form_actions` 提取：`probe._extract_forms` 现在收集页面所有 `<form>` 的 `action` 属性，纳入评分池

### Changed
- **register_form 评分逻辑重构**：`type` / `name` / `id` / `value` / `action` 五个维度全部平铺到一个统一文本池，子串匹配时完全平等，每命中一个配置项独立计分
- 去除 `has_register_form` 阀门约束，register_form 始终参与评分
- 移除硬编码 fallback 输出 `"注册表单"`，无匹配时不产生 hit、不加分
- 清理所有 `debug_*.py` 调试脚本及 `test_portals.txt`、`urls.txt` 临时文件
