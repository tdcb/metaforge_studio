import React, { useState } from 'react';
import Editor from '@monaco-editor/react';
import {
  GitCompare,
  Upload,
  X,
  Play,
  Download,
  CheckCircle2,
  PlusCircle,
  MinusCircle,
  RefreshCw,
  Database,
} from 'lucide-react';
import { useModelStore } from '../../store/useModelStore';
import { api } from '../../services/api';
import type { CompareDiffResult, TargetDialect } from '../../types/metamodel';

const SAMPLE_PRODUCTION_DRIFT_DDL = `-- Simulated Legacy Production DDL with Schema Drift
CREATE TABLE CORE.DIM_CUSTOMER (
    CUST_ID NUMBER(38,0) PRIMARY KEY,
    CUST_FULL_NM VARCHAR(80) NOT NULL, -- Shorter length than canvas (150)
    LEGACY_LOYALTY_FLAG VARCHAR(10),   -- Legacy column dropped in canvas
    CUST_STAT_CD VARCHAR(30) NOT NULL
);

CREATE TABLE CORE.DIM_POLICY (
    PLCY_ID NUMBER(38,0) PRIMARY KEY,
    CUST_ID NUMBER(38,0) NOT NULL,
    PLCY_NBR VARCHAR(30) NOT NULL,
    PLCY_EFF_DT DATE NOT NULL
);
-- Note: FCT_CLAIM and STG_RAW_CLAIMS are missing from legacy target DB!
`;

const SAMPLE_REVERSE_ENG_DDL = `-- Sample Enterprise Reinsurance DDL + Complex Analytical View (Parsed via SQLGlot AST)
CREATE TABLE FINANCE.DIM_REINSURER (
    REINSURER_ID NUMBER(38,0) PRIMARY KEY,
    REINSURER_CD VARCHAR(30) NOT NULL,
    REINSURER_LEGAL_NM VARCHAR(200) NOT NULL,
    AM_BEST_RATING_CD VARCHAR(10) NOT NULL,
    CONTACT_EMAIL_ADDR VARCHAR(255)
);

CREATE TABLE FINANCE.FCT_CEDED_PREMIUM (
    CEDED_TXN_ID NUMBER(38,0) PRIMARY KEY,
    REINSURER_ID NUMBER(38,0) NOT NULL,
    PLCY_ID NUMBER(38,0) NOT NULL,
    CEDED_PREM_AMT NUMBER(18,2) NOT NULL,
    ACCOUNTING_EFF_DT DATE NOT NULL
);

ALTER TABLE FINANCE.FCT_CEDED_PREMIUM
    ADD CONSTRAINT FK_CEDED_REINSURER FOREIGN KEY (REINSURER_ID)
    REFERENCES FINANCE.DIM_REINSURER (REINSURER_ID);

-- Complex View with CTEs, Multi-Table JOINs, CASE WHEN & Aggregations:
-- SQLGlot AST extracts projected columns, expressions, inferred types, and Upstream Lineage edges!
CREATE OR REPLACE VIEW FINANCE.VW_REINSURER_RISK_EXPOSURE AS
WITH CEDED_AGG AS (
    SELECT
        REINSURER_ID,
        COUNT(CEDED_TXN_ID) AS CEDED_TXN_CNT,
        SUM(CEDED_PREM_AMT) AS TOTAL_CEDED_PREM_AMT
    FROM FINANCE.FCT_CEDED_PREMIUM
    GROUP BY REINSURER_ID
)
SELECT
    R.REINSURER_ID AS REINSURER_ID,
    R.REINSURER_LEGAL_NM AS REINSURER_LEGAL_NM,
    R.AM_BEST_RATING_CD AS AM_BEST_RATING_CD,
    COALESCE(A.CEDED_TXN_CNT, 0) AS CEDED_TXN_COUNT,
    COALESCE(A.TOTAL_CEDED_PREM_AMT, 0) AS TOTAL_CEDED_PREMIUM_AMT,
    CASE
        WHEN COALESCE(A.TOTAL_CEDED_PREM_AMT, 0) > 1000000 THEN 'HIGH_EXPOSURE'
        ELSE 'STANDARD'
    END AS EXPOSURE_TIER_CD
FROM FINANCE.DIM_REINSURER R
LEFT JOIN CEDED_AGG A
    ON R.REINSURER_ID = A.REINSURER_ID;
`;

export const CompareModal: React.FC = () => {
  const isCompareModalOpen = useModelStore((s) => s.isCompareModalOpen);
  const compareModalTab = useModelStore((s) => s.compareModalTab);
  const project = useModelStore((s) => s.project);
  const targetDialect = useModelStore((s) => s.targetDialect);
  const authToken = useModelStore((s) => s.authToken);

  const closeCompareModal = useModelStore((s) => s.closeCompareModal);
  const openCompareModal = useModelStore((s) => s.openCompareModal);
  const setProject = useModelStore((s) => s.setProject);
  const setStatusBanner = useModelStore((s) => s.setStatusBanner);
  const refreshCompiledCode = useModelStore((s) => s.refreshCompiledCode);

  const [dialect, setDialect] = useState<TargetDialect>(targetDialect);
  const [targetDdl, setTargetDdl] = useState<string>(SAMPLE_PRODUCTION_DRIFT_DDL);
  const [diffResult, setDiffResult] = useState<CompareDiffResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Reverse Engineer tab state
  const [revDdl, setRevDdl] = useState<string>(SAMPLE_REVERSE_ENG_DDL);
  const [revSubjectArea, setRevSubjectArea] = useState<string>('Finance');
  const [mergeIntoExisting, setMergeIntoExisting] = useState<boolean>(true);

  if (!isCompareModalOpen) return null;

  const handleRunCompare = async () => {
    setIsLoading(true);
    try {
      const res = await api.runCompleteCompare(
        project,
        dialect,
        targetDdl,
        undefined,
        authToken
      );
      setDiffResult(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Compare failed';
      setStatusBanner({ type: 'error', message: msg });
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunReverseEngineer = async () => {
    setIsLoading(true);
    try {
      const res = await api.reverseEngineerDdl(
        revDdl,
        dialect,
        revSubjectArea,
        mergeIntoExisting,
        authToken
      );
      setProject(res.project, true);
      setStatusBanner({
        type: 'success',
        message: `Reverse-engineered ${res.entities_parsed} tables and ${res.relationships_parsed} relationships via SQLGlot!`,
      });
      await refreshCompiledCode();
      closeCompareModal();
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('metaforge:auto-layout'));
      }, 150);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'DDL Reverse Engineering failed';
      setStatusBanner({ type: 'error', message: msg });
    } finally {
      setIsLoading(false);
    }
  };

  const downloadAlterScript = () => {
    if (!diffResult) return;
    const blob = new Blob([diffResult.alter_script], {
      type: 'text/plain;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `metaforge_complete_compare_${dialect}_alter.sql`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-6xl h-[86vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header & Tab Switcher */}
        <div className="px-6 py-3.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => openCompareModal('compare')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                compareModalTab === 'compare'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <GitCompare className="w-4 h-4" />
              <span>Model Compare &amp; ALTER Sync</span>
            </button>

            <button
              type="button"
              onClick={() => openCompareModal('reverse')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                compareModalTab === 'reverse'
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Upload className="w-4 h-4" />
              <span>Reverse Engineer SQL DDL (SQLGlot AST)</span>
            </button>
          </div>

          <div className="flex items-center gap-3">
            <select
              value={dialect}
              onChange={(e) => setDialect(e.target.value as TargetDialect)}
              className="bg-slate-900 text-xs font-semibold text-sky-400 px-3 py-1.5 rounded-lg border border-slate-700"
            >
              <option value="snowflake">Target: Snowflake</option>
              <option value="sql_server">Target: SQL Server (T-SQL)</option>
              <option value="oracle">Target: Oracle (PL/SQL)</option>
            </select>

            <button
              type="button"
              onClick={closeCompareModal}
              className="text-slate-400 hover:text-white p-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* TAB 1: Complete Compare */}
        {compareModalTab === 'compare' ? (
          <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0">
            {/* Left Column: Target DDL Input + Diff Summary */}
            <div className="lg:col-span-5 border-r border-slate-800 flex flex-col min-h-0 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  1. Target Production DDL Baseline
                </span>
                <button
                  type="button"
                  onClick={handleRunCompare}
                  disabled={isLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold shadow"
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>{isLoading ? 'Diffing...' : 'Run Complete Compare'}</span>
                </button>
              </div>

              <textarea
                value={targetDdl}
                onChange={(e) => setTargetDdl(e.target.value)}
                rows={9}
                className="w-full bg-slate-950 font-mono text-xs text-slate-200 p-3 rounded-xl border border-slate-800 resize-none outline-none focus:border-amber-500"
              />

              {/* Structured Diff Categorization */}
              <div className="flex-1 overflow-y-auto bg-slate-950 rounded-xl border border-slate-800 p-3 space-y-2.5">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-xs font-bold text-slate-300">
                    2. Detected Schema Differences
                  </span>
                  {diffResult && (
                    <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono text-[11px] font-bold">
                      {diffResult.total_differences} changes
                    </span>
                  )}
                </div>

                {!diffResult ? (
                  <p className="text-xs text-slate-500 py-6 text-center">
                    Click &ldquo;Run Complete Compare&rdquo; above to diff the active Canvas Metamodel against the Target DDL and generate a safe ALTER script.
                  </p>
                ) : (
                  <div className="space-y-2 text-xs">
                    {diffResult.added_tables.map((t) => (
                      <div
                        key={t}
                        className="px-2.5 py-1.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 flex items-center gap-2 font-mono"
                      >
                        <PlusCircle className="w-3.5 h-3.5 shrink-0" />
                        <span>ADDED TABLE: {t}</span>
                      </div>
                    ))}
                    {diffResult.dropped_tables.map((t) => (
                      <div
                        key={t}
                        className="px-2.5 py-1.5 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 flex items-center gap-2 font-mono"
                      >
                        <MinusCircle className="w-3.5 h-3.5 shrink-0" />
                        <span>DROPPED TABLE: {t}</span>
                      </div>
                    ))}
                    {diffResult.column_diffs.map((cd, i) => (
                      <div
                        key={`${cd.table_name}-${cd.column_name}-${i}`}
                        className="px-2.5 py-1.5 rounded bg-slate-900 border border-slate-800 flex items-start justify-between gap-2"
                      >
                        <div>
                          <div className="font-mono font-semibold text-slate-200">
                            {cd.table_name}.{cd.column_name}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            {cd.details}
                          </div>
                        </div>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                            cd.change_type === 'ADDED'
                              ? 'bg-emerald-500/20 text-emerald-300'
                              : cd.change_type === 'DROPPED'
                              ? 'bg-rose-500/20 text-rose-300'
                              : 'bg-amber-500/20 text-amber-300'
                          }`}
                        >
                          {cd.change_type}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Right Column: Generated Dialect-Specific ALTER Synchronization Script */}
            <div className="lg:col-span-7 flex flex-col min-h-0">
              <div className="px-4 py-2.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
                <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4" />
                  Generated Non-Destructive ALTER Migration Script ({dialect.toUpperCase()})
                </span>
                {diffResult && (
                  <button
                    type="button"
                    onClick={downloadAlterScript}
                    className="flex items-center gap-1 px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download ALTER Script</span>
                  </button>
                )}
              </div>
              <div className="flex-1 min-h-0">
                <Editor
                  height="100%"
                  theme="vs-dark"
                  language="sql"
                  value={
                    diffResult?.alter_script ||
                    '-- Click "Run Complete Compare" on the left to generate the dialect-specific ALTER TABLE synchronization script.'
                  }
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    fontSize: 12,
                    wordWrap: 'on',
                  }}
                />
              </div>
            </div>
          </div>
        ) : (
          /* TAB 2: Reverse Engineer SQL DDL into Canvas */
          <div className="flex-1 flex flex-col p-6 space-y-4 min-h-0">
            {/* Live Database & SQLite Callout Banner */}
            <div className="p-3 bg-gradient-to-r from-emerald-950/80 to-slate-900 border border-emerald-500/40 rounded-xl flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5">
                <Database className="w-5 h-5 text-emerald-400 shrink-0" />
                <div>
                  <div className="text-xs font-bold text-white flex items-center gap-2">
                    <span>Connect directly to Live SQLite Warehouse or Cloud Database?</span>
                    <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      Recommended
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-300">
                    Reverse engineer pre-seeded Staging, Core DWH, and Marts directly from SQLite without manual copy/pasting.
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  closeCompareModal();
                  window.dispatchEvent(
                    new CustomEvent('metaforge:open-connections', { detail: { tab: 'reverse' } })
                  );
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shrink-0 shadow-md transition-all cursor-pointer"
              >
                <Database className="w-3.5 h-3.5" />
                <span>Reverse Engineer SQLite &raquo;</span>
              </button>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-bold text-white">
                  SQLGlot AST Reverse-Engineering Engine
                </h3>
                <p className="text-xs text-slate-400">
                  Paste or upload existing Snowflake, SQL Server (T-SQL), or Oracle (PL/SQL) CREATE TABLE &amp; ALTER TABLE scripts to automatically infer entities, cross-dialect data types, PKs, FKs, and PII tags.
                </p>
              </div>

              <div className="flex items-center gap-3">
                <input
                  value={revSubjectArea}
                  onChange={(e) => setRevSubjectArea(e.target.value)}
                  placeholder="Target Subject Area"
                  className="bg-slate-950 text-xs text-white px-3 py-1.5 rounded-lg border border-slate-700 w-36"
                />

                <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={mergeIntoExisting}
                    onChange={(e) => setMergeIntoExisting(e.target.checked)}
                    className="rounded accent-sky-500"
                  />
                  <span>Merge into current project</span>
                </label>

                <button
                  type="button"
                  onClick={handleRunReverseEngineer}
                  disabled={isLoading}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold shadow"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                  <span>Parse DDL &amp; Import to Canvas</span>
                </button>
              </div>
            </div>

            <div className="flex-1 rounded-xl overflow-hidden border border-slate-800">
              <Editor
                height="100%"
                theme="vs-dark"
                language="sql"
                value={revDdl}
                onChange={(v) => setRevDdl(v || '')}
                options={{
                  minimap: { enabled: false },
                  fontSize: 12,
                  wordWrap: 'on',
                }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
