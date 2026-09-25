import React, { useState, useEffect } from 'react';
import { fetchCampaigns, cancelCampaign, type WhatsAppCampaign } from '../api/whatsapp';
import { WhatsAppCampaignDetailView } from './WhatsAppCampaignDetailView';

export const WhatsAppHistoryView: React.FC = () => {
  const [campaigns, setCampaigns] = useState<WhatsAppCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState<WhatsAppCampaign | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchCampaigns();
      setCampaigns(data);
    } catch (err: any) {
      alert("Error loading history: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // Pause the refresh while a campaign is open so the detail screen is not
    // disturbed by background list updates.
    if (selectedCampaign) return;
    const interval = setInterval(loadData, 10000); // Auto refresh
    return () => clearInterval(interval);
  }, [selectedCampaign]);

  const handleCancel = async (id: string) => {
    if (window.confirm("Are you sure you want to cancel this campaign? Pending messages will not be sent.")) {
      try {
        await cancelCampaign(id);
        loadData();
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'COMPLETED': return 'text-emerald-400 border-emerald-800 bg-emerald-950/50';
      case 'RUNNING': return 'text-sky-400 border-sky-800 bg-sky-950/50';
      case 'FAILED': return 'text-rose-400 border-rose-800 bg-rose-950/50';
      case 'PARTIAL': return 'text-amber-400 border-amber-800 bg-amber-950/50';
      case 'CANCELLED': return 'text-slate-400 border-slate-700 bg-slate-800/50';
      default: return 'text-slate-400 border-slate-700 bg-slate-800/50';
    }
  };

  if (selectedCampaign) {
    return (
      <WhatsAppCampaignDetailView
        campaign={selectedCampaign}
        onBack={() => { setSelectedCampaign(null); loadData(); }}
      />
    );
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">Campaign History</h1>
          <p className="text-xs text-slate-400 mt-0.5">View and manage past WhatsApp campaigns</p>
        </div>
        <button
          onClick={loadData}
          className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-mono-code rounded flex items-center gap-1.5 transition-all shadow-sm"
        >
          <span className={`material-symbols-outlined text-[16px] text-slate-400 ${loading ? 'animate-spin' : ''}`}>
            refresh
          </span>
          Refresh
        </button>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-950 border-b border-slate-800">
            <tr>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Campaign Name</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Status</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Total</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Sent</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Failed</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Skipped</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs" title="Recipients who opened the campaign link at least once">Unique Visits</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs" title="Extra opens beyond each recipient's first">Repeated Visits</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Created At</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {campaigns.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-4 py-8 text-center text-slate-500">
                  No campaigns found.
                </td>
              </tr>
            ) : (
              campaigns.map(camp => (
                <tr key={camp.campaign_id} className="hover:bg-slate-800/50 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-200">{camp.name}</td>
                  <td className="px-4 py-3">
                    <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${getStatusColor(camp.status)}`}>
                      {camp.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300 font-mono-code">{camp.total_contacts}</td>
                  <td className="px-4 py-3 text-emerald-400 font-mono-code font-semibold">{camp.successful_count}</td>
                  <td className="px-4 py-3 text-rose-400 font-mono-code">{camp.failed_count}</td>
                  <td className="px-4 py-3 text-slate-400 font-mono-code">{camp.skipped_count}</td>
                  <td className="px-4 py-3 font-mono-code text-sky-400 font-semibold">{camp.unique_visits ?? 0}</td>
                  <td className="px-4 py-3 font-mono-code text-purple-400">{camp.repeated_visits ?? 0}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{new Date(camp.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right">
                    {camp.status === 'RUNNING' || camp.status === 'PENDING' ? (
                      <button
                        onClick={() => handleCancel(camp.campaign_id)}
                        className="text-xs text-rose-400 hover:text-rose-300 font-semibold border border-rose-900/50 px-2 py-1 rounded bg-rose-950/20"
                      >
                        Cancel
                      </button>
                    ) : (
                      <button
                        onClick={() => setSelectedCampaign(camp)}
                        className="text-xs text-sky-400 hover:text-sky-300 font-semibold"
                      >
                        View Details
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
