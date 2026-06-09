# Evidence-grounded Software Diagnosis

诊断只能基于已验证的 `ProductCapability` 与 `ProductFact`。

- 当前类型和增强标签只能使用 `validated + current` 能力。
- `planned/unknown` 能力只能形成风险提示。
- 诊断理由必须引用已有 `capability_id` 或 `fact_id`。
- 不得读取原始资料关键词直接判断软件类型。
- 不得自行添加无法追溯到已验证能力的增强标签。
- 输出必须是 JSON object。
