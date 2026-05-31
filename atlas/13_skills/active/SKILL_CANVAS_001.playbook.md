# canvas

<!-- Source: migrated from ~/.claude/skills/canvas/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: canvas -->

**Summary.** Custom D3.js visualizations with Codename CANVAS. Low-level SVG and Canvas rendering, force-directed graphs, custom chart types unavailable in standard React/Vue chart libraries, animated transitions, brush and zoom interactions, and binding D3 to React/Angular component lifecycles. Trigger on: "D3", "custom visualization", "SVG animation", "force graph", "canvas rendering", "CANVAS", "d3.js".

# Custom D3.js Visualizations (CANVAS)

## Core Expertise
- SVG-based custom charts: bullet charts, radial gauges, waterfall diagrams
- Canvas rendering for high-density data (10k+ points) without DOM overhead
- Force-directed graphs for KPI relationship mapping
- Animated transitions with d3-transition for KPI value changes
- Brush and zoom interactions for time-series drill-down
- D3 integration with React using useRef + useEffect pattern

## When to Use
- Required chart type is not available in ApexCharts or Recharts
- Dashboard needs animated SVG transitions between KPI states
- Visualizing relationships or hierarchies (force graph, treemap, sunburst)
- High-volume time-series data requiring Canvas rendering for performance
- Custom gauge, bullet chart, or waterfall that needs pixel-perfect control

## Key Patterns

1. **D3 in React with useRef/useEffect**
```jsx
function D3KpiGauge({ value, min = 0, max = 100, threshold = 90 }) {
  const svgRef = useRef(null);
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove(); // clear before redraw
    drawGauge(svg, { value, min, max, threshold });
  }, [value, min, max, threshold]);
  return <svg ref={svgRef} width={200} height={120} aria-label={`Gauge: ${value}`} />;
}
```

2. **Radial Gauge Arc**
```javascript
function drawGauge(svg, { value, min, max, threshold }) {
  const arc = d3.arc().innerRadius(60).outerRadius(80).startAngle(-Math.PI / 2);
  const scale = d3.scaleLinear().domain([min, max]).range([-Math.PI / 2, Math.PI / 2]);
  const color = value >= threshold ? '#16A34A' : '#DB0717';
  // Background arc
  svg.append('path').datum({ endAngle: Math.PI / 2 })
     .attr('d', arc).attr('fill', '#E5E7EB').attr('transform', 'translate(100,100)');
  // Value arc with transition
  svg.append('path').datum({ endAngle: scale(min) })
     .attr('d', arc).attr('fill', color).attr('transform', 'translate(100,100)')
     .transition().duration(800).attrTween('d', function(d) {
       const interp = d3.interpolate(d.endAngle, scale(value));
       return t => arc({ ...d, endAngle: interp(t) });
     });
  svg.append('text').attr('x', 100).attr('y', 105)
     .attr('text-anchor', 'middle').attr('font-size', '20px')
     .text(`${value}%`);
}
```

3. **Waterfall Chart for Penalty Breakdown**
```javascript
function drawWaterfall(svg, data, { width, height }) {
  let cumulative = 0;
  const processed = data.map(d => {
    const start = cumulative;
    cumulative += d.value;
    return { ...d, start, end: cumulative };
  });
  const x = d3.scaleBand().domain(data.map(d => d.label)).range([0, width]).padding(0.3);
  const y = d3.scaleLinear().domain([0, cumulative]).range([height, 0]);
  svg.selectAll('rect').data(processed).join('rect')
     .attr('x', d => x(d.label))
     .attr('y', d => y(Math.max(d.start, d.end)))
     .attr('height', d => Math.abs(y(d.start) - y(d.end)))
     .attr('width', x.bandwidth())
     .attr('fill', d => d.value > 0 ? '#DB0717' : '#16A34A');
}
```

4. **Canvas Renderer for Large Datasets**
```javascript
function renderCanvasTimeSeries(canvas, data) {
  const ctx = canvas.getContext('2d');
  const { width, height } = canvas;
  ctx.clearRect(0, 0, width, height);
  const x = d3.scaleTime().domain(d3.extent(data, d => d.date)).range([40, width - 10]);
  const y = d3.scaleLinear().domain([0, d3.max(data, d => d.value)]).range([height - 30, 10]);
  ctx.beginPath();
  data.forEach((d, i) => {
    const px = x(d.date), py = y(d.value);
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  });
  ctx.strokeStyle = '#DB0717'; ctx.lineWidth = 2; ctx.stroke();
}
```

5. **Animated Value Transition**
```javascript
function animateValue(selection, newValue, accessor, format) {
  selection.transition().duration(600).tween('text', function() {
    const current = parseFloat(this.textContent) || 0;
    const interp = d3.interpolateNumber(current, newValue);
    return t => d3.select(this).text(format(interp(t)));
  });
}
```

## Standards
- Always clear SVG contents before redrawing: `svg.selectAll('*').remove()`
- Use Canvas API (not SVG) when rendering more than 1,000 data points
- All D3 SVG elements must have aria-label or be wrapped in a figure with figcaption
- Transition duration: 600-800ms for value changes, 300ms for hover states
- Debounce resize handlers at 150ms to prevent excessive redraws
- Scope D3 selections to the component's root ref, never select globally
