"""
财报侦察官 - Ontology服务层
管理财务术语本体的CRUD和版本控制。
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ONTOLOGY_DIR = Path(__file__).parent.parent / "ontology"


def _current_path() -> Path:
    return ONTOLOGY_DIR / "current.json"


def _version_path(version: int) -> Path:
    return ONTOLOGY_DIR / f"v{version}.json"


def load_current() -> dict:
    """加载当前生效的ontology。"""
    path = _current_path()
    if not path.exists():
        raise FileNotFoundError("当前ontology不存在，请先初始化")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_versions() -> list[dict]:
    """列出所有历史版本的元数据（不含完整terms）。"""
    versions = []
    for p in sorted(ONTOLOGY_DIR.glob("v*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            versions.append({
                "version": data["version"],
                "created_at": data.get("created_at", ""),
                "author": data.get("author", ""),
                "description": data.get("description", ""),
                "term_count": len(data.get("terms", {})),
                "file": p.name,
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return versions


def get_version(version: int) -> dict:
    """获取指定版本的完整ontology。"""
    path = _version_path(version)
    if not path.exists():
        raise FileNotFoundError(f"版本v{version}不存在")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _next_version() -> int:
    existing = [int(p.stem[1:]) for p in ONTOLOGY_DIR.glob("v*.json")
                if p.stem[1:].isdigit()]
    return max(existing, default=0) + 1


def save_new_version(data: dict, author: str = "user",
                     description: str = "") -> dict:
    """
    保存为新版本并更新current.json。
    data应包含完整的terms和relationships。
    返回保存后的完整ontology（含version等元数据）。
    """
    new_ver = _next_version()
    data["version"] = new_ver
    data["created_at"] = datetime.now(timezone.utc).isoformat()
    data["author"] = author
    data["description"] = description or f"版本{new_ver}"

    # 保存版本文件
    ver_path = _version_path(new_ver)
    _save(data, ver_path)

    # 更新current
    _save(data, _current_path())

    return data


def rollback_to(version: int) -> dict:
    """回滚到指定版本：将该版本复制为新版本号并设为current。"""
    old_data = get_version(version)

    new_ver = _next_version()
    old_data["version"] = new_ver
    old_data["created_at"] = datetime.now(timezone.utc).isoformat()
    old_data["author"] = "system"
    old_data["description"] = f"回滚至v{version}"

    ver_path = _version_path(new_ver)
    _save(old_data, ver_path)
    _save(old_data, _current_path())

    return old_data


def diff_versions(v1: int, v2: int) -> dict:
    """对比两个版本的差异。"""
    data1 = get_version(v1)
    data2 = get_version(v2)

    terms1 = set(data1.get("terms", {}).keys())
    terms2 = set(data2.get("terms", {}).keys())

    added = terms2 - terms1
    removed = terms1 - terms2
    common = terms1 & terms2

    modified = []
    for key in common:
        if data1["terms"][key] != data2["terms"][key]:
            modified.append({
                "term_id": key,
                "v1": data1["terms"][key],
                "v2": data2["terms"][key],
            })

    return {
        "v1": v1,
        "v2": v2,
        "added": list(added),
        "removed": list(removed),
        "modified": modified,
    }


# ---------------------------------------------------------------------------
# Term-level CRUD (操作current，返回时不立即创建版本)
# ---------------------------------------------------------------------------

def get_term(term_id: str) -> dict | None:
    """获取当前ontology中某个term。"""
    data = load_current()
    return data.get("terms", {}).get(term_id)


def update_term(term_id: str, term_data: dict, author: str = "user",
                description: str = "") -> dict:
    """更新或新增一个term，自动创建新版本。"""
    data = load_current()
    data.setdefault("terms", {})[term_id] = term_data
    desc = description or f"更新术语: {term_data.get('canonical', term_id)}"
    return save_new_version(data, author=author, description=desc)


def delete_term(term_id: str, author: str = "user") -> dict:
    """删除一个term，自动创建新版本。"""
    data = load_current()
    terms = data.get("terms", {})
    if term_id not in terms:
        raise KeyError(f"术语 {term_id} 不存在")
    canonical = terms[term_id].get("canonical", term_id)
    del terms[term_id]
    return save_new_version(data, author=author,
                            description=f"删除术语: {canonical}")


# ---------------------------------------------------------------------------
# 给PDF提取器用的别名查询
# ---------------------------------------------------------------------------

def get_aliases_for_extraction(lang: str = "zh_CN") -> dict[str, list[str]]:
    """
    返回 {field_key: [所有别名]} 映射，供LLM提取时使用。
    """
    data = load_current()
    result = {}
    for term_id, term in data.get("terms", {}).items():
        field_key = term.get("field_key", term.get("canonical", ""))
        aliases = []
        for lang_aliases in term.get("aliases", {}).values():
            aliases.extend(lang_aliases)
        # 去重，保留顺序
        seen = set()
        unique = []
        for a in aliases:
            if a not in seen:
                seen.add(a)
                unique.append(a)
        result[field_key] = unique
    return result


def get_field_definitions() -> dict[str, str]:
    """返回 {field_key: definition} 映射，供前端展示术语解释。"""
    data = load_current()
    result = {}
    for term in data.get("terms", {}).values():
        field_key = term.get("field_key", term.get("canonical", ""))
        result[field_key] = term.get("definition", "")
    return result
