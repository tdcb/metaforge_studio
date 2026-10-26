import React, { useState, useEffect } from 'react';
import {
  Bot,
  Terminal,
  Sparkles,
  Send,
  X,
  CheckCircle2,
  Cpu,
  Key,
  Eye,
  EyeOff,
  Settings2,
  Wand2,
  PlusCircle,
  Link2,
} from 'lucide-react';
import { useModelStore } from '../../store/useModelStore';
import { api } from '../../services/api';
import { callGeminiDirect } from '../../services/geminiClient';
import type { AgentExecutionResponse } from '../../types/metamodel';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  modeUsed?: string;
  mutated?: boolean;
  actionsTaken?: string[];
  cliCommand?: string;
}

const GEMINI_MODELS = [
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', badge: 'Recommended · Ultra Fast' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', badge: 'Deep Reasoning' },
  { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', badge: 'Fast Multimodal' },
  { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash', badge: 'High Speed' },
  { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', badge: '2M Context' },
];

const QUICK_PROMPT_CHIPS = [
  {
    label: '+ Table DIM_SUPPLIER',
    prompt:
      'Create table DIM_SUPPLIER with columns SUPPLIER_ID number pk, SUPPLIER_NAME varchar not null, COUNTRY_CD varchar, CONTACT_EMAIL varchar, IS_ACTIVE boolean',
    category: 'Table',
  },
  {
    label: '+ View VW_HIGH_CLAIMS',
    prompt:
      'Create view VW_HIGH_VALUE_CLAIMS as SELECT c.CLM_TXN_ID, c.CLM_LOSS_AMT, c.CLM_PAID_AMT, p.PLCY_NBR, cust.CUST_FULL_NM FROM FCT_CLAIM_TRANSACTION c INNER JOIN DIM_INSURANCE_POLICY p ON c.PLCY_ID = p.PLCY_ID INNER JOIN DIM_CUSTOMER cust ON c.CUST_ID = cust.CUST_ID WHERE c.CLM_PAID_AMT > 25000',
    category: 'View',
  },
  {
    label: 'Connect Tables',
    prompt:
      'Connect relationship between DIM_CUSTOMER and FCT_CLAIM_TRANSACTION with non-identifying one-to-many cardinality.',
    category: 'Relation',
  },
  {
    label: '+ Column to Customer',
    prompt: 'Add column MOBILE_PHONE_NBR varchar to DIM_CUSTOMER with classification RESTRICTED_PII',
    category: 'Table',
  },
  {
    label: '+ Area Logistics',
    prompt: 'Add subject area Logistics & Fleet Operations',
    category: 'Model',
  },
  {
    label: 'PII Impact Audit',
    prompt: 'Which tables contain Restricted PII?',
    category: 'Q&A',
  },
  {
    label: 'FCT_CLAIM Lineage',
    prompt: 'Show me the upstream and downstream lineage of FCT_CLAIM_TRANSACTION',
    category: 'Q&A',
  },
  {
    label: 'Scaffold Star Schema',
    prompt:
      'Create a Star Schema for Retail Orders with 1 Fact table and 3 Dimension tables (DIM_CUSTOMER, DIM_PRODUCT, DIM_DATE) and wire the non-identifying foreign keys.',
    category: 'Refactor',
  },
  {
    label: '+ Audit Columns',
    prompt:
      'Add standard enterprise audit columns (REC_CRTD_TS, REC_UPDT_TS, SRC_SYS_CD) to all tables in the Claims subject area.',
    category: 'Refactor',
  },
  {
    label: 'Apply NSM Glossary',
    prompt: 'Apply the Enterprise Naming Glossary to standardize all physical table and column names.',
    category: 'Refactor',
  },
];

export const AgentSidebar: React.FC = () => {
  const isAgentSidebarOpen = useModelStore((s) => s.isAgentSidebarOpen);
  const project = useModelStore((s) => s.project);
  const authToken = useModelStore((s) => s.authToken);
  const setAgentSidebarOpen = useModelStore((s) => s.setAgentSidebarOpen);
  const setProject = useModelStore((s) => s.setProject);
  const currentUser = useModelStore((s) => s.currentUser);
  const setApiKeyModalOpen = useModelStore((s) => s.setApiKeyModalOpen);
  const setMcpModalOpen = useModelStore((s) => s.setMcpModalOpen);
  const refreshCompiledCode = useModelStore((s) => s.refreshCompiledCode);
  const setStatusBanner = useModelStore((s) => s.setStatusBanner);

  const [agentMode, setAgentMode] = useState<'gemini' | 'builtin-llm' | 'kilo-cli'>('gemini');
  const [geminiApiKey, setGeminiApiKey] = useState(() => {
    return (
      localStorage.getItem(`metaforge_gemini_key_${currentUser.email}`) ||
      localStorage.getItem('metaforge_gemini_api_key') ||
      ''
    );
  });
  const [geminiModel, setGeminiModel] = useState(() => {
    return (
      localStorage.getItem(`metaforge_gemini_model_${currentUser.email}`) ||
      localStorage.getItem('metaforge_gemini_model') ||
      'gemini-2.5-flash'
    );
  });
  const [showApiKey, setShowApiKey] = useState(false);
  const [showConfig, setShowConfig] = useState(false);

  const [inputPrompt, setInputPrompt] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'msg-welcome',
      role: 'assistant',
      content:
        '### MetaForge AI Agentic Control Plane\n\nI can **inspect, question, and modify** your canonical data model:\n- **Add / Modify Models & Subject Areas**\n- **Add / Modify Tables & Columns** (PKs, FKs, types, PII tags)\n- **Add / Modify Relationships** (cardinalities, identifying/non-identifying)\n- **Add / Modify Views & SQL Lineage**\n\nChoose **Google Gemini** or the **Built-in Architect**, or pick a quick action below.',
      modeUsed: 'Google Gemini (gemini-2.5-flash)',
    },
  ]);

  // Sync when currentUser changes
  useEffect(() => {
    const userKey =
      localStorage.getItem(`metaforge_gemini_key_${currentUser.email}`) ||
      localStorage.getItem('metaforge_gemini_api_key') ||
      '';
    const userModel =
      localStorage.getItem(`metaforge_gemini_model_${currentUser.email}`) ||
      localStorage.getItem('metaforge_gemini_model') ||
      'gemini-2.5-flash';
    setGeminiApiKey(userKey);
    setGeminiModel(userModel);
  }, [currentUser.email]);

  useEffect(() => {
    if (geminiApiKey) {
      localStorage.setItem(`metaforge_gemini_key_${currentUser.email}`, geminiApiKey);
      localStorage.setItem('metaforge_gemini_api_key', geminiApiKey);
    }
  }, [geminiApiKey, currentUser.email]);

  useEffect(() => {
    localStorage.setItem(`metaforge_gemini_model_${currentUser.email}`, geminiModel);
    localStorage.setItem('metaforge_gemini_model', geminiModel);
  }, [geminiModel, currentUser.email]);

  if (!isAgentSidebarOpen) return null;

  const runPrompt = async (promptText: string) => {
    const trimmed = promptText.trim();
    if (!trimmed || isExecuting) return;

    const effectiveKey =
      geminiApiKey.trim() ||
      localStorage.getItem(`metaforge_gemini_key_${currentUser.email}`) ||
      localStorage.getItem('metaforge_gemini_api_key') ||
      '';

    if (agentMode === 'gemini' && !effectiveKey) {
      setApiKeyModalOpen(true);
      setStatusBanner({
        type: 'error',
        message: 'Please set your Google Gemini API Key in User Settings.',
      });
      return;
    }

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputPrompt('');
    setIsExecuting(true);

    try {
      let res: AgentExecutionResponse;

      if (agentMode === 'gemini' && geminiApiKey.trim()) {
        try {
          // 1. First attempt: Direct browser-to-Gemini REST API (not blocked by backend sandbox)
          const directGemini = await callGeminiDirect(
            project,
            trimmed,
            geminiApiKey,
            geminiModel
          );
          // Apply structured mutations on backend metamodel & commit revision
          res = await api.applyAgentMutations(
            directGemini.mutations,
            trimmed,
            directGemini.reply,
            `Google Gemini (${geminiModel})`,
            project,
            authToken
          );
        } catch (directErr) {
          console.warn('Browser direct Gemini attempt fallback to backend:', directErr);
          // 2. Fall back to backend agent execution
          res = await api.executeAgent(
            trimmed,
            agentMode,
            project,
            geminiApiKey,
            geminiModel,
            authToken
          );
        }
      } else {
        res = await api.executeAgent(
          trimmed,
          agentMode,
          project,
          geminiApiKey,
          geminiModel,
          authToken
        );
      }

      if (res.mutated && res.updated_model) {
        setProject(res.updated_model, true);
        await refreshCompiledCode();
        setStatusBanner({
          type: 'success',
          message: `Model mutated successfully (${res.actions_taken.join(' · ')})`,
        });
      }

      const assistantMsg: ChatMessage = {
        id: `asst-${Date.now()}`,
        role: 'assistant',
        content: res.reply,
        modeUsed: res.mode_used,
        mutated: res.mutated,
        actionsTaken: res.actions_taken,
        cliCommand: res.cli_trace?.command as string | undefined,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Agent execution error';
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `**Execution Error:**\n${msg}`,
        },
      ]);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <aside className="w-96 bg-slate-900 border-l border-slate-800 flex flex-col shrink-0 z-10">
      {/* Header */}
      <div className="p-3.5 border-b border-slate-800 bg-slate-950/70 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-violet-400" />
            <span className="text-xs font-bold text-white">AI Agentic Control Plane</span>
            <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-violet-950 border border-violet-800 text-violet-300">
              Gemini + MCP
            </span>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setApiKeyModalOpen(true)}
              title="Configure Personal Gemini API Key & Model"
              className="p-1 rounded text-sky-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <Key className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setMcpModalOpen(true)}
              title="MCP Capabilities & External Coding Assistants (Claude Code, Cursor, Kiro, Gemini)"
              className="p-1 rounded text-indigo-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <Terminal className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setShowConfig(!showConfig)}
              title="Toggle Gemini API & Model Configuration Drawer"
              className={`p-1 rounded text-slate-400 hover:text-white transition-colors ${
                showConfig ? 'bg-violet-900/60 text-violet-300' : 'hover:bg-slate-800'
              }`}
            >
              <Settings2 className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setAgentSidebarOpen(false)}
              className="text-slate-400 hover:text-white p-1 hover:bg-slate-800 rounded"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* 3-Way Engine Mode Toggle: Gemini | Built-in | Kilo-CLI */}
        <div className="grid grid-cols-3 gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            type="button"
            onClick={() => setAgentMode('gemini')}
            className={`flex items-center justify-center gap-1 py-1 rounded text-[11px] font-semibold transition-all ${
              agentMode === 'gemini'
                ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Sparkles className="w-3 h-3 text-sky-300" />
            <span>Gemini AI</span>
          </button>
          <button
            type="button"
            onClick={() => setAgentMode('builtin-llm')}
            className={`flex items-center justify-center gap-1 py-1 rounded text-[11px] font-semibold transition-all ${
              agentMode === 'builtin-llm'
                ? 'bg-violet-600 text-white shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Cpu className="w-3 h-3 text-violet-300" />
            <span>Built-in</span>
          </button>
          <button
            type="button"
            onClick={() => setAgentMode('kilo-cli')}
            className={`flex items-center justify-center gap-1 py-1 rounded text-[11px] font-semibold transition-all ${
              agentMode === 'kilo-cli'
                ? 'bg-slate-800 text-white shadow border border-slate-700'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Terminal className="w-3 h-3 text-emerald-400" />
            <span>CLI Agent</span>
          </button>
        </div>

        {/* Google Gemini API & Model Configuration Drawer */}
        {(showConfig || (agentMode === 'gemini' && !geminiApiKey)) && (
          <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 space-y-2 text-xs">
            <div className="flex items-center justify-between text-[11px] font-semibold text-slate-300">
              <span className="flex items-center gap-1 text-sky-400">
                <Key className="w-3.5 h-3.5" />
                Google Gemini API Settings
              </span>
              <span className="text-[10px] text-slate-500 font-normal">Stored locally in browser</span>
            </div>

            {/* Model Selector */}
            <div className="space-y-1">
              <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">
                Gemini Model:
              </label>
              <select
                value={geminiModel}
                onChange={(e) => setGeminiModel(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100 outline-none focus:border-blue-500"
              >
                {GEMINI_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} — {m.badge}
                  </option>
                ))}
              </select>
            </div>

            {/* API Key Input */}
            <div className="space-y-1">
              <label className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold flex items-center justify-between">
                <span>API Key:</span>
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="text-slate-400 hover:text-slate-200 flex items-center gap-0.5 text-[9px]"
                >
                  {showApiKey ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                  {showApiKey ? 'Hide' : 'Show'}
                </button>
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={geminiApiKey}
                  onChange={(e) => setGeminiApiKey(e.target.value)}
                  placeholder="Paste your Gemini API key..."
                  className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 pr-7 text-xs text-slate-100 outline-none focus:border-blue-500 font-mono"
                />
              </div>
              <p className="text-[10px] text-slate-500">
                Get an API key from{' '}
                <a
                  href="https://aistudio.google.com/app/apikey"
                  target="_blank"
                  rel="noreferrer"
                  className="text-sky-400 hover:underline"
                >
                  Google AI Studio
                </a>
                .
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Quick Prompt Chips */}
      <div className="p-2 border-b border-slate-800 bg-slate-950/40">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1.5 px-1 flex items-center justify-between">
          <span>AI Instructions & Governance</span>
          <span className="text-[9px] text-slate-600">Click to execute</span>
        </div>
        <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
          {QUICK_PROMPT_CHIPS.map((chip, i) => (
            <button
              key={i}
              type="button"
              disabled={isExecuting}
              onClick={() => runPrompt(chip.prompt)}
              className="px-2 py-1 rounded-md text-[10px] font-medium bg-slate-800/80 hover:bg-slate-700 text-slate-300 border border-slate-700/60 whitespace-nowrap shrink-0 transition-colors flex items-center gap-1 disabled:opacity-50"
            >
              <span className="text-violet-400">✦</span>
              <span>{chip.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 min-h-0 overflow-y-auto p-3.5 space-y-3.5">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[90%] rounded-xl p-3 text-xs leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white shadow-md'
                  : 'bg-slate-800/90 text-slate-200 border border-slate-700/80 shadow-md'
              }`}
            >
              {/* Mode & Mutation Badge */}
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-1.5 mb-2 pb-1.5 border-b border-slate-700/50 text-[10px] text-slate-400">
                  <Bot className="w-3 h-3 text-violet-400" />
                  <span className="font-semibold text-violet-300">{msg.modeUsed || 'Agent'}</span>
                  {msg.mutated && (
                    <span className="px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[9px] font-bold">
                      Mutated Model
                    </span>
                  )}
                </div>
              )}

              {/* Message Content */}
              <div className="prose prose-invert prose-xs max-w-none whitespace-pre-wrap font-sans">
                {msg.content}
              </div>

              {/* Actions Taken Audit Pill */}
              {msg.actionsTaken && msg.actionsTaken.length > 0 && (
                <div className="mt-2.5 pt-2 border-t border-slate-700/50 space-y-1">
                  <div className="text-[10px] font-semibold text-slate-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    <span>Actions Performed:</span>
                  </div>
                  <ul className="text-[10px] text-slate-300 space-y-0.5 list-disc list-inside">
                    {msg.actionsTaken.map((act, i) => (
                      <li key={i} className="text-slate-300">
                        {act}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* CLI Command Trace */}
              {msg.cliCommand && (
                <div className="mt-2 text-[10px] font-mono text-emerald-400 bg-slate-950 p-1.5 rounded border border-slate-800 truncate">
                  $ {msg.cliCommand}
                </div>
              )}
            </div>
          </div>
        ))}

        {isExecuting && (
          <div className="flex items-center gap-2 p-3 rounded-xl bg-slate-800/60 border border-slate-700 text-xs text-slate-400">
            <div className="w-2 h-2 rounded-full bg-violet-400 animate-ping" />
            <span>
              {agentMode === 'gemini'
                ? `Reasoning with ${geminiModel}…`
                : agentMode === 'kilo-cli'
                ? 'Running CLI agent against canonical_model.json…'
                : 'Processing natural-language instruction…'}
            </span>
          </div>
        )}
      </div>

      {/* Input Prompt Box */}
      <div className="p-3 border-t border-slate-800 bg-slate-950/80">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            runPrompt(inputPrompt);
          }}
          className="flex items-end gap-2"
        >
          <div className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 focus-within:border-violet-500 focus-within:ring-1 focus-within:ring-violet-500 transition-all">
            <textarea
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  runPrompt(inputPrompt);
                }
              }}
              rows={2}
              placeholder={
                agentMode === 'gemini'
                  ? 'Ask Gemini to add/modify tables, views, relations, or answer questions…'
                  : 'Enter instruction (e.g., "Add table DIM_SUPPLIER", "Create view VW_CLAIMS")…'
              }
              className="w-full bg-transparent resize-none outline-none text-xs text-slate-100 placeholder:text-slate-500"
            />
          </div>
          <button
            type="submit"
            disabled={!inputPrompt.trim() || isExecuting}
            className="p-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-30 disabled:pointer-events-none text-white transition-all shrink-0 shadow-lg shadow-violet-600/20"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </aside>
  );
};

export default AgentSidebar;
