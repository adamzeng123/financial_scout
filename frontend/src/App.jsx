import { useState, useEffect, useCallback } from 'react'
import './App.css'
import OntologyEditor from './OntologyEditor'
import './OntologyEditor.css'
import CompanyComparison from './CompanyComparison'
import './CompanyComparison.css'

const API_BASE = 'http://localhost:5000/api'

const CATEGORY_LABELS = {
  '商业质量': { max: 30, color: '#4f46e5' },
  '财务安全': { max: 25, color: '#059669' },
  '盈利质量与现金含量': { max: 25, color: '#d97706' },
  '成长质量': { max: 20, color: '#dc2626' },
}

function RatingBadge({ rating }) {
  const level = rating?.charAt(0) || '?'
  const colors = {
    A: '#059669', B: '#3b82f6', C: '#d97706', D: '#dc2626', E: '#7f1d1d'
  }
  return (
    <span className="rating-badge" style={{ background: colors[level] || '#666' }}>
      {rating}
    </span>
  )
}

function ScoreBar({ score, max }) {
  const pct = max > 0 ? (score / max) * 100 : 0
  return (
    <div className="score-bar-container">
      <div className="score-bar" style={{ width: `${pct}%` }} />
    </div>
  )
}

function formatValue(item) {
  const val = item.value ?? item.trend ?? 'N/A'
  if (typeof val === 'number') {
    return `${(val * 100).toFixed(2)}%`
  }
  return val
}

function ScoreCard({ name, item, roeMethod, debtScope }) {
  const [expanded, setExpanded] = useState(false)
  let extra = null

  if (name === 'ROE当期值') {
    extra = (
      <div className="extra-values">
        <span className={roeMethod === 'endpoint' ? 'active' : ''}>
          期末法: {(item.value_endpoint * 100).toFixed(2)}%
        </span>
        <span className={roeMethod === 'weighted_avg' ? 'active' : ''}>
          加权平均: {(item.value_weighted * 100).toFixed(2)}%
        </span>
      </div>
    )
  }

  if (name === '货币资金与短期有息负债比') {
    extra = (
      <div className="extra-values">
        <span className={debtScope === 'narrow' ? 'active' : ''}>
          窄口径: {item.value_narrow?.toFixed(4)}
        </span>
        <span className={debtScope === 'wide' ? 'active' : ''}>
          宽口径: {item.value_wide?.toFixed(4)}
        </span>
      </div>
    )
  }

  const hasDetail = item.description || item.formula || item.detail

  return (
    <div className={`score-card ${expanded ? 'expanded' : ''}`}>
      <div className="score-card-header" onClick={() => hasDetail && setExpanded(!expanded)} style={hasDetail ? { cursor: 'pointer' } : {}}>
        <span className="indicator-name">
          {name}
          {hasDetail && <span className="expand-icon">{expanded ? ' \u25B2' : ' \u25BC'}</span>}
        </span>
        <span className="indicator-score">{item.score}/{item.max}</span>
      </div>
      <div className="indicator-value">{formatValue(item)}</div>
      {extra}
      <ScoreBar score={item.score} max={item.max} />
      {expanded && hasDetail && (
        <div className="card-detail">
          {item.description && <p className="detail-desc">{item.description}</p>}
          {item.formula && <div className="detail-row"><span className="detail-label">公式</span><span>{item.formula}</span></div>}
          {item.detail && <div className="detail-row"><span className="detail-label">计算</span><span>{item.detail}</span></div>}
          {item.thresholds && <div className="detail-row"><span className="detail-label">阈值</span><span>{item.thresholds}</span></div>}
          {item.matched_rule && <div className="detail-row matched-rule"><span className="detail-label">命中</span><span>{item.matched_rule}</span></div>}
        </div>
      )}
    </div>
  )
}

// 思维网络组件（B部分：规则化 + A部分：LLM claims引用）
function MindNetwork({ insights, observations, judgments }) {
  const strengths = insights?.filter(i => i.level === 'strength') || []
  const risks = insights?.filter(i => i.level === 'risk') || []
  const neutrals = insights?.filter(i => i.level === 'neutral') || []

  return (
    <div className="mind-network">
      <div className="network-columns">
        <div className="network-col strength-col">
          <h4 className="col-title strength-title">优势</h4>
          {strengths.map(i => (
            <div key={i.indicator} className="network-node strength-node">
              <span className="node-name">{i.indicator}</span>
              <span className="node-score">{i.score}/{i.max}</span>
            </div>
          ))}
        </div>
        <div className="network-col neutral-col">
          <h4 className="col-title neutral-title">中性</h4>
          {neutrals.map(i => (
            <div key={i.indicator} className="network-node neutral-node">
              <span className="node-name">{i.indicator}</span>
              <span className="node-score">{i.score}/{i.max}</span>
            </div>
          ))}
        </div>
        <div className="network-col risk-col">
          <h4 className="col-title risk-title">风险</h4>
          {risks.map(i => (
            <div key={i.indicator} className="network-node risk-node">
              <span className="node-name">{i.indicator}</span>
              <span className="node-score">{i.score}/{i.max}</span>
            </div>
          ))}
        </div>
      </div>

      {observations && observations.length > 0 && (
        <div className="claims-section observations-section">
          <h4 className="claims-title">📊 事实陈述（基于数据）</h4>
          {observations.map((obs, i) => (
            <div key={i} className="claim-item observation-item">
              <p className="claim-text">{obs.text}</p>
              <div className="claim-sources">
                <span className="type-badge factual">事实</span>
                {obs.sources?.map((src, j) => {
                  const insight = insights?.find(ins => ins.indicator === src)
                  const level = insight?.level || (src === '审计意见' ? 'audit' : 'unknown')
                  return (
                    <span key={j} className={`source-tag ${level}`}>{src}</span>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {judgments && judgments.length > 0 && (
        <div className="claims-section judgments-section">
          <h4 className="claims-title">💡 综合推断（AI分析）</h4>
          {judgments.map((jdg, i) => (
            <div key={i} className="claim-item judgment-item">
              <p className="claim-text">{jdg.text}</p>
              <div className="claim-sources">
                <span className="type-badge inference">推断</span>
                {jdg.sources?.map((src, j) => {
                  const insight = insights?.find(ins => ins.indicator === src)
                  const level = insight?.level || (src === '审计意见' ? 'audit' : 'unknown')
                  return (
                    <span key={j} className={`source-tag ${level}`}>{src}</span>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function PdfUploader({ onExtracted }) {
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [company, setCompany] = useState('')
  const [reportYear, setReportYear] = useState('2024')
  const [file, setFile] = useState(null)

  const handleUpload = async () => {
    if (!file || !company) return
    setUploading(true)
    setUploadResult(null)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('company', company)
    formData.append('report_year', reportYear)

    try {
      const res = await fetch(`${API_BASE}/extract`, { method: 'POST', body: formData })
      const data = await res.json()
      setUploadResult(data)
      if (data.success) {
        onExtracted?.(data.dataset_id)
      }
    } catch (e) {
      setUploadResult({ success: false, error: e.message })
    } finally {
      setUploading(false)
    }
  }

  return (
    <section className="pdf-uploader">
      <h3>PDF年报上传</h3>
      <p className="upload-hint">上传年报PDF，系统将自动提取财务数据和审计意见，按公司+年度独立存储</p>
      <div className="upload-form">
        <input type="text" placeholder="公司名称" value={company} onChange={e => setCompany(e.target.value)} className="upload-input" />
        <input type="number" placeholder="报告年度" value={reportYear} onChange={e => setReportYear(e.target.value)} className="upload-input upload-year" />
        <label className="file-label">
          {file ? file.name : '选择PDF文件'}
          <input type="file" accept=".pdf" onChange={e => setFile(e.target.files[0])} hidden />
        </label>
        <button onClick={handleUpload} disabled={uploading || !file || !company} className="upload-btn">
          {uploading ? '提取中...' : '提取数据'}
        </button>
      </div>
      {uploadResult && (
        <div className={`upload-result ${uploadResult.success ? 'success' : 'fail'}`}>
          <p>{uploadResult.message || uploadResult.error}</p>
          {uploadResult.missing_fields?.length > 0 && (
            <details>
              <summary>缺失字段 ({uploadResult.missing_fields.length})</summary>
              <ul>{uploadResult.missing_fields.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </details>
          )}
        </div>
      )}
    </section>
  )
}

function DatasetSelector({ datasets, current, onChange }) {
  if (!datasets || datasets.length === 0) return null
  return (
    <section className="dataset-selector">
      <label>选择数据集：</label>
      <select value={current || ''} onChange={e => onChange(e.target.value || null)}>
        {datasets.map(ds => (
          <option key={ds.id} value={ds.id}>
            {ds.company} {ds.report_year}年
          </option>
        ))}
      </select>
    </section>
  )
}

function App() {
  const [page, setPage] = useState('dashboard') // 'dashboard' | 'ontology'
  const [data, setData] = useState(null)
  const [evaluation, setEvaluation] = useState(null)
  const [auditOpinion, setAuditOpinion] = useState(null)
  const [roeMethod, setRoeMethod] = useState('weighted_avg')
  const [debtScope, setDebtScope] = useState('narrow')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [datasetId, setDatasetId] = useState(null)

  const loadDatasets = useCallback(() => {
    fetch(`${API_BASE}/datasets`)
      .then(r => r.json())
      .then(ds => {
        setDatasets(ds)
        if (!datasetId && ds.length > 0) {
          setDatasetId(ds[0].id)
        }
      })
      .catch(() => {})
  }, [datasetId])

  const [fromCache, setFromCache] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const loadScore = useCallback((dsId) => {
    const id = dsId ?? datasetId
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roe_method: roeMethod, debt_scope: debtScope, dataset_id: id })
    })
      .then(r => r.json())
      .then(d => {
        setData(d)
        setEvaluation(d.evaluation || null)
        setAuditOpinion(d.audit_opinion || null)
        setFromCache(d.from_cache || false)
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [roeMethod, debtScope, datasetId])

  const refreshScore = useCallback(() => {
    setRefreshing(true)
    fetch(`${API_BASE}/score/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roe_method: roeMethod, debt_scope: debtScope, dataset_id: datasetId })
    })
      .then(r => r.json())
      .then(d => {
        setData(d)
        setEvaluation(d.evaluation || null)
        setAuditOpinion(d.audit_opinion || null)
        setFromCache(false)
        setRefreshing(false)
      })
      .catch(e => {
        setError(e.message)
        setRefreshing(false)
      })
  }, [roeMethod, debtScope, datasetId])

  useEffect(() => {
    loadDatasets()
    loadScore()
  }, [])

  const recompute = useCallback((newRoe, newDebt) => {
    fetch(`${API_BASE}/score/compute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        roe_method: newRoe,
        debt_scope: newDebt,
        audit_opinion_clean: auditOpinion?.is_clean ?? true,
        dataset_id: datasetId
      })
    })
      .then(r => r.json())
      .then(d => setData(d))
      .catch(e => setError(e.message))
  }, [auditOpinion, datasetId])

  const handleDatasetChange = (id) => {
    setDatasetId(id)
    loadScore(id)
  }

  const handlePdfExtracted = (newDatasetId) => {
    loadDatasets()
    if (newDatasetId) {
      setDatasetId(newDatasetId)
      loadScore(newDatasetId)
    }
  }

  const handleRoeChange = (method) => {
    setRoeMethod(method)
    recompute(method, debtScope)
  }

  const handleDebtChange = (scope) => {
    setDebtScope(scope)
    recompute(roeMethod, scope)
  }

  const NavBar = () => (
    <nav className="app-nav">
      <button className={page === 'dashboard' ? 'active' : ''} onClick={() => setPage('dashboard')}>评分仪表盘</button>
      <button className={page === 'comparison' ? 'active' : ''} onClick={() => setPage('comparison')}>跨公司对比</button>
      <button className={page === 'ontology' ? 'active' : ''} onClick={() => setPage('ontology')}>Ontology 编辑器</button>
    </nav>
  )

  if (page === 'ontology') {
    return (
      <div className="app">
        <NavBar />
        <OntologyEditor />
      </div>
    )
  }

  if (page === 'comparison') {
    return (
      <div className="app">
        <NavBar />
        <CompanyComparison />
      </div>
    )
  }

  if (loading) {
    return <div className="loading">正在加载评分数据（含LLM分析）...</div>
  }

  if (error) {
    return <div className="error">加载失败: {error}</div>
  }

  if (!data) return null

  const categories = {}
  Object.entries(data.scores).forEach(([name, item]) => {
    const cat = item.category
    if (!categories[cat]) categories[cat] = []
    categories[cat].push([name, item])
  })

  return (
    <div className="app">
      <NavBar />
      <header className="header">
        <h1>财报侦察官</h1>
        <p className="subtitle">{data.company} {data.report_year}年度财务评分报告</p>
      </header>

      <PdfUploader onExtracted={handlePdfExtracted} />
      <DatasetSelector datasets={datasets} current={datasetId} onChange={handleDatasetChange} />

      <section className="summary">
        <div className="total-score">
          <div className="score-number">{data.final_total}</div>
          <div className="score-max">/ {data.max_total}</div>
        </div>
        <RatingBadge rating={data.rating} />
        {data.raw_total !== data.final_total && (
          <div className="raw-score">原始得分: {data.raw_total}（红线调整后: {data.final_total}）</div>
        )}
        <div className="cache-actions">
          {fromCache && <span className="cache-badge">缓存</span>}
          <button className="refresh-btn" onClick={refreshScore} disabled={refreshing}>
            {refreshing ? '分析中...' : '重新AI分析'}
          </button>
        </div>
      </section>

      {data.waterfall && (
        <section className="waterfall">
          <h3>得分瀑布图</h3>
          <div className="waterfall-bars">
            {data.waterfall.map((item, i) => {
              if (item.category) {
                return (
                  <div key={i} className="waterfall-item">
                    <div className="waterfall-label">{item.category}</div>
                    <div className="waterfall-bar-wrap">
                      <div className="waterfall-bar earned" style={{ width: `${item.pct}%` }}>
                        {item.earned}
                      </div>
                      <div className="waterfall-bar lost" style={{ width: `${(1 - item.pct / 100) * 100}%` }}>
                        {item.lost > 0 ? `-${item.lost}` : ''}
                      </div>
                    </div>
                    <div className="waterfall-fraction">{item.earned}/{item.max}</div>
                  </div>
                )
              }
              if (item.adjustment !== undefined) {
                return (
                  <div key={i} className={`waterfall-item adjustment ${item.adjustment < 0 ? 'negative' : ''}`}>
                    <div className="waterfall-label">{item.label}</div>
                    <div className="waterfall-value">{item.adjustment === 0 ? '无调整' : `${item.adjustment}分`}</div>
                  </div>
                )
              }
              return (
                <div key={i} className="waterfall-item total">
                  <div className="waterfall-label">{item.label}</div>
                  <div className="waterfall-value total-value">{item.total}分</div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      <section className="options">
        <div className="option-group">
          <label>ROE计算口径：</label>
          <button className={roeMethod === 'weighted_avg' ? 'active' : ''} onClick={() => handleRoeChange('weighted_avg')}>加权平均</button>
          <button className={roeMethod === 'endpoint' ? 'active' : ''} onClick={() => handleRoeChange('endpoint')}>期末值</button>
        </div>
        <div className="option-group">
          <label>短期有息负债口径：</label>
          <button className={debtScope === 'narrow' ? 'active' : ''} onClick={() => handleDebtChange('narrow')}>窄口径</button>
          <button className={debtScope === 'wide' ? 'active' : ''} onClick={() => handleDebtChange('wide')}>宽口径</button>
        </div>
      </section>

      {data.red_lines && data.red_lines.length > 0 && (
        <section className="red-lines">
          <h3>红线检查</h3>
          {data.red_lines.map((rl, i) => (
            <div key={i} className={`red-line-item ${rl.triggered ? 'triggered' : 'safe'}`}>
              <div className="red-line-header">
                <span className={`red-line-badge ${rl.triggered ? 'triggered' : 'safe'}`}>
                  {rl.triggered ? '触发' : '安全'}
                </span>
                <span className="red-line-rule">{rl.rule}</span>
                {rl.triggered && <span className="red-line-cap">上限{rl.cap}分</span>}
              </div>
              <p className="red-line-explanation">{rl.explanation}</p>
            </div>
          ))}
        </section>
      )}

      {Object.entries(categories).map(([cat, items]) => {
        const catScore = items.reduce((s, [, it]) => s + it.score, 0)
        const catMax = CATEGORY_LABELS[cat]?.max || items.reduce((s, [, it]) => s + it.max, 0)
        const color = CATEGORY_LABELS[cat]?.color || '#666'
        return (
          <section key={cat} className="category">
            <div className="category-header">
              <h2 style={{ borderLeftColor: color }}>{cat}</h2>
              <span className="category-score">{catScore}/{catMax}</span>
            </div>
            <div className="cards-grid">
              {items.map(([name, item]) => (
                <ScoreCard key={name} name={name} item={item} roeMethod={roeMethod} debtScope={debtScope} />
              ))}
            </div>
          </section>
        )
      })}

      {auditOpinion && (
        <section className="audit-section">
          <h2>审计意见</h2>
          <div className="audit-result">
            <span className="audit-label">分类结果：</span>
            <span className="audit-type">{auditOpinion.opinion_type}</span>
            <span className={`audit-badge ${auditOpinion.is_clean ? 'clean' : 'warning'}`}>
              {auditOpinion.is_clean ? '标准' : '非标准'}
            </span>
          </div>
          {auditOpinion.audit_text && (
            <details className="audit-text-detail">
              <summary>查看审计意见原文</summary>
              <div className="audit-text-content">{auditOpinion.audit_text}</div>
            </details>
          )}
        </section>
      )}

      {/* 思维网络 + AI评价 */}
      <section className="evaluation">
        <h2>AI综合评价与思维网络</h2>
        {evaluation?.summary && <p className="eval-summary">{evaluation.summary}</p>}
        <MindNetwork insights={data.insights} observations={evaluation?.observations} judgments={evaluation?.judgments} />
      </section>

      <footer className="footer">
        <p>数据来源：{data.company}年度报告 | LLM：OpenAI GPT-4o-mini | 评分逻辑由代码计算，LLM仅用于文本分析与生成</p>
      </footer>
    </div>
  )
}

export default App
