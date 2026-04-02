import { useRef, useEffect, useState, useCallback } from 'react'
import * as d3 from 'd3'

const TABLE_COLORS = {
  balance_sheet: { fill: '#dbeafe', stroke: '#3b82f6', text: '#1e40af' },
  income_statement: { fill: '#fef3c7', stroke: '#f59e0b', text: '#92400e' },
  cash_flow: { fill: '#d1fae5', stroke: '#10b981', text: '#065f46' },
  derived: { fill: '#f3e8ff', stroke: '#8b5cf6', text: '#6d28d9' },
}

const EDGE_COLORS = {
  derived_from: '#8b5cf6',
  related_to: '#9ca3af',
}

export default function OntologyGraph({ ontology, onSelectTerm }) {
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const simulationRef = useRef(null)
  const [dimensions, setDimensions] = useState({ width: 900, height: 600 })
  const [tooltip, setTooltip] = useState(null)

  // Build nodes and links from ontology
  const buildGraphData = useCallback(() => {
    if (!ontology?.terms) return { nodes: [], links: [] }

    const terms = ontology.terms
    const termIds = new Set(Object.keys(terms))

    // Nodes: one per term
    const nodes = Object.entries(terms).map(([id, t]) => ({
      id,
      canonical: t.canonical,
      source_table: t.source_table,
      definition: t.definition,
      field_key: t.field_key,
      aliasCount: Object.values(t.aliases || {}).flat().length,
    }))

    // Collect derived terms from relationships (may not be in terms dict)
    const derivedNodes = new Set()
    const links = []

    // From explicit relationships
    ;(ontology.relationships || []).forEach(rel => {
      // Add derived node if not a term
      if (!termIds.has(rel.from)) {
        derivedNodes.add(rel.from)
      }
      links.push({
        source: rel.from,
        target: rel.to,
        type: rel.type || 'derived_from',
        formula: rel.formula,
        description: rel.description,
      })
    })

    // From related_to fields
    Object.entries(terms).forEach(([id, t]) => {
      ;(t.related_to || []).forEach(relId => {
        if (termIds.has(relId)) {
          // Avoid duplicate links
          const exists = links.some(l =>
            (l.source === id && l.target === relId) ||
            (l.source === relId && l.target === id)
          )
          if (!exists) {
            links.push({ source: id, target: relId, type: 'related_to' })
          }
        }
      })
    })

    // Add derived concept nodes
    derivedNodes.forEach(id => {
      const rel = ontology.relationships.find(r => r.from === id)
      nodes.push({
        id,
        canonical: rel?.description?.split('=')[0]?.trim() || id,
        source_table: 'derived',
        definition: rel?.description || '',
        field_key: '',
        aliasCount: 0,
      })
    })

    return { nodes, links }
  }, [ontology])

  // Resize observer
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setDimensions({ width: Math.max(width, 400), height: Math.max(height, 400) })
      }
    })
    ro.observe(container)
    return () => ro.disconnect()
  }, [])

  // D3 force simulation
  useEffect(() => {
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const { width, height } = dimensions
    const { nodes, links } = buildGraphData()
    if (nodes.length === 0) return

    // Zoom
    const g = svg.append('g')
    const zoom = d3.zoom()
      .scaleExtent([0.3, 3])
      .on('zoom', (event) => g.attr('transform', event.transform))
    svg.call(zoom)

    // Arrow markers
    const defs = svg.append('defs')
    Object.entries(EDGE_COLORS).forEach(([type, color]) => {
      defs.append('marker')
        .attr('id', `arrow-${type}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 28)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', color)
    })

    // Simulation
    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(50))

    simulationRef.current = simulation

    // Links
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', d => EDGE_COLORS[d.type] || '#ccc')
      .attr('stroke-width', d => d.type === 'derived_from' ? 2 : 1)
      .attr('stroke-dasharray', d => d.type === 'related_to' ? '4,4' : 'none')
      .attr('marker-end', d => `url(#arrow-${d.type || 'related_to'})`)

    // Link labels (formula)
    const linkLabel = g.append('g')
      .selectAll('text')
      .data(links.filter(l => l.formula))
      .join('text')
      .attr('font-size', 9)
      .attr('fill', '#8b5cf6')
      .attr('text-anchor', 'middle')
      .attr('dy', -6)
      .text(d => d.formula)

    // Node groups
    const node = g.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null
          d.fy = null
        })
      )

    // Node rectangles
    node.append('rect')
      .attr('width', d => Math.max(d.canonical.length * 14, 60) + 16)
      .attr('height', 32)
      .attr('x', d => -(Math.max(d.canonical.length * 14, 60) + 16) / 2)
      .attr('y', -16)
      .attr('rx', 8)
      .attr('ry', 8)
      .attr('fill', d => (TABLE_COLORS[d.source_table] || TABLE_COLORS.derived).fill)
      .attr('stroke', d => (TABLE_COLORS[d.source_table] || TABLE_COLORS.derived).stroke)
      .attr('stroke-width', 1.5)

    // Node text
    node.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', 4)
      .attr('font-size', 12)
      .attr('font-weight', 500)
      .attr('fill', d => (TABLE_COLORS[d.source_table] || TABLE_COLORS.derived).text)
      .text(d => d.canonical)

    // Sub-label (term id)
    node.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', 26)
      .attr('font-size', 9)
      .attr('fill', '#999')
      .text(d => d.id)

    // Hover tooltip
    node
      .on('mouseenter', (event, d) => {
        const rect = containerRef.current.getBoundingClientRect()
        setTooltip({
          x: event.clientX - rect.left + 12,
          y: event.clientY - rect.top - 10,
          term: d,
        })
      })
      .on('mouseleave', () => setTooltip(null))
      .on('click', (event, d) => {
        if (onSelectTerm) onSelectTerm(d.id)
      })

    // Tick
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y)

      linkLabel
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2)

      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })

    // Initial zoom to fit
    setTimeout(() => {
      svg.call(zoom.transform, d3.zoomIdentity.translate(0, 0).scale(0.85))
    }, 500)

    return () => simulation.stop()
  }, [ontology, dimensions, buildGraphData, onSelectTerm])

  return (
    <div className="ontology-graph" ref={containerRef}>
      <div className="graph-legend">
        <span className="legend-item"><span className="legend-dot" style={{ background: '#3b82f6' }} />资产负债表</span>
        <span className="legend-item"><span className="legend-dot" style={{ background: '#f59e0b' }} />利润表</span>
        <span className="legend-item"><span className="legend-dot" style={{ background: '#10b981' }} />现金流量表</span>
        <span className="legend-item"><span className="legend-dot" style={{ background: '#8b5cf6' }} />衍生指标</span>
        <span className="legend-item"><span className="legend-line solid" />推导关系</span>
        <span className="legend-item"><span className="legend-line dashed" />关联关系</span>
      </div>
      <svg ref={svgRef} width={dimensions.width} height={dimensions.height} />
      {tooltip && (
        <div className="graph-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          <div className="tooltip-title">{tooltip.term.canonical}</div>
          <div className="tooltip-id">{tooltip.term.id}</div>
          {tooltip.term.definition && <div className="tooltip-def">{tooltip.term.definition}</div>}
          {tooltip.term.field_key && <div className="tooltip-field">field_key: {tooltip.term.field_key}</div>}
          <div className="tooltip-hint">点击编辑</div>
        </div>
      )}
    </div>
  )
}
