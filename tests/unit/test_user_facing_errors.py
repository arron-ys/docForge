from docforge_core.workflow.user_facing_errors import UserFacingErrorMapper


def test_error_mapper_missing_reference_message() -> None:
    mapped = UserFacingErrorMapper().map_error("reference_style source missing")

    assert mapped.code == "missing_reference"
    assert mapped.user_message == "请先上传参考软著样例文档。"


def test_error_mapper_missing_product_message() -> None:
    mapped = UserFacingErrorMapper().map_error("product_evidence source missing")

    assert mapped.code == "missing_product"
    assert mapped.user_message == "请先上传产品资料文档。"


def test_error_mapper_hash_mismatch_message() -> None:
    mapped = UserFacingErrorMapper().map_error(
        "artifact hash mismatch: abc123abc123abc123abc123abc123ab"
    )

    assert mapped.code == "artifact_hash_mismatch"
    assert "可信度" in mapped.user_message


def test_error_mapper_waiting_for_confirmation_message() -> None:
    mapped = UserFacingErrorMapper().map_error("workflow waiting for human confirmation")

    assert mapped.code == "waiting_for_confirmation"
    assert "确认推荐模板" in mapped.user_message


def test_error_mapper_screenshot_fact_misuse_message() -> None:
    mapped = UserFacingErrorMapper().map_error("PRODUCT_SCREENSHOT used as product fact")

    assert mapped.code == "screenshot_fact_misuse"
    assert "截图" in mapped.user_message


def test_error_mapper_does_not_expose_internal_evidence_id() -> None:
    mapped = UserFacingErrorMapper().map_error(
        "ev_secret_001 source_id=source_hidden raw quote finding_id=finding_1"
    )

    assert "ev_secret_001" not in mapped.user_message
    assert "source_hidden" not in mapped.user_message
    assert "finding_1" not in mapped.user_message
    assert "raw quote" not in mapped.user_message
