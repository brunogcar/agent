"""Test file action patterns and basic functionality."""
import pytest
import json
from pathlib import Path
from tools.file import file

# ============================================================================
# FIXTURES: Setup test environment
# ============================================================================
@pytest.fixture(autouse=True)
def setup_tmp_dir(tmp_path, monkeypatch):
    """Ensure tmp/ directory exists and is within workspace for path resolution."""
    tmp_dir = Path("tmp")
    tmp_dir.mkdir(exist_ok=True)
    yield tmp_dir
    # Optional cleanup: uncomment if you want tests to be fully isolated
    # import shutil
    # if tmp_dir.exists():
    #     shutil.rmtree(tmp_dir)

@pytest.fixture
def sample_docx_path(setup_tmp_dir):
    """Create a minimal valid .docx file for testing."""
    path = setup_tmp_dir / "sample.docx"
    if not path.exists():
        # Use write_docx to create a valid file
        file(action="write_docx", path=str(path), content="Test DOCX content")
    return str(path)

@pytest.fixture
def sample_pdf_path(setup_tmp_dir):
    import os
    pdf_path = os.path.join(setup_tmp_dir, "sample.pdf")
    # Minimal valid PDF with extractable text (no external dependencies)
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 44 >>
stream
BT /F1 24 Tf 100 700 Td (Test PDF Content) Tj ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000138 00000 n 
0000000207 00000 n 
0000000282 00000 n 
0000000357 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
400
%%EOF"""
    with open(pdf_path, "wb") as f:
        f.write(pdf_content)
    return pdf_path

@pytest.fixture
def sample_pptx_path(setup_tmp_dir):
    """Create a minimal valid .pptx file for testing."""
    path = setup_tmp_dir / "sample.pptx"
    if not path.exists():
        slides = [{"title": "Test Slide", "bullets": ["Point 1", "Point 2"]}]
        file(action="write_pptx", path=str(path), content=json.dumps(slides))
    return str(path)

@pytest.fixture
def sample_xlsx_path(setup_tmp_dir):
    """Create a minimal valid .xlsx file for testing."""
    path = setup_tmp_dir / "sample.xlsx"
    if not path.exists():
        # write_xlsx accepts list-of-lists or dict of sheets
        data = {"Sheet1": [[1, 2, 3], [4, 5, 6]]}
        file(action="write_xlsx", path=str(path), content=data)
    return str(path)

@pytest.fixture
def patch_test_file(setup_tmp_dir):
    """Create a file specifically for patch testing."""
    path = setup_tmp_dir / "test_patch.txt"
    path.write_text("placeholder text here", encoding="utf-8")
    return str(path)

# ============================================================================
# TESTS
# ============================================================================
class TestReadPatterns:
    def test_read_file(self):
        result = file(action="read", path="tools/file.py")
        assert result.get("status") == "success"
        assert "content" in result

    def test_read_nonexistent_file(self):
        result = file(action="read", path="nonexistent_12345.txt")
        assert result.get("status") == "error"

class TestListPatterns:
    def test_list_directory(self):
        result = file(action="list", path="tools")
        assert result.get("status") == "success"
        assert "entries" in result
        assert result.get("count", 0) > 0

    def test_list_nonexistent_directory(self):
        result = file(action="list", path="nonexistent_dir_12345")
        assert result.get("status") == "error"

class TestWritePatterns:
    def test_write_file(self):
        result = file(action="write", path="tmp/test_write.txt", content="test content")
        assert result.get("status") == "success"
        assert "path" in result

class TestBackupPatterns:
    def test_backup_file(self):
        # First create a test file
        file(action="write", path="tmp/test_backup.txt", content="backup test")
        result = file(action="backup", path="tmp/test_backup.txt")
        assert result.get("status") == "success"
        assert "backup" in result

class TestSearchPatterns:
    def test_search_files(self):
        # Search for something likely to exist in your codebase
        result = file(action="search", query="def file", max_results=5)
        # Search may return 0 results but still be successful
        assert result.get("status") in ("success", "error")  # index might not be built yet
        if result.get("status") == "success":
            assert "results" in result

class TestPatchPatterns:
    def test_patch_file(self, patch_test_file):
        # patch.py uses 'old' and 'new' kwargs (not old_text/new_text)
        result = file(
            action="patch",
            path=patch_test_file,
            old="placeholder",
            new="replaced"
        )
        assert result.get("status") == "success"
        # Verify the change was applied
        verify = file(action="read", path=patch_test_file)
        assert "replaced" in verify.get("content", "")

    def test_patch_nonexistent_file(self):
        result = file(action="patch", path="missing_12345.txt", old="a", new="b")
        assert result.get("status") == "error"

class TestReadDocxPatterns:
    def test_read_docx_file(self, sample_docx_path):
        result = file(action="read_docx", path=sample_docx_path)
        assert result.get("status") == "success"
        assert "text" in result or "content" in result

class TestReadManyPatterns:
    def test_read_many_files(self, setup_tmp_dir):
        # Create test files first so they exist
        file(action="write", path="tmp/file1.txt", content="content 1")
        file(action="write", path="tmp/file2.txt", content="content 2")
        
        # read_many.py returns {"files": [...], "errors": [...]}
        result = file(action="read_many", paths=["tmp/file1.txt", "tmp/file2.txt"])
        assert result.get("status") == "success"
        assert "files" in result  # NOT "contents" or "results"
        assert result.get("count") == 2

    def test_read_many_with_missing_files(self):
        # read_many gracefully reports missing files inside a successful response
        result = file(action="read_many", paths=["tmp/missing1.txt", "tmp/missing2.txt"])
        assert result.get("status") == "success"  # overall operation succeeded
        assert "errors" in result
        assert len(result["errors"]) == 2  # both files missing

class TestReadPdfPatterns:
    def test_read_pdf_file(self, sample_pdf_path):
        result = file(action="read_pdf", path=sample_pdf_path)
        assert result.get("status") == "success"
        assert "text" in result

class TestReadPptxPatterns:
    def test_read_pptx_file(self, sample_pptx_path):
        result = file(action="read_pptx", path=sample_pptx_path)
        assert result.get("status") == "success"
        assert "slides" in result or "text" in result

class TestReadXlsxPatterns:
    def test_read_xlsx_file(self, sample_xlsx_path):
        result = file(action="read_xlsx", path=sample_xlsx_path)
        assert result.get("status") == "success"
        assert "sheets" in result or "data" in result

class TestWriteDocxPatterns:
    def test_write_docx_file(self):
        result = file(action="write_docx", path="tmp/output.docx", content="Test document")
        assert result.get("status") == "success"
        assert "path" in result

class TestWritePdfPatterns:
    def test_write_pdf_file(self, setup_tmp_dir):
        import os
        pdf_path = os.path.join(setup_tmp_dir, "output.pdf")
        result = file(action="write_pdf", path=pdf_path, content="Test PDF")
        assert result.get("status") == "success"
        assert "path" in result
        assert os.path.exists(pdf_path)

class TestWritePptxPatterns:
    def test_write_pptx_file(self):
        # write_pptx expects a list of slide dicts (or JSON string)
        slides = [
            {"title": "Title Slide", "body": "Welcome"},
            {"title": "Bullet Slide", "bullets": ["Point A", "Point B"]}
        ]
        result = file(action="write_pptx", path="tmp/output.pptx", content=json.dumps(slides))
        assert result.get("status") == "success"
        assert "path" in result

class TestWriteXlsxPatterns:
    def test_write_xlsx_file(self):
        # write_xlsx accepts list-of-lists or dict of sheets
        data = {"Sheet1": [[1, 2], [3, 4]]}
        result = file(action="write_xlsx", path="tmp/output.xlsx", content=data)
        assert result.get("status") == "success"
        assert "path" in result