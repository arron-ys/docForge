from pathlib import Path

from docx import Document

from docforge_core.exporters.docx_acceptance import DocxAcceptanceChecker
from docforge_core.exporters.docx_exporter import DocxExportService

from .test_docx_exporter import (
    _normal_docx_path,
    _prepare_v1_passed,
    _prepare_v3_risk,
    _risk_docx_path,
)


def _write_docx(path: Path, lines: list[str]) -> Path:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    doc.save(path)
    return path


def test_docx_acceptance_passes_normal_docx(tmp_path: Path) -> None:
    store, state = _prepare_v1_passed(tmp_path)
    DocxExportService(store).export_current_docx(state.run_id)

    report = DocxAcceptanceChecker().check_normal_docx(
        _normal_docx_path(store, state.run_id),
        store.load_state(state.run_id),
    )

    assert report.passed is True
    assert report.issues == []


def test_docx_acceptance_rejects_docx_with_evidence_id(tmp_path: Path) -> None:
    path = _write_docx(tmp_path / "bad.docx", ["软件著作权文档", "ev_secret_001"])

    report = DocxAcceptanceChecker().check_normal_docx(path)

    assert report.passed is False
    assert any("evidence_id" in issue for issue in report.issues)


def test_docx_acceptance_rejects_docx_with_source_id(tmp_path: Path) -> None:
    path = _write_docx(tmp_path / "bad.docx", ["软件著作权文档", "source_id"])

    report = DocxAcceptanceChecker().check_normal_docx(path)

    assert report.passed is False
    assert any("source_id" in issue for issue in report.issues)


def test_docx_acceptance_rejects_docx_with_raw_quote(tmp_path: Path) -> None:
    quote = "当前版本明确支持数据集管理能力"
    path = _write_docx(tmp_path / "bad.docx", ["软件著作权文档", quote])

    report = DocxAcceptanceChecker().check_normal_docx(path, raw_quotes=[quote])

    assert report.passed is False
    assert any("raw quote" in issue for issue in report.issues)


def test_docx_acceptance_rejects_docx_with_export_manifest(tmp_path: Path) -> None:
    path = _write_docx(tmp_path / "bad.docx", ["软件著作权文档", "export_manifest"])

    report = DocxAcceptanceChecker().check_normal_docx(path)

    assert report.passed is False
    assert any("export_manifest" in issue for issue in report.issues)


def test_docx_acceptance_passes_risk_docx_summary_only(tmp_path: Path) -> None:
    store, state = _prepare_v3_risk(tmp_path)
    DocxExportService(store).export_current_docx(state.run_id)

    report = DocxAcceptanceChecker().check_risk_docx(
        _risk_docx_path(store, state.run_id),
        store.load_state(state.run_id),
    )

    assert report.passed is True
    assert report.issues == []


def test_docx_acceptance_rejects_risk_docx_dumping_findings(tmp_path: Path) -> None:
    path = _write_docx(
        tmp_path / "bad_risk.docx",
        [
            "风险版文档",
            "请人工复核",
            "blocker_count: 1",
            "major_count: 1",
            "finding_secret_001",
            "suggested_fix",
        ],
    )

    report = DocxAcceptanceChecker().check_risk_docx(path)

    assert report.passed is False
    assert any("finding_id" in issue or "suggested_fix" in issue for issue in report.issues)
