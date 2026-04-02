"""
财报侦察官 - Flask API
提供评分计算、LLM调用、PDF提取、Ontology管理和Neo4j跨公司查询的REST接口。
"""

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(Path(__file__).parent.parent / ".env")
from flask_cors import CORS
from scorer import load_financial_data, run_scoring
from llm_client import classify_audit_opinion, generate_evaluation
from pdf_extractor import process_pdf, validate_financial_data
import ontology_service

app = Flask(__name__)
CORS(app)

DATA_DIR = Path(__file__).parent.parent / "data"


# ---------------------------------------------------------------------------
# Neo4j helpers (graceful degradation)
# ---------------------------------------------------------------------------

def _neo4j_available() -> bool:
    try:
        import neo4j_client
        return neo4j_client.is_available()
    except Exception:
        return False


def _neo4j_write_scoring(company: str, year: int, result: dict) -> None:
    """将评分结果写入Neo4j（静默失败）。"""
    try:
        if _neo4j_available():
            import neo4j_repository
            neo4j_repository.save_scoring_result(company, year, result)
    except Exception:
        pass


def _neo4j_write_financial(data: dict) -> None:
    """将财务数据写入Neo4j（静默失败）。"""
    try:
        if _neo4j_available():
            import neo4j_repository
            neo4j_repository.upsert_financial_data(data)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Scoring cache — avoid repeated LLM calls for unchanged data
# ---------------------------------------------------------------------------

def _sanitize_for_json(obj):
    """递归替换Infinity/NaN为JSON安全值，避免序列化崩溃。"""
    if isinstance(obj, float):
        if math.isinf(obj):
            return 9999999 if obj > 0 else -9999999
        if math.isnan(obj):
            return 0
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _cache_path(data_dir: Path) -> Path:
    return data_dir / "scoring_cache.json"


def _data_fingerprint(data_dir: Path) -> str:
    """Hash of financial_data.json + audit_opinion.txt to detect changes."""
    h = hashlib.md5()
    for name in ["financial_data.json", "audit_opinion.txt"]:
        p = data_dir / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def _load_cache(data_dir: Path, roe_method: str, debt_scope: str) -> dict | None:
    """Load cached scoring result if data hasn't changed and options match."""
    cp = _cache_path(data_dir)
    if not cp.exists():
        return None
    try:
        with open(cp, "r", encoding="utf-8") as f:
            cache = json.load(f)
        # Verify fingerprint and options match
        if (cache.get("_fingerprint") == _data_fingerprint(data_dir)
                and cache.get("options", {}).get("roe_method") == roe_method
                and cache.get("options", {}).get("debt_scope") == debt_scope):
            return cache
    except Exception:
        pass
    return None


def _save_cache(data_dir: Path, result: dict) -> None:
    """Save scoring result to cache file."""
    try:
        result["_fingerprint"] = _data_fingerprint(data_dir)
        safe_result = _sanitize_for_json(result)
        with open(_cache_path(data_dir), "w", encoding="utf-8") as f:
            json.dump(safe_result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _resolve_data_dir(dataset_id: str | None = None) -> Path:
    """根据dataset_id返回对应的数据目录。"""
    if dataset_id:
        sub = DATA_DIR / dataset_id
        if sub.exists():
            return sub
    return DATA_DIR


# ---------------------------------------------------------------------------
# 核心API
# ---------------------------------------------------------------------------

@app.route("/api/datasets", methods=["GET"])
def list_datasets():
    """列出所有可用的数据集（公司+年度）。"""
    datasets = []
    # 检查默认目录
    if (DATA_DIR / "financial_data.json").exists():
        data = load_financial_data(DATA_DIR / "financial_data.json")
        datasets.append({
            "id": "_default",
            "company": data.get("company", "默认数据"),
            "report_year": data.get("report_year", ""),
            "path": "data/"
        })
    # 检查子目录
    for sub in sorted(DATA_DIR.iterdir()):
        if sub.is_dir() and (sub / "financial_data.json").exists():
            data = load_financial_data(sub / "financial_data.json")
            datasets.append({
                "id": sub.name,
                "company": data.get("company", sub.name),
                "report_year": data.get("report_year", ""),
                "path": f"data/{sub.name}/"
            })
    return jsonify(datasets)


@app.route("/api/score", methods=["POST"])
def score():
    """
    计算评分。优先读取缓存（秒返回），缓存不存在或数据变更时才调用LLM。
    """
    options = request.get_json(silent=True) or {}
    roe_method = options.get("roe_method", "weighted_avg")
    debt_scope = options.get("debt_scope", "narrow")
    dataset_id = options.get("dataset_id")

    data_dir = _resolve_data_dir(dataset_id)

    # Try cache first
    cached = _load_cache(data_dir, roe_method, debt_scope)
    if cached:
        cached["dataset_id"] = dataset_id
        cached["from_cache"] = True
        return jsonify(cached)

    # Cache miss — full LLM pipeline
    return _score_with_llm(data_dir, dataset_id, roe_method, debt_scope)


@app.route("/api/score/refresh", methods=["POST"])
def score_refresh():
    """强制重新分析（忽略缓存，重新调用LLM）。"""
    options = request.get_json(silent=True) or {}
    roe_method = options.get("roe_method", "weighted_avg")
    debt_scope = options.get("debt_scope", "narrow")
    dataset_id = options.get("dataset_id")

    data_dir = _resolve_data_dir(dataset_id)
    return _score_with_llm(data_dir, dataset_id, roe_method, debt_scope)


def _score_with_llm(data_dir: Path, dataset_id, roe_method: str, debt_scope: str):
    """执行完整评分流程（含LLM），并缓存结果。LLM调用并行化。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    data = load_financial_data(data_dir / "financial_data.json")

    audit_path = data_dir / "audit_opinion.txt"
    audit_text = ""
    if audit_path.exists():
        with open(audit_path, "r", encoding="utf-8") as f:
            audit_text = f.read()

    # 并行：审计分类 + 先用默认is_clean计算评分（评分不依赖LLM）
    with ThreadPoolExecutor(max_workers=2) as pool:
        # 1. 审计分类（LLM调用）
        future_opinion = pool.submit(
            classify_audit_opinion, audit_text
        ) if audit_text else None

        # 2. 同时先用 is_clean=True 跑一遍评分（纯计算，<10ms）
        #    如果审计结果回来后 is_clean 不同再重算
        result_optimistic = run_scoring(
            data, roe_method=roe_method, debt_scope=debt_scope,
            audit_opinion_clean=True
        )

    # 拿到审计分类结果
    opinion = future_opinion.result() if future_opinion else {
        "opinion_type": "未提供审计意见", "is_clean": True
    }

    # 如果审计非标准，需要重算（会触发红线）
    if not opinion.get("is_clean", True):
        result = run_scoring(
            data, roe_method=roe_method, debt_scope=debt_scope,
            audit_opinion_clean=False
        )
    else:
        result = result_optimistic

    # 并行：生成评价（LLM调用）
    # 在审计分类完成后才能生成评价（需要分数和审计结果作为输入）
    evaluation = generate_evaluation(result, audit_text)

    opinion["audit_text"] = audit_text
    result["audit_opinion"] = opinion
    result["evaluation"] = evaluation
    result["dataset_id"] = dataset_id
    result["from_cache"] = False

    # Save cache
    _save_cache(data_dir, result)

    # Dual-write to Neo4j
    _neo4j_write_financial(data)
    _neo4j_write_scoring(data.get("company", ""), data.get("report_year", 0), result)

    return jsonify(_sanitize_for_json(result))


@app.route("/api/score/compute", methods=["POST"])
def score_compute_only():
    """仅计算评分，不调用LLM。"""
    options = request.get_json(silent=True) or {}
    roe_method = options.get("roe_method", "weighted_avg")
    debt_scope = options.get("debt_scope", "narrow")
    audit_clean = options.get("audit_opinion_clean", True)
    dataset_id = options.get("dataset_id")

    data_dir = _resolve_data_dir(dataset_id)
    data = load_financial_data(data_dir / "financial_data.json")
    result = run_scoring(
        data,
        roe_method=roe_method,
        debt_scope=debt_scope,
        audit_opinion_clean=audit_clean
    )

    return jsonify(_sanitize_for_json(result))


@app.route("/api/extract", methods=["POST"])
def extract_from_pdf():
    """从上传的PDF中提取财务数据。"""
    if "file" not in request.files:
        return jsonify({"error": "请上传PDF文件"}), 400

    file = request.files["file"]
    company = request.form.get("company", "未知公司")
    report_year = int(request.form.get("report_year", 2024))

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = process_pdf(tmp_path, company, report_year, output_dir=DATA_DIR)

        # Dual-write to Neo4j
        _neo4j_write_financial(result["financial_data"])

        # 预热缓存：后台触发评分+LLM分析，用户打开时直接读缓存
        import threading
        def _prewarm(ds_id):
            try:
                data_dir = _resolve_data_dir(ds_id)
                _score_with_llm(data_dir, ds_id, "weighted_avg", "narrow")
            except Exception:
                pass
        threading.Thread(target=_prewarm, args=(result["dataset_id"],), daemon=True).start()

        return jsonify({
            "success": True,
            "dataset_id": result["dataset_id"],
            "company": company,
            "report_year": report_year,
            "missing_fields": result["missing_fields"],
            "pages_found": result["pages_found"],
            "message": "提取完成，" + ("所有字段完整" if not result["missing_fields"] else f"缺少{len(result['missing_fields'])}个字段"),
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Neo4j 跨公司查询 API
# ---------------------------------------------------------------------------

@app.route("/api/neo4j/status", methods=["GET"])
def neo4j_status():
    """检查Neo4j连接状态。"""
    return jsonify({"available": _neo4j_available()})


@app.route("/api/compare/companies", methods=["GET"])
def list_neo4j_companies():
    """列出Neo4j中的所有公司及可用年度。"""
    if not _neo4j_available():
        return jsonify({"error": "Neo4j不可用", "available": False}), 503
    import neo4j_repository
    return jsonify(neo4j_repository.get_companies())


@app.route("/api/compare/indicator", methods=["GET"])
def compare_indicator():
    """
    跨公司对比指标。
    ?indicator=ROE当期值&companies=立讯精密,鸿海精密&years=2023,2024
    """
    if not _neo4j_available():
        return jsonify({"error": "Neo4j不可用"}), 503

    indicator = request.args.get("indicator")
    if not indicator:
        return jsonify({"error": "请提供indicator参数"}), 400

    companies = request.args.get("companies", "").split(",") if request.args.get("companies") else None
    years = [int(y) for y in request.args.get("years", "").split(",") if y.strip()] if request.args.get("years") else None

    import neo4j_repository
    results = neo4j_repository.compare_indicator(indicator, companies, years)
    return jsonify(results)


@app.route("/api/compare/field", methods=["GET"])
def compare_field():
    """
    跨公司对比原始字段。
    ?field_key=营业收入&companies=立讯精密,鸿海精密&years=2023,2024
    """
    if not _neo4j_available():
        return jsonify({"error": "Neo4j不可用"}), 503

    field_key = request.args.get("field_key")
    if not field_key:
        return jsonify({"error": "请提供field_key参数"}), 400

    companies = request.args.get("companies", "").split(",") if request.args.get("companies") else None
    years = [int(y) for y in request.args.get("years", "").split(",") if y.strip()] if request.args.get("years") else None

    import neo4j_repository
    results = neo4j_repository.compare_field(field_key, companies, years)
    return jsonify(results)


@app.route("/api/lineage/<company>/<int:year>/<indicator>", methods=["GET"])
def get_lineage(company, year, indicator):
    """获取指标的完整溯源链。"""
    if not _neo4j_available():
        return jsonify({"error": "Neo4j不可用"}), 503

    import neo4j_repository
    result = neo4j_repository.get_scoring_lineage(company, year, indicator)
    return jsonify(result)


@app.route("/api/trend/<company>", methods=["GET"])
def get_trend(company):
    """
    获取某公司某指标的多年趋势。
    ?indicator=ROE当期值
    """
    if not _neo4j_available():
        return jsonify({"error": "Neo4j不可用"}), 503

    indicator = request.args.get("indicator")
    if not indicator:
        return jsonify({"error": "请提供indicator参数"}), 400

    import neo4j_repository
    results = neo4j_repository.get_company_trend(company, indicator)
    return jsonify(results)


@app.route("/api/scorings/summary", methods=["GET"])
def scorings_summary():
    """获取所有公司最新评分总览。"""
    if not _neo4j_available():
        return jsonify({"error": "Neo4j不可用"}), 503

    import neo4j_repository
    return jsonify(neo4j_repository.get_all_scorings_summary())


# ---------------------------------------------------------------------------
# Ontology API
# ---------------------------------------------------------------------------

@app.route("/api/ontology", methods=["GET"])
def get_ontology():
    """获取当前生效的ontology。"""
    try:
        data = ontology_service.load_current()
        return jsonify(data)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/ontology/versions", methods=["GET"])
def list_ontology_versions():
    return jsonify(ontology_service.list_versions())


@app.route("/api/ontology/versions/<int:version>", methods=["GET"])
def get_ontology_version(version):
    try:
        return jsonify(ontology_service.get_version(version))
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/ontology/save", methods=["POST"])
def save_ontology():
    body = request.get_json()
    if not body or "terms" not in body:
        return jsonify({"error": "请提供terms字段"}), 400

    result = ontology_service.save_new_version(
        {"terms": body["terms"], "relationships": body.get("relationships", [])},
        author=body.get("author", "user"),
        description=body.get("description", "")
    )

    # Sync to Neo4j
    try:
        if _neo4j_available():
            import neo4j_repository
            neo4j_repository.sync_ontology_terms(result)
    except Exception:
        pass

    return jsonify(result)


@app.route("/api/ontology/term/<term_id>", methods=["GET"])
def get_term(term_id):
    term = ontology_service.get_term(term_id)
    if term is None:
        return jsonify({"error": f"术语 {term_id} 不存在"}), 404
    return jsonify({"term_id": term_id, **term})


@app.route("/api/ontology/term/<term_id>", methods=["PUT"])
def update_term(term_id):
    body = request.get_json()
    if not body:
        return jsonify({"error": "请提供术语数据"}), 400
    result = ontology_service.update_term(
        term_id, body,
        author=body.pop("_author", "user"),
        description=body.pop("_description", "")
    )
    return jsonify({"version": result["version"], "term_id": term_id})


@app.route("/api/ontology/term/<term_id>", methods=["DELETE"])
def delete_term(term_id):
    try:
        result = ontology_service.delete_term(term_id)
        return jsonify({"version": result["version"], "deleted": term_id})
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/ontology/rollback/<int:version>", methods=["POST"])
def rollback_ontology(version):
    try:
        result = ontology_service.rollback_to(version)
        return jsonify({"version": result["version"], "rolled_back_from": version})
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/ontology/diff", methods=["GET"])
def diff_ontology():
    v1 = request.args.get("v1", type=int)
    v2 = request.args.get("v2", type=int)
    if v1 is None or v2 is None:
        return jsonify({"error": "请提供v1和v2参数"}), 400
    try:
        return jsonify(ontology_service.diff_versions(v1, v2))
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404


@app.route("/api/health", methods=["GET"])
def health():
    neo4j = _neo4j_available()
    return jsonify({"status": "ok", "neo4j": neo4j})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
