"""
Ontology服务层测试：版本控制、CRUD、别名查询、diff。
"""

import sys
import json
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import ontology_service


class TestOntologyService:
    """使用临时目录隔离测试，不影响真实ontology数据。"""

    def setup_method(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self._orig_dir = ontology_service.ONTOLOGY_DIR
        ontology_service.ONTOLOGY_DIR = self.tmp_dir

        # 写入种子v1
        seed = {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "author": "test",
            "description": "seed",
            "terms": {
                "revenue": {
                    "canonical": "营业收入",
                    "field_key": "营业收入",
                    "source_table": "income_statement",
                    "aliases": {"zh_CN": ["营业收入"], "en": ["Revenue"]},
                    "definition": "test def",
                    "related_to": [],
                    "gaap": {}
                }
            },
            "relationships": []
        }
        (self.tmp_dir / "v1.json").write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
        (self.tmp_dir / "current.json").write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

    def teardown_method(self):
        ontology_service.ONTOLOGY_DIR = self._orig_dir
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_load_current(self):
        data = ontology_service.load_current()
        assert data["version"] == 1
        assert "revenue" in data["terms"]

    def test_list_versions(self):
        versions = ontology_service.list_versions()
        assert len(versions) == 1
        assert versions[0]["version"] == 1

    def test_save_new_version(self):
        data = ontology_service.load_current()
        data["terms"]["cost"] = {
            "canonical": "营业成本",
            "field_key": "营业成本",
            "source_table": "income_statement",
            "aliases": {"zh_CN": ["营业成本"]},
            "definition": "cost",
            "related_to": [],
            "gaap": {}
        }
        result = ontology_service.save_new_version(data, author="tester", description="add cost")
        assert result["version"] == 2
        assert (self.tmp_dir / "v2.json").exists()

        # current应该也是v2
        current = ontology_service.load_current()
        assert current["version"] == 2
        assert "cost" in current["terms"]

    def test_update_term_creates_version(self):
        ontology_service.update_term("new_term", {
            "canonical": "新术语",
            "field_key": "新术语",
            "source_table": "balance_sheet",
            "aliases": {"zh_CN": ["新术语"]},
            "definition": "test",
            "related_to": [],
            "gaap": {}
        })
        current = ontology_service.load_current()
        assert current["version"] == 2
        assert "new_term" in current["terms"]
        assert "revenue" in current["terms"]  # 原有的还在

    def test_delete_term_creates_version(self):
        ontology_service.delete_term("revenue", author="tester")
        current = ontology_service.load_current()
        assert current["version"] == 2
        assert "revenue" not in current["terms"]

    def test_rollback(self):
        # 先创建v2
        ontology_service.update_term("new_term", {
            "canonical": "新术语", "field_key": "新", "source_table": "balance_sheet",
            "aliases": {}, "definition": "", "related_to": [], "gaap": {}
        })
        assert ontology_service.load_current()["version"] == 2

        # 回滚到v1
        result = ontology_service.rollback_to(1)
        assert result["version"] == 3  # 回滚创建新版本号
        current = ontology_service.load_current()
        assert "new_term" not in current["terms"]
        assert "revenue" in current["terms"]

    def test_diff_versions(self):
        # v1 has revenue, add cost in v2
        ontology_service.update_term("cost", {
            "canonical": "营业成本", "field_key": "营业成本", "source_table": "income_statement",
            "aliases": {}, "definition": "", "related_to": [], "gaap": {}
        })
        diff = ontology_service.diff_versions(1, 2)
        assert "cost" in diff["added"]
        assert diff["removed"] == []

    def test_get_aliases_for_extraction(self):
        aliases = ontology_service.get_aliases_for_extraction()
        assert "营业收入" in aliases
        assert "Revenue" in aliases["营业收入"]

    def test_get_field_definitions(self):
        defs = ontology_service.get_field_definitions()
        assert defs["营业收入"] == "test def"

    def test_get_nonexistent_term(self):
        result = ontology_service.get_term("nonexistent")
        assert result is None

    def test_get_existing_term(self):
        result = ontology_service.get_term("revenue")
        assert result["canonical"] == "营业收入"
