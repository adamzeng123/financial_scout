"""
财报侦察官 - Neo4j数据访问层
所有Cypher查询集中在此文件。
核心原则：get_financial_data()返回的dict结构与financial_data.json完全一致，
使得scorer.py无需任何修改。
"""

from datetime import datetime, timezone
from neo4j_client import get_session


# ---------------------------------------------------------------------------
# 写入：公司 + 财务数据
# ---------------------------------------------------------------------------

def upsert_company(name: str, metadata: dict | None = None) -> None:
    """创建或更新公司节点。"""
    meta = metadata or {}
    with get_session() as session:
        session.run(
            """
            MERGE (c:Company {name: $name})
            SET c.stock_code = $stock_code,
                c.industry = $industry,
                c.updated_at = $now
            """,
            name=name,
            stock_code=meta.get("stock_code", ""),
            industry=meta.get("industry", ""),
            now=datetime.now(timezone.utc).isoformat()
        )


def upsert_financial_data(data: dict) -> dict:
    """
    将financial_data.json结构的数据写入Neo4j。
    幂等：使用MERGE，重复导入不会创建重复节点。

    返回统计信息 {"company": ..., "year": ..., "data_points": int}
    """
    company = data.get("company", "")
    year = data.get("report_year", 0)
    currency = data.get("currency", "RMB")
    unit = data.get("unit", "元")

    data_points = []
    for period_key in ["current_period", "prior_period"]:
        period = data.get(period_key, {})
        period_label = period.get("label", period_key)
        period_year = year if period_key == "current_period" else year - 1

        for table_key in ["balance_sheet", "income_statement", "cash_flow"]:
            table = period.get(table_key, {})
            for field_key, value in table.items():
                if value is not None:
                    data_points.append({
                        "company": company,
                        "year": period_year,
                        "period_label": period_label,
                        "source_table": table_key,
                        "field_key": field_key,
                        "value": float(value),
                        "currency": currency,
                        "unit": unit,
                    })

    with get_session() as session:
        # 创建公司节点
        session.run(
            "MERGE (c:Company {name: $name})",
            name=company
        )

        # 批量写入数据点
        session.run(
            """
            UNWIND $points AS p
            MERGE (c:Company {name: p.company})
            MERGE (c)-[:HAS_PERIOD]->(rp:ReportingPeriod {company: p.company, year: p.year})
              ON CREATE SET rp.label = p.period_label, rp.currency = p.currency, rp.unit = p.unit
            MERGE (rp)-[:HAS_STATEMENT]->(fs:FinancialStatement {company: p.company, year: p.year, type: p.source_table})
            MERGE (fs)-[:CONTAINS]->(dp:DataPoint {company: p.company, year: p.year, field_key: p.field_key})
              ON CREATE SET dp.source_table = p.source_table
            SET dp.value = p.value
            """,
            points=data_points
        )

        # 创建相邻年度的PRIOR_PERIOD关系
        session.run(
            """
            MATCH (cur:ReportingPeriod {company: $company, year: $year})
            MATCH (pri:ReportingPeriod {company: $company, year: $prior_year})
            MERGE (cur)-[:PRIOR_PERIOD]->(pri)
            """,
            company=company, year=year, prior_year=year - 1
        )

    return {"company": company, "year": year, "data_points": len(data_points)}


# ---------------------------------------------------------------------------
# 写入：审计意见
# ---------------------------------------------------------------------------

def upsert_audit_opinion(company: str, year: int, text: str,
                         opinion_type: str, is_clean: bool) -> None:
    """写入审计意见节点。"""
    with get_session() as session:
        session.run(
            """
            MERGE (c:Company {name: $company})
            MERGE (c)-[:HAS_PERIOD]->(rp:ReportingPeriod {company: $company, year: $year})
            MERGE (rp)-[:HAS_AUDIT]->(ao:AuditOpinion {company: $company, year: $year})
            SET ao.text = $text, ao.opinion_type = $opinion_type, ao.is_clean = $is_clean
            """,
            company=company, year=year, text=text,
            opinion_type=opinion_type, is_clean=is_clean
        )


# ---------------------------------------------------------------------------
# 写入：评分结果
# ---------------------------------------------------------------------------

def save_scoring_result(company: str, year: int, result: dict) -> None:
    """
    将run_scoring()的返回值写入Neo4j。
    包含ScoringResult主节点 + 16个IndicatorScore子节点 + 红线检查节点。
    每个IndicatorScore通过DERIVED_FROM连接到对应的DataPoint。
    """
    with get_session() as session:
        # 主评分节点
        session.run(
            """
            MERGE (c:Company {name: $company})
            MERGE (c)-[:HAS_PERIOD]->(rp:ReportingPeriod {company: $company, year: $year})
            MERGE (rp)-[:HAS_SCORING]->(sr:ScoringResult {company: $company, year: $year})
            SET sr.raw_total = $raw_total,
                sr.final_total = $final_total,
                sr.max_total = $max_total,
                sr.rating = $rating,
                sr.roe_method = $roe_method,
                sr.debt_scope = $debt_scope,
                sr.computed_at = $now
            """,
            company=company, year=year,
            raw_total=result["raw_total"],
            final_total=result["final_total"],
            max_total=result["max_total"],
            rating=result["rating"],
            roe_method=result["options"]["roe_method"],
            debt_scope=result["options"]["debt_scope"],
            now=datetime.now(timezone.utc).isoformat()
        )

        # 指标得分节点
        indicators = []
        for name, item in result["scores"].items():
            value = item.get("value", item.get("trend", None))
            if isinstance(value, float):
                value = value
            else:
                value = None
            indicators.append({
                "name": name,
                "value": value,
                "score": item["score"],
                "max": item["max"],
                "category": item["category"],
                "matched_rule": item.get("matched_rule", ""),
                "company": company,
                "year": year,
            })

        session.run(
            """
            UNWIND $indicators AS ind
            MATCH (sr:ScoringResult {company: ind.company, year: ind.year})
            MERGE (sr)-[:INCLUDES_INDICATOR]->(is:IndicatorScore {company: ind.company, year: ind.year, name: ind.name})
            SET is.value = ind.value,
                is.score = ind.score,
                is.max = ind.max,
                is.category = ind.category,
                is.matched_rule = ind.matched_rule
            """,
            indicators=indicators
        )

        # 红线检查节点
        red_lines = []
        for rl in result.get("red_lines", []):
            if isinstance(rl, dict):
                red_lines.append({
                    "rule": rl["rule"],
                    "triggered": rl["triggered"],
                    "cap": rl["cap"],
                    "explanation": rl["explanation"],
                    "company": company,
                    "year": year,
                })

        if red_lines:
            session.run(
                """
                UNWIND $red_lines AS rl
                MATCH (sr:ScoringResult {company: rl.company, year: rl.year})
                MERGE (sr)-[:INCLUDES_REDLINE]->(rc:RedLineCheck {company: rl.company, year: rl.year, rule: rl.rule})
                SET rc.triggered = rl.triggered, rc.cap = rl.cap, rc.explanation = rl.explanation
                """,
                red_lines=red_lines
            )


# ---------------------------------------------------------------------------
# 写入：Ontology同步
# ---------------------------------------------------------------------------

def sync_ontology_terms(ontology_data: dict) -> None:
    """将ontology terms和relationships同步到Neo4j。"""
    version = ontology_data.get("version", 0)
    terms = []
    for term_id, t in ontology_data.get("terms", {}).items():
        terms.append({
            "term_id": term_id,
            "canonical": t.get("canonical", ""),
            "field_key": t.get("field_key", ""),
            "source_table": t.get("source_table", ""),
            "definition": t.get("definition", ""),
            "version": version,
        })

    rels = []
    for r in ontology_data.get("relationships", []):
        rels.append({
            "from_id": r["from"],
            "to_id": r["to"],
            "type": r.get("type", "derived_from"),
            "formula": r.get("formula", ""),
            "description": r.get("description", ""),
        })

    with get_session() as session:
        # Upsert terms
        session.run(
            """
            UNWIND $terms AS t
            MERGE (ot:OntologyTerm {term_id: t.term_id})
            SET ot.canonical = t.canonical,
                ot.field_key = t.field_key,
                ot.source_table = t.source_table,
                ot.definition = t.definition,
                ot.version = t.version
            """,
            terms=terms
        )

        # 清除旧关系再重建
        session.run("MATCH (:OntologyTerm)-[r:ONTO_REL]->(:OntologyTerm) DELETE r")

        if rels:
            session.run(
                """
                UNWIND $rels AS r
                MERGE (a:OntologyTerm {term_id: r.from_id})
                MERGE (b:OntologyTerm {term_id: r.to_id})
                CREATE (a)-[:ONTO_REL {type: r.type, formula: r.formula, description: r.description}]->(b)
                """,
                rels=rels
            )

        # 将DataPoint链接到OntologyTerm（通过field_key匹配）
        session.run(
            """
            MATCH (dp:DataPoint), (ot:OntologyTerm)
            WHERE dp.field_key = ot.field_key
            MERGE (dp)-[:DEFINED_BY]->(ot)
            """
        )


# ---------------------------------------------------------------------------
# 读取：还原为financial_data.json格式
# ---------------------------------------------------------------------------

def get_financial_data(company: str, year: int) -> dict | None:
    """
    从Neo4j读取数据，返回与financial_data.json完全相同的dict结构。
    这样scorer.py的run_scoring()无需任何修改。
    """
    with get_session() as session:
        # 取当期和上期的所有DataPoint
        result = session.run(
            """
            MATCH (dp:DataPoint)
            WHERE dp.company = $company AND dp.year IN [$year, $prior_year]
            RETURN dp.year AS year, dp.source_table AS source_table,
                   dp.field_key AS field_key, dp.value AS value
            """,
            company=company, year=year, prior_year=year - 1
        )

        records = list(result)
        if not records:
            return None

        # 重建嵌套dict
        data = {
            "company": company,
            "report_year": year,
            "currency": "RMB",
            "unit": "元",
            "current_period": {
                "label": f"{year}年度",
                "balance_sheet": {},
                "income_statement": {},
                "cash_flow": {},
            },
            "prior_period": {
                "label": f"{year - 1}年度",
                "balance_sheet": {},
                "income_statement": {},
                "cash_flow": {},
            },
        }

        for rec in records:
            period_key = "current_period" if rec["year"] == year else "prior_period"
            table_key = rec["source_table"]
            if table_key in data[period_key]:
                data[period_key][table_key][rec["field_key"]] = rec["value"]

        return data


# ---------------------------------------------------------------------------
# 查询：公司列表
# ---------------------------------------------------------------------------

def get_companies() -> list[dict]:
    """列出所有公司及其可用年度。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (c:Company)-[:HAS_PERIOD]->(rp:ReportingPeriod)
            WITH c, collect(DISTINCT rp.year) AS years
            RETURN c.name AS name, c.stock_code AS stock_code,
                   c.industry AS industry, years
            ORDER BY c.name
            """
        )
        return [dict(r) for r in result]


def get_company_years(company: str) -> list[int]:
    """获取公司的可用年度列表。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (c:Company {name: $company})-[:HAS_PERIOD]->(rp:ReportingPeriod)
            RETURN rp.year AS year ORDER BY year DESC
            """,
            company=company
        )
        return [r["year"] for r in result]


# ---------------------------------------------------------------------------
# 查询：跨公司对比
# ---------------------------------------------------------------------------

def compare_indicator(indicator_name: str,
                      companies: list[str] | None = None,
                      years: list[int] | None = None) -> list[dict]:
    """
    跨公司对比某个评分指标。
    返回 [{"company": ..., "year": ..., "value": ..., "score": ..., "max": ..., "matched_rule": ...}]
    """
    where_parts = ["is.name = $indicator_name"]
    params = {"indicator_name": indicator_name}

    if companies:
        where_parts.append("is.company IN $companies")
        params["companies"] = companies
    if years:
        where_parts.append("is.year IN $years")
        params["years"] = years

    where_clause = " AND ".join(where_parts)

    with get_session() as session:
        result = session.run(
            f"""
            MATCH (is:IndicatorScore)
            WHERE {where_clause}
            RETURN is.company AS company, is.year AS year,
                   is.value AS value, is.score AS score,
                   is.max AS max, is.matched_rule AS matched_rule,
                   is.category AS category
            ORDER BY is.year, is.company
            """,
            **params
        )
        return [dict(r) for r in result]


def compare_field(field_key: str,
                  companies: list[str] | None = None,
                  years: list[int] | None = None) -> list[dict]:
    """
    跨公司对比某个原始字段值。
    返回 [{"company": ..., "year": ..., "field_key": ..., "value": ...}]
    """
    where_parts = ["dp.field_key = $field_key"]
    params = {"field_key": field_key}

    if companies:
        where_parts.append("dp.company IN $companies")
        params["companies"] = companies
    if years:
        where_parts.append("dp.year IN $years")
        params["years"] = years

    where_clause = " AND ".join(where_parts)

    with get_session() as session:
        result = session.run(
            f"""
            MATCH (dp:DataPoint)
            WHERE {where_clause}
            RETURN dp.company AS company, dp.year AS year,
                   dp.field_key AS field_key, dp.value AS value
            ORDER BY dp.year, dp.company
            """,
            **params
        )
        return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# 查询：溯源（Lineage）
# ---------------------------------------------------------------------------

def get_scoring_lineage(company: str, year: int,
                        indicator_name: str) -> dict:
    """
    获取某个指标的完整溯源链：
    IndicatorScore → ScoringResult → DataPoints used
    """
    with get_session() as session:
        # 获取指标得分
        indicator = session.run(
            """
            MATCH (is:IndicatorScore {company: $company, year: $year, name: $name})
            RETURN is.value AS value, is.score AS score, is.max AS max,
                   is.category AS category, is.matched_rule AS matched_rule
            """,
            company=company, year=year, name=indicator_name
        ).single()

        if not indicator:
            return {"error": f"未找到 {company} {year} 的 {indicator_name}"}

        # 获取该公司该年度的所有数据点（作为输入来源）
        data_points = session.run(
            """
            MATCH (dp:DataPoint {company: $company})
            WHERE dp.year IN [$year, $prior_year]
            RETURN dp.field_key AS field_key, dp.value AS value,
                   dp.year AS year, dp.source_table AS source_table
            ORDER BY dp.year DESC, dp.source_table, dp.field_key
            """,
            company=company, year=year, prior_year=year - 1
        )

        # 获取评分总览
        scoring = session.run(
            """
            MATCH (sr:ScoringResult {company: $company, year: $year})
            RETURN sr.raw_total AS raw_total, sr.final_total AS final_total,
                   sr.rating AS rating, sr.roe_method AS roe_method,
                   sr.debt_scope AS debt_scope, sr.computed_at AS computed_at
            """,
            company=company, year=year
        ).single()

        return {
            "indicator": dict(indicator),
            "scoring": dict(scoring) if scoring else None,
            "data_points": [dict(r) for r in data_points],
        }


# ---------------------------------------------------------------------------
# 查询：趋势
# ---------------------------------------------------------------------------

def get_company_trend(company: str,
                      indicator_name: str) -> list[dict]:
    """获取某公司某指标的多年趋势。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (is:IndicatorScore {company: $company, name: $name})
            RETURN is.year AS year, is.value AS value,
                   is.score AS score, is.max AS max,
                   is.matched_rule AS matched_rule
            ORDER BY is.year
            """,
            company=company, name=indicator_name
        )
        return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# 查询：总览仪表盘
# ---------------------------------------------------------------------------

def get_all_scorings_summary() -> list[dict]:
    """获取所有公司最新年度的评分总览。"""
    with get_session() as session:
        result = session.run(
            """
            MATCH (sr:ScoringResult)
            WITH sr.company AS company, max(sr.year) AS latest_year
            MATCH (sr2:ScoringResult {company: company, year: latest_year})
            RETURN sr2.company AS company, sr2.year AS year,
                   sr2.raw_total AS raw_total, sr2.final_total AS final_total,
                   sr2.rating AS rating
            ORDER BY sr2.final_total DESC
            """
        )
        return [dict(r) for r in result]
