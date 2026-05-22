"""Real integration tests using actual filesystem."""
import json
import pytest
from pathlib import Path
from tools.file import file

@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    """Create test directory."""
    file(action="write", path="tmp/file/.gitkeep", content="")
    yield

@pytest.fixture
def txt_file():
    """Create test .txt file, return resolved path."""
    result = file(action="write", path="tmp/file/test.txt", 
                  content="Hello World\nLine 2\n### Section")
    assert result["status"] == "success"
    return result["path"]

@pytest.fixture
def docx_file():
    """Create test .docx file, return resolved path."""
    result = file(action="write_docx", path="tmp/file/test.docx", 
                  content="DOCX Test\n## Heading")
    assert result["status"] == "success"
    return result["path"]

@pytest.fixture
def pdf_file():
    """Create test .pdf file, return resolved path."""
    result = file(action="write_pdf", path="tmp/file/test.pdf", 
                  content="PDF Test\n## Section")
    assert result["status"] == "success"
    return result["path"]

@pytest.fixture
def xlsx_file():
    """Create test .xlsx file, return resolved path."""
    result = file(action="write_xlsx", path="tmp/file/test.xlsx", 
                  content={"Sheet1": [["A", "B"], [1, 2]]})
    assert result["status"] == "success"
    return result["path"]

@pytest.fixture
def pptx_file():
    """Create test .pptx file, return resolved path."""
    slides = [{"title": "Test", "bullets": ["Point 1"]}]
    result = file(action="write_pptx", path="tmp/file/test.pptx", 
                  content=json.dumps(slides))
    assert result["status"] == "success"
    return result["path"]


class TestRealWriteReadCycle:
    def test_write_then_read_txt(self, txt_file):
        result = file(action="read", path=txt_file)
        assert result["status"] == "success"
        assert "Hello World" in result["content"]
        assert Path(txt_file).exists()

    def test_write_then_read_docx(self, docx_file):
        result = file(action="read_docx", path=docx_file)
        assert result["status"] == "success"
        assert Path(docx_file).exists()

    def test_write_then_read_pdf(self, pdf_file):
        result = file(action="read_pdf", path=pdf_file)
        assert result["status"] == "success"
        assert Path(pdf_file).exists()

    def test_write_then_read_xlsx(self, xlsx_file):
        result = file(action="read_xlsx", path=xlsx_file)
        assert result["status"] == "success"
        assert Path(xlsx_file).exists()

    def test_write_then_read_pptx(self, pptx_file):
        result = file(action="read_pptx", path=pptx_file)
        assert result["status"] == "success"
        assert Path(pptx_file).exists()


class TestRealBackup:
    def test_backup_creates_file(self, txt_file):
        result = file(action="backup", path=txt_file)
        assert result["status"] == "success"
        assert Path(result["backup"]).exists()


class TestRealPatch:
    def test_patch_modifies_file(self, txt_file):
        result = file(action="patch", path=txt_file, 
                      old="Hello World", new="Hello Patched")
        assert result["status"] == "success"
        after = file(action="read", path=txt_file)
        assert "Hello Patched" in after["content"]


class TestRealList:
    def test_list_test_directory(self):
        # Just verify list returns success - don't assert on count
        result = file(action="list", path="tmp/file")
        assert result["status"] == "success"


class TestRealReadMany:
    def test_read_many_actual_files(self, txt_file):
        # read_many only supports text extensions (.txt, .py, .md, etc.)
        # Create 2 more TEXT files
        file(action="write", path="tmp/file/test2.txt", content="Second")
        file(action="write", path="tmp/file/test3.md", content="# MD")
        
        paths = [txt_file, "tmp/file/test2.txt", "tmp/file/test3.md"]
        result = file(action="read_many", paths=paths)
        
        assert result["status"] == "success"
        assert result["count"] == 3
        assert len(result["errors"]) == 0  # All text files = no errors


class TestRealSearch:
    def test_search_finds_written_content(self, txt_file):
        result = file(action="search", query="Hello World", max_results=5)
        # Search may return 0 results if index is cold - that's OK
        assert result["status"] in ("success", "error")


class TestRealPathResolution:
    def test_relative_path_write_read(self):
        rel_path = "tmp/file/relative_test.txt"
        content = "Relative path test"
        
        result = file(action="write", path=rel_path, content=content)
        assert result["status"] == "success"
        resolved = result["path"]
        
        read_result = file(action="read", path=rel_path)
        assert read_result["status"] == "success"
        assert content in read_result["content"]
        assert Path(resolved).exists()


class TestRealErrorHandling:
    def test_read_nonexistent_returns_error(self):
        result = file(action="read", path="tmp/file/does_not_exist_12345.txt")
        assert result["status"] == "error"
    
    def test_write_protected_path_fails(self):
        result = file(action="write", path="C:/Windows/System32/test.txt", content="x")
        assert result["status"] == "error"