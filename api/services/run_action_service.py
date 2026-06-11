from __future__ import annotations

from api.action_guard import ActionGuard
from api.errors import (
    action_not_allowed,
    backend_internal_error,
    cannot_auto_confirm,
    confirmation_payload_invalid,
    model_config_missing,
    product_evidence_missing,
    reference_only_not_allowed,
    screenshot_only_not_allowed,
    source_missing,
    source_parse_failed,
    state_not_found,
    strategy_reset_required,
    workflow_dependency_missing,
)
from api.schemas import (
    ActionResultView,
    ConfirmDocPlanRequest,
    ConfirmProductTypeRequest,
    RunSettingsUpdateRequest,
)
from api.services.workspace_view_service import WorkspaceViewService
from docforge_core.config.runtime_model_config import RuntimeModelConfigService
from docforge_core.config.settings import Settings, get_settings
from docforge_core.domain.enums import (
    AllowedUsage,
    FileType,
    NextAction,
    SourceType,
    WorkflowStatus,
)
from docforge_core.domain.schemas import DocForgeState
from docforge_core.io.state_store import StateStore
from docforge_core.workflow import WorkflowOrchestratorService, WorkflowRunSummary
from docforge_core.workflow.auto_confirmation import (
    AutoConfirmationPolicy,
    build_confirmation_payload,
    product_type_option_for_diagnosis,
)
from docforge_core.workflow.run_settings import (
    doc_output_type_label,
    get_run_settings,
    product_type_label,
    reference_style_strength_label,
    set_run_settings,
)
from docforge_core.workflow.strategy_reset import (
    StrategyResetService,
    StrategyRestartRequiredError,
    strategy_change_mode,
)


class RunActionService:
    def __init__(
        self,
        *,
        state_store: StateStore,
        orchestrator: WorkflowOrchestratorService,
        workspace_service: WorkspaceViewService,
        model_config_service: RuntimeModelConfigService,
        settings: Settings | None = None,
    ) -> None:
        self.state_store = state_store
        self.orchestrator = orchestrator
        self.workspace_service = workspace_service
        self.model_config_service = model_config_service
        self.settings = settings or get_settings()
        self.guard = ActionGuard()

    def run_next(self, run_id: str) -> ActionResultView:
        state = self._load_state(run_id)
        self.guard.ensure_allowed(state, "next")
        summary = self.orchestrator.run_next_step(run_id)
        summary, message = self._try_auto_confirmation(run_id, summary)
        return self._result_from_summary(run_id, summary, message=message)

    def start(self, run_id: str) -> ActionResultView:
        state = self._load_state(run_id)
        if (
            state.workflow_status == WorkflowStatus.USER_CONFIRM_REQUIRED
            and state.next_action == NextAction.ASK_HUMAN_CONFIRMATION
        ):
            summary, message = self._try_auto_confirmation(
                run_id,
                self.orchestrator.get_summary(run_id),
            )
            return self._result_from_summary(run_id, summary, message=message)
        self.guard.ensure_allowed(state, "start")
        self._ensure_start_requirements(state)

        summary = self.orchestrator.run_until_human_confirmation_required(
            run_id,
            max_steps=8,
        )
        summary, message = self._try_auto_confirmation(run_id, summary)
        return self._result_from_summary(run_id, summary, message=message)

    def confirm_product_type(
        self,
        run_id: str,
        payload: ConfirmProductTypeRequest,
    ) -> ActionResultView:
        return self._submit_manual_confirmation(
            run_id,
            endpoint_action="confirm-product-type",
            selected_product_type=payload.selected_product_type,
            use_agent_recommendation=payload.use_agent_recommendation,
            selected_doc_type=payload.selected_doc_type,
            reference_style_strength=payload.reference_style_strength,
            user_note=payload.user_note or payload.reason,
        )

    def confirm_doc_plan(
        self,
        run_id: str,
        payload: ConfirmDocPlanRequest,
    ) -> ActionResultView:
        if not payload.accepted:
            raise cannot_auto_confirm(
                "当前版本尚未接入手动修改模板和目录的表单。请先接受推荐方案，或调整资料后重新生成策略。"
            )
        return self._submit_manual_confirmation(
            run_id,
            endpoint_action="confirm-doc-plan",
            selected_product_type=payload.selected_product_type,
            use_agent_recommendation=payload.use_agent_recommendation,
            selected_doc_type=payload.selected_doc_type,
            reference_style_strength=payload.reference_style_strength,
            user_note=payload.note,
        )

    def update_settings(
        self,
        run_id: str,
        payload: RunSettingsUpdateRequest,
    ) -> ActionResultView:
        return self._update_settings(run_id, payload, allow_restart=False)

    def restart_strategy(
        self,
        run_id: str,
        payload: RunSettingsUpdateRequest,
    ) -> ActionResultView:
        return self._update_settings(run_id, payload, allow_restart=True)

    def export_final_docx(self, run_id: str) -> ActionResultView:
        return self._execute_guarded(run_id, "export-final-docx")

    def export_risk_docx(self, run_id: str) -> ActionResultView:
        return self._execute_guarded(run_id, "export-risk-docx")

    def _load_state(self, run_id: str) -> DocForgeState:
        try:
            return self.state_store.load_state(run_id)
        except FileNotFoundError as exc:
            raise state_not_found(run_id) from exc

    def _execute_guarded(self, run_id: str, endpoint_action: str) -> ActionResultView:
        state = self._load_state(run_id)
        self.guard.ensure_allowed(state, endpoint_action)

        summary = self.orchestrator.run_next_step(run_id)
        return self._result_from_summary(run_id, summary)

    def _submit_manual_confirmation(
        self,
        run_id: str,
        *,
        endpoint_action: str,
        selected_product_type: str | None,
        use_agent_recommendation: bool,
        selected_doc_type: str | None,
        reference_style_strength: str | None,
        user_note: str | None,
    ) -> ActionResultView:
        state = self._load_state(run_id)
        self.guard.ensure_allowed(state, endpoint_action)
        original_state = state.model_copy(deep=True)
        if state.diagnosis_result is None:
            raise confirmation_payload_invalid("当前缺少产品类型判断结果。")

        settings = get_run_settings(state)
        if selected_doc_type:
            settings["doc_output_type"] = selected_doc_type
        if reference_style_strength:
            settings["reference_style_strength"] = reference_style_strength

        recommended_product_type = str(state.diagnosis_result.primary_type or "").strip()
        if use_agent_recommendation:
            confirmed_product_type = recommended_product_type
            recommended_option = product_type_option_for_diagnosis(recommended_product_type)
            if recommended_option:
                settings["product_type_hint"] = recommended_option
        else:
            raw_selection = (selected_product_type or "").strip()
            if not raw_selection:
                raise confirmation_payload_invalid("请明确选择采用哪一种产品类型。")
            confirmed_product_type = product_type_label(raw_selection)
        if not confirmed_product_type:
            raise confirmation_payload_invalid("确认的产品类型不能为空。")

        state.diagnosis_result.primary_type = confirmed_product_type
        set_run_settings(state, settings)
        self.state_store.save_state(state)

        try:
            decision = build_confirmation_payload(
                state,
                user_note=user_note or "用户在工作台确认采用当前推荐的产品类型和文档策略。",
            )
        except ValueError as exc:
            self.state_store.save_state(original_state)
            raise confirmation_payload_invalid(str(exc)) from exc

        metadata = self._confirmation_metadata(
            state,
            source="manual",
            selected_product_type=confirmed_product_type,
            message=(
                "已按你的选择确认产品类型和文档策略。"
                f"产品类型：{confirmed_product_type}；"
                f"文档类型：{doc_output_type_label(settings['doc_output_type'])}；"
                f"参考风格：{reference_style_strength_label(settings['reference_style_strength'])}。"
            ),
        )
        summary = self.orchestrator.submit_human_confirmation(
            run_id,
            decision,
            confirmation_source="manual",
            confirmation_metadata=metadata,
        )
        if not summary.success:
            self.state_store.save_state(original_state)
        return self._result_from_summary(run_id, summary, message=metadata["message"])

    def _try_auto_confirmation(
        self,
        run_id: str,
        summary: WorkflowRunSummary,
    ) -> tuple[WorkflowRunSummary, str | None]:
        if not summary.success:
            return summary, None
        state = self._load_state(run_id)
        decision = AutoConfirmationPolicy().evaluate(state)
        if not decision.can_auto_confirm or decision.confirmation_payload is None:
            return summary, None

        confirmed = self.orchestrator.submit_human_confirmation(
            run_id,
            decision.confirmation_payload,
            confirmation_source="auto",
            confirmation_metadata=decision.as_metadata(),
        )
        return confirmed, decision.message

    def _update_settings(
        self,
        run_id: str,
        payload: RunSettingsUpdateRequest,
        *,
        allow_restart: bool,
    ) -> ActionResultView:
        current = self._load_state(run_id)
        mode = strategy_change_mode(current)
        try:
            state = StrategyResetService(self.state_store).update_settings(
                run_id,
                payload.model_dump(),
                allow_restart=allow_restart,
            )
        except StrategyRestartRequiredError as exc:
            raise strategy_reset_required() from exc
        if mode == "restart":
            message = "关键策略已保存，当前生成结果已失效，系统将重新评估产品类型和文档策略。"
        elif mode == "reevaluate":
            message = "关键策略已保存，系统将重新评估产品类型和文档策略。"
        else:
            message = "关键策略已保存。"
        return ActionResultView(
            run_id=run_id,
            success=True,
            message=message,
            workspace=self.workspace_service.get_workspace(state.run_id),
        )

    def _result_from_summary(
        self,
        run_id: str,
        summary: WorkflowRunSummary,
        *,
        message: str | None = None,
    ) -> ActionResultView:
        if not summary.success:
            self._raise_workflow_error(summary.error or "当前动作执行失败，状态未推进。")
        return ActionResultView(
            run_id=run_id,
            success=True,
            message=message or summary.description,
            workspace=self.workspace_service.get_workspace(run_id),
        )

    @staticmethod
    def _confirmation_metadata(
        state: DocForgeState,
        *,
        source: str,
        selected_product_type: str,
        message: str,
    ) -> dict[str, object]:
        settings = get_run_settings(state)
        return {
            "can_auto_confirm": source == "auto",
            "auto_confirmed": source == "auto",
            "confirmation_source": source,
            "selected_product_type": selected_product_type,
            "selected_doc_type": doc_output_type_label(settings["doc_output_type"]),
            "selected_reference_style_strength": reference_style_strength_label(
                settings["reference_style_strength"]
            ),
            "recommended_product_type": (
                str(state.diagnosis_result.primary_type) if state.diagnosis_result else ""
            ),
            "user_selected_product_type": product_type_label(settings["product_type_hint"]),
            "product_type_conflict": False,
            "reason": "用户已在人工确认卡片中明确选择。",
            "message": message,
        }

    def _ensure_start_requirements(self, state: DocForgeState) -> None:
        if not state.source_registry:
            raise source_missing()

        reference_sources = [
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

        if not product_documents:
            if reference_sources and len(reference_sources) == len(state.source_registry):
                raise reference_only_not_allowed()
            if screenshots:
                raise screenshot_only_not_allowed()
            raise product_evidence_missing()

        if not self._model_config_available():
            raise model_config_missing()

    def _model_config_available(self) -> bool:
        llm_config = self.model_config_service.get_llm_config()
        embedding_config = self.model_config_service.get_embedding_config()
        if llm_config and embedding_config:
            return bool(llm_config.verified and embedding_config.verified)

        llm_provider = self.settings.default_llm_provider.lower()
        embedding_provider = self.settings.default_embedding_provider.lower()
        llm_available = (
            llm_provider == "mock"
            or (
                llm_provider == "qwen"
                and bool(self.settings.qwen_api_key.strip())
                and bool(self.settings.qwen_base_url.strip())
            )
            or (
                llm_provider == "deepseek"
                and bool(self.settings.deepseek_api_key.strip())
                and bool(self.settings.deepseek_base_url.strip())
            )
        )
        embedding_available = (
            embedding_provider == "mock"
            or (
                embedding_provider == "jina"
                and bool(self.settings.jina_api_key.strip())
            )
        )
        return llm_available and embedding_available

    def _raise_workflow_error(self, raw_error: str) -> None:
        error = self._safe_error_text(raw_error)
        lowered = error.lower()
        if "source_parsing_service" in error:
            raise workflow_dependency_missing(
                "解析服务未接入，当前后端不能执行资料解析。"
            )
        if "缺少工作流服务依赖" in error or "missing workflow" in lowered:
            raise workflow_dependency_missing(
                "后端工作流服务未完整接入，当前不能执行主流程。"
            )
        if "模型密钥未配置" in error or "api_key" in lowered or "api key" in lowered:
            raise model_config_missing()
        if "找不到已上传文件" in error:
            raise source_parse_failed(error)
        if "解析" in error or "parse" in lowered or "pdf 文件无法打开" in lowered:
            raise source_parse_failed("资料解析失败，请检查文件格式、文件内容或模型服务配置。")
        if "不支持当前 workflow_status" in error or "next_action" in error:
            raise action_not_allowed(error)
        raise backend_internal_error(error)

    @staticmethod
    def _safe_error_text(raw_error: str) -> str:
        if "Traceback" in raw_error or "\n  File " in raw_error:
            return "后端执行失败，请查看服务日志。"
        return raw_error.strip()[:300] or "后端执行失败，请稍后重试。"
