# Evidence-grounded Product Understanding

你只能使用输入中的 `evidence_packets` 理解产品。不得使用参考软著、常识或关键词联想补全功能。

你输出的是候选能力，不代表能力已经被系统确认。系统会继续校验引用来源，并通过
`ProductCapabilityGroundingVerifier` 判断 quote 是否语义支持候选名称、类型和实现状态。
系统也会通过 `ProductProfileEntityGroundingVerifier` 分别校验业务对象、目标用户、页面和流程。

输出必须是一个 JSON object，结构如下：

```json
{
  "capabilities": [
    {
      "name": "能力名称",
      "description": "能力说明",
      "capability_type": "CapabilityType 枚举值",
      "implementation_status": "current | planned | unknown",
      "supporting_evidence_ids": ["ev_xxx"],
      "supporting_quotes": ["证据原文短句"],
      "confidence": 0.8,
      "reasoning": "判断理由"
    }
  ],
  "business_objects": [
    {
      "name": "业务对象",
      "implementation_status": "current | planned | unknown",
      "supporting_evidence_ids": ["ev_xxx"],
      "supporting_quotes": ["证据原文短句"],
      "confidence": 0.8
    }
  ],
  "target_users": [
    {
      "name": "目标用户",
      "implementation_status": "current | planned | unknown",
      "supporting_evidence_ids": ["ev_xxx"],
      "supporting_quotes": ["证据原文短句"],
      "confidence": 0.8
    }
  ],
  "pages": [
    {
      "name": "页面",
      "implementation_status": "current | planned | unknown",
      "supporting_evidence_ids": ["ev_xxx"],
      "supporting_quotes": ["证据原文短句"],
      "confidence": 0.8
    }
  ],
  "workflows": [
    {
      "name": "流程",
      "implementation_status": "current | planned | unknown",
      "steps": ["步骤1", "步骤2"],
      "supporting_evidence_ids": ["ev_xxx"],
      "supporting_quotes": ["证据原文短句"],
      "confidence": 0.8
    }
  ],
  "uncertain_items": []
}
```

强制规则：

- 每个能力、业务对象、用户角色、页面和流程必须引用真实 `evidence_id` 和原文 `quote`。
- 不得根据能力自行推断页面、流程、用户角色或业务对象。
- 页面、流程、用户角色和业务对象也必须标记 `implementation_status`。
- planned/future/待建设/尚未上线 的辅助字段必须标记为 `planned` 或 `unknown`。
- `current` 只能用于资料明确表达当前版本提供、具备或已实现的辅助字段。
- 系统会分别执行 source grounding、semantic grounding 和 implementation status 校验。
- `supporting_quotes` 必须逐字来自对应 EvidencePacket，不得改写。
- 不得因为“导入”“模型”“仿真”等词自行扩展平台类型或功能。
- `planned/future/待建设/尚未上线` 能力必须标记为 `planned` 或 `unknown`。
- `current` 只能用于资料明确表达当前版本支持、提供、具备或已实现的能力。
- 不确定内容放入 `uncertain_items`。
- 不得使用 `reference_style`。
