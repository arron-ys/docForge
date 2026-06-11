import json
from pathlib import Path

import streamlit as st

from docforge_core.agents.audit_agent import AuditAgentService
from docforge_core.agents.figure_slot_planner import FigureSlotPlannerService
from docforge_core.agents.human_confirm_gate import HumanConfirmGate
from docforge_core.agents.human_confirm_pipeline_service import HumanConfirmPipelineService
from docforge_core.agents.outline_agent import OutlineAgent
from docforge_core.agents.revision_loop_service import RevisionLoopService
from docforge_core.agents.writer_agent import WriterAgent
from docforge_core.domain.enums import SourceType, WorkflowStatus
from docforge_core.domain.schemas import TemplateConfirmationDecision
from docforge_core.evidence.extractor import EvidenceExtractorService
from docforge_core.evidence.qdrant_store import QdrantStore
from docforge_core.exporters.docx_exporter import DocxExportService
from docforge_core.gates.plan_quality_gate import PlanQualityGate
from docforge_core.io.file_registry import SourceFileRegistry
from docforge_core.io.state_store import StateStore
from docforge_core.llm.provider_factory import create_llm_provider
from docforge_core.parsers.source_parsing_service import SourceParsingService
from docforge_core.workflow import WorkflowOrchestratorService, build_workflow_orchestrator
from docforge_core.workflow.wiring import LazyWriterAgent as _LazyWriterAgent
from docforge_core.workflow.diagnostics import WorkflowDiagnosticsService
from docforge_core.workflow.e2e_sample_runner import load_e2e_sample_project
from docforge_core.workflow.user_facing_errors import UserFacingErrorMapper

STAGE_TEXT = "Sprint 16：产品级端到端验收"
JINA_KEY_MESSAGE = (
    "当前默认 EmbeddingProvider 为 jina，但未配置 JINA_API_KEY。请在 .env 中配置 "
    "JINA_API_KEY，或将 DEFAULT_EMBEDDING_PROVIDER 设置为 mock 仅用于本地测试。"
)
LLM_KEY_MESSAGE = (
    "当前默认 LLMProvider 需要 API Key。若仅做本地测试，可将 DEFAULT_LLM_PROVIDER 设置为 mock。"
)

PRODUCT_SOURCE_TYPE_OPTIONS: dict[str, SourceType] = {
    "product_intro_doc": SourceType.PRODUCT_INTRO_DOC,
    "prd": SourceType.PRD,
    "hld": SourceType.HLD,
    "detailed_design_doc": SourceType.DETAILED_DESIGN_DOC,
    "other": SourceType.OTHER,
}


def main() -> None:
    st.title("墨衡 DocForge")
    st.write("软件著作权文档生成系统")
    st.info(f"当前阶段：{STAGE_TEXT}")

    store = StateStore()
    run_id = _render_run_task(store)
    if run_id is None:
        return

    registry = SourceFileRegistry(run_id)
    _render_reference_upload(store, registry, run_id)
    _render_product_upload(store, registry, run_id)
    _render_screenshot_upload(store, registry, run_id)
    _render_workflow_panel(store, run_id)
    with st.expander("开发调试入口", expanded=False):
        _render_state_table(store, run_id)


def _build_workflow_orchestrator(store: StateStore) -> WorkflowOrchestratorService:
    return build_workflow_orchestrator(store)


def _create_ui_llm_provider():
    return create_llm_provider()


def _build_template_confirmation_decision(
    store: StateStore,
    run_id: str,
    risk_acknowledged: bool,
) -> TemplateConfirmationDecision:
    gate = HumanConfirmGate(store)
    state = store.load_state(run_id)
    decision = gate.build_default_decision(state)
    decision.risk_acknowledged = risk_acknowledged
    if risk_acknowledged and state.template_strategy is not None:
        decision.acknowledged_risk_chapters = list(state.template_strategy.risk_chapters)
    return decision


def _render_workflow_panel(store: StateStore, run_id: str) -> None:
    st.header("主流程")
    state = store.load_state(run_id)
    orchestrator = _build_workflow_orchestrator(store)
    preview = orchestrator.get_summary(run_id)
    health = WorkflowDiagnosticsService(store).inspect(run_id)
    _render_health_report(health)
    st.write(f"说明：{preview.description}")
    _render_sample_project_loader(store, run_id)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("执行下一步", key=f"wf_next_{run_id}"):
            _run_workflow_action(lambda: orchestrator.run_next_step(run_id))
    with col2:
        if st.button("执行到人工确认", key=f"wf_until_human_{run_id}"):
            _run_workflow_action(
                lambda: orchestrator.run_until_human_confirmation_required(run_id)
            )
    with col3:
        risk_chapters = state.template_strategy.risk_chapters if state.template_strategy else []
        risk_acknowledged = True
        if risk_chapters:
            st.warning("风险章节：" + "、".join(risk_chapters))
            risk_acknowledged = st.checkbox(
                "我已知晓风险章节不会自动写入当前功能。",
                key=f"wf_risk_ack_{run_id}",
            )
        confirm_disabled = state.workflow_status != WorkflowStatus.USER_CONFIRM_REQUIRED
        if st.button(
            "确认模板并继续",
            type="primary",
            key=f"wf_confirm_{run_id}",
            disabled=confirm_disabled or bool(risk_chapters and not risk_acknowledged),
        ):
            decision = _build_template_confirmation_decision(
                store,
                run_id,
                risk_acknowledged=risk_acknowledged,
            )
            _run_workflow_action(
                lambda: orchestrator.submit_human_confirmation(run_id, decision)
            )
    with col4:
        if st.button("继续到终态", key=f"wf_terminal_{run_id}"):
            _run_workflow_action(lambda: orchestrator.run_until_terminal(run_id))

    refreshed = store.load_state(run_id)
    if refreshed.export_result and refreshed.export_result.docx_path:
        docx_path = store.data_dir / "runs" / refreshed.run_id / refreshed.export_result.docx_path
        if docx_path.exists():
            _render_docx_download(str(docx_path), "下载 DOCX")


def _render_health_report(health) -> None:
    st.write(f"run_id：{health.run_id}")
    st.write(f"workflow_status：{health.workflow_status}")
    st.write(f"next_action：{health.next_action}")
    if health.can_download_docx:
        st.success("健康状态：已完成，可下载 DOCX。")
    elif health.needs_human_confirmation:
        st.info("健康状态：等待用户确认。")
    elif health.is_healthy and health.can_continue:
        st.success("健康状态：正常，可继续。")
    elif health.is_healthy:
        st.info("健康状态：正常。")
    else:
        st.error("健康状态：错误阻断。")
    st.write(f"下一步建议：{health.suggested_user_action}")
    if not health.is_healthy:
        st.error(health.user_message)
    with st.expander("开发调试信息", expanded=False):
        st.write(health.developer_message)
        st.dataframe(
            [
                {
                    "severity": item.severity.value,
                    "code": item.code,
                    "developer_message": item.developer_message,
                    "suggested_action": item.suggested_action,
                }
                for item in health.issues
            ],
            use_container_width=True,
        )


def _run_workflow_action(action):
    mapper = UserFacingErrorMapper()
    try:
        summary = action()
    except ValueError as exc:
        if "JINA_API_KEY" in str(exc):
            st.error(JINA_KEY_MESSAGE)
        elif "API_KEY" in str(exc):
            st.error(LLM_KEY_MESSAGE)
        else:
            mapped = mapper.map_error(exc)
            st.error(mapped.user_message)
            with st.expander("开发调试信息", expanded=False):
                st.write(mapped.developer_message)
        return
    except Exception as exc:
        mapped = mapper.map_error(exc)
        st.error(mapped.user_message)
        with st.expander("开发调试信息", expanded=False):
            st.exception(exc)
        return
    if summary.success:
        st.success(summary.description)
    else:
        error = summary.error or summary.description
        if "JINA_API_KEY" in error:
            st.error(JINA_KEY_MESSAGE)
        elif "API_KEY" in error:
            st.error(LLM_KEY_MESSAGE)
        else:
            mapped = mapper.map_error(error)
            st.error(mapped.user_message)
            with st.expander("开发调试信息", expanded=False):
                st.write(mapped.developer_message)
    st.write(f"状态：{summary.workflow_status} / {summary.next_action}")
    st.write(f"下一步：{summary.next_operation}")
    if summary.success:
        st.rerun()


def _render_sample_project_loader(store: StateStore, run_id: str) -> None:
    with st.expander("样例工程", expanded=False):
        st.caption("加载本地样例工程，只登记 source，不自动执行流程。")
        if st.button("加载本地样例工程", key=f"load_sample_{run_id}"):
            try:
                result = load_e2e_sample_project(store, run_id)
            except Exception as exc:
                mapped = UserFacingErrorMapper().map_error(exc)
                st.error(mapped.user_message)
                with st.expander("开发调试信息", expanded=False):
                    st.write(mapped.developer_message)
            else:
                if result.skipped_existing:
                    st.info("样例工程已加载，本次未重复导入。")
                else:
                    st.success(f"已导入 {result.imported_count} 个样例 source。")
                st.rerun()
        state = store.load_state(run_id)
        sample_sources = [
            item
            for item in state.source_registry
            if item.metadata.get("sample_fixture") == "e2e_sample"
        ]
        if sample_sources:
            counts = {
                "reference": sum(item.is_reference_source for item in sample_sources),
                "product": sum(
                    item.is_product_source and item.source_type != SourceType.SCREENSHOT
                    for item in sample_sources
                ),
                "screenshot": sum(item.source_type == SourceType.SCREENSHOT for item in sample_sources),
            }
            st.caption(
                "已导入 source 数："
                f"{len(sample_sources)}；reference={counts['reference']}，"
                f"product={counts['product']}，screenshot={counts['screenshot']}"
            )
            st.dataframe(
                [
                    {
                        "file_name": item.file_name,
                        "source_type": item.source_type.value,
                        "corpus": item.corpus_type.value,
                        "usage": item.allowed_usage.value,
                        "parse_status": item.parse_status.value,
                    }
                    for item in sample_sources
                ],
                use_container_width=True,
            )


def _create_outline_with_ui_provider(store: StateStore, run_id: str):
    llm_provider = _create_ui_llm_provider()
    return OutlineAgent(store, llm_provider=llm_provider).create_outline(run_id)


def _run_plan_quality_gate_with_ui_provider(store: StateStore, run_id: str):
    llm_provider = _create_ui_llm_provider()
    return PlanQualityGate(store, llm_provider=llm_provider).run(run_id)


def _write_v1_draft_with_ui_provider(store: StateStore, run_id: str):
    llm_provider = _create_ui_llm_provider()
    return WriterAgent(store, llm_provider=llm_provider).write_v1_draft(run_id)


def _plan_figure_slots(store: StateStore, run_id: str):
    return FigureSlotPlannerService(store).plan_figure_slots(run_id)


def _audit_draft_with_ui_provider(store: StateStore, run_id: str):
    llm_provider = _create_ui_llm_provider()
    return AuditAgentService(store, llm_provider=llm_provider).audit_draft(run_id)


def _run_draft_quality_gate(store: StateStore, run_id: str):
    return RevisionLoopService(store).run_quality_gate_for_current_draft(run_id)


def _revise_draft_with_ui_provider(store: StateStore, run_id: str):
    llm_provider = _create_ui_llm_provider()
    return RevisionLoopService(store, llm_provider=llm_provider).revise_current_draft(run_id)


def _audit_revised_draft_with_ui_provider(store: StateStore, run_id: str):
    llm_provider = _create_ui_llm_provider()
    return RevisionLoopService(store, llm_provider=llm_provider).audit_revised_draft(run_id)


def _export_docx(store: StateStore, run_id: str):
    return DocxExportService(store).export_current_docx(run_id)


def _render_run_task(store: StateStore) -> str | None:
    st.header("运行任务")
    if "run_id" not in st.session_state:
        if st.button("创建新任务", type="primary"):
            state = store.create_initial_state()
            st.session_state["run_id"] = state.run_id
            st.success("新任务已创建")
            st.rerun()
        return None

    run_id = str(st.session_state["run_id"])
    st.code(run_id, language=None)
    return run_id


def _render_reference_upload(
    store: StateStore, registry: SourceFileRegistry, run_id: str
) -> None:
    st.header("参考软著资料上传")
    st.caption(
        "外部参考软著只能用于学习目录结构、章节写法、配图方式和语言风格，"
        "不能作为产品事实来源。"
    )
    uploaded_files = st.file_uploader(
        "允许上传：docx / pdf / md / txt",
        type=["docx", "pdf", "md", "txt"],
        accept_multiple_files=True,
        key="reference_files",
    )
    if st.button("保存参考软著资料", disabled=not uploaded_files):
        for uploaded_file in uploaded_files or []:
            source_item = registry.register_reference_file(
                file_name=uploaded_file.name,
                content=uploaded_file.getvalue(),
            )
            store.add_source_item(run_id, source_item)
        st.success("参考软著资料已保存")
        st.rerun()


def _render_product_upload(
    store: StateStore, registry: SourceFileRegistry, run_id: str
) -> None:
    st.header("自有产品资料上传")
    st.caption(
        "自有产品资料才是产品事实来源，可包括产品介绍、PRD、HLD、详细设计文档等。"
    )
    selected_source_type = st.selectbox(
        "资料来源类型",
        options=list(PRODUCT_SOURCE_TYPE_OPTIONS.keys()),
        key="product_source_type",
    )
    uploaded_files = st.file_uploader(
        "允许上传：docx / pdf / md / txt / html",
        type=["docx", "pdf", "md", "txt", "html"],
        accept_multiple_files=True,
        key="product_files",
    )
    if st.button("保存自有产品资料", disabled=not uploaded_files):
        source_type = PRODUCT_SOURCE_TYPE_OPTIONS[selected_source_type]
        for uploaded_file in uploaded_files or []:
            source_item = registry.register_product_file(
                file_name=uploaded_file.name,
                content=uploaded_file.getvalue(),
                source_type=source_type,
            )
            store.add_source_item(run_id, source_item)
        st.success("自有产品资料已保存")
        st.rerun()


def _render_screenshot_upload(
    store: StateStore, registry: SourceFileRegistry, run_id: str
) -> None:
    st.header("产品截图上传")
    st.caption("产品截图仅用于补图占位和展示材料登记，MVP 不做 OCR、视觉识别或产品事实证明。")
    uploaded_files = st.file_uploader(
        "允许上传：png / jpg / jpeg / webp",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key="screenshot_files",
    )
    if st.button("保存产品截图", disabled=not uploaded_files):
        for uploaded_file in uploaded_files or []:
            source_item = registry.register_screenshot_file(
                file_name=uploaded_file.name,
                content=uploaded_file.getvalue(),
            )
            store.add_source_item(run_id, source_item)
        st.success("产品截图已保存")
        st.rerun()


def _render_state_table(store: StateStore, run_id: str) -> None:
    st.header("状态")
    state = store.load_state(run_id)
    source_rows = [
        {
            "source_id": item.source_id,
            "source_type": item.source_type.value,
            "file_type": item.file_type.value,
            "corpus_type": item.corpus_type.value,
            "allowed_usage": item.allowed_usage.value,
            "file_name": item.file_name,
            "file_path": item.file_path,
            "parse_status": item.parse_status.value,
            "parse_error": item.parse_error,
        }
        for item in state.source_registry
    ]
    st.dataframe(source_rows, use_container_width=True)

    if st.button("解析已上传资料", disabled=not state.source_registry):
        parsed_state = SourceParsingService().parse_run(run_id)
        failed_sources = [
            item for item in parsed_state.source_registry if item.parse_status.value == "failed"
        ]
        if failed_sources:
            st.warning(f"解析完成，但有 {len(failed_sources)} 个资料解析失败。")
        else:
            st.success("解析完成")
        st.rerun()

    st.header("ParsedAssets")
    asset_rows = [
        {
            "asset_id": item.asset_id,
            "source_id": item.source_id,
            "asset_type": item.asset_type.value,
            "title": item.title,
            "summary": item.summary,
            "extracted_text_ref": item.extracted_text_ref,
            "image_ref": item.image_ref,
            "page_number": item.page_number,
        }
        for item in state.parsed_assets
    ]
    st.dataframe(asset_rows, use_container_width=True)

    if st.button("生成 Evidence 并写入 Qdrant", disabled=not state.parsed_assets):
        try:
            evidence_state = EvidenceExtractorService().extract_run(run_id)
            indexed_count = QdrantStore().upsert_evidence_items(
                evidence_state.qdrant_collection,
                evidence_state.evidence_map,
            )
        except ValueError as exc:
            if "JINA_API_KEY" in str(exc):
                st.error(JINA_KEY_MESSAGE)
            else:
                st.exception(exc)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success(
                f"已生成 {len(evidence_state.evidence_map)} 个 EvidenceItem，"
                f"写入 Qdrant {indexed_count} 条。"
            )
            state = evidence_state

    st.header("EvidenceMap")
    evidence_rows = [
        {
            "evidence_id": item.evidence_id,
            "source_id": item.source_id,
            "source_type": item.source_type.value,
            "evidence_type": item.evidence_type.value,
            "corpus_type": item.corpus_type.value,
            "allowed_usage": item.allowed_usage.value,
            "evidence_strength": item.evidence_strength.value,
            "summary": item.summary,
            "tags": item.tags,
            "confidence": item.confidence,
        }
        for item in state.evidence_map
    ]
    st.dataframe(evidence_rows, use_container_width=True)

    if state.evidence_map and state.workflow_status != WorkflowStatus.EVIDENCE_MAPPED:
        st.caption(f"当前状态为 {state.workflow_status.value}，理解与诊断流程已运行或尚未就绪。")
    if st.button("运行理解与诊断", disabled=not state.evidence_map):
        if state.workflow_status != WorkflowStatus.EVIDENCE_MAPPED:
            st.info("请先生成 Evidence 并写入 Qdrant。")
        else:
            try:
                state = UnderstandingPipelineService().run_until_template_recommended(run_id)
            except ValueError as exc:
                if "API_KEY" in str(exc):
                    st.error(LLM_KEY_MESSAGE)
                else:
                    st.exception(exc)
            except Exception as exc:
                st.exception(exc)
            else:
                st.success("理解与诊断已完成，模板策略等待后续用户确认。")

    st.header("ReferenceStyleProfile")
    st.json(state.style_profile.model_dump(mode="json"))
    st.header("ProductProfile")
    st.json(state.product_profile.model_dump(mode="json"))
    st.header("ProductCapabilities")
    capability_rows = [
        {
            "capability_id": item.capability_id,
            "name": item.name,
            "capability_type": item.capability_type.value,
            "implementation_status": item.implementation_status.value,
            "validation_status": item.validation_status.value,
            "confidence": item.confidence,
            "evidence_ids": [support.evidence_id for support in item.evidence_supports],
            "quotes": [support.quote for support in item.evidence_supports],
            "reasoning": item.reasoning,
        }
        for item in state.product_capabilities
    ]
    st.dataframe(capability_rows, use_container_width=True)
    if state.warnings:
        st.header("Grounding Warnings")
        for warning in state.warnings:
            st.warning(warning)
    st.header("ProductFacts")
    fact_rows = [
        {
            "fact_id": item.fact_id,
            "fact_type": item.fact_type.value,
            "content": item.content,
            "implementation_status": item.implementation_status.value,
            "capability_type": item.capability_type.value if item.capability_type else None,
            "validation_status": item.validation_status.value,
            "source_ids": item.source_ids,
            "supporting_evidence_ids": item.supporting_evidence_ids,
        }
        for item in state.product_facts
    ]
    st.dataframe(fact_rows, use_container_width=True)
    st.header("DiagnosisResult")
    st.json(state.diagnosis_result.model_dump(mode="json") if state.diagnosis_result else {})
    st.header("TemplateStrategy")
    st.json(state.template_strategy.model_dump(mode="json") if state.template_strategy else {})
    _render_human_confirmation(store, state)
    _render_frozen_doc_plan(store, state)


def _render_human_confirmation(store: StateStore, state) -> None:
    st.header("HumanConfirmGate")
    if st.button(
        "准备用户确认",
        disabled=state.workflow_status != WorkflowStatus.TEMPLATE_RECOMMENDED,
    ):
        try:
            HumanConfirmGate(store).prepare_confirmation(state.run_id)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("模板策略已进入用户确认阶段。")
            st.rerun()

    risk_chapters = state.template_strategy.risk_chapters if state.template_strategy else []
    risk_acknowledged = False
    if risk_chapters:
        st.warning("风险章节：" + "、".join(risk_chapters))
        risk_acknowledged = st.checkbox(
            "我已知晓风险章节不会自动写入当前功能，后续如需纳入需人工确认。",
            key=f"risk_acknowledged_{state.run_id}",
        )

    can_accept = state.workflow_status in {
        WorkflowStatus.TEMPLATE_RECOMMENDED,
        WorkflowStatus.USER_CONFIRM_REQUIRED,
    }
    if st.button(
        "接受推荐方案并冻结计划",
        type="primary",
        disabled=not can_accept or bool(risk_chapters and not risk_acknowledged),
    ):
        try:
            HumanConfirmPipelineService(
                human_confirm_gate=HumanConfirmGate(store)
            ).accept_recommendation_and_freeze(
                state.run_id,
                risk_acknowledged=risk_acknowledged,
            )
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("推荐方案已确认，FrozenDocPlan 已冻结。")
            st.rerun()


def _render_frozen_doc_plan(store: StateStore, state) -> None:
    st.header("FrozenDocPlan")
    plan = state.frozen_doc_plan
    if plan is None:
        st.caption("尚未冻结文档计划。")
        return
    st.json(
        {
            "plan_id": plan.plan_id,
            "locked_status": plan.locked_status.value,
            "locked_top_level_chapters": plan.chapter_policy.get(
                "locked_top_level_chapters", []
            ),
            "allowed_current_feature_names": plan.feature_policy.get(
                "allowed_current_feature_names", []
            ),
            "forbidden_as_current_feature_names": plan.feature_policy.get(
                "forbidden_as_current_feature_names", []
            ),
            "factual_evidence_filter": plan.evidence_policy.get(
                "factual_evidence_filter", {}
            ),
            "style_reference_filter": plan.evidence_policy.get(
                "style_reference_filter", {}
            ),
            "downstream_permissions": plan.downstream_permissions,
        }
    )

    if st.button(
        "生成文档大纲",
        disabled=state.workflow_status != WorkflowStatus.PLAN_FROZEN,
    ):
        try:
            _create_outline_with_ui_provider(store, state.run_id)
        except ValueError as exc:
            if "API_KEY" in str(exc):
                st.error(LLM_KEY_MESSAGE)
            else:
                st.exception(exc)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("DocumentOutline 与 SectionPlan 已生成。")
            st.rerun()

    if st.button(
        "运行 PlanQualityGate",
        disabled=state.workflow_status != WorkflowStatus.OUTLINE_CREATED,
    ):
        try:
            _run_plan_quality_gate_with_ui_provider(store, state.run_id)
        except ValueError as exc:
            if "API_KEY" in str(exc):
                st.error(LLM_KEY_MESSAGE)
            else:
                st.exception(exc)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("PlanQualityGate 已完成。")
            st.rerun()

    st.header("DocumentOutline")
    if state.outline is None:
        st.caption("尚未生成文档大纲。")
    else:
        st.json(
            {
                "outline_id": state.outline.outline_id,
                "based_on_plan_id": state.outline.based_on_plan_id,
                "chapters": state.outline.chapters,
            }
        )

    st.header("SectionPlan")
    st.dataframe(
        [
            {
                "chapter_title": item.chapter_title,
                "section_title": item.section_title,
                "section_level": item.section_level,
                "parent_section_title": item.parent_section_title,
                "section_path": item.section_path,
                "writing_goal": item.writing_goal,
                "required_evidence_ids": item.required_evidence_ids,
                "required_capability_ids": item.required_capability_ids,
                "required_fact_ids": item.required_fact_ids,
                "needs_human_confirmation": item.needs_human_confirmation,
                "writing_constraints": item.writing_constraints,
            }
            for item in state.section_plan
        ],
        use_container_width=True,
    )

    st.header("PlanQualityGate")
    report = state.plan_quality_gate_report
    if report is None:
        st.caption("尚未运行生成前质量门禁。")
    else:
        st.json(
            {
                "passed": report.passed,
                "checklist_results": report.checklist_results,
                "blocker_issues": report.blocker_issues,
                "major_issues": report.major_issues,
                "minor_issues": report.minor_issues,
                "missing_information": report.missing_information,
            }
        )

    if st.button(
        "生成 v1 草稿",
        disabled=state.workflow_status != WorkflowStatus.PLAN_GATE_PASSED,
    ):
        try:
            _write_v1_draft_with_ui_provider(store, state.run_id)
        except ValueError as exc:
            if "API_KEY" in str(exc):
                st.error(LLM_KEY_MESSAGE)
            else:
                st.exception(exc)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("v1 草稿已生成")
            st.rerun()

    st.header("DraftVersions")
    st.dataframe(
        [
            {
                "draft_id": item.draft_id,
                "version_label": item.version_label.value,
                "based_on_plan_id": item.based_on_plan_id,
                "based_on_outline_id": item.based_on_outline_id,
                "content_ref": item.content_ref,
                "created_at": item.created_at,
            }
            for item in state.draft_versions
        ],
        use_container_width=True,
    )
    _render_figure_slots(store, state)


def _render_figure_slots(store: StateStore, state) -> None:
    st.header("FigureSlotPlanner")
    st.caption(
        "当前只是补图建议，未绑定真实截图；所有截图状态均为 missing，后续用户需要按清单补充截图。"
    )
    st.write(f"当前 workflow_status：{state.workflow_status.value}")
    if st.button(
        "生成配图补图清单",
        disabled=state.workflow_status != WorkflowStatus.DRAFT_V1_CREATED,
    ):
        try:
            result = _plan_figure_slots(store, state.run_id)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("配图补图清单已生成。")
            _render_figure_slot_result(result.model_dump(mode="json"))
            st.rerun()

    if state.figure_slots_ref:
        figure_path = store.data_dir / "runs" / state.run_id / state.figure_slots_ref
        if figure_path.exists():
            _render_figure_slot_result(
                json.loads(figure_path.read_text(encoding="utf-8"))
            )
        else:
            st.warning(f"state 中记录了 figure_slots_ref，但文件不存在：{state.figure_slots_ref}")
    _render_draft_audit(store, state)


def _render_figure_slot_result(result: dict) -> None:
    st.subheader("FigureSlotSummary")
    st.json(result.get("summary", {}))
    st.subheader("FigureSlots")
    st.dataframe(
        [
            {
                "section_path": " / ".join(slot.get("section_path", [])),
                "section_title": slot.get("section_title"),
                "recommended_caption": slot.get("recommended_caption"),
                "recommended_screenshot": slot.get("recommended_screenshot"),
                "required": slot.get("required"),
                "status": slot.get("status"),
                "user_action": slot.get("user_action"),
                "warnings": slot.get("warnings"),
            }
            for slot in result.get("figure_slots", [])
        ],
        use_container_width=True,
    )


def _render_draft_audit(store: StateStore, state) -> None:
    st.header("AuditAgent")
    figure_path = store.data_dir / "runs" / state.run_id / "drafts" / "figure_slots_v1.json"
    can_audit = (
        state.workflow_status == WorkflowStatus.FIGURE_SLOTS_PLANNED
        and state.next_action.value == "audit_draft"
    ) or (
        state.workflow_status == WorkflowStatus.DRAFT_V1_CREATED
        and state.next_action.value == "audit_draft"
        and figure_path.exists()
    )
    if st.button("运行草稿审计", disabled=not can_audit):
        try:
            result = _audit_draft_with_ui_provider(store, state.run_id)
        except ValueError as exc:
            if "API_KEY" in str(exc):
                st.error(LLM_KEY_MESSAGE)
            else:
                st.exception(exc)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("草稿审计已完成，下一步为 RUN_DRAFT_QUALITY_GATE。")
            _render_audit_result(result.model_dump(mode="json"))
            st.rerun()

    if state.audit_report_ref:
        audit_path = store.data_dir / "runs" / state.run_id / state.audit_report_ref
        if audit_path.exists():
            _render_audit_result(json.loads(audit_path.read_text(encoding="utf-8")))
        else:
            st.warning(f"state 中记录了 audit_report_ref，但文件不存在：{state.audit_report_ref}")
    _render_revision_loop(store, state)


def _render_revision_loop(store: StateStore, state) -> None:
    st.header("DraftQualityGate / RevisionLoop")
    if st.button(
        "运行 DraftQualityGate",
        disabled=state.next_action.value != "run_draft_quality_gate",
    ):
        try:
            _run_draft_quality_gate(store, state.run_id)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("DraftQualityGate 已完成。")
            st.rerun()

    if st.button(
        "执行一次受控修订",
        disabled=state.next_action.value != "revise_draft",
    ):
        try:
            _revise_draft_with_ui_provider(store, state.run_id)
        except ValueError as exc:
            if "API_KEY" in str(exc):
                st.error(LLM_KEY_MESSAGE)
            else:
                st.exception(exc)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("受控修订稿已生成，必须重新审计。")
            st.rerun()

    if st.button(
        "审计修订稿",
        disabled=state.next_action.value != "audit_revised_draft",
    ):
        try:
            _audit_revised_draft_with_ui_provider(store, state.run_id)
        except ValueError as exc:
            if "API_KEY" in str(exc):
                st.error(LLM_KEY_MESSAGE)
            else:
                st.exception(exc)
        except Exception as exc:
            st.exception(exc)
        else:
            st.success("修订稿审计已完成，必须重新运行 DraftQualityGate。")
            st.rerun()

    if state.draft_quality_gate_report_ref:
        gate_path = store.data_dir / "runs" / state.run_id / state.draft_quality_gate_report_ref
        if gate_path.exists():
            st.json(json.loads(gate_path.read_text(encoding="utf-8")))
    _render_docx_export(store, state)


def _render_docx_export(store: StateStore, state) -> None:
    st.header("DOCX Export")
    if state.next_action.value == "export_docx":
        if st.button("导出 DOCX"):
            try:
                result = _export_docx(store, state.run_id)
            except Exception as exc:
                st.exception(exc)
            else:
                st.success("DOCX 已导出。")
                _render_docx_download(result.docx_path, "下载 DOCX")
    elif state.next_action.value == "export_risk_docx":
        if st.button("导出风险版 DOCX"):
            try:
                result = _export_docx(store, state.run_id)
            except Exception as exc:
                st.exception(exc)
            else:
                st.warning("风险版 DOCX 已导出，请人工复核。")
                _render_docx_download(result.docx_path, "下载风险版 DOCX")
    elif state.export_result and state.export_result.docx_path:
        docx_path = store.data_dir / "runs" / state.run_id / state.export_result.docx_path
        if docx_path.exists():
            _render_docx_download(str(docx_path), "下载已导出的 DOCX")


def _render_docx_download(docx_path: str, label: str) -> None:
    path = Path(docx_path)
    st.download_button(
        label,
        data=path.read_bytes(),
        file_name=path.name,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _render_audit_result(result: dict) -> None:
    st.subheader("AuditSummary")
    summary = result.get("summary", {})
    st.json(
        {
            "overall_passed": result.get("overall_passed"),
            "blocker_count": summary.get("blocker_count"),
            "major_count": summary.get("major_count"),
            "minor_count": summary.get("minor_count"),
            "suggestion_count": summary.get("suggestion_count"),
            "next_action": "RUN_DRAFT_QUALITY_GATE",
        }
    )
    sections_by_id = {
        item.get("section_id"): item.get("section_title")
        for item in result.get("section_summaries", [])
        if isinstance(item, dict)
    }
    st.subheader("AuditFindings")
    st.dataframe(
        [
            {
                "severity": item.get("severity"),
                "category": item.get("category"),
                "section_title": sections_by_id.get(item.get("section_id")),
                "message": item.get("message"),
                "recommendation": item.get("recommendation"),
            }
            for item in result.get("findings", [])
        ],
        use_container_width=True,
    )


if __name__ == "__main__":
    main()
