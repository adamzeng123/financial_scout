"""
财报侦察官 - JSON → Neo4j 数据迁移脚本
将data/目录下所有existing JSON数据导入Neo4j。
幂等：使用MERGE，安全重复运行。

用法：
  cd financial-scout
  NEO4J_PASSWORD=financial_scout uv run python src/migration.py
"""

import json
import sys
import io
from pathlib import Path

# Fix Windows console encoding for Chinese output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent))

from neo4j_client import is_available, ensure_constraints
import neo4j_repository
import ontology_service

DATA_DIR = Path(__file__).parent.parent / "data"


def discover_datasets() -> list[dict]:
    """扫描data/目录，发现所有数据集。"""
    datasets = []

    # 默认目录的数据
    default_json = DATA_DIR / "financial_data.json"
    if default_json.exists():
        datasets.append({
            "json_path": default_json,
            "audit_path": DATA_DIR / "audit_opinion.txt",
            "source": "default",
        })

    # 子目录的数据
    for sub in sorted(DATA_DIR.iterdir()):
        if sub.is_dir() and (sub / "financial_data.json").exists():
            datasets.append({
                "json_path": sub / "financial_data.json",
                "audit_path": sub / "audit_opinion.txt",
                "source": sub.name,
            })

    return datasets


def migrate_dataset(dataset: dict) -> dict:
    """迁移单个数据集到Neo4j。"""
    with open(dataset["json_path"], "r", encoding="utf-8") as f:
        data = json.load(f)

    company = data.get("company", "")
    year = data.get("report_year", 0)

    if not company or not year:
        return {"source": dataset["source"], "status": "skipped", "reason": "missing company or year"}

    # 检查是否有null值（未完成的提取）
    null_count = 0
    for period_key in ["current_period", "prior_period"]:
        period = data.get(period_key, {})
        for table_key in ["balance_sheet", "income_statement", "cash_flow"]:
            table = period.get(table_key, {})
            null_count += sum(1 for v in table.values() if v is None)

    if null_count > 10:
        return {
            "source": dataset["source"],
            "status": "skipped",
            "reason": f"too many null fields ({null_count}), likely incomplete extraction"
        }

    # 写入财务数据
    stats = neo4j_repository.upsert_financial_data(data)

    # 写入审计意见
    audit_path = dataset["audit_path"]
    if audit_path.exists():
        with open(audit_path, "r", encoding="utf-8") as f:
            audit_text = f.read()
        if audit_text.strip():
            # 简单判断审计意见类型（不调用LLM）
            is_clean = "标准无保留意见" in audit_text or "标准的无保留意见" in audit_text
            opinion_type = "标准无保留意见" if is_clean else "待分类"
            neo4j_repository.upsert_audit_opinion(
                company, year, audit_text, opinion_type, is_clean
            )

    return {
        "source": dataset["source"],
        "status": "ok",
        "company": company,
        "year": year,
        "data_points": stats["data_points"],
        "null_fields": null_count,
    }


def migrate_ontology() -> dict:
    """同步当前ontology到Neo4j。"""
    try:
        data = ontology_service.load_current()
        neo4j_repository.sync_ontology_terms(data)
        return {
            "status": "ok",
            "version": data["version"],
            "terms": len(data.get("terms", {})),
            "relationships": len(data.get("relationships", [])),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_migration():
    """执行完整迁移。"""
    print("=" * 60)
    print("  财报侦察官 - JSON → Neo4j 数据迁移")
    print("=" * 60)
    print()

    # 检查Neo4j连接
    print("[1/4] 检查Neo4j连接...")
    if not is_available():
        print("  ✗ Neo4j不可用，请确保Neo4j已启动")
        print("  提示：docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \\")
        print("        -e NEO4J_AUTH=neo4j/financial_scout neo4j:5-community")
        sys.exit(1)
    print("  ✓ Neo4j连接正常")

    # 创建约束和索引
    print("\n[2/4] 创建约束和索引...")
    ensure_constraints()
    print("  ✓ 约束和索引就绪")

    # 迁移数据集
    print("\n[3/4] 迁移财务数据...")
    datasets = discover_datasets()
    print(f"  发现 {len(datasets)} 个数据集")

    total_points = 0
    for ds in datasets:
        result = migrate_dataset(ds)
        if result["status"] == "ok":
            total_points += result["data_points"]
            print(f"  ✓ {result['company']} {result['year']}年"
                  f" - {result['data_points']}个数据点"
                  f" (null: {result['null_fields']})")
        else:
            print(f"  - {result['source']}: 跳过 ({result['reason']})")

    # 迁移Ontology
    print("\n[4/4] 同步Ontology...")
    onto_result = migrate_ontology()
    if onto_result["status"] == "ok":
        print(f"  ✓ v{onto_result['version']}"
              f" - {onto_result['terms']}个术语"
              f" - {onto_result['relationships']}条关系")
    else:
        print(f"  ✗ {onto_result['error']}")

    print(f"\n{'=' * 60}")
    print(f"  迁移完成！共写入 {total_points} 个数据点")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run_migration()
