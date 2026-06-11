from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApiError(Exception):
    error_code: str
    message: str
    status_code: int = 400
    recoverable: bool = True
    suggested_action: str = ""


def run_not_found(run_id: str) -> ApiError:
    return ApiError(
        error_code="run_not_found",
        message="任务不存在，请确认 run_id 是否正确。",
        status_code=404,
        suggested_action="返回工作台并重新选择任务。",
    )


def state_not_found(run_id: str) -> ApiError:
    return ApiError(
        error_code="state_not_found",
        message="任务状态文件不存在，请先创建任务或重新上传资料。",
        status_code=404,
        suggested_action="创建新任务后再继续。",
    )


def invalid_run_id() -> ApiError:
    return ApiError(
        error_code="invalid_run_id",
        message="任务编号格式非法，系统已拒绝访问。",
        status_code=400,
        recoverable=False,
        suggested_action="返回工作台并重新选择任务。",
    )


def action_not_allowed(message: str) -> ApiError:
    return ApiError(
        error_code="action_not_allowed",
        message=message,
        status_code=409,
        suggested_action="刷新工作台后重新选择当前可执行动作。",
    )


def workflow_dependency_missing(message: str | None = None) -> ApiError:
    return ApiError(
        error_code="workflow_dependency_missing",
        message=message or "后端工作流服务未完整接入，当前不能执行主流程。",
        status_code=500,
        suggested_action="请检查 FastAPI 工作流服务装配。",
    )


def model_config_missing() -> ApiError:
    return ApiError(
        error_code="model_config_missing",
        message="模型密钥未配置或连接不可用。请先在右上角“配置密钥”中完成连接测试。",
        status_code=409,
        suggested_action="配置并测试 LLM 与 Embedding 密钥后再开始。",
    )


def model_connection_failed() -> ApiError:
    return ApiError(
        error_code="model_connection_failed",
        message="模型连接不可用。请重新测试 LLM 与 Embedding 连接。",
        status_code=409,
        suggested_action="检查 API Key、BaseURL、模型名称和网络环境。",
    )


def source_missing() -> ApiError:
    return ApiError(
        error_code="source_missing",
        message="要开始生成软著，请先上传自有产品资料。",
        status_code=409,
        suggested_action="请上传产品介绍、PRD、HLD、详细设计或用户手册等自有产品文档。",
    )


def source_parse_failed(message: str | None = None) -> ApiError:
    return ApiError(
        error_code="source_parse_failed",
        message=message or "资料解析失败，请检查文件格式、文件内容或模型服务配置。",
        status_code=409,
        suggested_action="请修复失败资料后重试，或重新上传支持的文档文件。",
    )


def product_evidence_missing() -> ApiError:
    return ApiError(
        error_code="product_evidence_missing",
        message="要开始生成软著，请先上传自有产品资料。",
        status_code=409,
        suggested_action="外部参考资料和截图不能作为产品事实来源。",
    )


def screenshot_only_not_allowed() -> ApiError:
    return ApiError(
        error_code="screenshot_only_not_allowed",
        message=(
            "当前只上传了产品截图。截图仅用于配图候选和展示，不做 OCR，"
            "也不能作为产品事实证据。请继续上传自有产品文档。"
        ),
        status_code=409,
        suggested_action="请上传产品介绍、PRD、HLD、详细设计或用户手册等文档。",
    )


def reference_only_not_allowed() -> ApiError:
    return ApiError(
        error_code="reference_only_not_allowed",
        message=(
            "当前只上传了外部参考资料。外部参考资料不能作为产品事实来源，"
            "请继续上传自有产品资料。"
        ),
        status_code=409,
        suggested_action="请上传自有产品文档后再开始。",
    )


def confirmation_not_required() -> ApiError:
    return ApiError(
        error_code="confirmation_not_required",
        message="当前不需要确认产品类型和文档策略。",
        status_code=409,
        suggested_action="请刷新工作台后选择当前可执行动作。",
    )


def confirmation_conflict(message: str | None = None) -> ApiError:
    return ApiError(
        error_code="confirmation_conflict",
        message=message or "系统判断结果与你当前选择不一致，请先确认采用哪一种产品类型。",
        status_code=409,
        suggested_action="请在确认卡片中选择采用系统推荐或保留你的选择。",
    )


def cannot_auto_confirm(message: str | None = None) -> ApiError:
    return ApiError(
        error_code="cannot_auto_confirm",
        message=message or "当前资料不足以自动确认产品类型和文档策略，请人工确认后继续。",
        status_code=409,
        suggested_action="请确认产品类型和文档策略后继续。",
    )


def confirmation_payload_invalid(message: str | None = None) -> ApiError:
    return ApiError(
        error_code="confirmation_payload_invalid",
        message=message or "确认内容不完整或不合法。",
        status_code=400,
        suggested_action="请刷新工作台后重新确认。",
    )


def strategy_reset_required() -> ApiError:
    return ApiError(
        error_code="strategy_reset_required",
        message="当前文档策略已确认，修改后需要重新生成策略。",
        status_code=409,
        suggested_action="确认重新开始策略评估后再修改。",
    )


def backend_internal_error(message: str | None = None) -> ApiError:
    return ApiError(
        error_code="backend_internal_error",
        message=message or "后端执行失败，请稍后重试。",
        status_code=500,
        suggested_action="请查看后端日志或刷新工作台后重试。",
    )


def upload_file_not_allowed(message: str) -> ApiError:
    return ApiError(
        error_code="upload_file_type_not_allowed",
        message=message,
        status_code=400,
        suggested_action="请上传支持的 docx、pdf、md、txt、html 或图片文件。",
    )


def upload_save_failed() -> ApiError:
    return ApiError(
        error_code="upload_save_failed",
        message="上传文件保存失败，请稍后重试。",
        status_code=500,
        suggested_action="重新上传文件。",
    )


def artifact_not_found() -> ApiError:
    return ApiError(
        error_code="artifact_not_found",
        message="导出文件不存在或尚未生成。",
        status_code=404,
        suggested_action="请先完成文档生成和导出。",
    )


def artifact_path_invalid() -> ApiError:
    return ApiError(
        error_code="artifact_path_invalid",
        message="导出文件路径非法，系统已拒绝下载。",
        status_code=400,
        recoverable=False,
        suggested_action="请重新生成导出文件。",
    )


def diagnostics_failed() -> ApiError:
    return ApiError(
        error_code="diagnostics_failed",
        message="诊断信息读取失败，请稍后重试。",
        status_code=500,
        suggested_action="刷新工作台或重新打开任务。",
    )
