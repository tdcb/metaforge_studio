/**
 * MetaForge Canvas Export Engine: High-Resolution PNG, SVG Vector, and PDF Exports
 * Pure browser implementation requiring zero external npm dependencies.
 *
 * Employs direct Canvas 2D primitive rendering and pure SVG vector generation
 * to ensure 100% untainted canvases (guaranteeing toBlob/toDataURL and PDF exports never fail).
 */

import { useModelStore } from '../store/useModelStore';
import type {
  ColumnModel,
  EntityModel,
  EnterpriseDomain,
  StickyNoteModel,
  TargetDialect,
  ViewMode,
} from '../types/metamodel';

export interface ExportCanvasOptions {
  projectName?: string;
  activeSubjectArea?: string;
  format: 'png' | 'svg' | 'pdf';
  theme?: 'dark' | 'light';
  scale?: number; // default 2 (Retina 300dpi)
}

interface NodeBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface DiagramBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Escapes special XML characters for valid standalone SVG rendering.
 */
function escapeXml(unsafe: string): string {
  if (!unsafe) return '';
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/**
 * Resolves the displayed column data type based on active view mode, target dialect, and domains.
 */
function getColumnDataType(
  col: ColumnModel,
  viewMode: ViewMode,
  targetDialect: TargetDialect,
  domains: Record<string, EnterpriseDomain>
): string {
  if (viewMode === 'logical') {
    if (col.domain_id && domains[col.domain_id]) {
      return domains[col.domain_id].name;
    }
    return col.data_type_snowflake ? col.data_type_snowflake.split('(')[0] : 'VARCHAR';
  }
  if (targetDialect === 'snowflake') return col.data_type_snowflake || 'VARCHAR';
  if (targetDialect === 'sql_server') return col.data_type_sql_server || 'VARCHAR';
  return col.data_type_oracle || 'VARCHAR2';
}

/**
 * Determines exact node bounding box from the live DOM (if rendered) or falls back to computed dimensions.
 */
function getNodeDimensions(
  entity: EntityModel,
  viewMode: ViewMode
): { width: number; height: number } {
  const domNode = document.querySelector<HTMLElement>(
    `.react-flow__node[data-id="${entity.id}"]`
  );
  if (domNode && domNode.offsetWidth > 0 && domNode.offsetHeight > 0) {
    return { width: domNode.offsetWidth, height: domNode.offsetHeight };
  }

  const width = 340;
  if (viewMode === 'conceptual') {
    return { width, height: 160 };
  }

  // Header (48px) + Governance strip (22px) + Columns (28px each) + Bottom padding (12px)
  const headerHeight = 48;
  const govHeight = 22;
  const columnsHeight = Math.max(1, entity.columns.length) * 28;
  return { width, height: headerHeight + govHeight + columnsHeight + 12 };
}

/**
 * Computes bounding box encompassing all visible entities, annotations, and padding.
 */
function computeDiagramBounds(
  entities: EntityModel[],
  notes: StickyNoteModel[],
  viewMode: ViewMode
): DiagramBounds {
  if (entities.length === 0 && notes.length === 0) {
    return { minX: 0, minY: 0, maxX: 1200, maxY: 800, x: 0, y: 0, width: 1200, height: 800 };
  }

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const ent of entities) {
    const x = ent.position?.x ?? 100;
    const y = ent.position?.y ?? 100;
    const { width, height } = getNodeDimensions(ent, viewMode);
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + width);
    maxY = Math.max(maxY, y + height);
  }

  for (const note of notes) {
    const x = note.position?.x ?? 80;
    const y = note.position?.y ?? 500;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + 260);
    maxY = Math.max(maxY, y + 140);
  }

  const padding = 80;
  const topExtra = 60; // Room for top watermark/header banner
  const boundsX = Math.max(0, minX - padding);
  const boundsY = Math.max(0, minY - padding - topExtra);
  const boundsW = Math.max(800, maxX - boundsX + padding);
  const boundsH = Math.max(600, maxY - boundsY + padding);

  return {
    minX,
    minY,
    maxX,
    maxY,
    x: boundsX,
    y: boundsY,
    width: boundsW,
    height: boundsH,
  };
}

/**
 * Path2D / Canvas 2D rounded rectangle helper with fallback.
 */
function drawRoundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  radii: number
) {
  if (typeof ctx.roundRect === 'function') {
    ctx.roundRect(x, y, w, h, radii);
  } else {
    ctx.moveTo(x + radii, y);
    ctx.arcTo(x + w, y, x + w, y + h, radii);
    ctx.arcTo(x + w, y + h, x, y + h, radii);
    ctx.arcTo(x, y + h, x, y, radii);
    ctx.arcTo(x, y, x + w, y, radii);
    ctx.closePath();
  }
}

/**
 * Renders the full diagram directly onto a clean, untainted HTML5 Canvas 2D context.
 */
export function renderDiagramToCanvas2D(
  options: ExportCanvasOptions
): { canvas: HTMLCanvasElement; bounds: DiagramBounds } {
  const store = useModelStore.getState();
  const project = store.project;
  const viewMode = store.viewMode;
  const targetDialect = store.targetDialect;
  const activeSubjectArea = options.activeSubjectArea || store.activeSubjectArea;
  const isDark = options.theme !== 'light';
  const scale = options.scale || 2; // 2x Retina

  // Filter visible entities and sticky notes
  const visibleEntities = Object.values(project.entities).filter(
    (e) => activeSubjectArea === 'All' || e.subject_area.toLowerCase() === activeSubjectArea.toLowerCase()
  );
  const visibleEntityIds = new Set(visibleEntities.map((e) => e.id));

  const visibleNotes = Object.values(project.annotations || {}).filter(
    (n) => activeSubjectArea === 'All' || n.subject_area.toLowerCase() === activeSubjectArea.toLowerCase()
  );

  const bounds = computeDiagramBounds(visibleEntities, visibleNotes, viewMode);

  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(bounds.width * scale);
  canvas.height = Math.ceil(bounds.height * scale);

  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Could not obtain HTML5 Canvas 2D rendering context.');

  ctx.scale(scale, scale);
  ctx.translate(-bounds.x, -bounds.y);

  // 1. Background
  const bgColor = isDark ? '#090d16' : '#f8fafc';
  ctx.fillStyle = bgColor;
  ctx.fillRect(bounds.x, bounds.y, bounds.width, bounds.height);

  // Subtle background dot grid
  ctx.fillStyle = isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)';
  const gridStep = 24;
  const startX = Math.floor(bounds.x / gridStep) * gridStep;
  const startY = Math.floor(bounds.y / gridStep) * gridStep;
  for (let gx = startX; gx < bounds.x + bounds.width; gx += gridStep) {
    for (let gy = startY; gy < bounds.y + bounds.height; gy += gridStep) {
      ctx.beginPath();
      ctx.arc(gx, gy, 1, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // 2. Watermark / Header Banner
  const title = options.projectName || project.name || 'MetaForge Data Model';
  const subAreaLabel = activeSubjectArea === 'All' ? 'Complete Enterprise Metamodel' : `Subject Area: ${activeSubjectArea}`;
  const bannerSubtitle = `${subAreaLabel} | Dialect: ${targetDialect.toUpperCase()} | Mode: ${viewMode.toUpperCase()} | Generated: ${new Date().toISOString().slice(0, 10)}`;

  ctx.fillStyle = isDark ? '#38bdf8' : '#0284c7';
  ctx.font = 'bold 16px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  ctx.fillText(title, bounds.x + 30, bounds.y + 36);

  ctx.fillStyle = isDark ? '#94a3b8' : '#64748b';
  ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  ctx.fillText(bannerSubtitle, bounds.x + 30, bounds.y + 54);

  // 3. Render Relationship Edges
  // Try extracting smoothstep paths rendered by React Flow in DOM
  const edgeSvg = document.querySelector<SVGSVGElement>('svg.react-flow__edges');
  let renderedEdgesCount = 0;

  if (edgeSvg) {
    const edgePaths = edgeSvg.querySelectorAll<SVGPathElement>('path.react-flow__edge-path');
    edgePaths.forEach((pathEl) => {
      const d = pathEl.getAttribute('d');
      if (!d) return;

      const stroke = pathEl.getAttribute('stroke') || (isDark ? '#94a3b8' : '#64748b');
      const strokeWidth = parseFloat(pathEl.getAttribute('stroke-width') || '2');
      const strokeDash = pathEl.getAttribute('stroke-dasharray');

      ctx.save();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = strokeWidth;
      if (strokeDash) {
        ctx.setLineDash(strokeDash.split(/[ ,]+/).map(Number));
      } else {
        ctx.setLineDash([]);
      }

      try {
        const p2d = new Path2D(d);
        ctx.stroke(p2d);
        renderedEdgesCount++;
      } catch {
        // Path2D string parsing fallback
      }
      ctx.restore();
    });

    // Render Crow's Foot markers from DOM
    const crowsfootGroups = edgeSvg.querySelectorAll<SVGGElement>('g.react-flow__edge-crowsfoot');
    crowsfootGroups.forEach((g) => {
      // Lines (Prongs and mandatory bars)
      const lines = g.querySelectorAll<SVGLineElement>('line');
      lines.forEach((line) => {
        const x1 = parseFloat(line.getAttribute('x1') || '0');
        const y1 = parseFloat(line.getAttribute('y1') || '0');
        const x2 = parseFloat(line.getAttribute('x2') || '0');
        const y2 = parseFloat(line.getAttribute('y2') || '0');
        const stroke = line.getAttribute('stroke') || '#94a3b8';
        const sw = parseFloat(line.getAttribute('stroke-width') || '2');

        ctx.save();
        ctx.strokeStyle = stroke;
        ctx.lineWidth = sw;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
        ctx.restore();
      });

      // Circles (Optional zero rings)
      const circles = g.querySelectorAll<SVGCircleElement>('circle');
      circles.forEach((circ) => {
        const cx = parseFloat(circ.getAttribute('cx') || '0');
        const cy = parseFloat(circ.getAttribute('cy') || '0');
        const r = parseFloat(circ.getAttribute('r') || '4.5');
        const fill = circ.getAttribute('fill') || (isDark ? '#0f172a' : '#ffffff');
        const stroke = circ.getAttribute('stroke') || '#94a3b8';

        ctx.save();
        ctx.fillStyle = fill;
        ctx.strokeStyle = stroke;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
      });

      // Polygons (Lineage arrows)
      const polygons = g.querySelectorAll<SVGPolygonElement>('polygon');
      polygons.forEach((poly) => {
        const pts = (poly.getAttribute('points') || '').trim().split(/\s+/);
        if (pts.length >= 3) {
          ctx.save();
          ctx.fillStyle = poly.getAttribute('fill') || '#22d3ee';
          ctx.beginPath();
          pts.forEach((pt, i) => {
            const [px, py] = pt.split(',').map(Number);
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          });
          ctx.closePath();
          ctx.fill();
          ctx.restore();
        }
      });
    });
  }

  // Fallback direct orthogonal line drawer if DOM edges were empty or not attached
  if (renderedEdgesCount === 0) {
    Object.values(project.relationships).forEach((rel) => {
      if (!visibleEntityIds.has(rel.parent_entity_id) || !visibleEntityIds.has(rel.child_entity_id)) return;
      const parent = project.entities[rel.parent_entity_id];
      const child = project.entities[rel.child_entity_id];
      if (!parent || !child) return;

      const pDim = getNodeDimensions(parent, viewMode);
      const cDim = getNodeDimensions(child, viewMode);

      const srcX = (parent.position?.x ?? 100) + pDim.width;
      const srcY = (parent.position?.y ?? 100) + 40;
      const tgtX = child.position?.x ?? 400;
      const tgtY = (child.position?.y ?? 100) + 40;

      ctx.save();
      ctx.strokeStyle = rel.rel_type === 'identifying' ? '#f59e0b' : rel.rel_type === 'upstream_lineage' ? '#22d3ee' : '#94a3b8';
      ctx.lineWidth = 2.2;
      if (rel.rel_type !== 'identifying') ctx.setLineDash([6, 4]);

      ctx.beginPath();
      const midX = (srcX + tgtX) / 2;
      ctx.moveTo(srcX, srcY);
      ctx.bezierCurveTo(midX, srcY, midX, tgtY, tgtX, tgtY);
      ctx.stroke();
      ctx.restore();
    });
  }

  // 4. Render Table Nodes
  const nodeRadius = 10;
  for (const ent of visibleEntities) {
    const x = ent.position?.x ?? 100;
    const y = ent.position?.y ?? 100;
    const { width: w, height: h } = getNodeDimensions(ent, viewMode);
    const headerHeight = 44;
    const govHeight = 22;

    const isView = ent.entity_type === 'view' || ent.entity_type === 'materialized_view';
    const primaryTitle = viewMode === 'physical' ? `${ent.database_schema}.${ent.physical_name}` : ent.logical_name;
    const secondarySubtitle = viewMode === 'physical' ? ent.logical_name : ent.physical_name;

    ctx.save();

    // Node Box Shadow
    ctx.shadowColor = isDark ? 'rgba(0, 0, 0, 0.5)' : 'rgba(0, 0, 0, 0.08)';
    ctx.shadowBlur = 12;
    ctx.shadowOffsetY = 4;

    // Node Background
    ctx.fillStyle = isDark ? '#0f172a' : '#ffffff';
    ctx.beginPath();
    drawRoundRect(ctx, x, y, w, h, nodeRadius);
    ctx.fill();

    // Reset shadow
    ctx.shadowColor = 'transparent';
    ctx.shadowBlur = 0;

    // Node Border
    ctx.strokeStyle = isDark ? '#334155' : '#cbd5e1';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // Clip to rounded card boundary for header and content
    ctx.save();
    ctx.beginPath();
    drawRoundRect(ctx, x, y, w, h, nodeRadius);
    ctx.clip();

    // --- Header ---
    ctx.fillStyle = ent.header_color || '#2563eb';
    ctx.fillRect(x, y, w, headerHeight);

    // Primary Title
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 12.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText(primaryTitle, x + 12, y + 20);

    // Subtitle & Subject Area
    ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText(`${secondarySubtitle}  •  ${ent.subject_area.toUpperCase()}`, x + 12, y + 35);

    // Header Right Badges (dbt layer & stereotype)
    const dbtTag = (ent.dbt_layer || 'MART').toUpperCase();
    ctx.font = 'bold 9px monospace';
    const dbtWidth = ctx.measureText(dbtTag).width + 8;
    ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
    ctx.beginPath();
    drawRoundRect(ctx, x + w - dbtWidth - 10, y + 10, dbtWidth, 16, 4);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.fillText(dbtTag, x + w - dbtWidth - 6, y + 22);

    if (isView) {
      const viewBadge = ent.entity_type === 'materialized_view' ? 'MAT VIEW' : 'VIEW';
      const vbWidth = ctx.measureText(viewBadge).width + 8;
      ctx.fillStyle = 'rgba(6, 182, 212, 0.3)';
      ctx.beginPath();
      drawRoundRect(ctx, x + w - dbtWidth - vbWidth - 16, y + 10, vbWidth, 16, 4);
      ctx.fill();
      ctx.fillStyle = '#a5f3fc';
      ctx.fillText(viewBadge, x + w - dbtWidth - vbWidth - 12, y + 22);
    }

    // --- Governance Strip ---
    const govY = y + headerHeight;
    ctx.fillStyle = isDark ? '#020617' : '#f1f5f9';
    ctx.fillRect(x, govY, w, govHeight);
    ctx.strokeStyle = isDark ? '#1e293b' : '#e2e8f0';
    ctx.beginPath();
    ctx.moveTo(x, govY + govHeight);
    ctx.lineTo(x + w, govY + govHeight);
    ctx.stroke();

    // Retention policy text
    const retDays = ent.retention_policy?.active_retention_days || 365;
    const regFrame = ent.retention_policy?.regulatory_framework || 'NONE';
    const retLabel = regFrame !== 'NONE' ? `${regFrame}: ${retDays}d` : `Ret: ${retDays}d`;

    ctx.font = '9.5px monospace';
    ctx.fillStyle = isDark ? '#818cf8' : '#4f46e5';
    ctx.fillText(retLabel, x + 10, govY + 15);

    // Row count volumetrics
    if (ent.volumetrics?.estimated_row_count) {
      const rows = ent.volumetrics.estimated_row_count;
      const rowStr = rows >= 1_000_000 ? `~${(rows / 1_000_000).toFixed(1)}M rows` : `~${(rows / 1000).toFixed(0)}K rows`;
      ctx.fillStyle = isDark ? '#34d399' : '#059669';
      ctx.fillText(rowStr, x + 100, govY + 15);
    }

    // Steward verification badge
    if (ent.metadata_status === 'STEWARD_VERIFIED') {
      ctx.fillStyle = isDark ? '#34d399' : '#059669';
      ctx.font = 'bold 9px sans-serif';
      const verText = '✓ Verified';
      const verW = ctx.measureText(verText).width;
      ctx.fillText(verText, x + w - verW - 10, govY + 15);
    }

    // --- Columns or Conceptual Content ---
    if (viewMode === 'conceptual') {
      ctx.fillStyle = isDark ? '#cbd5e1' : '#334155';
      ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
      const desc = ent.description || 'No business description documented yet.';
      const words = desc.split(' ');
      let line = '';
      let curY = govY + govHeight + 20;
      for (const word of words) {
        const testLine = line + word + ' ';
        if (ctx.measureText(testLine).width > w - 24) {
          ctx.fillText(line, x + 12, curY);
          line = word + ' ';
          curY += 16;
          if (curY > y + h - 20) break;
        } else {
          line = testLine;
        }
      }
      ctx.fillText(line, x + 12, curY);
    } else {
      const colsStartY = govY + govHeight;
      const rowHeight = 28;

      ent.columns.forEach((col, idx) => {
        const rowY = colsStartY + idx * rowHeight;

        // Subtle row divider
        if (idx > 0) {
          ctx.strokeStyle = isDark ? 'rgba(51, 65, 85, 0.4)' : 'rgba(226, 232, 240, 0.8)';
          ctx.beginPath();
          ctx.moveTo(x, rowY);
          ctx.lineTo(x + w, rowY);
          ctx.stroke();
        }

        let curX = x + 10;

        // PK Badge
        if (col.is_pk) {
          ctx.fillStyle = isDark ? '#78350f' : '#fef3c7';
          ctx.beginPath();
          drawRoundRect(ctx, curX, rowY + 6, 20, 15, 3);
          ctx.fill();
          ctx.fillStyle = isDark ? '#fde68a' : '#92400e';
          ctx.font = 'bold 8.5px monospace';
          ctx.fillText('PK', curX + 4, rowY + 17);
          curX += 26;
        } else if (col.is_fk) {
          ctx.fillStyle = isDark ? '#082f49' : '#e0f2fe';
          ctx.beginPath();
          drawRoundRect(ctx, curX, rowY + 6, 20, 15, 3);
          ctx.fill();
          ctx.fillStyle = isDark ? '#7dd3fc' : '#0369a1';
          ctx.font = 'bold 8.5px monospace';
          ctx.fillText('FK', curX + 4, rowY + 17);
          curX += 26;
        } else {
          ctx.fillStyle = isDark ? '#64748b' : '#94a3b8';
          ctx.beginPath();
          ctx.arc(curX + 4, rowY + 14, 2, 0, Math.PI * 2);
          ctx.fill();
          curX += 16;
        }

        // Column Name
        const colLabel = viewMode === 'physical' ? col.physical_name : col.logical_name;
        ctx.fillStyle = col.is_pk
          ? isDark ? '#fef3c7' : '#92400e'
          : col.is_fk
          ? isDark ? '#bae6fd' : '#0284c7'
          : isDark ? '#f1f5f9' : '#1e293b';

        ctx.font = viewMode === 'physical'
          ? '11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
          : '11.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        if (col.is_pk) ctx.font = `bold ${ctx.font}`;
        ctx.fillText(colLabel, curX, rowY + 18);

        // Expression indicator (fx)
        if (col.source_expression) {
          const colW = ctx.measureText(colLabel).width;
          const fxX = curX + colW + 6;
          ctx.fillStyle = isDark ? 'rgba(6, 182, 212, 0.25)' : 'rgba(6, 182, 212, 0.15)';
          ctx.beginPath();
          drawRoundRect(ctx, fxX, rowY + 7, 16, 13, 2);
          ctx.fill();
          ctx.fillStyle = isDark ? '#67e8f9' : '#0891b2';
          ctx.font = 'bold 8px monospace';
          ctx.fillText('fx', fxX + 4, rowY + 16);
        }

        // Right-aligned Data Type
        const colType = getColumnDataType(col, viewMode, targetDialect, project.domains);
        ctx.fillStyle = isDark ? '#94a3b8' : '#64748b';
        ctx.font = '10.5px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace';
        const typeW = ctx.measureText(colType).width;
        ctx.fillText(colType, x + w - typeW - 12, rowY + 18);
      });
    }

    ctx.restore(); // restore card clipping
    ctx.restore(); // restore node shadow
  }

  // 5. Render Sticky Notes
  for (const note of visibleNotes) {
    const nx = note.position?.x ?? 80;
    const ny = note.position?.y ?? 500;
    const nw = 250;
    const nh = 120;

    ctx.save();
    ctx.shadowColor = 'rgba(0, 0, 0, 0.25)';
    ctx.shadowBlur = 8;
    ctx.shadowOffsetY = 3;

    ctx.fillStyle = note.color || '#fef08a';
    ctx.beginPath();
    drawRoundRect(ctx, nx, ny, nw, nh, 8);
    ctx.fill();

    ctx.shadowColor = 'transparent';
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#78350f';
    ctx.font = 'bold 10.5px sans-serif';
    ctx.fillText(`Sticky Note (${note.subject_area})`, nx + 10, ny + 18);

    ctx.strokeStyle = 'rgba(120, 53, 15, 0.2)';
    ctx.beginPath();
    ctx.moveTo(nx + 10, ny + 24);
    ctx.lineTo(nx + nw - 10, ny + 24);
    ctx.stroke();

    ctx.fillStyle = '#1c1917';
    ctx.font = '11px sans-serif';
    const words = (note.text || '').split(' ');
    let line = '';
    let curY = ny + 40;
    for (const word of words) {
      const test = line + word + ' ';
      if (ctx.measureText(test).width > nw - 20) {
        ctx.fillText(line, nx + 10, curY);
        line = word + ' ';
        curY += 15;
      } else {
        line = test;
      }
    }
    ctx.fillText(line, nx + 10, curY);
    ctx.restore();
  }

  return { canvas, bounds };
}

/**
 * Generates a standalone, pure SVG vector graphic without foreignObjects.
 */
export function generatePureSvgDiagram(options: ExportCanvasOptions): string {
  const store = useModelStore.getState();
  const project = store.project;
  const viewMode = store.viewMode;
  const targetDialect = store.targetDialect;
  const activeSubjectArea = options.activeSubjectArea || store.activeSubjectArea;
  const isDark = options.theme !== 'light';

  const visibleEntities = Object.values(project.entities).filter(
    (e) => activeSubjectArea === 'All' || e.subject_area.toLowerCase() === activeSubjectArea.toLowerCase()
  );
  const visibleEntityIds = new Set(visibleEntities.map((e) => e.id));

  const visibleNotes = Object.values(project.annotations || {}).filter(
    (n) => activeSubjectArea === 'All' || n.subject_area.toLowerCase() === activeSubjectArea.toLowerCase()
  );

  const bounds = computeDiagramBounds(visibleEntities, visibleNotes, viewMode);
  const bgColor = isDark ? '#090d16' : '#f8fafc';

  // Get edge SVG markup if available from React Flow
  const edgeSvg = document.querySelector<SVGSVGElement>('svg.react-flow__edges');
  let edgesMarkup = '';
  if (edgeSvg) {
    // Clone and strip any foreignObjects or script tags for security
    const clone = edgeSvg.cloneNode(true) as SVGSVGElement;
    clone.querySelectorAll('foreignObject, script').forEach((el) => el.remove());
    edgesMarkup = clone.innerHTML;
  }

  // Generate pure SVG nodes markup
  let nodesMarkup = '';
  for (const ent of visibleEntities) {
    const x = ent.position?.x ?? 100;
    const y = ent.position?.y ?? 100;
    const { width: w, height: h } = getNodeDimensions(ent, viewMode);
    const headerHeight = 44;
    const govHeight = 22;

    const primaryTitle = escapeXml(viewMode === 'physical' ? `${ent.database_schema}.${ent.physical_name}` : ent.logical_name);
    const secondarySubtitle = escapeXml(viewMode === 'physical' ? ent.logical_name : ent.physical_name);
    const headerColor = ent.header_color || '#2563eb';
    const isView = ent.entity_type === 'view' || ent.entity_type === 'materialized_view';
    const dbtTag = escapeXml((ent.dbt_layer || 'MART').toUpperCase());

    let columnsSvg = '';
    if (viewMode === 'conceptual') {
      const desc = escapeXml(ent.description || 'No business description documented yet.');
      columnsSvg = `<text x="${x + 12}" y="${y + headerHeight + govHeight + 22}" fill="${isDark ? '#cbd5e1' : '#334155'}" font-size="11" font-family="sans-serif">${desc}</text>`;
    } else {
      const colsStartY = y + headerHeight + govHeight;
      const rowH = 28;
      ent.columns.forEach((col, idx) => {
        const rowY = colsStartY + idx * rowH;
        const colLabel = escapeXml(viewMode === 'physical' ? col.physical_name : col.logical_name);
        const colType = escapeXml(getColumnDataType(col, viewMode, targetDialect, project.domains));
        const colNameFill = col.is_pk
          ? isDark ? '#fef3c7' : '#92400e'
          : col.is_fk
          ? isDark ? '#bae6fd' : '#0284c7'
          : isDark ? '#f1f5f9' : '#1e293b';

        let badgeSvg = '';
        let textX = x + 10;
        if (col.is_pk) {
          badgeSvg = `<rect x="${textX}" y="${rowY + 6}" width="20" height="15" rx="3" fill="${isDark ? '#78350f' : '#fef3c7'}" /><text x="${textX + 4}" y="${rowY + 17}" fill="${isDark ? '#fde68a' : '#92400e'}" font-size="8.5" font-family="monospace" font-weight="bold">PK</text>`;
          textX += 26;
        } else if (col.is_fk) {
          badgeSvg = `<rect x="${textX}" y="${rowY + 6}" width="20" height="15" rx="3" fill="${isDark ? '#082f49' : '#e0f2fe'}" /><text x="${textX + 4}" y="${rowY + 17}" fill="${isDark ? '#7dd3fc' : '#0369a1'}" font-size="8.5" font-family="monospace" font-weight="bold">FK</text>`;
          textX += 26;
        } else {
          badgeSvg = `<circle cx="${textX + 4}" cy="${rowY + 14}" r="2" fill="${isDark ? '#64748b' : '#94a3b8'}" />`;
          textX += 16;
        }

        const fontFam = viewMode === 'physical' ? 'monospace' : 'sans-serif';
        const fontW = col.is_pk ? 'bold' : 'normal';

        columnsSvg += `
          <line x1="${x}" y1="${rowY}" x2="${x + w}" y2="${rowY}" stroke="${isDark ? 'rgba(51, 65, 85, 0.4)' : 'rgba(226, 232, 240, 0.8)'}" stroke-width="1" />
          ${badgeSvg}
          <text x="${textX}" y="${rowY + 18}" fill="${colNameFill}" font-size="11" font-family="${fontFam}" font-weight="${fontW}">${colLabel}</text>
          <text x="${x + w - 12}" y="${rowY + 18}" fill="${isDark ? '#94a3b8' : '#64748b'}" font-size="10.5" font-family="monospace" text-anchor="end">${colType}</text>
        `;
      });
    }

    const retDays = ent.retention_policy?.active_retention_days || 365;
    const regFrame = ent.retention_policy?.regulatory_framework || 'NONE';
    const retLabel = escapeXml(regFrame !== 'NONE' ? `${regFrame}: ${retDays}d` : `Ret: ${retDays}d`);
    const rowStr = ent.volumetrics?.estimated_row_count ? `~${Math.round(ent.volumetrics.estimated_row_count / 1000)}K rows` : '';

    nodesMarkup += `
      <g id="entity-${ent.id}">
        <!-- Node Card Base -->
        <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" fill="${isDark ? '#0f172a' : '#ffffff'}" stroke="${isDark ? '#334155' : '#cbd5e1'}" stroke-width="1.2" />
        
        <!-- Header -->
        <path d="M ${x} ${y + 10} Q ${x} ${y} ${x + 10} ${y} L ${x + w - 10} ${y} Q ${x + w} ${y} ${x + w} ${y + 10} L ${x + w} ${y + headerHeight} L ${x} ${y + headerHeight} Z" fill="${headerColor}" />
        <text x="${x + 12}" y="${y + 20}" fill="#ffffff" font-size="12.5" font-weight="bold" font-family="sans-serif">${primaryTitle}</text>
        <text x="${x + 12}" y="${y + 35}" fill="rgba(255, 255, 255, 0.85)" font-size="10" font-family="sans-serif">${secondarySubtitle} • ${escapeXml(ent.subject_area.toUpperCase())}</text>
        
        <!-- dbt Layer Badge -->
        <rect x="${x + w - 46}" y="${y + 10}" width="38" height="16" rx="4" fill="rgba(0,0,0,0.35)" />
        <text x="${x + w - 27}" y="${y + 22}" fill="#ffffff" font-size="9" font-family="monospace" font-weight="bold" text-anchor="middle">${dbtTag}</text>

        <!-- Governance Strip -->
        <rect x="${x}" y="${y + headerHeight}" width="${w}" height="${govHeight}" fill="${isDark ? '#020617' : '#f1f5f9'}" />
        <line x1="${x}" y1="${y + headerHeight + govHeight}" x2="${x + w}" y2="${y + headerHeight + govHeight}" stroke="${isDark ? '#1e293b' : '#e2e8f0'}" stroke-width="1" />
        <text x="${x + 10}" y="${y + headerHeight + 15}" fill="${isDark ? '#818cf8' : '#4f46e5'}" font-size="9.5" font-family="monospace">${retLabel}</text>
        <text x="${x + 100}" y="${y + headerHeight + 15}" fill="${isDark ? '#34d399' : '#059669'}" font-size="9.5" font-family="monospace">${rowStr}</text>

        <!-- Columns -->
        ${columnsSvg}
      </g>
    `;
  }

  const title = escapeXml(options.projectName || project.name || 'MetaForge Data Model');
  const subAreaLabel = escapeXml(activeSubjectArea === 'All' ? 'Complete Metamodel' : `Subject Area: ${activeSubjectArea}`);
  const bannerSubtitle = escapeXml(`${subAreaLabel} | Dialect: ${targetDialect.toUpperCase()} | Mode: ${viewMode.toUpperCase()} | ${new Date().toISOString().slice(0, 10)}`);

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}" width="${bounds.width}" height="${bounds.height}">
  <style>
    text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  </style>
  <rect x="${bounds.x}" y="${bounds.y}" width="${bounds.width}" height="${bounds.height}" fill="${bgColor}" />
  
  <!-- Banner Header -->
  <text x="${bounds.x + 30}" y="${bounds.y + 36}" fill="${isDark ? '#38bdf8' : '#0284c7'}" font-size="16" font-weight="bold">${title}</text>
  <text x="${bounds.x + 30}" y="${bounds.y + 54}" fill="${isDark ? '#94a3b8' : '#64748b'}" font-size="11">${bannerSubtitle}</text>

  <!-- Edges -->
  <g class="react-flow__edges">${edgesMarkup}</g>

  <!-- Nodes -->
  <g class="entities">${nodesMarkup}</g>
</svg>`;
}

/**
 * Triggers a file download in the browser.
 */
function downloadBlob(blob: Blob, filename: string) {
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

/**
 * Generates an uncompressed binary PDF 1.4 file containing an embedded JPEG of the diagram.
 */
function createPdfFromJpeg(jpegData: Uint8Array, imgWidth: number, imgHeight: number, title: string): Blob {
  const pageWidth = 842; // A4 landscape width (pt)
  const pageHeight = 595; // A4 landscape height (pt)

  const margin = 36;
  const maxW = pageWidth - margin * 2;
  const maxH = pageHeight - margin * 2 - 30;

  const aspect = imgWidth / imgHeight;
  let renderW = maxW;
  let renderH = maxW / aspect;
  if (renderH > maxH) {
    renderH = maxH;
    renderW = maxH * aspect;
  }
  const renderX = margin + (maxW - renderW) / 2;
  const renderY = margin;

  const enc = new TextEncoder();
  const objects: Uint8Array[] = [];
  const offsets: number[] = [];

  const addObj = (content: string, binaryStream?: Uint8Array) => {
    offsets.push(objects.reduce((acc, o) => acc + o.length, 0));
    const header = enc.encode(`${offsets.length} 0 obj\n${content}\n`);
    const footer = enc.encode(`\nendobj\n`);
    const totalLen = header.length + (binaryStream ? binaryStream.length : 0) + footer.length;
    const combined = new Uint8Array(totalLen);
    combined.set(header, 0);
    if (binaryStream) combined.set(binaryStream, header.length);
    combined.set(footer, header.length + (binaryStream ? binaryStream.length : 0));
    objects.push(combined);
  };

  addObj(`<< /Type /Catalog /Pages 2 0 R >>`);
  addObj(`<< /Type /Pages /Kids [3 0 R] /Count 1 >>`);
  addObj(
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Contents 4 0 R /Resources << /XObject << /Im1 5 0 R >> /Font << /F1 6 0 R >> >> >>`
  );

  const titleText = title.replace(/[()\\]/g, '');
  const contentStreamStr = `
q
BT
/F1 14 Tf
${margin} ${pageHeight - margin - 14} Td
(${titleText}) Tj
ET
q
${renderW.toFixed(2)} 0 0 ${renderH.toFixed(2)} ${renderX.toFixed(2)} ${renderY.toFixed(2)} cm
/Im1 Do
Q
Q
`.trim();
  const contentStreamBytes = enc.encode(contentStreamStr);

  addObj(`<< /Length ${contentStreamBytes.length} >>\nstream\n`, contentStreamBytes);
  addObj(
    `<< /Type /XObject /Subtype /Image /Width ${imgWidth} /Height ${imgHeight} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegData.length} >>\nstream\n`,
    jpegData
  );
  addObj(`<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>`);

  const headerBytes = enc.encode("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  const startXref = headerBytes.length + objects.reduce((acc, o) => acc + o.length, 0);

  let xrefStr = `xref\n0 ${offsets.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) {
    const actualOffset = headerBytes.length + off;
    xrefStr += actualOffset.toString().padStart(10, '0') + ' 00000 n \n';
  }
  xrefStr += `trailer\n<< /Size ${offsets.length + 1} /Root 1 0 R >>\nstartxref\n${startXref}\n%%EOF\n`;
  const trailerBytes = enc.encode(xrefStr);

  const fullPdf = new Uint8Array(headerBytes.length + objects.reduce((acc, o) => acc + o.length, 0) + trailerBytes.length);
  fullPdf.set(headerBytes, 0);
  let pos = headerBytes.length;
  for (const obj of objects) {
    fullPdf.set(obj, pos);
    pos += obj.length;
  }
  fullPdf.set(trailerBytes, pos);

  return new Blob([fullPdf], { type: 'application/pdf' });
}

/**
 * Main Export Entrypoint: Exports canvas diagram as PNG, SVG, or standalone PDF.
 * Guaranteed never to throw 'Tainted canvases may not be exported'.
 */
export async function exportCanvasDiagram(options: ExportCanvasOptions): Promise<void> {
  const store = useModelStore.getState();
  const projName = (options.projectName || store.project.name || 'metaforge_datamodel').replace(/[^a-zA-Z0-9_-]/g, '_');
  const subjectArea = options.activeSubjectArea && options.activeSubjectArea !== 'All' ? `_${options.activeSubjectArea}` : '';
  const timestamp = new Date().toISOString().slice(0, 10);
  const baseFilename = `${projName}${subjectArea}_${timestamp}`;

  // 1. Pure SVG Vector Export (Infinite resolution, no foreignObjects)
  if (options.format === 'svg') {
    const svgStr = generatePureSvgDiagram(options);
    const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
    downloadBlob(blob, `${baseFilename}.svg`);
    return;
  }

  // Render to untainted Canvas 2D
  const { canvas } = renderDiagramToCanvas2D(options);

  // 2. High-Resolution PNG Image Export
  if (options.format === 'png') {
    await new Promise<void>((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error('Failed to convert canvas to PNG blob.'));
          return;
        }
        downloadBlob(blob, `${baseFilename}.png`);
        resolve();
      }, 'image/png', 1.0);
    });
    return;
  }

  // 3. Landscape PDF Document Export
  if (options.format === 'pdf') {
    const jpegBlob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((b) => {
        if (b) resolve(b);
        else reject(new Error('Failed to create JPEG blob for PDF'));
      }, 'image/jpeg', 0.95);
    });

    const jpegBuffer = await jpegBlob.arrayBuffer();
    const jpegBytes = new Uint8Array(jpegBuffer);

    const pdfTitle = `${options.projectName || store.project.name || 'MetaForge Data Model'} — Subject Area: ${options.activeSubjectArea || 'All'}`;
    const pdfBlob = createPdfFromJpeg(jpegBytes, canvas.width, canvas.height, pdfTitle);
    downloadBlob(pdfBlob, `${baseFilename}.pdf`);
  }
}
