import React, { useState, useEffect } from 'react';
import { fetchCampaigns, fetchSpend, cancelCampaign,
  type WhatsAppCampaign, type Spend } from '../api/whatsapp';
import { WhatsAppCampaignDetailView } from './WhatsAppCampaignDetailView';

export const WhatsAppHistoryView: React.FC = () => {
  const [campaigns, setCampaigns] = useState<WhatsAppCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState<WhatsAppCampaign | null>(null);
  const [spend, setSpend] = useState<Spend | null>(null);

  /** Amounts are shown whole: paise on a four-figure bill is noise. */
  const money = (n: number) =>
    `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchCampaigns();
      setCampaigns(data);
      // Separately, because a Meta outage should cost the page its spend
      // figure and nothing else.
      try {
        setSpend(await fetchSpend(30));
      } catch {
        setSpend(null);
      }
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

      {spend && spend.billable_messages > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 mb-4 shrink-0">
          <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold">
                This app's campaigns
              </div>
              <div className="text-3xl font-semibold text-slate-100 mt-1 tabular-nums">
                {money(spend.total)}
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                {money(spend.net)} + {money(spend.gst)} GST ·{' '}
                {spend.billable_messages.toLocaleString('en-IN')} messages
              </div>
            </div>

            {spend.by_category.map(c => (
              <div key={c.category}>
                <div className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold">
                  {c.category}
                </div>
                <div className="text-xl font-semibold text-slate-200 mt-1 tabular-nums">
                  {money(c.total)}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {c.billable_messages.toLocaleString('en-IN')} messages
                </div>
              </div>
            ))}

            {/* Meta's figure sits beside ours rather than replacing it: ours
                is the only one that can be split per campaign, and a gap
                between the two is itself worth seeing. */}
            {spend.meta_total !== null && (
              <div
                title={`Everything billed on this WhatsApp number in the last ${spend.meta_days} days, `
                  + 'whoever sent it. The number was in use before this app existed, so any '
                  + 'other tool sending on it lands here too. Nothing older than the window is '
                  + 'included.'}
              >
                <div className="text-[11px] uppercase tracking-wide text-slate-500 font-semibold">
                  Whole number · last {spend.meta_days}d
                </div>
                <div className="text-xl font-semibold text-emerald-400 mt-1 tabular-nums">
                  {money(spend.meta_total)}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  all tools, before GST
                </div>
              </div>
            )}
          </div>

          {spend.estimated_from_sends > 0 && (
            <p className="text-[11px] text-amber-400 mt-3 flex items-start gap-1.5 leading-relaxed">
              <span className="material-symbols-outlined text-[14px] mt-px shrink-0">info</span>
              <span>
                {spend.estimated_from_sends} campaign
                {spend.estimated_from_sends === 1 ? '' : 's'} include sends Meta
                never reported back on — mostly from before delivery reporting
                was switched on. Those are counted as delivered, so the figure
                is an upper bound. Meta's own total is the one to trust.
              </span>
            </p>
          )}
          {spend.meta_error && (
            <p className="text-[11px] text-slate-500 mt-2">
              Meta's own figure is unavailable: {spend.meta_error}
            </p>
          )}
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shrink-0">
        {/* Thirteen columns do not fit most screens. Without this the ones
            past the edge were simply clipped, with no way to reach them. */}
        <div className="overflow-x-auto">
        <table className="w-full text-left text-sm min-w-[1220px]">
          {/* Sticky, so the numbers still have headings once the page is
              scrolled down past them. */}
          <thead className="bg-slate-950 border-b border-slate-800 sticky top-0 z-10">
            <tr>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Campaign Name</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Status</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Total</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Sent</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Failed</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Skipped</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs" title="Reached the handset, as reported by Meta. A dash means Meta has not reported on this campaign.">Delivered</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs" title="Opened the message. Every read message was also delivered.">Read</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs" title="Quick-reply button taps. Meta sends no event for call-to-action URL buttons.">Clicks</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs" title="Recipients who opened the campaign link at least once">Unique Visits</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs" title="Extra opens beyond each recipient's first">Repeated Visits</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs text-right" title="Meta bills per delivered message, at a rate set by the template's category. Includes GST.">Cost</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs">Created At</th>
              <th className="px-4 py-3 font-semibold text-slate-400 text-xs text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {campaigns.length === 0 ? (
              <tr>
                <td colSpan={14} className="px-4 py-8 text-center text-slate-500">
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
                  {/* A dash, not a zero: with no webhook yet, "0 delivered"
                      would read as a failure that never happened. */}
                  <td className="px-4 py-3 font-mono-code text-emerald-400 font-semibold">
                    {camp.has_delivery_data ? camp.delivered_count : <span className="text-slate-600">—</span>}
                  </td>
                  <td className="px-4 py-3 font-mono-code text-sky-400 font-semibold">
                    {camp.has_delivery_data ? camp.read_count : <span className="text-slate-600">—</span>}
                  </td>
                  <td className="px-4 py-3 font-mono-code text-purple-400">{camp.button_click_count ?? 0}</td>
                  <td className="px-4 py-3 font-mono-code text-sky-400 font-semibold"
                    title={camp.automated_hits ? `${camp.automated_hits} automated hit(s) — link previews, scanners or scripts — not counted` : undefined}>
                    {camp.unique_visits ?? 0}
                  </td>
                  <td className="px-4 py-3 font-mono-code text-purple-400">{camp.repeated_visits ?? 0}</td>
                  <td
                    className="px-4 py-3 font-mono-code text-right whitespace-nowrap"
                    title={camp.billable_messages
                      ? `${camp.billable_messages} ${camp.cost_basis} × ₹${camp.rate_per_message}`
                        + ` (${camp.billing_category}) = ₹${camp.cost_net} + ₹${camp.cost_gst} GST`
                        + (camp.cost_basis === 'sent'
                            ? ' — includes sends Meta never reported back on,'
                              + ' counted as delivered. A ceiling, not a measurement.'
                            : '')
                      : 'Nothing billable yet'}
                  >
                    {camp.billable_messages ? (
                      <span className={camp.cost_basis === 'sent' ? 'text-amber-400' : 'text-slate-200'}>
                        {money(camp.cost_total)}
                        {camp.cost_basis === 'sent' && <span className="text-amber-600">*</span>}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
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
    </div>
  );
};
