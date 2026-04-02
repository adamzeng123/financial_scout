import { useState, useEffect, useCallback } from 'react'
import OntologyGraph from './OntologyGraph'
import './OntologyGraph.css'

const API_BASE = 'http://localhost:5000/api'

const SOURCE_TABLE_LABELS = {
  balance_sheet: '资产负债表',
  income_statement: '利润表',
  cash_flow: '现金流量表',
}

const LANG_LABELS = { zh_CN: '简体中文', zh_TW: '繁体中文', en: 'English' }

function TermEditor({ termId, term, onSave, onCancel }) {
  const [data, setData] = useState(() => ({
    canonical: '',
    field_key: '',
    source_table: 'balance_sheet',
    aliases: { zh_CN: [], zh_TW: [], en: [] },
    definition: '',
    related_to: [],
    gaap: { CAS: '', IFRS: '' },
    ...term,
  }))

  const updateField = (key, value) => setData(prev => ({ ...prev, [key]: value }))

  const updateAlias = (lang, value) => {
    setData(prev => ({
      ...prev,
      aliases: { ...prev.aliases, [lang]: value.split(',').map(s => s.trim()).filter(Boolean) }
    }))
  }

  const updateGaap = (key, value) => {
    setData(prev => ({ ...prev, gaap: { ...prev.gaap, [key]: value } }))
  }

  return (
    <div className="term-editor">
      <h4>{termId ? `编辑: ${termId}` : '新增术语'}</h4>

      <div className="editor-grid">
        <label>Term ID (英文标识符)</label>
        <input value={termId || ''} disabled={!!term} placeholder="e.g. revenue" className="editor-input"
          onChange={e => {/* only for new terms, handled by parent */}} />

        <label>标准名称 (canonical)</label>
        <input value={data.canonical} onChange={e => updateField('canonical', e.target.value)} className="editor-input" />

        <label>字段Key (field_key)</label>
        <input value={data.field_key} onChange={e => updateField('field_key', e.target.value)} className="editor-input" />

        <label>所属报表</label>
        <select value={data.source_table} onChange={e => updateField('source_table', e.target.value)} className="editor-input">
          {Object.entries(SOURCE_TABLE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>

        <label>定义</label>
        <textarea value={data.definition} onChange={e => updateField('definition', e.target.value)}
          className="editor-input editor-textarea" rows={3} />

        {Object.entries(LANG_LABELS).map(([lang, label]) => (
          <div key={lang} className="editor-full-row">
            <label>别名 - {label} (逗号分隔)</label>
            <input value={(data.aliases[lang] || []).join(', ')}
              onChange={e => updateAlias(lang, e.target.value)} className="editor-input" />
          </div>
        ))}

        <label>关联术语 (逗号分隔term ID)</label>
        <input value={(data.related_to || []).join(', ')}
          onChange={e => updateField('related_to', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
          className="editor-input" />

        <label>CAS准则参考</label>
        <input value={data.gaap?.CAS || ''} onChange={e => updateGaap('CAS', e.target.value)} className="editor-input" />

        <label>IFRS准则参考</label>
        <input value={data.gaap?.IFRS || ''} onChange={e => updateGaap('IFRS', e.target.value)} className="editor-input" />
      </div>

      <div className="editor-actions">
        <button className="btn-save" onClick={() => onSave(termId, data)}>保存 (创建新版本)</button>
        <button className="btn-cancel" onClick={onCancel}>取消</button>
      </div>
    </div>
  )
}

function VersionHistory({ versions, currentVersion, onRollback, onViewDiff }) {
  if (!versions.length) return null

  return (
    <div className="version-history">
      <h4>版本历史</h4>
      <div className="version-list">
        {versions.map(v => (
          <div key={v.version} className={`version-item ${v.version === currentVersion ? 'current' : ''}`}>
            <div className="version-meta">
              <span className="version-tag">v{v.version}</span>
              {v.version === currentVersion && <span className="version-current-badge">当前</span>}
              <span className="version-author">{v.author}</span>
              <span className="version-date">{v.created_at?.slice(0, 16).replace('T', ' ')}</span>
            </div>
            <div className="version-desc">{v.description}</div>
            <div className="version-stats">{v.term_count} 个术语</div>
            <div className="version-actions">
              {v.version !== currentVersion && (
                <button className="btn-small" onClick={() => onRollback(v.version)}>回滚到此版本</button>
              )}
              {v.version !== currentVersion && (
                <button className="btn-small btn-secondary" onClick={() => onViewDiff(v.version, currentVersion)}>
                  与当前版本对比
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function DiffViewer({ diff, onClose }) {
  if (!diff) return null
  return (
    <div className="diff-viewer">
      <div className="diff-header">
        <h4>版本对比: v{diff.v1} → v{diff.v2}</h4>
        <button className="btn-small" onClick={onClose}>关闭</button>
      </div>
      {diff.added.length > 0 && (
        <div className="diff-section">
          <h5 className="diff-added">新增 ({diff.added.length})</h5>
          {diff.added.map(t => <span key={t} className="diff-tag added">{t}</span>)}
        </div>
      )}
      {diff.removed.length > 0 && (
        <div className="diff-section">
          <h5 className="diff-removed">删除 ({diff.removed.length})</h5>
          {diff.removed.map(t => <span key={t} className="diff-tag removed">{t}</span>)}
        </div>
      )}
      {diff.modified.length > 0 && (
        <div className="diff-section">
          <h5 className="diff-modified">修改 ({diff.modified.length})</h5>
          {diff.modified.map(m => (
            <div key={m.term_id} className="diff-mod-item">
              <span className="diff-tag modified">{m.term_id}</span>
              <span className="diff-canonical">{m.v2.canonical}</span>
            </div>
          ))}
        </div>
      )}
      {diff.added.length === 0 && diff.removed.length === 0 && diff.modified.length === 0 && (
        <p className="diff-empty">两个版本完全相同</p>
      )}
    </div>
  )
}

const EMPTY_REL = { from: '', to: '', type: 'derived_from', formula: '', description: '' }
const REL_TYPES = [
  { value: 'derived_from', label: '推导 (derived_from)' },
  { value: 'component_of', label: '组成 (component_of)' },
  { value: 'related_to', label: '关联 (related_to)' },
  { value: 'inverse_of', label: '反向 (inverse_of)' },
]

function RelationshipEditor({ relationships, termIds, onSave }) {
  const [rels, setRels] = useState(relationships || [])
  const [editing, setEditing] = useState(null) // index or 'new'
  const [draft, setDraft] = useState({ ...EMPTY_REL })
  const [dirty, setDirty] = useState(false)

  const updateDraft = (key, value) => setDraft(prev => ({ ...prev, [key]: value }))

  const handleAdd = () => {
    setEditing('new')
    setDraft({ ...EMPTY_REL })
  }

  const handleEdit = (index) => {
    setEditing(index)
    setDraft({ ...rels[index] })
  }

  const handleSaveDraft = () => {
    if (!draft.from || !draft.to) { alert('请填写 From 和 To'); return }
    const updated = [...rels]
    if (editing === 'new') {
      updated.push({ ...draft })
    } else {
      updated[editing] = { ...draft }
    }
    setRels(updated)
    setEditing(null)
    setDirty(true)
  }

  const handleDelete = (index) => {
    const updated = rels.filter((_, i) => i !== index)
    setRels(updated)
    setDirty(true)
  }

  const handleSaveAll = () => {
    onSave(rels)
    setDirty(false)
  }

  return (
    <div className="relationships-section">
      <div className="rel-header">
        <h4>术语关系 ({rels.length})</h4>
        <div className="rel-header-actions">
          {dirty && <button className="btn-save-rel" onClick={handleSaveAll}>保存变更 (新版本)</button>}
          <button className="btn-small" onClick={handleAdd}>+ 新增关系</button>
        </div>
      </div>

      {editing !== null && (
        <div className="rel-edit-form">
          <div className="rel-edit-row">
            <label>From (来源)</label>
            <input list="term-list-from" value={draft.from} onChange={e => updateDraft('from', e.target.value)}
              placeholder="e.g. gross_profit" className="rel-edit-input" />
            <datalist id="term-list-from">
              {termIds.map(id => <option key={id} value={id} />)}
            </datalist>
          </div>
          <div className="rel-edit-row">
            <label>To (目标)</label>
            <input list="term-list-to" value={draft.to} onChange={e => updateDraft('to', e.target.value)}
              placeholder="e.g. revenue" className="rel-edit-input" />
            <datalist id="term-list-to">
              {termIds.map(id => <option key={id} value={id} />)}
            </datalist>
          </div>
          <div className="rel-edit-row">
            <label>关系类型</label>
            <select value={draft.type} onChange={e => updateDraft('type', e.target.value)} className="rel-edit-input">
              {REL_TYPES.map(rt => <option key={rt.value} value={rt.value}>{rt.label}</option>)}
            </select>
          </div>
          <div className="rel-edit-row">
            <label>公式</label>
            <input value={draft.formula} onChange={e => updateDraft('formula', e.target.value)}
              placeholder="e.g. revenue - cost_of_revenue" className="rel-edit-input" />
          </div>
          <div className="rel-edit-row">
            <label>描述</label>
            <input value={draft.description} onChange={e => updateDraft('description', e.target.value)}
              placeholder="e.g. 毛利 = 营业收入 - 营业成本" className="rel-edit-input" />
          </div>
          <div className="rel-edit-actions">
            <button className="btn-small" onClick={handleSaveDraft}>确认</button>
            <button className="btn-small btn-secondary" onClick={() => setEditing(null)}>取消</button>
          </div>
        </div>
      )}

      <div className="rel-list">
        {rels.map((rel, i) => (
          <div key={i} className="rel-item">
            <div className="rel-item-main">
              <span className="rel-from">{rel.from}</span>
              <span className="rel-arrow">→</span>
              <span className="rel-to">{rel.to}</span>
              <span className={`rel-type-badge ${rel.type}`}>{rel.type}</span>
            </div>
            {rel.formula && <code className="rel-formula">{rel.formula}</code>}
            {rel.description && <span className="rel-desc">{rel.description}</span>}
            <div className="rel-item-actions">
              <button className="btn-small" onClick={() => handleEdit(i)}>编辑</button>
              <button className="btn-small btn-danger" onClick={() => handleDelete(i)}>删除</button>
            </div>
          </div>
        ))}
        {rels.length === 0 && <p className="rel-empty">暂无关系，点击"+ 新增关系"创建</p>}
      </div>
    </div>
  )
}

export default function OntologyEditor() {
  const [ontology, setOntology] = useState(null)
  const [versions, setVersions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editingTerm, setEditingTerm] = useState(null) // { termId, term } or { termId: null } for new
  const [searchText, setSearchText] = useState('')
  const [filterTable, setFilterTable] = useState('')
  const [diff, setDiff] = useState(null)
  const [newTermId, setNewTermId] = useState('')
  const [viewMode, setViewMode] = useState('list') // 'list' | 'graph'

  const loadOntology = useCallback(async () => {
    try {
      const [ontRes, verRes] = await Promise.all([
        fetch(`${API_BASE}/ontology`),
        fetch(`${API_BASE}/ontology/versions`)
      ])
      setOntology(await ontRes.json())
      setVersions(await verRes.json())
      setLoading(false)
    } catch (e) {
      setError(e.message)
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadOntology() }, [loadOntology])

  const handleSaveTerm = async (termId, termData) => {
    const id = termId || newTermId
    if (!id) { alert('请输入Term ID'); return }

    try {
      await fetch(`${API_BASE}/ontology/term/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(termData)
      })
      setEditingTerm(null)
      setNewTermId('')
      await loadOntology()
    } catch (e) {
      alert('保存失败: ' + e.message)
    }
  }

  const handleDeleteTerm = async (termId) => {
    if (!confirm(`确定删除术语 "${termId}" 吗？将创建新版本。`)) return
    try {
      await fetch(`${API_BASE}/ontology/term/${termId}`, { method: 'DELETE' })
      await loadOntology()
    } catch (e) {
      alert('删除失败: ' + e.message)
    }
  }

  const handleRollback = async (version) => {
    if (!confirm(`确定回滚到 v${version} 吗？将以新版本号保存。`)) return
    try {
      await fetch(`${API_BASE}/ontology/rollback/${version}`, { method: 'POST' })
      await loadOntology()
    } catch (e) {
      alert('回滚失败: ' + e.message)
    }
  }

  const handleSaveRelationships = async (newRels) => {
    try {
      await fetch(`${API_BASE}/ontology/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          terms: ontology.terms,
          relationships: newRels,
          author: 'user',
          description: '更新术语关系'
        })
      })
      await loadOntology()
    } catch (e) {
      alert('保存关系失败: ' + e.message)
    }
  }

  const handleViewDiff = async (v1, v2) => {
    try {
      const res = await fetch(`${API_BASE}/ontology/diff?v1=${v1}&v2=${v2}`)
      setDiff(await res.json())
    } catch (e) {
      alert('对比失败: ' + e.message)
    }
  }

  if (loading) return <div className="loading">加载Ontology...</div>
  if (error) return <div className="error">加载失败: {error}</div>
  if (!ontology) return null

  const terms = ontology.terms || {}
  const filteredTerms = Object.entries(terms).filter(([id, t]) => {
    if (filterTable && t.source_table !== filterTable) return false
    if (searchText) {
      const q = searchText.toLowerCase()
      return id.toLowerCase().includes(q) ||
        t.canonical?.toLowerCase().includes(q) ||
        Object.values(t.aliases || {}).flat().some(a => a.toLowerCase().includes(q))
    }
    return true
  })

  return (
    <div className="ontology-editor">
      <header className="onto-header">
        <div>
          <h2>Ontology 术语本体编辑器</h2>
          <p className="onto-subtitle">
            当前版本: v{ontology.version} | {Object.keys(terms).length} 个术语 | {ontology.author}
          </p>
        </div>
      </header>

      <div className="onto-toolbar">
        <input type="text" placeholder="搜索术语 (ID / 中文名 / 别名)" value={searchText}
          onChange={e => setSearchText(e.target.value)} className="onto-search" />
        <select value={filterTable} onChange={e => setFilterTable(e.target.value)} className="onto-filter">
          <option value="">全部报表</option>
          {Object.entries(SOURCE_TABLE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <button className="btn-add" onClick={() => { setEditingTerm({ termId: null, term: null }); setNewTermId('') }}>
          + 新增术语
        </button>
      </div>

      {editingTerm && (
        <div className="editor-overlay">
          {!editingTerm.termId && (
            <div className="new-term-id-row">
              <label>新术语 Term ID:</label>
              <input value={newTermId} onChange={e => setNewTermId(e.target.value)}
                placeholder="e.g. goodwill" className="editor-input" />
            </div>
          )}
          <TermEditor
            termId={editingTerm.termId}
            term={editingTerm.term}
            onSave={handleSaveTerm}
            onCancel={() => setEditingTerm(null)}
          />
        </div>
      )}

      <DiffViewer diff={diff} onClose={() => setDiff(null)} />

      <div className="graph-tab-bar">
        <button className={viewMode === 'list' ? 'active' : ''} onClick={() => setViewMode('list')}>列表视图</button>
        <button className={viewMode === 'graph' ? 'active' : ''} onClick={() => setViewMode('graph')}>关系图谱</button>
      </div>

      {viewMode === 'graph' ? (
        <OntologyGraph
          ontology={ontology}
          onSelectTerm={(termId) => {
            const t = terms[termId]
            if (t) setEditingTerm({ termId, term: t })
          }}
        />
      ) : (
        <div className="onto-content">
          <div className="terms-panel">
            <h3>术语列表 ({filteredTerms.length})</h3>
            <div className="terms-table">
              <div className="terms-header-row">
                <span>Term ID</span>
                <span>标准名称</span>
                <span>报表</span>
                <span>别名数</span>
                <span>操作</span>
              </div>
              {filteredTerms.map(([id, t]) => {
                const aliasCount = Object.values(t.aliases || {}).flat().length
                return (
                  <div key={id} className="terms-row">
                    <span className="term-id-cell">{id}</span>
                    <span className="term-canonical-cell">{t.canonical}</span>
                    <span className="term-table-cell">
                      <span className={`table-badge ${t.source_table}`}>
                        {SOURCE_TABLE_LABELS[t.source_table] || t.source_table}
                      </span>
                    </span>
                    <span className="term-alias-count">{aliasCount}</span>
                    <span className="term-actions-cell">
                      <button className="btn-small" onClick={() => setEditingTerm({ termId: id, term: t })}>编辑</button>
                      <button className="btn-small btn-danger" onClick={() => handleDeleteTerm(id)}>删除</button>
                    </span>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="side-panel">
            <RelationshipEditor
              relationships={ontology.relationships}
              termIds={Object.keys(terms)}
              onSave={handleSaveRelationships}
            />
            <VersionHistory
              versions={versions}
              currentVersion={ontology.version}
              onRollback={handleRollback}
              onViewDiff={handleViewDiff}
            />
          </div>
        </div>
      )}

      {viewMode === 'graph' && (
        <div className="side-panel" style={{ marginTop: 20 }}>
          <VersionHistory
            versions={versions}
            currentVersion={ontology.version}
            onRollback={handleRollback}
            onViewDiff={handleViewDiff}
          />
        </div>
      )}
    </div>
  )
}
