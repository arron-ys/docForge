"""Map internal workflow errors to safe user-facing messages."""

from __future__ import annotations

import re
from dataclasses import dataclass

INTERNAL_ID_PATTERN = re.compile(
    r"\b(?:ev|source|finding|audit|gate|draft)_[A-Za-z0-9_:-]+\b",
    re.IGNORECASE,
)
HASH_PATTERN = re.compile(r"\b[a-f0-9]{32,64}\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class UserFacingError:
    """Safe error text for the UI plus traceable developer detail."""

    code: str
    user_message: str
    developer_message: str
    suggested_action: str


class UserFacingErrorMapper:
    """Translate low-level exceptions without exposing internal identifiers."""

    def map_error(self, error: BaseException | str) -> UserFacingError:
        raw = str(error)
        lowered = raw.lower()
        if "reference_style" in lowered or "reference" in lowered and "missing" in lowered:
            return self._error(
                "missing_reference",
                "请先上传参考软著样例文档。",
                raw,
                "上传参考软著后重新执行流程。",
            )
        if "product_evidence" in lowered or "product" in lowered and "missing" in lowered:
            return self._error(
                "missing_product",
                "请先上传产品资料文档。",
                raw,
                "上传产品 PRD、HLD 或产品介绍后重新执行流程。",
            )
        if "human confirmation" in lowered or "人工确认" in raw or "用户确认" in raw:
            return self._error(
                "waiting_for_confirmation",
                "请确认推荐模板和软件基本信息后继续。",
                raw,
                "在主流程中提交模板确认。",
            )
        if "hash" in lowered or "不匹配" in raw and (
            "source_" in lowered or "artifact" in lowered or "manifest" in lowered
        ):
            return self._error(
                "artifact_hash_mismatch",
                "流程产物已被修改，系统已停止继续执行以保护文档可信度。",
                raw,
                "请重新开始一个任务，或由开发者检查数据目录。",
            )
        if "state 指向的产物不存在" in raw or "artifact 文件不存在" in raw or "缺失" in raw:
            return self._error(
                "artifact_missing",
                "当前流程文件不完整，不能继续。请重新开始一个任务或联系开发者检查数据目录。",
                raw,
                "检查 state 中的 artifact ref 与 data/runs 下文件是否一致。",
            )
        if "目标 docx 已存在" in lowered or "force=false" in lowered:
            return self._error(
                "export_target_exists",
                "已存在导出文档。如需重新导出，请先创建新任务或使用开发调试模式。",
                raw,
                "DocxExportService 拒绝在 force=False 时覆盖已有 DOCX。",
            )
        if "截图 evidence" in raw or "product_screenshot" in lowered or "screenshot evidence" in lowered:
            return self._error(
                "screenshot_fact_misuse",
                "检测到截图被误用为产品事实依据，系统已停止生成。",
                raw,
                "screenshot evidence used as product fact.",
            )
        return self._error(
            "workflow_error",
            "流程执行失败，请查看开发调试信息或重新开始一个任务。",
            raw,
            "查看开发调试信息中的原始错误。",
        )

    def _error(
        self,
        code: str,
        user_message: str,
        developer_message: str,
        suggested_action: str,
    ) -> UserFacingError:
        return UserFacingError(
            code=code,
            user_message=self._sanitize_user_text(user_message),
            developer_message=developer_message,
            suggested_action=self._sanitize_user_text(suggested_action),
        )

    @staticmethod
    def _sanitize_user_text(value: str) -> str:
        value = INTERNAL_ID_PATTERN.sub("[internal-id]", value)
        value = HASH_PATTERN.sub("[hash]", value)
        for token in ("evidence_id", "source_id", "finding_id", "raw quote"):
            value = value.replace(token, "[internal-field]")
        return value
