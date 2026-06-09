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
