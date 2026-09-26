import React, { useState, useEffect } from 'react';
import {
  fetchCampaign,
  fetchCampaignLogs,
  fetchCampaignRecipients,
  fetchTemplate,
  type WhatsAppCampaign,
  type WhatsAppCampaignRecipient,
  type WhatsAppTemplate,
  type CampaignLogsResponse,
} from '../api/whatsapp';
import { WhatsAppPreview } from '../components/WhatsAppPreview';

interface Props {
  campaign: WhatsAppCampaign;
  onBack: () => void;
}

const statusChip = (status: string) => {
  switch (status) {
    case 'COMPLETED': return 'text-emerald-400 border-emerald-800 bg-emerald-950/50';
    case 'RUNNING': return 'text-sky-400 border-sky-800 bg-sky-950/50';
    case 'FAILED': return 'text-rose-400 border-rose-800 bg-rose-950/50';
    case 'PARTIAL': return 'text-amber-400 border-amber-800 bg-amber-950/50';
    default: return 'text-slate-400 border-slate-700 bg-slate-800/50';
  }
};

const formatStamp = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString() : '';

const formatDuration = (seconds: number | null) => {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  return `${m}m ${Math.round(seconds % 60)}s`;
};

export const WhatsAppCampaignDetailView: React.FC<Props> = ({ campaign, onBack }) => {
  const [logs, setLogs] = useState<CampaignLogsResponse | null>(null);
  // Re-read rather than trusting the row the list handed over: delivery
  // counts keep moving after a campaign finishes, as webhooks land.
  const [live, setLive] = useState<WhatsAppCampaign>(campaign);
  const [recipients, setRecipients] = useState<WhatsAppCampaignRecipient[]>([]);
  const [template, setTemplate] = useState<WhatsAppTemplate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        // The template may have been deleted since the campaign ran, so it is
        // fetched separately and a failure there must not hide the logs.
        const [logsRes, recipientsRes] = await Promise.all([
          fetchCampaignLogs(campaign.campaign_id),
          fetchCampaignRecipients(campaign.campaign_id, 1, 500),
        ]);
        if (cancelled) return;
        setLogs(logsRes);
        setRecipients(recipientsRes.items);
        setError(null);

        // A stale count here is cosmetic, so a failure must not hide the logs.
        try {
          const fresh = await fetchCampaign(campaign.campaign_id);
          if (!cancelled) setLive(fresh);
        } catch { /* keep the row we were handed */ }

        if (campaign.template_id) {
          try {
            const tmpl = await fetchTemplate(campaign.template_id);
            if (!cancelled) setTemplate(tmpl);
          } catch {
            if (!cancelled) setTemplate(null);
          }
        }
      } catch (err: any) {
        if (!cancelled) setError(err.message || 'Failed to load campaign details');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, [campaign.campaign_id, campaign.template_id]);

  const failedRecipients = recipients.filter(r => r.status === 'FAILED');
  const skippedRecipients = recipients.filter(r => r.status === 'SKIPPED');

  // Group failures by reason so the cause is obvious at a glance rather than
  // having to scan every row.
  const failureReasons = failedRecipients.reduce<Record<string, number>>((acc, r) => {
    const key = r.reason || 'Unknown reason';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  // Campaign-level log rows carry no recipient_id: these are the aborts that
  // stopped the run before any message was attempted.
  const campaignLevelErrors = (logs?.items || []).filter(i => !i.recipient_id && i.status === 'ERROR');

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 overflow-y-auto">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900 shrink-0 flex items-center gap-4">
        <button
          onClick={onBack}
          className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold rounded flex items-center gap-1.5 transition-colors"
        >
          <span className="material-symbols-outlined text-[16px]">arrow_back</span>
          Back
        </button>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight truncate">{campaign.name}</h1>
          <p className="text-xs text-slate-400 mt-0.5 font-mono-code">{campaign.campaign_id}</p>
        </div>
        <span className={`ml-auto text-[10px] uppercase font-bold px-2.5 py-1 rounded border ${statusChip(campaign.status)}`}>
          {campaign.status}
        </span>
      </div>

      <div className="flex-1 p-6 space-y-6">
        {loading && <div className="text-slate-500 text-sm">Loading campaign details...</div>}

        {error && (
          <div className="bg-rose-950/30 border border-rose-900 rounded-lg p-4 text-rose-300 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && logs && (
          <>
            {/* Summary counters */}
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              {[
                { label: 'Total', value: logs.total_contacts, cls: 'text-slate-200' },
                { label: 'Sent', value: logs.successful_count, cls: 'text-emerald-400' },
                { label: 'Failed', value: logs.failed_count, cls: 'text-rose-400' },
                { label: 'Skipped', value: logs.skipped_count, cls: 'text-amber-400' },
              ].map(c => (
                <div key={c.label} className="bg-slate-900 border border-slate-800 rounded-lg py-3 text-center">
                  <div className={`text-2xl font-bold ${c.cls}`}>{c.value}</div>
                  <div className="text-[10px] uppercase text-slate-500 tracking-wider">{c.label}</div>
                </div>
              ))}
              <div className="bg-slate-900 border border-slate-800 rounded-lg py-3 text-center">
                <div className="text-lg font-bold text-slate-300">{formatDuration(logs.duration_seconds)}</div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider">Duration</div>
              </div>
              <div className="bg-slate-900 border border-slate-800 rounded-lg py-3 text-center">
                <div className="text-lg font-bold text-slate-300">
                  {logs.total_contacts > 0
                    ? `${Math.round((logs.successful_count / logs.total_contacts) * 100)}%`
                    : '—'}
                </div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider">Success Rate</div>
              </div>
            </div>

            {/* What happened after the send.
                "Sent" above means Meta accepted the message; everything here
                is Meta reporting back what the handset did with it. */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-slate-200">Delivery &amp; Engagement</h3>
                {!live.has_delivery_data && (
                  <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded border
                                   text-amber-400 border-amber-800 bg-amber-950/50">
                    Awaiting webhook
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 divide-x divide-slate-800 border-b border-slate-800">
                {[
                  { label: 'Delivered', value: live.delivered_count, cls: 'text-emerald-400',
                    hint: 'Reached the handset' },
                  { label: 'Read', value: live.read_count, cls: 'text-sky-400',
                    hint: 'Blue ticks' },
                  { label: 'Not delivered', value: live.undelivered_count, cls: 'text-rose-400',
                    hint: 'Meta reported a failure' },
                  { label: 'Button clicks', value: live.button_click_count, cls: 'text-purple-300',
                    hint: `${live.button_clickers} recipient${live.button_clickers === 1 ? '' : 's'}` },
                  { label: 'Link visits', value: live.unique_visits, cls: 'text-amber-300',
                    hint: `${live.repeated_visits} repeat` },
                ].map(c => (
                  <div key={c.label} className="py-3 px-4 text-center">
                    <div className={`text-2xl font-bold ${c.cls}`}>{c.value}</div>
                    <div className="text-[10px] uppercase text-slate-500 tracking-wider">{c.label}</div>
                    <div className="text-[10px] text-slate-600 mt-0.5">{c.hint}</div>
                  </div>
                ))}
              </div>

              <p className="px-5 py-2.5 text-[11px] text-slate-500 leading-relaxed">
                {live.has_delivery_data
                  ? 'Delivered and read accumulate — every message that was read was also delivered. A sent message with no report yet counts as neither delivered nor failed.'
                  : 'Meta has not reported on this campaign. Delivery, read and button data only arrive once the webhook is reachable at a public URL and subscribed in the Meta app; Meta does not replay events for messages already sent.'}
                {' '}Button clicks count quick-reply taps only — Meta sends no event when a
                call-to-action URL button is tapped, so those are measured by the tracking link instead.
              </p>
            </div>

            {/* Timing */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1">Started</div>
                <div className="text-slate-300">{logs.started_at ? new Date(logs.started_at).toLocaleString() : '—'}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1">Completed</div>
                <div className="text-slate-300">{logs.completed_at ? new Date(logs.completed_at).toLocaleString() : '—'}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1">Created</div>
                <div className="text-slate-300">{new Date(campaign.created_at).toLocaleString()}</div>
              </div>
            </div>

            {/* Campaign-level failure - why nothing was sent at all */}
            {campaignLevelErrors.length > 0 && (
              <div className="bg-rose-950/20 border border-rose-900/60 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-rose-300 mb-2 flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px]">error</span>
                  Campaign stopped before sending
                </h3>
                {campaignLevelErrors.map(e => (
                  <div key={e.log_id} className="text-sm text-rose-200/90 leading-relaxed">
                    {e.error_reason}
                    {e.provider_code && (
                      <span className="ml-2 text-[10px] font-mono-code bg-rose-900/40 border border-rose-800 px-1.5 py-0.5 rounded">
                        code {e.provider_code}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Failure reasons rollup */}
            {Object.keys(failureReasons).length > 0 && (
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                <h3 className="text-sm font-semibold text-slate-200 mb-3">Why messages failed</h3>
                <div className="space-y-2">
                  {Object.entries(failureReasons)
                    .sort((a, b) => b[1] - a[1])
                    .map(([reason, count]) => (
                      <div key={reason} className="flex items-start gap-3 bg-slate-950 border border-slate-800 rounded px-3 py-2">
                        <span className="text-rose-400 font-bold text-sm shrink-0">{count}×</span>
                        <span className="text-sm text-slate-300 leading-relaxed">{reason}</span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-6 items-start">
              {/* Template used */}
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                <h3 className="text-sm font-semibold text-slate-200 mb-4">Template Sent</h3>
                {template ? (
                  <>
                    <div className="mb-4 text-xs space-y-1">
                      <div className="text-slate-300 font-semibold">{template.name}</div>
                      {template.meta_template_name && (
                        <div className="text-slate-500 font-mono-code">
                          Meta: {template.meta_template_name} ({template.language_code})
                        </div>
                      )}
                    </div>
                    <WhatsAppPreview
                      businessName="Sample Business"
                      templateBody={template.body}
                      headerType={template.header_type}
                      headerContent={template.header_content}
                      footer={template.footer}
                      buttons={template.buttons}
                    />
                  </>
                ) : (
                  <div className="text-sm text-slate-500">
                    Template is no longer available (it may have been deleted).
                  </div>
                )}
              </div>

              {/* Recipients */}
              <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-200">
                    Recipients ({recipients.length})
                  </h3>
                  <div className="text-xs text-slate-500">
                    {failedRecipients.length} failed · {skippedRecipients.length} skipped
                  </div>
                </div>
                <div className="max-h-[520px] overflow-y-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-950 border-b border-slate-800 sticky top-0">
                      <tr>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Phone</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Name</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Status</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Delivered</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Read</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Clicked</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Detail</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {recipients.length === 0 ? (
                        <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">No recipients.</td></tr>
                      ) : (
                        recipients.map(r => (
                          <tr key={r.recipient_id} className="hover:bg-slate-800/40 transition-colors">
                            <td className="px-4 py-2 font-mono-code text-slate-300 whitespace-nowrap">{r.phone}</td>
                            <td className="px-4 py-2 text-slate-400 max-w-[160px] truncate">{r.name || '—'}</td>
                            <td className="px-4 py-2">
                              <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${
                                r.status === 'SENT' ? 'text-emerald-400 border-emerald-800 bg-emerald-950/50'
                                : r.status === 'FAILED' ? 'text-rose-400 border-rose-800 bg-rose-950/50'
                                : r.status === 'SKIPPED' ? 'text-amber-400 border-amber-800 bg-amber-950/50'
                                : 'text-slate-400 border-slate-700 bg-slate-800/50'
                              }`}>
                                {r.status}
                              </span>
                            </td>
                            {/* A blank cell here means no report has arrived,
                                which is not the same as "not delivered" — the
                                failure case is the dash under a FAILED row. */}
                            <td className="px-4 py-2 text-xs whitespace-nowrap">
                              {r.delivered_at
                                ? <span className="text-emerald-400" title={formatStamp(r.delivered_at)}>
                                    <span className="material-symbols-outlined text-[15px] align-middle">done_all</span>
                                  </span>
                                : <span className="text-slate-700">—</span>}
                            </td>
                            <td className="px-4 py-2 text-xs whitespace-nowrap">
                              {r.read_at
                                ? <span className="text-sky-400" title={formatStamp(r.read_at)}>
                                    <span className="material-symbols-outlined text-[15px] align-middle">done_all</span>
                                  </span>
                                : <span className="text-slate-700">—</span>}
                            </td>
                            <td className="px-4 py-2 text-xs whitespace-nowrap">
                              {r.button_clicks > 0 || r.link_clicks > 0 ? (
                                <span className="flex items-center gap-1.5">
                                  {r.button_clicks > 0 && (
                                    <span
                                      className="text-[10px] font-bold px-1.5 py-0.5 rounded border
                                                 text-purple-300 border-purple-800 bg-purple-950/50"
                                      title={r.last_button_text || 'Quick-reply button'}
                                    >
                                      {r.last_button_text || `${r.button_clicks}x`}
                                    </span>
                                  )}
                                  {r.link_clicks > 0 && (
                                    <span
                                      className="text-[10px] font-bold px-1.5 py-0.5 rounded border
                                                 text-amber-300 border-amber-800 bg-amber-950/50"
                                      title="Visits to this recipient's tracking link"
                                    >
                                      link {r.link_clicks}
                                    </span>
                                  )}
                                </span>
                              ) : <span className="text-slate-700">—</span>}
                            </td>
                            <td className="px-4 py-2 text-xs text-slate-400 max-w-[320px]">
                              {r.reason
                                ? <span className="text-rose-300/90">{r.reason}</span>
                                : r.provider_message_id
                                  ? <span className="font-mono-code text-slate-500 truncate block">{r.provider_message_id}</span>
                                  : '—'}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Raw execution log */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
              <div className="px-5 py-3 border-b border-slate-800">
                <h3 className="text-sm font-semibold text-slate-200">Execution Log ({logs.items.length})</h3>
              </div>
              <div className="max-h-[360px] overflow-y-auto">
                {logs.items.length === 0 ? (
                  <div className="px-5 py-8 text-center text-slate-500 text-sm">No log entries recorded.</div>
                ) : (
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-950 border-b border-slate-800 sticky top-0">
                      <tr>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Time</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Result</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">HTTP</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Code</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Took</th>
                        <th className="px-4 py-2 font-semibold text-slate-400 text-xs">Message</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {logs.items.map(item => (
                        <tr key={item.log_id} className="hover:bg-slate-800/40 transition-colors">
                          <td className="px-4 py-2 text-xs text-slate-500 whitespace-nowrap">
                            {new Date(item.created_at).toLocaleTimeString()}
                          </td>
                          <td className="px-4 py-2">
                            <span className={item.status === 'SUCCESS' ? 'text-emerald-400' : 'text-rose-400'}>
                              {item.status === 'SUCCESS' ? '✓' : '✗'} {item.status}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-xs font-mono-code text-slate-400">{item.provider_status || '—'}</td>
                          <td className="px-4 py-2 text-xs font-mono-code text-slate-400">{item.provider_code || '—'}</td>
                          <td className="px-4 py-2 text-xs font-mono-code text-slate-500">
                            {item.duration_ms !== null ? `${item.duration_ms}ms` : '—'}
                          </td>
                          <td className="px-4 py-2 text-xs text-slate-400 max-w-[420px]">
                            {item.error_reason || <span className="text-slate-500">—</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
