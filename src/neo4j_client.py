"""
财报侦察官 - Neo4j连接管理
提供driver单例和session上下文管理器。
Neo4j不可用时不影响系统核心功能（JSON fallback）。
"""

import os
from contextlib import contextmanager
from neo4j import GraphDatabase

_driver = None


def get_driver():
    """获取Neo4j driver单例。"""
    global _driver
    if _driver is None:
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "financial_scout")
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver


def close_driver():
    """关闭driver，在Flask app teardown时调用。"""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


@contextmanager
def get_session():
    """获取Neo4j session的上下文管理器。"""
    driver = get_driver()
    session = driver.session()
    try:
        yield session
    finally:
        session.close()


def is_available() -> bool:
    """检查Neo4j是否可用。"""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except Exception:
        return False


def ensure_constraints():
    """创建必要的唯一性约束和索引（幂等）。"""
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (t:OntologyTerm) REQUIRE t.term_id IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (d:DataPoint) ON (d.field_key, d.company, d.year)",
        "CREATE INDEX IF NOT EXISTS FOR (s:ScoringResult) ON (s.company, s.year)",
        "CREATE INDEX IF NOT EXISTS FOR (i:IndicatorScore) ON (i.name, i.company, i.year)",
    ]
    with get_session() as session:
        for cypher in constraints:
            session.run(cypher)
