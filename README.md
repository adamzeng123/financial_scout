# 财报侦察官 (Financial Scout)

基于财务数据的结构化评分系统，从年报PDF中自动提取数据，通过16项指标计算100分制财务质量评分，支持跨公司对比分析。

## 演示视频

[![Financial Scout Demo](https://img.youtube.com/vi/s_T65UJgOnQ/maxresdefault.jpg)](https://www.youtube.com/watch?v=s_T65UJgOnQ)

> 点击图片观看完整演示

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React 19 + Vite)               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ 评分仪表盘    │  │ 跨公司对比    │  │ Ontology 编辑器     │    │
│  │ ScoreCard    │  │ 雷达图/排行榜 │  │ D3关系图谱          │    │
│  │ 瀑布图/红线   │  │ 指标柱状图    │  │ 术语CRUD/版本控制   │    │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘    │
│         │                 │                    │                │
│         ▼                 ▼                    ▼                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │            REST API (Flask)  :5000                       │   │
│  │  /api/score     /api/compare/*   /api/ontology/*        │   │
│  │  /api/extract   /api/lineage/*   /api/trend/*           │   │
│  └───┬─────────────────┬──────────────────┬────────────────┘   │
│      │                 │                  │                     │
│      ▼                 ▼                  ▼                     │
│  ┌────────┐    ┌──────────────┐    ┌────────────┐             │
│  │scorer  │    │ llm_client   │    │ ontology   │             │
│  │.py     │    │ .py          │    │ _service.py│             │
│  │16指标   │    │ GPT-4o-mini  │    │ 版本化JSON │             │
│  │评分逻辑 │    │ 审计分类+评价 │    │ 术语/关系  │             │
│  └────────┘    └──────────────┘    └────────────┘             │
│      │                                    │                    │
│      ▼                                    ▼                    │
│  ┌──────────────────────────────────────────────┐             │
│  │              数据层                           │             │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────┐ │             │
│  │  │ JSON文件  │  │ Neo4j    │  │ ontology/  │ │             │
│  │  │ data/    │  │ 图数据库  │  │ v1.json    │ │             │
│  │  │ 主存储    │  │ 跨公司查询│  │ current    │ │             │
│  │  └──────────┘  └──────────┘  └────────────┘ │             │
│  └──────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

## 项目结构

```
financial-scout/
├── src/                           # 后端核心模块
│   ├── app.py                     # Flask API (评分/对比/ontology/提取)
│   ├── scorer.py                  # 评分引擎 (16指标 + 红线 + 瀑布图)
│   ├── llm_client.py              # LLM调用 (审计分类 + 评价生成)
│   ├── pdf_extractor.py           # PDF→JSON (自动单位检测 + ontology别名)
│   ├── ontology_service.py        # Ontology CRUD + 版本控制
│   ├── neo4j_client.py            # Neo4j连接管理
│   ├── neo4j_repository.py        # Neo4j数据访问 (Cypher查询)
│   └── migration.py               # JSON→Neo4j 数据迁移脚本
│
├── frontend/                      # React前端
│   └── src/
│       ├── App.jsx                # 评分仪表盘 (主页)
│       ├── CompanyComparison.jsx  # 跨公司对比 (雷达图/排行榜)
│       ├── OntologyEditor.jsx     # Ontology编辑器 (术语/关系CRUD)
│       └── OntologyGraph.jsx      # D3力导向关系图谱
│
├── data/                          # 财务数据 (每公司一个子目录)
│   ├── financial_data.json        # 立讯精密2024 (默认数据集)
│   ├── audit_opinion.txt
│   ├── scoring_cache.json         # LLM结果缓存 (自动生成)
│   └── 比亚迪股份有限公司_2024/
│       ├── financial_data.json
│       └── audit_opinion.txt
│
├── ontology/                      # 术语本体 (版本化JSON)
│   ├── v1.json                    # 版本1: 25个术语 + 9条关系
│   └── current.json               # 当前生效版本
│
├── tests/
│   ├── test_scorer.py             # 评分引擎测试 (26个)
│   └── test_ontology.py           # Ontology服务测试 (11个)
│
├── docker-compose.yml             # 一键启动 (Neo4j + 后端 + 前端)
├── Dockerfile.backend
├── Dockerfile.frontend
└── pyproject.toml
```

## 快速启动

### 方式一：Docker Compose (推荐)

```powershell
# 设置 OpenAI API Key
$env:OPENAI_API_KEY="sk-..."

# 一键启动全部服务 (Neo4j + 后端 + 前端)
docker compose up --build

# 数据迁移 (首次运行)
docker compose exec backend uv run python src/migration.py
```

| 服务 | URL | 说明 |
|------|-----|------|
| 前端 | http://localhost:5173 | 评分仪表盘 / 跨公司对比 / Ontology编辑器 |
| 后端 API | http://localhost:5000 | REST API |
| Neo4j Browser | http://localhost:7474 | 图数据库 (neo4j/financial_scout) |

所有服务支持**热更新**：编辑本地 `src/` 或 `frontend/src/` 文件，后端自动重启，前端浏览器即时刷新。

### 方式二：本地开发

```powershell
# 安装依赖
uv sync
cd frontend && npm install && cd ..

# 启动 Neo4j (可选，跨公司对比功能需要)
docker compose up neo4j -d

# 启动后端
$env:OPENAI_API_KEY="sk-..."; $env:NEO4J_PASSWORD="financial_scout"; uv run python src/app.py

# 启动前端 (另一个终端)
cd frontend; npm run dev

# 运行测试
uv run pytest tests/ -v
```

## 核心功能

### 1. 财务评分 (100分制)

| 类别 | 满分 | 指标 |
|------|------|------|
| 商业质量 | 30 | ROE、毛利率、毛利率变动、期间费用率趋势 |
| 财务安全 | 25 | 资产负债率、利息保障倍数、流动比率、现金/短期负债 |
| 盈利质量与现金含量 | 25 | 经营现金流/利润、自由现金流率、应收增速、存货增速 |
| 成长质量 | 20 | 营收增速、净利润增速、双增、ROE趋势 |

**红线机制**：3条一票否决规则，触发后强制压低总分上限 (59/54/49分)。

每个指标包含完整的**可追溯信息**：
- `formula` — 计算公式
- `detail` — 具体数值代入过程
- `matched_rule` — 命中了哪个评分区间
- `thresholds` — 全部阈值说明

### 2. PDF自动提取

```
年报PDF → PyMuPDF提取文本 → 关键词定位报表页 → LLM提取25个字段 → 自动单位检测 → JSON
```

- **Ontology别名注入**：提取时从ontology读取三语别名，注入LLM prompt，提高跨公司术语容错
- **单位自动检测**：LLM识别报表单位（元/千元/万元/百万元），代码自动换算
- **置信度标注**：单位检测结果附带 high/medium/low 置信度

### 3. Ontology 术语本体

25个财务术语的结构化定义，支持：
- **三语别名**：zh_CN / zh_TW / en，用于跨公司/跨语言PDF提取
- **术语关系**：derived_from (推导)、related_to (关联)，含公式
- **版本控制**：每次编辑自动创建新版本，支持回滚、diff对比
- **D3关系图谱**：力导向图可视化术语间的推导和关联关系
- **前端编辑器**：CRUD术语和关系，无需改代码

### 4. Neo4j 图数据库

```
(Company) → (ReportingPeriod) → (FinancialStatement) → (DataPoint)
                ↓                                           ↓
         (ScoringResult) → (IndicatorScore)          (OntologyTerm)
                ↓
          (AuditOpinion)
          (RedLineCheck)
```

提供跨公司查询能力：
- **指标对比**：同一指标在不同公司间的得分对比
- **原始数据对比**：同一字段在不同公司间的数值对比
- **评分排行榜**：所有公司按总分排序
- **溯源查询**：从评分追溯到原始数据点

Neo4j 为可选组件，系统在 Neo4j 不可用时自动降级为 JSON 文件模式。

### 5. 跨公司对比

前端"跨公司对比"页面：
- **公司选择器**：从 Neo4j 加载所有公司，点击选择/取消
- **雷达图**：6个核心指标的得分率对比
- **评分排行榜**：按总分降序，显示评级和条形图
- **分类别柱状图**：16个指标按类别分组，横向柱状图对比

### 6. 评分缓存

首次评分后结果缓存为 `scoring_cache.json`，后续页面加载直接读缓存（<100ms），无需重复调用LLM。

缓存自动失效条件：`financial_data.json` 或 `audit_opinion.txt` 内容变更（MD5指纹检测）。

前端提供"重新AI分析"按钮，手动强制刷新。

## API 接口

### 评分

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/score` | 评分（优先读缓存，无缓存时调LLM） |
| POST | `/api/score/refresh` | 强制重新评分（忽略缓存） |
| POST | `/api/score/compute` | 仅计算评分（不调LLM，用于口径切换） |
| GET | `/api/datasets` | 列出所有数据集 |
| POST | `/api/extract` | 上传PDF提取财务数据 |

### 跨公司 (需要Neo4j)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/compare/companies` | 列出所有公司 |
| GET | `/api/compare/indicator?indicator=ROE当期值&companies=A,B` | 指标对比 |
| GET | `/api/compare/field?field_key=营业收入` | 原始数据对比 |
| GET | `/api/lineage/<公司>/<年度>/<指标>` | 指标溯源 |
| GET | `/api/trend/<公司>?indicator=ROE当期值` | 多年趋势 |
| GET | `/api/scorings/summary` | 评分排行榜 |

### Ontology

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ontology` | 获取当前ontology |
| POST | `/api/ontology/save` | 保存新版本 |
| GET/PUT/DELETE | `/api/ontology/term/<id>` | 术语CRUD |
| GET | `/api/ontology/versions` | 版本列表 |
| POST | `/api/ontology/rollback/<v>` | 回滚 |
| GET | `/api/ontology/diff?v1=1&v2=2` | 版本对比 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（含Neo4j状态） |
| GET | `/api/neo4j/status` | Neo4j连接状态 |

## 导入新公司

```powershell
# 1. 运行PDF提取
$env:OPENAI_API_KEY="sk-..."
uv run python src/pdf_extractor.py <pdf路径> <公司名> <报告年度>

# 示例
uv run python src/pdf_extractor.py data/byd_2024.pdf 比亚迪股份有限公司 2024

# 2. 导入Neo4j (可选)
$env:NEO4J_PASSWORD="financial_scout"
uv run python src/migration.py
```

提取器会自动：
- 用 PyMuPDF 提取PDF文本
- 关键词定位三张报表和审计意见
- LLM 提取 25 个字段 × 2 期（当期+上期）
- 从 Ontology 注入术语别名提高容错
- 自动检测金额单位（元/千元/万元等）并换算
- 保存为 `data/<公司名>_<年度>/financial_data.json`

## 设计原则

| 原则 | 做法 |
|------|------|
| **LLM不做计算** | 16项指标全部由Python代码计算，LLM仅做文本理解和生成 |
| **可追溯** | 每个指标附带公式、数值代入、命中规则，形成完整审计链 |
| **Graceful degradation** | Neo4j不可用时降级为JSON模式；LLM失败时回退到关键词匹配 |
| **Dual-write** | 数据同时写入JSON文件和Neo4j，互为备份 |
| **版本化** | Ontology每次编辑自动创建新版本，可回滚可diff |
| **缓存优先** | LLM结果缓存到文件，页面加载秒开，按需刷新 |

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 19, Vite, Recharts (图表), D3 (关系图谱) |
| 后端 | Python 3.13+, Flask, uv |
| LLM | OpenAI GPT-4o-mini |
| PDF解析 | PyMuPDF (fitz) |
| 图数据库 | Neo4j 5 Community |
| 容器化 | Docker Compose (热更新) |
| 测试 | pytest (37个测试) |

## 测试

```powershell
uv run pytest tests/ -v
```

| 测试组 | 数量 | 覆盖范围 |
|--------|------|---------|
| TestLuxshareScoring | 10 | 立讯精密真实数据完整评分验证 |
| TestRedLineRules | 5 | 三条红线规则 + 叠加取最严 |
| TestIndicatorCalculations | 10 | 衍生指标公式正确性 |
| TestRatingMapping | 1 | 评级边界映射 |
| TestOntologyService | 11 | Ontology CRUD、版本控制、回滚、diff、别名查询 |

## 当前数据

| 公司 | 年度 | 总分 | 评级 |
|------|------|------|------|
| 立讯精密工业股份有限公司 | 2024 | 76 | B级（质量尚可可跟踪） |
| 比亚迪股份有限公司 | 2024 | 70 | B级（质量尚可可跟踪） |
