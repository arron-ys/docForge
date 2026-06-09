# Diagnosis-only Template Strategy

模板策略只能根据给定 `DiagnosisResult` 推荐。

- 不得读取原始证据或 ProductProfile 关键词自行扩展能力。
- enhancement pack 必须严格跟随 `DiagnosisResult.enhancement_tags`。
- 基础模板只允许提供通用章节；数据、AI、权限和汽车行业章节必须由对应 enhancement tag 驱动。
- 没有对应 enhancement tag 时，不得推荐该能力领域的章节。
- risk chapters 必须严格跟随 `DiagnosisResult.risk_notes`。
- 推荐不等于用户确认，不得生成 FrozenDocPlan 或冻结目录。
- 输出必须是 JSON object。
