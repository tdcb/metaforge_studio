import React from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  Position,
  getSmoothStepPath,
  type EdgeProps,
} from '@xyflow/react';
import type { RelationshipModel } from '../../types/metamodel';
import { useModelStore } from '../../store/useModelStore';

export interface CrowFootEdgeData extends Record<string, unknown> {
  relationship: RelationshipModel;
}

export const CrowFootEdge: React.FC<EdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}) => {
  const edgeData = data as unknown as CrowFootEdgeData | undefined;
  const rel = edgeData?.relationship;
  const selectedRelationshipId = useModelStore((s) => s.selectedRelationshipId);
  const selectRelationship = useModelStore((s) => s.selectRelationship);
  const toggleRelationshipType = useModelStore((s) => s.toggleRelationshipType);
  const toggleRelationshipMandatory = useModelStore((s) => s.toggleRelationshipMandatory);
  const cycleRelationshipCardinality = useModelStore(
    (s) => s.cycleRelationshipCardinality
  );
  const deleteRelationship = useModelStore((s) => s.deleteRelationship);

  const isSelected = selected || selectedRelationshipId === id;
  const relType = rel?.rel_type || 'non_identifying';
  const isIdentifying = relType === 'identifying';
  const isLineage = relType === 'upstream_lineage';
  const cardinality = rel?.cardinality || '1:N';
  const isMandatory = rel?.is_mandatory ?? (isIdentifying || cardinality === '1:N' || cardinality === '1:1');

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 12,
  });

  const strokeColor = isSelected
    ? '#38bdf8'
    : isLineage
    ? '#22d3ee'
    : isIdentifying
    ? '#f59e0b'
    : isMandatory
    ? '#60a5fa'
    : '#94a3b8';

  // Compute direction unit vector at target for direct Crow's Foot SVG geometry
  // If target handle is on the Left of target node, edge approaches from left (-1, 0) into targetX, targetY
  const dirX =
    targetPosition === Position.Left
      ? -1
      : targetPosition === Position.Right
      ? 1
      : 0;
  const srcDirX =
    sourcePosition === Position.Right
      ? 1
      : sourcePosition === Position.Left
      ? -1
      : 1;

  const isMany = cardinality === '1:N' || cardinality === '0:N';
  const isZero = !isMandatory || cardinality === '0:N' || cardinality === '0:1';

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: strokeColor,
          strokeWidth: isSelected ? 2.8 : (isMandatory || isIdentifying ? 2.2 : 1.8),
          strokeDasharray: isIdentifying || isMandatory
            ? undefined
            : isLineage
            ? '4 4'
            : '6 4',
        }}
      />

      {/* Direct SVG Crow's Foot & Parent Tick Marks (Never clipped by browser marker bounds) */}
      <g className="react-flow__edge-crowsfoot" pointerEvents="none">
        {/* Source (Parent = 1 Mandatory Bar ||) */}
        {!isLineage && (
          <>
            <line
              x1={sourceX + srcDirX * 8}
              y1={sourceY - 7}
              x2={sourceX + srcDirX * 8}
              y2={sourceY + 7}
              stroke={strokeColor}
              strokeWidth={2.2}
            />
            <line
              x1={sourceX + srcDirX * 13}
              y1={sourceY - 7}
              x2={sourceX + srcDirX * 13}
              y2={sourceY + 7}
              stroke={strokeColor}
              strokeWidth={2.2}
            />
          </>
        )}

        {/* Target: either Upstream->Downstream Lineage Arrow OR True IE Crow's Foot Notation */}
        {isLineage ? (
          <polygon
            points={`${targetX},${targetY} ${targetX + dirX * 12},${targetY - 6} ${
              targetX + dirX * 12
            },${targetY + 6}`}
            fill={strokeColor}
          />
        ) : (
          <>
            {/* Three-pronged Crow's Foot (<) for 1:N and 0:N */}
            {isMany && (
              <>
                <line
                  x1={targetX + dirX * 14}
                  y1={targetY}
                  x2={targetX}
                  y2={targetY - 8}
                  stroke={strokeColor}
                  strokeWidth={2.2}
                  strokeLinecap="round"
                />
                <line
                  x1={targetX + dirX * 14}
                  y1={targetY}
                  x2={targetX}
                  y2={targetY}
                  stroke={strokeColor}
                  strokeWidth={2.2}
                  strokeLinecap="round"
                />
                <line
                  x1={targetX + dirX * 14}
                  y1={targetY}
                  x2={targetX}
                  y2={targetY + 8}
                  stroke={strokeColor}
                  strokeWidth={2.2}
                  strokeLinecap="round"
                />
              </>
            )}

            {/* Mandatory '1' Bar (|) vs Optional '0' Ring (O) before the Crow's Foot */}
            {isZero ? (
              <circle
                cx={targetX + dirX * 20}
                cy={targetY}
                r={4.5}
                fill="#0f172a"
                stroke={strokeColor}
                strokeWidth={2}
              />
            ) : (
              <line
                x1={targetX + dirX * 16}
                y1={targetY - 7}
                x2={targetX + dirX * 16}
                y2={targetY + 7}
                stroke={strokeColor}
                strokeWidth={2.2}
              />
            )}

            {/* If 1:1 or 0:1, draw the single bar near target */}
            {!isMany && (
              <line
                x1={targetX + dirX * 9}
                y1={targetY - 7}
                x2={targetX + dirX * 9}
                y2={targetY + 7}
                stroke={strokeColor}
                strokeWidth={2.2}
              />
            )}
          </>
        )}
      </g>

      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="nodrag nopan"
        >
          <div
            onClick={(e) => {
              e.stopPropagation();
              selectRelationship(id);
            }}
            className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono shadow-lg border transition-all cursor-pointer ${
              isSelected
                ? 'bg-slate-900 border-sky-400 text-sky-200 ring-2 ring-sky-500/30'
                : isLineage
                ? 'bg-cyan-950/90 border-cyan-500/50 text-cyan-200 hover:border-cyan-400'
                : isIdentifying
                ? 'bg-amber-950/90 border-amber-500/50 text-amber-200 hover:border-amber-400'
                : 'bg-slate-900/90 border-slate-700 text-slate-300 hover:border-slate-500'
            }`}
          >
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                toggleRelationshipType(id);
              }}
              title="Click to cycle: Non-Identifying FK -> Identifying (PK+FK) -> Upstream/Downstream Lineage"
              className="font-semibold hover:underline"
            >
              {isLineage ? 'LINEAGE ↑↓' : isIdentifying ? 'IDENTIFYING' : 'NON-ID'}
            </button>
            {!isLineage && (
              <>
                <span className="text-slate-600">|</span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleRelationshipMandatory(id);
                  }}
                  title="Click to toggle: Mandatory (Solid Line) vs Optional (Dashed Line)"
                  className={`font-semibold hover:underline ${
                    isMandatory ? 'text-blue-300 font-bold' : 'text-amber-300'
                  }`}
                >
                  {isMandatory ? 'MANDATORY' : 'OPTIONAL'}
                </button>
              </>
            )}
            <span className="text-slate-600">|</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                cycleRelationshipCardinality(id);
              }}
              title="Click to cycle Crow's Foot cardinality (1:N, 0:N, 1:1, 0:1)"
              className="text-sky-300 font-bold hover:underline"
            >
              {cardinality}
            </button>
            {isSelected && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  deleteRelationship(id);
                }}
                title="Delete relationship"
                className="ml-1 text-rose-400 hover:text-rose-300 font-bold"
              >
                ×
              </button>
            )}
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
};
