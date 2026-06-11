from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from docforge_core.agents.human_confirm_gate import (
    CONFIRMATION_RESULT_KEY,
    CONFIRMATION_SOURCE_KEY,
)
from docforge_core.domain.enums import (
    AllowedUsage,
    ConfirmationStatus,
    ConfirmationType,
    FileType,
    NextAction,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DocForgeState, SourceItem
from docforge_core.io.run_paths import get_run_dir
from docforge_core.workflow.auto_confirmation import AutoConfirmationPolicy
from docforge_core.workflow.run_settings import get_run_settings
from docforge_core.workflow.strategy_reset import strategy_change_mode

from .schemas import (
    AgentActionView,
    AgentMessageView,
    ConfirmationStateView,
    DiagnosticIssueView,
    DiagnosticSummaryView,
    ExportArtifactView,
    RunListItemView,
    RunSummaryView,
    SeverityCountsView,
    SourceItemView,
    SourceUsagePolicyView,
    WorkspaceSettingsView,
    WorkspaceView,
)

STATUS_LABELS: dict[str, str] = {
    "CREATED": "项目已创建，等待上传资料",
    "MATERIAL_UPLOADED": "资料已上传，等待开始",
    "SOURCE_PARSED": "资料解析完成，正在分析参考风格和产品内容",
    "REFERENCE_STYLE_ANALYZED": "参考风格已分析，正在理解产品内容",
    "PRODUCT_UNDERSTOOD": "产品理解已完成，正在构建证据地图",
    "EVIDENCE_MAPPED": "证据地图已构建，正在诊断软件类型",
    "DIAGNOSED": "软件类型已诊断，正在生成推荐文档策略",
    "TEMPLATE_RECOMMENDED": "已生成推荐文档策略，等待你确认",
    "USER_CONFIRM_REQUIRED": "需要你确认产品类型和文档策略",
    "USER_CONFIRMED": "已收到你的确认，正在冻结文档方案",
    "PLAN_FROZEN": "文档方案已冻结，正在生成目录",
    "OUTLINE_CREATED": "文档目录已生成，正在检查计划质量",
    "PLAN_GATE_REVIEWING": "正在检查文档计划质量",
    "PLAN_GATE_PASSED": "文档计划已通过，正在生成正文",
    "PLAN_GATE_FAILED": "关键信息不足，需要补充后才能生成正文",
    "DRAFT_V1_CREATED": "第一版草稿已生成，正在审计",
    "FIGURE_SLOTS_PLANNED": "配图位置已规划，正在审计正文",
    "DRAFT_AUDITED": "草稿审计完成，正在执行质量门禁",
    "DRAFT_QUALITY_GATE_PASSED": "草稿质量已通过，准备导出 DOCX",
    "DRAFT_REVISION_REQUIRED": "草稿未通过审计，正在修订",
    "AUDIT_V1_COMPLETED": "第一轮审计已完成",
    "DRAFT_V2_CREATED": "第二版草稿已生成，正在审计",
    "DRAFT_V2_AUDITED": "第二版草稿审计完成",
    "AUDIT_V2_COMPLETED": "第二轮审计已完成",
    "DRAFT_V3_CREATED": "第三版草稿已生成，正在审计",
    "DRAFT_V3_AUDITED": "第三版草稿审计完成",
    "AUDIT_V3_COMPLETED": "第三轮审计已完成",
    "RISK_VERSION_READY": "存在较高风险，已准备风险版 DOCX",
    "DRAFT_GATE_PASSED": "草稿质量已通过",
    "REVISION_REQUIRED": "草稿未通过审计，正在修订",
    "FINAL_EXPORTED": "最终文档已生成，可下载",
    "RISK_EXPORTED": "风险版文档已生成，建议人工复核后使用",
    "FAILED": "任务失败，请查看错误说明或重试",
}

NEXT_ACTION_LABELS: dict[str, str] = {
    "ingest_materials": "上传资料",
    "parse_sources": "开始解析资料",
    "analyze_reference_style": "分析参考风格",
    "understand_product": "理解产品资料",
    "extract_evidence": "构建证据地图",
    "diagnose_software_type": "诊断软件类型",
    "recommend_template": "推荐文档策略",
    "ask_human_confirmation": "确认产品类型和文档策略",
    "freeze_doc_plan": "冻结文档方案",
    "create_outline": "生成文档目录",
    "run_plan_quality_gate": "检查文档计划",
    "ask_missing_information": "补充缺失信息",
    "write_draft": "生成正文草稿",
    "plan_figure_slots": "规划配图位置",
    "audit_draft": "审计正文草稿",
    "run_draft_quality_gate": "检查正文质量",
    "revise_draft": "修订正文草稿",
    "audit_revised_draft": "审计修订稿",
    "export_docx": "导出 DOCX",
    "export_risk_docx": "导出风险版 DOCX",
    "export_final_doc": "导出最终文档",
    "export_risk_doc": "导出风险文档",
    "stop": "任务已结束",
}


def status_label(status: WorkflowStatus | str) -> str:
    value = status.value if isinstance(status, WorkflowStatus) else str(status)
    return STATUS_LABELS.get(value, "任务状态已更新")


def next_action_label(next_action: NextAction | str) -> str:
    value = next_action.value if isinstance(next_action, NextAction) else str(next_action)
    return NEXT_ACTION_LABELS.get(value, "查看下一步建议")


def to_workspace_view(
    state: DocForgeState,
    *,
    data_dir: Path,
    diagnostics: DiagnosticSummaryView | None = None,
) -> WorkspaceView:
    stage = status_label(state.workflow_status)
    diagnostic_summary = diagnostics or DiagnosticSummaryView(
        health_label="正常，可继续",
        stage_label=stage,
        next_suggestion=next_action_label(state.next_action),
    )
    actions = available_actions_for_state(state)
    primary = next((action for action in actions if action.primary), None)

    return WorkspaceView(
        run_summary=RunSummaryView(
            run_id=state.run_id,
            project_name=state.project_name or state.target_product_name or "未命名项目",
            task_name=f"当前运行任务：{state.project_name or state.target_product_name or state.run_id}",
            stage_label=stage,
            health_label=diagnostic_summary.health_label,
            health_tone="success" if diagnostic_summary.health_label.startswith("正常") else "warning",
        ),
        sources=[to_source_view(state.run_id, source) for source in state.source_registry],
        export_artifacts=export_artifacts_for_state(state, data_dir=data_dir),
        messages=workspace_messages_for_state(state, stage),
        settings=WorkspaceSettingsView(
            **get_run_settings(state),
            strategy_change_mode=strategy_change_mode(state),
        ),
        confirmation_state=confirmation_state_for_state(state),
        diagnostics=diagnostic_summary,
        available_actions=actions,
        primary_action=primary,
        error=state.errors[-1].get("message") if state.errors else None,
        last_error=None,
    )


def to_run_list_item_view(state: DocForgeState, *, state_file: Path | None = None) -> RunListItemView:
    updated_at = datetime.now(UTC)
    if state_file and state_file.exists():
        updated_at = datetime.fromtimestamp(state_file.stat().st_mtime, tz=UTC)

    created_at = created_at_from_run_id(state.run_id) or updated_at
    project_name = state.project_name or state.target_product_name or "未命名项目"
    return RunListItemView(
        run_id=state.run_id,
        project_name=project_name,
        task_name=f"当前运行任务：{project_name if project_name != '未命名项目' else state.run_id}",
        stage_label=status_label(state.workflow_status),
        created_at=created_at.isoformat(),
        updated_at=updated_at.isoformat(),
    )


def created_at_from_run_id(run_id: str) -> datetime | None:
    try:
        return datetime.strptime(run_id[:15], "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def to_source_view(run_id: str, source: SourceItem) -> SourceItemView:
    policy = usage_policy_for_source(source)
    file_size = None
    if source.file_path:
        path = Path(source.file_path)
        if path.exists():
            file_size = path.stat().st_size
    return SourceItemView(
        source_id=source.source_id,
        run_id=run_id,
        source_type=source.source_type.value,
        file_type=source.file_type.value,
        corpus_type=source.corpus_type.value,
        allowed_usage=display_allowed_usage(source),
        file_name=source.file_name,
        file_path=source.file_path,
        file_size=file_size,
        uploaded_at=source.uploaded_at,
        parse_status=source.parse_status.value,
        parse_error=source.parse_error,
        status_label=parse_status_label(source),
        usage_policy=policy,
        notes=source.notes,
        metadata=dict(source.metadata),
    )


def usage_policy_for_source(source: SourceItem) -> SourceUsagePolicyView:
    if source.source_type == SourceType.REFERENCE_SOFT_COPYRIGHT_DOC:
        return SourceUsagePolicyView(
            label="外部参考软著",
            allowed_use="仅参考目录、章法、配图方式和语言风格",
            risk_boundary="不能作为产品事实来源",
            badge_type="warning",
        )
    if source.source_type == SourceType.SCREENSHOT:
        return SourceUsagePolicyView(
            label="产品截图",
            allowed_use="仅作为配图占位和展示材料登记",
            risk_boundary="MVP 不做 OCR，不作为强产品事实证据",
            badge_type="info",
        )
    return SourceUsagePolicyView(
        label="自有产品资料",
        allowed_use="可用于产品能力描述和事实归纳",
        risk_boundary="可以作为产品事实来源",
        badge_type="success",
    )


def display_allowed_usage(source: SourceItem) -> str:
    return source.allowed_usage.value


def parse_status_label(source: SourceItem) -> str:
    labels = {
        "pending": "等待开始",
        "parsed": "已解析",
        "failed": "解析失败",
        "skipped": "已跳过",
    }
    if source.source_type == SourceType.SCREENSHOT and source.parse_status.value == "pending":
        return "已保存"
    return labels.get(source.parse_status.value, "已保存")


def workspace_messages_for_state(
    state: DocForgeState,
    stage: str,
) -> list[AgentMessageView]:
    now = datetime.now(UTC)
    messages = [
        AgentMessageView(
            message_id=f"message-{state.run_id}-status",
            run_id=state.run_id,
            role="agent",
            content=f"当前任务状态：{stage}。下一步建议：{next_action_label(state.next_action)}。",
            created_at=now.isoformat(),
            created_at_label=now.strftime("%H:%M"),
            event_type="system_notice",
        )
    ]
    confirmation_message = persisted_confirmation_message(state)
    if confirmation_message:
        messages.append(
            AgentMessageView(
                message_id=f"message-{state.run_id}-strategy-confirmation",
                run_id=state.run_id,
                role="agent",
                content=confirmation_message,
                created_at=now.isoformat(),
                created_at_label=now.strftime("%H:%M"),
                event_type="doc_plan_confirm",
            )
        )
    guidance = start_guidance_for_state(state)
    if guidance:
        messages.append(
            AgentMessageView(
                message_id=f"message-{state.run_id}-start-guidance",
                run_id=state.run_id,
                role="agent",
                content=guidance,
                created_at=now.isoformat(),
                created_at_label=now.strftime("%H:%M"),
                event_type="system_notice",
                card=confirmation_card_for_state(state),
            )
        )
    return messages


def start_guidance_for_state(state: DocForgeState) -> str:
    if state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED:
        return "资料解析和产品理解已完成。请根据下方确认卡片核对产品类型和文档策略。"

    if state.next_action != NextAction.PARSE_SOURCES:
        return ""

    references = [
        source
        for source in state.source_registry
        if source.source_type == SourceType.REFERENCE_SOFT_COPYRIGHT_DOC
    ]
    screenshots = [
        source
        for source in state.source_registry
        if source.source_type == SourceType.SCREENSHOT
        or source.allowed_usage == AllowedUsage.DISPLAY_MATERIAL_ONLY
    ]
    product_documents = [
        source
        for source in state.source_registry
        if source.is_product_source
        and source.allowed_usage == AllowedUsage.FACTUAL_EVIDENCE
        and source.source_type != SourceType.SCREENSHOT
        and source.file_type
        in {
            FileType.DOCX,
            FileType.PDF,
            FileType.MD,
            FileType.TXT,
            FileType.HTML,
        }
    ]

    if product_documents:
        return (
            "检测到您已上传自有产品资料。\n\n"
            "如果希望开始生成《软件著作权文档》，请回复：“开始”。\n\n"
            "我将先解析资料、构建证据、理解产品内容，并在需要确认时暂停让您确认。"
        )
    if references and len(references) == len(state.source_registry):
        return (
            "已收到外部参考资料。它只能用于参考目录、章法、配图方式和语言风格，"
            "不能作为产品事实来源。\n\n要开始生成软著，还需要上传自有产品资料。"
        )
    if screenshots:
        return (
            "已收到产品截图。截图仅用于配图候选和展示，不做 OCR，也不能作为产品事实证据。\n\n"
            "要开始生成软著，请继续上传自有产品文档，例如产品介绍、PRD、HLD、详细设计或用户手册。"
        )
    return ""


def confirmation_card_for_state(state: DocForgeState) -> dict[str, object] | None:
    if state.workflow_status != WorkflowStatus.USER_CONFIRM_REQUIRED:
        return None
    strategy = state.template_strategy
    diagnosis = state.diagnosis_result
    if strategy is None:
        return None

    decision = AutoConfirmationPolicy().evaluate(state)
    product_type = str(diagnosis.primary_type) if diagnosis is not None else "待确认"
    template_name = strategy.base_template_name or "推荐文档策略"
    sections = list(strategy.recommended_chapters)
    if not sections:
        sections = ["引言", "软件概述", "核心功能说明"]

    actions = [
        {
            "actionId": "action_use_agent_recommendation",
            "actionType": "use_agent_recommendation",
            "label": "采用系统推荐并继续",
            "variant": "primary",
            "disabled": False,
            "description": "采用 Agent 根据自有产品资料得出的产品类型并继续。",
            "payload": {
                "selected_product_type": product_type,
                "use_agent_recommendation": True,
            },
        }
    ]
    if decision.user_selected_product_type and decision.user_selected_product_type != "让 Agent 根据资料判断":
        actions.append(
            {
                "actionId": "action_use_user_selection",
                "actionType": "use_user_selection",
                "label": "保留我的选择并继续",
                "variant": "secondary",
                "disabled": False,
                "description": "明确采用右侧当前选择，并继续冻结文档计划。",
                "payload": {
                    "selected_product_type": decision.user_selected_product_type,
                    "use_agent_recommendation": False,
                },
            }
        )

    return {
        "cardId": f"card-{state.run_id}-doc-plan-confirm",
        "cardType": "doc_plan_confirm",
        "title": "需要确认产品类型和文档策略",
        "summary": f"{decision.reason} 产品类型：{product_type}；文档策略：{template_name}。",
        "sections": sections,
        "payload": {
            "recommendedProductType": decision.recommended_product_type,
            "userSelectedProductType": decision.user_selected_product_type,
            "productTypeConflict": decision.product_type_conflict,
            "recommendedDocType": template_name,
            "selectedDocType": decision.selected_doc_type,
            "referenceStyleStrength": decision.selected_reference_style_strength,
            "reason": decision.reason,
            "evidenceBoundary": "产品事实只来自自有产品文档；外部参考资料和截图不会作为产品事实证据。",
        },
        "actions": actions,
    }


def confirmation_state_for_state(state: DocForgeState) -> ConfirmationStateView | None:
    if state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED:
        decision = AutoConfirmationPolicy().evaluate(state)
        return ConfirmationStateView(
            required=True,
            auto_confirmed=False,
            can_auto_confirm=decision.can_auto_confirm,
            reason=decision.reason,
            recommended_product_type=decision.recommended_product_type,
            user_selected_product_type=decision.user_selected_product_type,
            product_type_conflict=decision.product_type_conflict,
            recommended_doc_type=(
                state.template_strategy.base_template_name if state.template_strategy else ""
            ),
            selected_doc_type=decision.selected_doc_type,
            reference_style_strength=decision.selected_reference_style_strength,
        )

    result = latest_confirmation_result(state)
    if not result:
        return None
    return ConfirmationStateView(
        required=False,
        auto_confirmed=bool(result.get("auto_confirmed")),
        can_auto_confirm=bool(result.get("can_auto_confirm")),
        reason=str(result.get("reason", "")),
        recommended_product_type=str(result.get("recommended_product_type", "")),
        user_selected_product_type=str(result.get("user_selected_product_type", "")),
        product_type_conflict=bool(result.get("product_type_conflict")),
        recommended_doc_type=str(result.get("selected_doc_type", "")),
        selected_doc_type=str(result.get("selected_doc_type", "")),
        reference_style_strength=str(result.get("selected_reference_style_strength", "")),
        message=str(result.get("message", "")),
    )


def persisted_confirmation_message(state: DocForgeState) -> str:
    result = latest_confirmation_result(state)
    return str(result.get("message", "")) if result else ""


def latest_confirmation_result(state: DocForgeState) -> dict[str, object] | None:
    for confirmation in reversed(state.human_confirmations):
        if (
            confirmation.confirmation_type == ConfirmationType.TEMPLATE_STRATEGY
            and confirmation.status == ConfirmationStatus.CONFIRMED
            and not confirmation.metadata.get("invalidated_by_strategy_change")
        ):
            raw = confirmation.metadata.get(CONFIRMATION_RESULT_KEY)
            if isinstance(raw, dict):
                result = dict(raw)
                result.setdefault(
                    "auto_confirmed",
                    confirmation.metadata.get(CONFIRMATION_SOURCE_KEY) == "auto",
                )
                return result
    return None


def available_actions_for_state(state: DocForgeState) -> list[AgentActionView]:
    actions: list[AgentActionView] = []
    if state.next_action == NextAction.INGEST_MATERIALS:
        actions.append(
            AgentActionView(
                action_id="action_upload_sources",
                action_type="open_upload",
                label="上传资料",
                primary=True,
                disabled=False,
                description="上传参考软著、自有产品资料或产品截图。",
            )
        )
    elif state.next_action == NextAction.ASK_HUMAN_CONFIRMATION:
        actions.append(
            AgentActionView(
                action_id="action_ask_human_confirmation",
                action_type=state.next_action.value,
                label="请先确认产品类型和文档策略",
                primary=True,
                disabled=True,
                description="请在确认卡片中选择采用系统推荐或保留你的选择。",
            )
        )
    elif state.next_action != NextAction.STOP:
        actions.append(
            AgentActionView(
                action_id=f"action_{state.next_action.value}",
                action_type=state.next_action.value,
                label=next_action_label(state.next_action),
                primary=True,
                disabled=False,
                description="该动作会经过后端状态校验后推进。",
            )
        )
    actions.append(
        AgentActionView(
            action_id="action_refresh_diagnostics",
            action_type="refresh_diagnostics",
            label="刷新诊断",
            primary=False,
            disabled=False,
            description="重新读取当前任务健康状态。",
        )
    )
    return actions


def export_artifacts_for_state(state: DocForgeState, *, data_dir: Path) -> list[ExportArtifactView]:
    run_dir = get_run_dir(state.run_id, data_dir)
    docx_path = None
    if state.export_result and state.export_result.docx_path:
        docx_path = (run_dir / state.export_result.docx_path).resolve()
    is_risk = state.workflow_status == WorkflowStatus.RISK_EXPORTED
    is_final = state.workflow_status == WorkflowStatus.FINAL_EXPORTED
    return [
        ExportArtifactView(
            artifact_id=f"{state.run_id}:final_docx",
            name="正常版 DOCX",
            type="normal_docx",
            status_label="已生成" if is_final and docx_path and docx_path.exists() else "未生成",
            downloadable=bool(is_final and docx_path and docx_path.exists()),
        ),
        ExportArtifactView(
            artifact_id=f"{state.run_id}:risk_docx",
            name="风险版 DOCX",
            type="risk_docx",
            status_label="已生成" if is_risk and docx_path and docx_path.exists() else "未生成",
            downloadable=bool(is_risk and docx_path and docx_path.exists()),
        ),
    ]


def diagnostics_to_view(report: object, stage_label: str) -> DiagnosticSummaryView:
    issues = getattr(report, "issues", [])
    counts = SeverityCountsView()
    views: list[DiagnosticIssueView] = []
    for issue in issues:
        severity = str(getattr(issue, "severity", "info"))
        if severity.endswith(".INFO"):
            severity = "info"
        elif severity.endswith(".WARNING"):
            severity = "warning"
        elif severity.endswith(".ERROR"):
            severity = "error"
        severity = severity.split(".")[-1].lower()
        if severity == "info":
            counts.info += 1
        elif severity == "warning":
            counts.warning += 1
        elif severity == "error":
            counts.error += 1
        views.append(
            DiagnosticIssueView(
                severity=severity,
                code=str(getattr(issue, "code", "diagnostic")),
                message=str(getattr(issue, "user_message", "当前任务状态已检查。")),
                suggested_action=str(getattr(issue, "suggested_action", "")),
            )
        )
    is_healthy = bool(getattr(report, "is_healthy", False))
    return DiagnosticSummaryView(
        health_label="正常，可继续" if is_healthy else "存在问题，请先处理",
        stage_label=stage_label,
        next_suggestion=str(getattr(report, "suggested_user_action", "")) or "查看下一步建议",
        issues=views,
        severity_counts=counts,
    )
