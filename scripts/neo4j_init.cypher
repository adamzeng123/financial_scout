// ============================================================
//  财报侦察官 - Neo4j 期初初始化脚本
//  基于 ontology/current.json v2 生成
// ============================================================
//
//  用途：在全新 Neo4j 实例上一键建立 Schema + Ontology 基础数据。
//  财务数据（公司/报表/评分）通过 src/migration.py 导入，不在此脚本中。
//
//  运行方式（本地 cypher-shell）：
//    cypher-shell -u neo4j -p financial_scout -f scripts/neo4j_init.cypher
//
//  运行方式（Docker）：
//    docker exec financial-scout-neo4j \
//      cypher-shell -u neo4j -p financial_scout \
//      -f /var/lib/neo4j/import/scripts/neo4j_init.cypher
//
//  幂等：所有语句使用 MERGE / IF NOT EXISTS，可安全重复执行。
// ============================================================


// ── 1. 约束 & 索引 ───────────────────────────────────────────

CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company)      REQUIRE c.name    IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (t:OntologyTerm) REQUIRE t.term_id IS UNIQUE;

CREATE INDEX IF NOT EXISTS FOR (d:DataPoint)     ON (d.field_key, d.company, d.year);
CREATE INDEX IF NOT EXISTS FOR (s:ScoringResult) ON (s.company, s.year);
CREATE INDEX IF NOT EXISTS FOR (i:IndicatorScore) ON (i.name, i.company, i.year);


// ── 2. Ontology 术语（v2）────────────────────────────────────
//  资产负债表项目

MERGE (t:OntologyTerm {term_id: 'cash_and_equivalents'})
SET t.canonical    = '货币资金',
    t.field_key    = '货币资金',
    t.source_table = 'balance_sheet',
    t.definition   = '企业持有的现金、银行存款及可随时变现的短期投资，是流动性最强的资产。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'accounts_receivable'})
SET t.canonical    = '应收账款',
    t.field_key    = '应收账款',
    t.source_table = 'balance_sheet',
    t.definition   = '企业因销售商品、提供服务等经营活动应收取的款项，反映信用销售规模。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'inventory'})
SET t.canonical    = '存货',
    t.field_key    = '存货',
    t.source_table = 'balance_sheet',
    t.definition   = '企业在日常活动中持有以备出售的产成品、在产品、原材料等。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'current_assets'})
SET t.canonical    = '流动资产合计',
    t.field_key    = '流动资产合计',
    t.source_table = 'balance_sheet',
    t.definition   = '企业预计在一个正常营业周期内或一年内变现、出售或耗用的资产总额。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'total_assets'})
SET t.canonical    = '资产总计',
    t.field_key    = '资产总计',
    t.source_table = 'balance_sheet',
    t.definition   = '企业所拥有或控制的全部经济资源的总额，是企业规模的核心度量。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'short_term_borrowings'})
SET t.canonical    = '短期借款',
    t.field_key    = '短期借款',
    t.source_table = 'balance_sheet',
    t.definition   = '企业向银行或其他金融机构借入的期限在一年以内的各种借款。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'notes_payable'})
SET t.canonical    = '应付票据',
    t.field_key    = '应付票据',
    t.source_table = 'balance_sheet',
    t.definition   = '企业因购买材料、商品或接受服务等而开出的商业汇票。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'trading_liabilities'})
SET t.canonical    = '交易性金融负债',
    t.field_key    = '交易性金融负债',
    t.source_table = 'balance_sheet',
    t.definition   = '企业以交易为目的持有的金融负债，按公允价值计量。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'current_non_current_liabilities'})
SET t.canonical    = '一年内到期的非流动负债',
    t.field_key    = '一年内到期的非流动负债',
    t.source_table = 'balance_sheet',
    t.definition   = '将在一年内到期偿还的长期负债部分，需要短期资金安排。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'current_liabilities'})
SET t.canonical    = '流动负债合计',
    t.field_key    = '流动负债合计',
    t.source_table = 'balance_sheet',
    t.definition   = '企业预计在一个正常营业周期内或一年内需要偿还的全部债务。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'total_liabilities'})
SET t.canonical    = '负债合计',
    t.field_key    = '负债合计',
    t.source_table = 'balance_sheet',
    t.definition   = '企业承担的全部债务总额，包括流动负债和非流动负债。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'equity_parent'})
SET t.canonical    = '归属于母公司所有者权益合计',
    t.field_key    = '归属于母公司所有者权益合计',
    t.source_table = 'balance_sheet',
    t.definition   = '扣除少数股东权益后，属于母公司股东的净资产总额，是ROE的分母。',
    t.version      = 2;

//  利润表项目

MERGE (t:OntologyTerm {term_id: 'revenue'})
SET t.canonical    = '营业收入',
    t.field_key    = '营业收入',
    t.source_table = 'income_statement',
    t.definition   = '企业在日常经营活动中形成的经济利益总流入，是衡量企业规模和成长性的核心指标。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'cost_of_revenue'})
SET t.canonical    = '营业成本',
    t.field_key    = '营业成本',
    t.source_table = 'income_statement',
    t.definition   = '企业为取得营业收入而发生的直接成本，与营业收入配比后得出毛利。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'selling_expenses'})
SET t.canonical    = '销售费用',
    t.field_key    = '销售费用',
    t.source_table = 'income_statement',
    t.definition   = '企业在销售商品和提供服务过程中发生的各种费用。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'admin_expenses'})
SET t.canonical    = '管理费用',
    t.field_key    = '管理费用',
    t.source_table = 'income_statement',
    t.definition   = '企业为组织和管理生产经营活动而发生的各种费用。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'rd_expenses'})
SET t.canonical    = '研发费用',
    t.field_key    = '研发费用',
    t.source_table = 'income_statement',
    t.definition   = '企业进行研究与开发活动发生的费用化支出，2018年后从管理费用中独立列示。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'finance_expenses'})
SET t.canonical    = '财务费用',
    t.field_key    = '财务费用',
    t.source_table = 'income_statement',
    t.definition   = '企业为筹集资金而发生的各种费用，包括利息支出、汇兑损失等。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'interest_expense'})
SET t.canonical    = '其中_利息费用',
    t.field_key    = '其中_利息费用',
    t.source_table = 'income_statement',
    t.definition   = '企业因借款而支付的利息，是财务费用的主要组成部分，用于计算利息保障倍数。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'profit_before_tax'})
SET t.canonical    = '利润总额',
    t.field_key    = '利润总额',
    t.source_table = 'income_statement',
    t.definition   = '企业在缴纳所得税之前的利润总额，加上利息费用即为息税前利润(EBIT)。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'income_tax'})
SET t.canonical    = '所得税费用',
    t.field_key    = '所得税费用',
    t.source_table = 'income_statement',
    t.definition   = '企业按税法规定计算的当期应交所得税及递延所得税之和。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'net_profit'})
SET t.canonical    = '净利润',
    t.field_key    = '净利润',
    t.source_table = 'income_statement',
    t.definition   = '企业在一定期间内的经营成果，等于利润总额减去所得税费用。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'net_profit_parent'})
SET t.canonical    = '归属于母公司股东的净利润',
    t.field_key    = '归属于母公司股东的净利润',
    t.source_table = 'income_statement',
    t.definition   = '扣除少数股东损益后，归属于母公司股东的净利润，是计算ROE的分子。',
    t.version      = 2;

//  现金流量表项目

MERGE (t:OntologyTerm {term_id: 'operating_cash_flow'})
SET t.canonical    = '经营活动产生的现金流量净额',
    t.field_key    = '经营活动产生的现金流量净额',
    t.source_table = 'cash_flow',
    t.definition   = '企业经营活动（非投资和筹资）产生的现金流入与流出的净差额，衡量利润的含金量。',
    t.version      = 2;

MERGE (t:OntologyTerm {term_id: 'capex'})
SET t.canonical    = '购建固定资产_无形资产和其他长期资产支付的现金',
    t.field_key    = '购建固定资产_无形资产和其他长期资产支付的现金',
    t.source_table = 'cash_flow',
    t.definition   = '企业为购建固定资产、无形资产等长期资产支付的现金，从经营现金流中扣除后得到自由现金流。',
    t.version      = 2;


// ── 3. Ontology 关系 ─────────────────────────────────────────
//  先清空旧关系（幂等），再重建

MATCH (:OntologyTerm)-[r:ONTO_REL]->(:OntologyTerm) DELETE r;

MATCH (a:OntologyTerm {term_id: 'gross_profit'}),  (b:OntologyTerm {term_id: 'revenue'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: 'revenue - cost_of_revenue',
       description: '毛利 = 营业收入 - 营业成本'}]->(b);

MATCH (a:OntologyTerm {term_id: 'ebit'}),           (b:OntologyTerm {term_id: 'profit_before_tax'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: 'profit_before_tax + interest_expense',
       description: '息税前利润 = 利润总额 + 利息费用'}]->(b);

MATCH (a:OntologyTerm {term_id: 'net_profit'}),     (b:OntologyTerm {term_id: 'profit_before_tax'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: 'profit_before_tax - income_tax',
       description: '净利润 = 利润总额 - 所得税费用'}]->(b);

MATCH (a:OntologyTerm {term_id: 'free_cash_flow'}), (b:OntologyTerm {term_id: 'operating_cash_flow'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: 'operating_cash_flow - capex',
       description: '自由现金流 = 经营现金流净额 - 资本性支出'}]->(b);

MATCH (a:OntologyTerm {term_id: 'roe'}),            (b:OntologyTerm {term_id: 'net_profit_parent'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: 'net_profit_parent / avg(equity_parent)',
       description: 'ROE = 归母净利润 / 平均归母权益'}]->(b);

MATCH (a:OntologyTerm {term_id: 'debt_ratio'}),     (b:OntologyTerm {term_id: 'total_liabilities'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: 'total_liabilities / total_assets',
       description: '资产负债率 = 负债合计 / 资产总计'}]->(b);

MATCH (a:OntologyTerm {term_id: 'current_ratio'}),  (b:OntologyTerm {term_id: 'current_assets'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: 'current_assets / current_liabilities',
       description: '流动比率 = 流动资产合计 / 流动负债合计'}]->(b);

MATCH (a:OntologyTerm {term_id: 'interest_coverage'}), (b:OntologyTerm {term_id: 'ebit'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: 'ebit / interest_expense',
       description: '利息保障倍数 = EBIT / 利息费用'}]->(b);

MATCH (a:OntologyTerm {term_id: 'period_expense_ratio'}), (b:OntologyTerm {term_id: 'selling_expenses'})
CREATE (a)-[:ONTO_REL {type: 'derived_from', formula: '(selling + admin + rd + finance) / revenue',
       description: '期间费用率 = 四费合计 / 营业收入'}]->(b);


// ── 4. DataPoint → OntologyTerm 链接（若财务数据已导入）────────

MATCH (dp:DataPoint), (ot:OntologyTerm)
WHERE dp.field_key = ot.field_key
MERGE (dp)-[:DEFINED_BY]->(ot);
