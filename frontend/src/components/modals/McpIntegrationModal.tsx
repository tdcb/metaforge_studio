import React, { useState, useEffect } from 'react';
import {
  Terminal,
  Copy,
  Check,
  Server,
  Wrench,
  BookOpen,
  Sparkles,
  ExternalLink,
  X,
  Play,
  Loader2,
  CheckCircle2,
  Code2,
  Cpu,
  Layers,
} from 'lucide-react';
import { useModelStore } from '../../store/useModelStore';
import { api } from '../../services/api';

interface McpIntegrationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type ClientTab = 'claude_code' | 'cursor' | 'kiro' | 'gemini' | 'claude_desktop' | 'http';

export const McpIntegrationModal: React.FC<McpIntegrationModalProps> = ({
  isOpen,
  onClose,
}) => {
  const authToken = useModelStore((s) => s.authToken);
  const setStatusBanner = useModelStore((s) => s.setStatusBanner);

  const [activeTab, setActiveTab] = useState<ClientTab>('claude_code');
  const [activeView, setActiveView] = useState<'setup' | 'tools' | 'tester'>('setup');
  const [mcpConfig, setMcpConfig] = useState<any>(null);
  const [toolsList, setToolsList] = useState<any[]>([]);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Live tool tester state
  const [selectedTestTool, setSelectedTestTool] = useState<string>('get_model_summary');
  const [testToolArgs, setTestToolArgs] = useState<string>('{}');
  const [isExecutingTest, setIsExecutingTest] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);

  useEffect(() => {
    if (!isOpen) return;
    api
      .getMcpConfig(authToken)
      .then((cfg) => setMcpConfig(cfg))
      .catch((err) => console.warn('Could not load MCP config:', err));

    api
      .getMcpTools(authToken)
      .then((res) => setToolsList(res.tools || []))
      .catch((err) => console.warn('Could not load MCP tools:', err));
  }, [isOpen, authToken]);

  if (!isOpen) return null;

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  const handleRunTestTool = async () => {
    setIsExecutingTest(true);
    setTestResult(null);
    try {
      let parsedArgs = {};
      try {
        parsedArgs = testToolArgs.trim() ? JSON.parse(testToolArgs) : {};
      } catch (e: any) {
        throw new Error(`Invalid JSON arguments: ${e.message}`);
      }
      const res = await api.callMcpTool(selectedTestTool, parsedArgs, authToken);
      setTestResult({ ok: true, data: res.result || res });
      setStatusBanner({
        type: 'success',
        message: `MCP Tool '${selectedTestTool}' executed successfully.`,
      });
    } catch (err: any) {
      setTestResult({ ok: false, error: err.message || String(err) });
      setStatusBanner({
        type: 'error',
        message: `MCP Tool error: ${err.message || err}`,
      });
    } finally {
      setIsExecutingTest(false);
    }
  };

  const pythonExec = mcpConfig?.server_info?.python_executable || '/path/to/.venv/bin/python3';
  const scriptPath = mcpConfig?.server_info?.script_path || '/path/to/data_model/mcp_server.py';

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-4xl max-h-[90vh] shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/50 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white">
                  Model Context Protocol (MCP) Server
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live &amp; Ready
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Expose canonical data modeling, DDL compilation, and dbt generation directly to your AI coding assistants
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* View Switcher: Setup Guide | Exposed Tools & Resources | Live Tester */}
        <div className="px-6 pt-3 bg-slate-950/30 border-b border-slate-800 flex items-center gap-4 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setActiveView('setup')}
            className={`pb-2.5 flex items-center gap-1.5 border-b-2 transition-all ${
              activeView === 'setup'
                ? 'border-indigo-500 text-indigo-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Server className="w-4 h-4" />
            <span>Assistant Setup &amp; Config</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveView('tools')}
            className={`pb-2.5 flex items-center gap-1.5 border-b-2 transition-all ${
              activeView === 'tools'
                ? 'border-indigo-500 text-indigo-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Wrench className="w-4 h-4" />
            <span>Exposed Capabilities ({toolsList.length} Tools)</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveView('tester')}
            className={`pb-2.5 flex items-center gap-1.5 border-b-2 transition-all ${
              activeView === 'tester'
                ? 'border-indigo-500 text-indigo-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Play className="w-3.5 h-3.5 text-emerald-400" />
            <span>Interactive Tool Console</span>
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5 text-xs text-slate-300">
          {activeView === 'setup' && (
            <div className="space-y-5">
              {/* Client Selector Tabs */}
              <div className="flex flex-wrap gap-2 p-1 bg-slate-950 rounded-xl border border-slate-800">
                {[
                  { id: 'claude_code', label: 'Claude Code', icon: Terminal },
                  { id: 'cursor', label: 'Cursor IDE', icon: Code2 },
                  { id: 'kiro', label: 'Kiro / Kilocode', icon: Cpu },
                  { id: 'gemini', label: 'Gemini CLI / Code', icon: Sparkles },
                  { id: 'claude_desktop', label: 'Claude Desktop', icon: Layers },
                  { id: 'http', label: 'HTTP / JSON-RPC', icon: Server },
                ].map((tab) => {
                  const Icon = tab.icon;
                  const active = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setActiveTab(tab.id as ClientTab)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                        active
                          ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                      }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      <span>{tab.label}</span>
                    </button>
                  );
                })}
              </div>

              {/* 1. Claude Code */}
              {activeTab === 'claude_code' && (
                <div className="space-y-4 animate-in fade-in duration-100">
                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                    <div className="font-semibold text-white flex items-center justify-between">
                      <span>Method 1: One-Line CLI Command (Recommended)</span>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopy(
                            `claude mcp add metaforge "${pythonExec}" "${scriptPath}"`,
                            'claude_cli'
                          )
                        }
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
                      >
                        {copiedKey === 'claude_cli' ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-sky-400" />
                        )}
                        <span>{copiedKey === 'claude_cli' ? 'Copied!' : 'Copy Command'}</span>
                      </button>
                    </div>
                    <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-sky-300 font-mono text-[11px] overflow-x-auto select-all">
                      {`claude mcp add metaforge "${pythonExec}" "${scriptPath}"`}
                    </pre>
                    <p className="text-[11px] text-slate-400">
                      Run this command once in your terminal. Claude Code will automatically connect to MetaForge Studio for all data modeling instructions.
                    </p>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                    <div className="font-semibold text-white flex items-center justify-between">
                      <span>Method 2: Manual Config File (~/.claude/config.json)</span>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopy(
                            JSON.stringify(
                              {
                                mcpServers: {
                                  metaforge: {
                                    command: pythonExec,
                                    args: [scriptPath],
                                  },
                                },
                              },
                              null,
                              2
                            ),
                            'claude_json'
                          )
                        }
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
                      >
                        {copiedKey === 'claude_json' ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-sky-400" />
                        )}
                        <span>{copiedKey === 'claude_json' ? 'Copied!' : 'Copy JSON'}</span>
                      </button>
                    </div>
                    <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-emerald-300 font-mono text-[11px] overflow-x-auto select-all">
                      {JSON.stringify(
                        {
                          mcpServers: {
                            metaforge: {
                              command: pythonExec,
                              args: [scriptPath],
                            },
                          },
                        },
                        null,
                        2
                      )}
                    </pre>
                  </div>
                </div>
              )}

              {/* 2. Cursor IDE */}
              {activeTab === 'cursor' && (
                <div className="space-y-4 animate-in fade-in duration-100">
                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                    <div className="font-semibold text-white flex items-center justify-between">
                      <span>Cursor MCP Configuration (.cursor/mcp.json)</span>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopy(
                            JSON.stringify(
                              {
                                mcpServers: {
                                  metaforge: {
                                    command: pythonExec,
                                    args: [scriptPath],
                                  },
                                },
                              },
                              null,
                              2
                            ),
                            'cursor_json'
                          )
                        }
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
                      >
                        {copiedKey === 'cursor_json' ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-sky-400" />
                        )}
                        <span>{copiedKey === 'cursor_json' ? 'Copied!' : 'Copy JSON'}</span>
                      </button>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Create or edit <code className="text-sky-300">.cursor/mcp.json</code> in your project root, or paste into <strong>Cursor Settings &gt; Features &gt; MCP</strong>:
                    </p>
                    <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-emerald-300 font-mono text-[11px] overflow-x-auto select-all">
                      {JSON.stringify(
                        {
                          mcpServers: {
                            metaforge: {
                              command: pythonExec,
                              args: [scriptPath],
                            },
                          },
                        },
                        null,
                        2
                      )}
                    </pre>
                  </div>
                </div>
              )}

              {/* 3. Kiro / Kilocode */}
              {activeTab === 'kiro' && (
                <div className="space-y-4 animate-in fade-in duration-100">
                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                    <div className="font-semibold text-white flex items-center justify-between">
                      <span>Kiro / Kilocode Configuration (mcp.json)</span>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopy(
                            JSON.stringify(
                              {
                                mcpServers: {
                                  metaforge: {
                                    command: pythonExec,
                                    args: [scriptPath],
                                  },
                                },
                              },
                              null,
                              2
                            ),
                            'kiro_json'
                          )
                        }
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
                      >
                        {copiedKey === 'kiro_json' ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-sky-400" />
                        )}
                        <span>{copiedKey === 'kiro_json' ? 'Copied!' : 'Copy JSON'}</span>
                      </button>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Paste into your workspace <code className="text-sky-300">mcp.json</code> or global Kiro settings:
                    </p>
                    <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-emerald-300 font-mono text-[11px] overflow-x-auto select-all">
                      {JSON.stringify(
                        {
                          mcpServers: {
                            metaforge: {
                              command: pythonExec,
                              args: [scriptPath],
                            },
                          },
                        },
                        null,
                        2
                      )}
                    </pre>
                  </div>
                </div>
              )}

              {/* 4. Gemini CLI / Code Assist */}
              {activeTab === 'gemini' && (
                <div className="space-y-4 animate-in fade-in duration-100">
                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                    <div className="font-semibold text-white flex items-center justify-between">
                      <span>Gemini CLI / Code Assist Config (gemini-mcp.json)</span>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopy(
                            JSON.stringify(
                              {
                                mcpServers: {
                                  metaforge: {
                                    command: pythonExec,
                                    args: [scriptPath],
                                  },
                                },
                              },
                              null,
                              2
                            ),
                            'gemini_json'
                          )
                        }
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
                      >
                        {copiedKey === 'gemini_json' ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-sky-400" />
                        )}
                        <span>{copiedKey === 'gemini_json' ? 'Copied!' : 'Copy JSON'}</span>
                      </button>
                    </div>
                    <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-emerald-300 font-mono text-[11px] overflow-x-auto select-all">
                      {JSON.stringify(
                        {
                          mcpServers: {
                            metaforge: {
                              command: pythonExec,
                              args: [scriptPath],
                            },
                          },
                        },
                        null,
                        2
                      )}
                    </pre>
                  </div>
                </div>
              )}

              {/* 5. Claude Desktop */}
              {activeTab === 'claude_desktop' && (
                <div className="space-y-4 animate-in fade-in duration-100">
                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                    <div className="font-semibold text-white flex items-center justify-between">
                      <span>Claude Desktop Config (claude_desktop_config.json)</span>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopy(
                            JSON.stringify(
                              {
                                mcpServers: {
                                  metaforge: {
                                    command: pythonExec,
                                    args: [scriptPath],
                                  },
                                },
                              },
                              null,
                              2
                            ),
                            'desktop_json'
                          )
                        }
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
                      >
                        {copiedKey === 'desktop_json' ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-sky-400" />
                        )}
                        <span>{copiedKey === 'desktop_json' ? 'Copied!' : 'Copy JSON'}</span>
                      </button>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Located at: <code className="text-sky-300">~/Library/Application Support/Claude/claude_desktop_config.json</code> (Mac)
                    </p>
                    <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-emerald-300 font-mono text-[11px] overflow-x-auto select-all">
                      {JSON.stringify(
                        {
                          mcpServers: {
                            metaforge: {
                              command: pythonExec,
                              args: [scriptPath],
                            },
                          },
                        },
                        null,
                        2
                      )}
                    </pre>
                  </div>
                </div>
              )}

              {/* 6. HTTP / JSON-RPC */}
              {activeTab === 'http' && (
                <div className="space-y-4 animate-in fade-in duration-100">
                  <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 space-y-2">
                    <div className="font-semibold text-white flex items-center justify-between">
                      <span>Live HTTP JSON-RPC 2.0 Endpoint</span>
                      <button
                        type="button"
                        onClick={() =>
                          handleCopy(
                            'http://127.0.0.1:8000/api/mcp/rpc',
                            'http_url'
                          )
                        }
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px]"
                      >
                        {copiedKey === 'http_url' ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-sky-400" />
                        )}
                        <span>{copiedKey === 'http_url' ? 'Copied!' : 'Copy URL'}</span>
                      </button>
                    </div>
                    <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-sky-300 font-mono text-[11px] overflow-x-auto select-all">
                      http://127.0.0.1:8000/api/mcp/rpc
                    </pre>
                    <p className="text-[11px] text-slate-400">
                      Example cURL to call <code className="text-emerald-300">get_model_summary</code>:
                    </p>
                    <pre className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 font-mono text-[10px] overflow-x-auto select-all">
{`curl -X POST http://127.0.0.1:8000/api/mcp/rpc \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_model_summary", "arguments": {}}}'`}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeView === 'tools' && (
            <div className="space-y-4">
              <div className="p-3 rounded-xl bg-indigo-950/30 border border-indigo-500/30 text-indigo-200 text-[11px]">
                <strong>{toolsList.length} MCP Tools Available</strong>: AI assistants connected via MCP have full access to inspect schemas, create and modify tables, wire relationships, compile DDL across dialects, and export dbt models.
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {toolsList.map((tool) => (
                  <div
                    key={tool.name}
                    className="p-3 rounded-xl bg-slate-950 border border-slate-800 hover:border-slate-700 transition-colors space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-xs text-emerald-400">
                        {tool.name}
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-slate-900 text-slate-400 border border-slate-800">
                        tool
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      {tool.description}
                    </p>
                    {tool.inputSchema?.properties && Object.keys(tool.inputSchema.properties).length > 0 && (
                      <div className="text-[10px] text-slate-500 font-mono pt-1">
                        params: {Object.keys(tool.inputSchema.properties).join(', ')}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeView === 'tester' && (
            <div className="space-y-4">
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="font-semibold text-white flex items-center justify-between">
                  <span>Interactive MCP Tool Runner</span>
                  <span className="text-[11px] text-slate-400">Test live server responses</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] text-slate-400 block mb-1">
                      Select MCP Tool:
                    </label>
                    <select
                      value={selectedTestTool}
                      onChange={(e) => {
                        const name = e.target.value;
                        setSelectedTestTool(name);
                        if (name === 'compile_ddl') {
                          setTestToolArgs('{\n  "dialect": "snowflake"\n}');
                        } else if (name === 'get_table_schema') {
                          setTestToolArgs('{\n  "table_name": "DIM_CUSTOMER"\n}');
                        } else if (name === 'search_metadata') {
                          setTestToolArgs('{\n  "query": "customer"\n}');
                        } else if (name === 'add_table') {
                          setTestToolArgs('{\n  "physical_name": "DIM_PROMO",\n  "subject_area": "Marketing"\n}');
                        } else {
                          setTestToolArgs('{}');
                        }
                      }}
                      className="w-full bg-slate-900 text-white font-mono text-xs px-3 py-2 rounded-lg border border-slate-700 outline-none"
                    >
                      {toolsList.map((t) => (
                        <option key={t.name} value={t.name}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-[11px] text-slate-400 block mb-1">
                      JSON Arguments:
                    </label>
                    <textarea
                      rows={3}
                      value={testToolArgs}
                      onChange={(e) => setTestToolArgs(e.target.value)}
                      className="w-full bg-slate-900 text-emerald-300 font-mono text-xs p-2 rounded-lg border border-slate-700 outline-none"
                    />
                  </div>
                </div>

                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={handleRunTestTool}
                    disabled={isExecutingTest}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow disabled:opacity-40 transition-colors"
                  >
                    {isExecutingTest ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Play className="w-3.5 h-3.5" />
                    )}
                    <span>{isExecutingTest ? 'Calling Tool...' : 'Execute Tool'}</span>
                  </button>
                </div>
              </div>

              {testResult && (
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between text-xs font-semibold">
                    <span className="flex items-center gap-1.5">
                      {testResult.ok ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <X className="w-4 h-4 text-rose-400" />
                      )}
                      <span>{testResult.ok ? 'Output Result' : 'Error'}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        handleCopy(
                          JSON.stringify(testResult.data || testResult.error, null, 2),
                          'result_json'
                        )
                      }
                      className="text-[10px] text-sky-400 hover:underline flex items-center gap-1"
                    >
                      <Copy className="w-3 h-3" />
                      <span>{copiedKey === 'result_json' ? 'Copied!' : 'Copy'}</span>
                    </button>
                  </div>
                  <pre className="p-3 rounded-lg bg-slate-900 text-slate-200 font-mono text-[11px] max-h-60 overflow-y-auto">
                    {JSON.stringify(testResult.data || testResult.error, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>Server protocolVersion: 2024-11-05 (JSON-RPC 2.0 stdio &amp; HTTP)</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl text-xs font-medium bg-slate-800 hover:bg-slate-700 text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
