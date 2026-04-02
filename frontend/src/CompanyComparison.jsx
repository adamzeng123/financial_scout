import { useState, useEffect, useCallback } from 'react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell
} from 'recharts'

const API_BASE = 'http://localhost:5000/api'

const COMPANY_COLORS = [
  '#4f46e5', '#059669', '#dc2626', '#d97706', '#7c3aed',
  '#0891b2', '#be185d', '#65a30d', '#c2410c', '#6366f1'
]

const CATEGORY_INDICATORS = {
  '商业质量': ['ROE当期值', '毛利率当期值', '毛利率同比变化绝对值', '期间费用率同比趋势'],
  '财务安全': ['资产负债率当期值', '利息保障倍数当期值', '流动比率当期值', '货币资金与短期有息负债比'],
  '盈利质量与现金含量': ['经营现金流与净利润比', '自由现金流率', '应收增速减营收增速', '存货增速减营收增速'],
  '成长质量': ['营收同比增速', '净利润同比增速', '营收与净利润双增', 'ROE同比趋势'],
}

const ALL_INDICATORS = Object.values(CATEGORY_INDICATORS).flat()

// 雷达图用的6个核心指标（每个类别选最有代表性的）
const RADAR_INDICATORS = [
  'ROE当期值', '毛利率当期值', '资产负债率当期值',
  '经营现金流与净利润比', '营收同比增速', '净利润同比增速'
]

function CompanySelector({ companies, selected, onChange }) {
  const toggle = (name) => {
    if (selected.includes(name)) {
      onChange(selected.filter(n => n !== name))
    } else {
      onChange([...selected, name])
    }
  }

  return (
    <div className="company-selector">
      <h4>选择公司</h4>
      <div className="company-chips">
        {companies.map((c, i) => (
          <button
            key={c.name}
            className={`company-chip ${selected.includes(c.name) ? 'selected' : ''}`}
            style={selected.includes(c.name) ? { background: COMPANY_COLORS[i % COMPANY_COLORS.length], borderColor: COMPANY_COLORS[i % COMPANY_COLORS.length] } : {}}
            onClick={() => toggle(c.name)}
          >
            {c.name.replace(/股份有限公司|有限公司/, '')}
            {c.years && <span className="chip-years">{c.years.sort().join(',')}</span>}
          </button>
        ))}
      </div>
      {companies.length === 0 && <p className="no-data">Neo4j 中暂无公司数据</p>}
    </div>
  )
}

function RadarCompare({ data, selectedCompanies }) {
  if (!data || data.length === 0) return null

  // Build radar data: each indicator as an axis, each company as a series
  const radarData = RADAR_INDICATORS.map(ind => {
    const point = { indicator: ind.replace('当期值', '').replace('同比', '') }
    selectedCompanies.forEach(company => {
      const match = data.find(d => d.name === ind && d.company === company)
      // Normalize score to percentage of max for fair comparison
      point[company] = match ? Math.round((match.score / match.max) * 100) : 0
    })
    return point
  })

  return (
    <div className="radar-section">
      <h3>核心指标雷达图</h3>
      <p className="radar-hint">得分率(%) — 越大越好，100%为满分</p>
      <ResponsiveContainer width="100%" height={400}>
        <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#e5e7eb" />
          <PolarAngleAxis dataKey="indicator" tick={{ fontSize: 12, fill: '#374151' }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
          {selectedCompanies.map((company, i) => (
            <Radar
              key={company}
              name={company.replace(/股份有限公司|有限公司/, '')}
              dataKey={company}
              stroke={COMPANY_COLORS[i % COMPANY_COLORS.length]}
              fill={COMPANY_COLORS[i % COMPANY_COLORS.length]}
              fillOpacity={0.15}
              strokeWidth={2}
            />
          ))}
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Tooltip formatter={(val) => `${val}%`} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

function ScoreRanking({ summaries }) {
  if (!summaries || summaries.length === 0) return null

  const RATING_COLORS = {
    'A': '#059669', 'B': '#3b82f6', 'C': '#d97706', 'D': '#dc2626', 'E': '#7f1d1d'
  }

  const sorted = [...summaries].sort((a, b) => b.final_total - a.final_total)
  const maxScore = 100

  return (
    <div className="ranking-section">
      <h3>评分排行榜</h3>
      <div className="ranking-list">
        {sorted.map((s, i) => {
          const ratingChar = s.rating?.charAt(0) || '?'
          const pct = (s.final_total / maxScore) * 100
          return (
            <div key={s.company} className="ranking-item">
              <span className="ranking-rank">#{i + 1}</span>
              <div className="ranking-info">
                <div className="ranking-name">
                  {s.company.replace(/股份有限公司|有限公司/, '')}
                  <span className="ranking-year">{s.year}年</span>
                </div>
                <div className="ranking-bar-wrap">
                  <div
                    className="ranking-bar"
                    style={{ width: `${pct}%`, background: COMPANY_COLORS[i % COMPANY_COLORS.length] }}
                  />
                </div>
              </div>
              <div className="ranking-score">
                <span className="ranking-number">{s.final_total}</span>
                <span className="ranking-badge" style={{ background: RATING_COLORS[ratingChar] || '#666' }}>
                  {ratingChar}级
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function IndicatorDetail({ indicator, data, selectedCompanies }) {
  if (!data || data.length === 0) return null

  const items = data.filter(d => d.name === indicator)
  if (items.length === 0) return null

  const chartData = items.map(d => ({
    company: d.company.replace(/股份有限公司|有限公司/, ''),
    fullName: d.company,
    score: d.score,
    max: d.max,
    value: d.value,
    matched_rule: d.matched_rule,
  }))

  return (
    <div className="indicator-detail">
      <h4>{indicator}</h4>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 80, right: 20 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, items[0]?.max || 10]} />
          <YAxis type="category" dataKey="company" tick={{ fontSize: 12 }} width={80} />
          <Tooltip
            formatter={(val, name, props) => {
              const item = props.payload
              return [`${val}/${item.max}`, '得分']
            }}
            labelFormatter={(label) => label}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const d = payload[0].payload
              return (
                <div className="custom-tooltip">
                  <p className="tooltip-company">{d.company}</p>
                  <p className="tooltip-score">得分: {d.score}/{d.max}</p>
                  {d.value != null && <p className="tooltip-value">值: {typeof d.value === 'number' ? (d.value * 100).toFixed(2) + '%' : d.value}</p>}
                  {d.matched_rule && <p className="tooltip-rule">{d.matched_rule}</p>}
                </div>
              )
            }}
          />
          <Bar dataKey="score" radius={[0, 4, 4, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={COMPANY_COLORS[selectedCompanies.indexOf(chartData[i].fullName) % COMPANY_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function CategoryComparison({ category, indicators, data, selectedCompanies }) {
  return (
    <div className="category-compare">
      <h3 className="category-compare-title">{category}</h3>
      <div className="indicator-grid">
        {indicators.map(ind => (
          <IndicatorDetail key={ind} indicator={ind} data={data} selectedCompanies={selectedCompanies} />
        ))}
      </div>
    </div>
  )
}

export default function CompanyComparison() {
  const [companies, setCompanies] = useState([])
  const [selected, setSelected] = useState([])
  const [neo4jAvailable, setNeo4jAvailable] = useState(null)
  const [summaries, setSummaries] = useState([])
  const [indicatorData, setIndicatorData] = useState([])
  const [loading, setLoading] = useState(true)

  // Check Neo4j and load companies
  useEffect(() => {
    (async () => {
      try {
        const statusRes = await fetch(`${API_BASE}/neo4j/status`)
        const status = await statusRes.json()
        setNeo4jAvailable(status.available)

        if (!status.available) {
          setLoading(false)
          return
        }

        const [compRes, sumRes] = await Promise.all([
          fetch(`${API_BASE}/compare/companies`),
          fetch(`${API_BASE}/scorings/summary`)
        ])
        const comps = await compRes.json()
        const sums = await sumRes.json()

        setCompanies(comps)
        setSummaries(sums)

        // Auto-select all companies
        const names = comps.map(c => c.name)
        setSelected(names)

        setLoading(false)
      } catch (e) {
        setNeo4jAvailable(false)
        setLoading(false)
      }
    })()
  }, [])

  // Fetch indicator data when selection changes
  const fetchIndicatorData = useCallback(async () => {
    if (selected.length === 0) {
      setIndicatorData([])
      return
    }

    const companiesParam = selected.join(',')
    const results = []

    // Fetch all indicators in parallel
    const promises = ALL_INDICATORS.map(ind =>
      fetch(`${API_BASE}/compare/indicator?indicator=${encodeURIComponent(ind)}&companies=${encodeURIComponent(companiesParam)}`)
        .then(r => r.json())
        .then(data => data.map(d => ({ ...d, name: ind })))
        .catch(() => [])
    )

    const allResults = await Promise.all(promises)
    setIndicatorData(allResults.flat())
  }, [selected])

  useEffect(() => {
    if (selected.length > 0) fetchIndicatorData()
  }, [selected, fetchIndicatorData])

  if (loading) return <div className="loading">加载跨公司数据...</div>

  if (neo4jAvailable === false) {
    return (
      <div className="comparison-page">
        <div className="neo4j-offline">
          <h3>Neo4j 未连接</h3>
          <p>跨公司对比功能需要 Neo4j 数据库。请启动 Neo4j 并运行数据迁移。</p>
          <pre>docker compose up -d{'\n'}$env:NEO4J_PASSWORD="financial_scout"; uv run python src/migration.py</pre>
        </div>
      </div>
    )
  }

  return (
    <div className="comparison-page">
      <header className="compare-header">
        <h2>跨公司财务对比</h2>
        <p className="compare-subtitle">
          {companies.length} 家公司 | 已选 {selected.length} 家 | {indicatorData.length} 条数据
        </p>
      </header>

      <CompanySelector companies={companies} selected={selected} onChange={setSelected} />

      {selected.length === 0 ? (
        <div className="no-selection">请选择至少一家公司</div>
      ) : (
        <>
          <div className="compare-top-row">
            <RadarCompare data={indicatorData} selectedCompanies={selected} />
            <ScoreRanking summaries={summaries.filter(s => selected.includes(s.company))} />
          </div>

          {Object.entries(CATEGORY_INDICATORS).map(([cat, indicators]) => (
            <CategoryComparison
              key={cat}
              category={cat}
              indicators={indicators}
              data={indicatorData}
              selectedCompanies={selected}
            />
          ))}
        </>
      )}
    </div>
  )
}
