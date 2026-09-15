import React, { useState, useEffect } from 'react';
import { getApiBaseUrl, setApiBaseUrl, resetApiBaseUrl, checkBackendHealth } from '../api';

interface BackendSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfigChanged: () => void;
}

export const BackendSettingsModal: React.FC<BackendSettingsModalProps> = ({
  isOpen,
  onClose,
  onConfigChanged,
}) => {
  const [apiUrl, setApiUrl] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
    latencyMs?: number;
  } | null>(null);

  useEffect(() => {
    if (isOpen) {
      setApiUrl(getApiBaseUrl());
      setTestResult(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    const previous = getApiBaseUrl();
    setApiBaseUrl(apiUrl);
    try {
      const res = await checkBackendHealth();
      setTestResult({
        success: true,
        message: `FastAPI backend is healthy. Latency: ${res.latencyMs}ms`,
        latencyMs: res.latencyMs,
      });
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.message || 'Connection failed. Verify that your FastAPI server is running.',
      });
      // Revert if ping failed
      setApiBaseUrl(previous);
    } finally {
      setTesting(false);
    }
  };

  const handleSave = () => {
    setApiBaseUrl(apiUrl);
    onConfigChanged();
    onClose();
  };

  const handleReset = () => {
    resetApiBaseUrl();
    setApiUrl(getApiBaseUrl());
    onConfigChanged();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-lg shadow-2xl max-w-lg w-full overflow-hidden text-slate-100">
        {/* Modal Header */}
        <div className="px-5 py-3.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="material-symbols-outlined text-sky-400 text-[22px]">settings_ethernet</span>
            <h2 className="text-base font-semibold text-white tracking-tight">FastAPI Backend Connection</h2>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 p-1 rounded hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-mono-code font-semibold uppercase text-slate-400 mb-1.5">
              API Base URL
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                placeholder="http://127.0.0.1:8000"
                className="flex-1 h-9 px-3 text-xs font-mono-code bg-slate-950 border border-slate-700 rounded text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
              <button
                onClick={handleTest}
                disabled={testing}
                className="h-9 px-3 text-xs font-mono-code bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded font-medium text-slate-200 flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
              >
                {testing ? (
                  <span className="w-3.5 h-3.5 border-2 border-sky-400 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <span className="material-symbols-outlined text-[16px] text-sky-400">network_ping</span>
                )}
                <span>Test Ping</span>
              </button>
            </div>
            <p className="text-[11px] text-slate-400 mt-1.5">
              Configured via <code className="text-sky-400 font-mono-code">VITE_API_BASE_URL</code> or runtime override. Defaults to <code className="text-sky-400 font-mono-code">http://127.0.0.1:8000</code>.
            </p>
          </div>

          {testResult && (
            <div
              className={`p-3 rounded text-xs font-mono-code border flex items-start gap-2 ${
                testResult.success
                  ? 'bg-emerald-950/80 border-emerald-800 text-emerald-300'
                  : 'bg-rose-950/80 border-rose-800 text-rose-300'
              }`}
            >
              <span className="material-symbols-outlined text-[18px] shrink-0 mt-0.5">
                {testResult.success ? 'check_circle' : 'error'}
              </span>
              <div className="flex-1 leading-relaxed">
                <div className="font-semibold">{testResult.success ? 'Connection Healthy' : 'Connection Failed'}</div>
                <div className="text-[11px] mt-0.5">{testResult.message}</div>
              </div>
            </div>
          )}

          <div className="bg-slate-950 border border-slate-800 rounded p-3 text-xs text-slate-400 space-y-1 font-mono-code">
            <div className="font-semibold text-slate-200 flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[16px] text-sky-400">info</span>
              <span>Backend Contract Endpoints:</span>
            </div>
            <div className="text-[11px] space-y-1 pt-1 text-slate-400">
              <div>• Health: <code className="text-sky-400">GET /health</code></div>
              <div>• Stats: <code className="text-sky-400">GET /api/v1/stats</code></div>
              <div>• Businesses: <code className="text-sky-400">GET /api/v1/businesses</code></div>
              <div>• Jobs: <code className="text-sky-400">GET /api/v1/jobs</code></div>
              <div>• Streaming CSV: <code className="text-sky-400">GET /api/v1/export/businesses?format=csv</code></div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          <button
            onClick={handleReset}
            className="text-xs font-mono-code text-slate-400 hover:text-slate-200 underline cursor-pointer"
          >
            Reset to Default
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="h-8 px-3 text-xs font-mono-code bg-slate-800 border border-slate-700 rounded text-slate-300 hover:bg-slate-700 transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="h-8 px-4 text-xs font-mono-code bg-sky-600 hover:bg-sky-500 text-white font-semibold rounded transition-colors shadow-sm cursor-pointer"
            >
              Save & Apply
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
