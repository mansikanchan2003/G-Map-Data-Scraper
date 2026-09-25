import React, { useState, useEffect } from 'react';
import {
  fetchTemplates, createTemplate, updateTemplate, deleteTemplate, uploadMedia,
  syncTemplateStatuses, submitTemplate, type WhatsAppTemplate
} from '../api/whatsapp';
import { WhatsAppPreview } from '../components/WhatsAppPreview';

// Template media is stored as a JSON descriptor; older rows hold a bare URL.
const resolveMediaUrl = (headerContent?: string | null): string | null => {
  if (!headerContent) return null;
  try {
    const data = JSON.parse(headerContent);
    if (data.source_type === 'upload' && data.media_id) {
      return `/api/v1/whatsapp/media/${data.media_id}`;
    }
    if (data.source_type === 'url' && data.url) return data.url;
    return null;
  } catch {
    return headerContent;
  }
};

// Meta's review states are stored verbatim, so they are rendered verbatim too.
const statusStyle = (status?: string | null) => {
  switch ((status || '').toUpperCase()) {
    case 'APPROVED':
      return 'bg-emerald-950/50 text-emerald-400 border-emerald-800';
    case 'PENDING':
    case 'IN_APPEAL':
      return 'bg-amber-950/50 text-amber-400 border-amber-800';
    case 'REJECTED':
    case 'DISABLED':
      return 'bg-rose-950/50 text-rose-400 border-rose-800';
    case 'PAUSED':
      return 'bg-purple-950/50 text-purple-400 border-purple-800';
    default:
      return 'bg-slate-800 text-slate-400 border-slate-700';
  }
};

// Meta's billing categories. A template's category decides how it is priced
// and what content is allowed, so it is worth showing next to the status.
const categoryStyle = (category?: string | null) => {
  switch ((category || '').toUpperCase()) {
    case 'UTILITY':
      return 'bg-sky-950/50 text-sky-400 border-sky-800';
    case 'MARKETING':
      return 'bg-purple-950/50 text-purple-400 border-purple-800';
    case 'MARKETING_LITE':
      return 'bg-amber-950/50 text-amber-400 border-amber-800';
    default:
      return 'bg-slate-800 text-slate-400 border-slate-700';
  }
};

const categoryLabel = (category?: string | null) => {
  const c = (category || '').toUpperCase();
  if (!c) return 'NO CATEGORY';
  return c === 'MARKETING_LITE' ? 'MARKETING LITE' : c;
};

const statusLabel = (t: WhatsAppTemplate) => {
  const s = (t.status || '').toUpperCase();
  // A template Meta has never seen is a local draft, whatever the row says.
  if (!t.meta_template_name) return 'NOT SUBMITTED';
  return s || 'PENDING';
};

export const WhatsAppTemplatesView: React.FC = () => {
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const [isCreating, setIsCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [search, setSearch] = useState('');
  const [saving, setSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [headerSourceType, setHeaderSourceType] = useState<'URL' | 'UPLOAD'>('URL');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewMediaUrl, setPreviewMediaUrl] = useState<string | null>(null);

  const [newTemplate, setNewTemplate] = useState<Partial<WhatsAppTemplate>>({
    name: '',
    header_type: 'NONE',
    header_content: '',
    body: '',
    footer: '',
    buttons: []
  });

  const loadTemplates = async () => {
    setLoading(true);
    try {
      const data = await fetchTemplates();
      setTemplates(data);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Pull the current review state from Meta whenever the page opens, so the
  // badges reflect reality rather than whatever was stored at submit time.
  const handleSync = async (silent = false) => {
    setSyncing(true);
    try {
      const res = await syncTemplateStatuses();
      if (res.status !== 'success' && !silent) {
        alert(res.error || 'Could not reach Meta to sync template statuses');
      }
      await loadTemplates();
    } catch (err: any) {
      if (!silent) alert(err.message);
    } finally {
      setSyncing(false);
    }
  };

  useEffect(() => {
    (async () => {
      await loadTemplates();
      handleSync(true);
    })();
  }, []);

  const startEdit = (t: WhatsAppTemplate) => {
    setEditingId(t.template_id);
    setNewTemplate({
      name: t.name,
      header_type: t.header_type || 'NONE',
      header_content: t.header_content || '',
      body: t.body,
      footer: t.footer || '',
      buttons: t.buttons || [],
    });
    // Existing media stays unless a new file is chosen.
    setHeaderSourceType(t.header_content && t.header_content.includes('"upload"') ? 'UPLOAD' : 'URL');
    setSelectedFile(null);
    setPreviewMediaUrl(resolveMediaUrl(t.header_content));
    setIsCreating(true);
  };

  const resetForm = () => {
    setIsCreating(false);
    setEditingId(null);
    setNewTemplate({ name: '', header_type: 'NONE', header_content: '', body: '', footer: '', buttons: [] });
    setSelectedFile(null);
    setPreviewMediaUrl(null);
    setHeaderSourceType('URL');
  };

  const handleSubmitForReview = async (t: WhatsAppTemplate) => {
    if (!window.confirm(`Submit "${t.name}" to Meta for review?`)) return;
    try {
      const res = await submitTemplate(t.template_id);
      if (res.status !== 'success') {
        alert(res.error || 'Meta rejected the submission');
      }
      await loadTemplates();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleCreate = async () => {
    try {
      if (!newTemplate.name || !newTemplate.body) {
        alert("Name and body are required");
        return;
      }

      let finalHeaderContent = newTemplate.header_content;

      if (newTemplate.header_type !== 'NONE' && headerSourceType === 'UPLOAD' && !(editingId && !selectedFile)) {
        if (!selectedFile) {
          alert("Please select a file to upload");
          return;
        }
        setIsUploading(true);
        try {
          const mediaType = newTemplate.header_type === 'IMAGE' ? 'image' : 'video';
          const res = await uploadMedia(selectedFile, mediaType);
          finalHeaderContent = JSON.stringify({ source_type: 'upload', media_id: res.media_id });
        } finally {
          setIsUploading(false);
        }
      } else if (newTemplate.header_type !== 'NONE') {
        // Fallback to JSON payload for explicitly saving URL type, although raw URL still works for backward compatibility
        finalHeaderContent = JSON.stringify({ source_type: 'url', url: newTemplate.header_content });
      }

      const payload = { ...newTemplate, header_content: finalHeaderContent };

      setSaving(true);
      if (editingId) {
        await updateTemplate(editingId, payload);
      } else {
        // New templates are sent to Meta for review as part of creation.
        const created: any = await createTemplate(payload);
        if (created?.submission_error) {
          alert(
            `Template saved, but Meta did not accept it for review:\n\n` +
            `${created.submission_error}\n\n` +
            `Fix it with Edit, then use "Submit for review".`
          );
        }
      }
      resetForm();
      await loadTemplates();
      handleSync(true);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (window.confirm("Are you sure you want to delete this template?")) {
      try {
        await deleteTemplate(id);
        loadTemplates();
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  const handleAddButton = () => {
    setNewTemplate(prev => ({
      ...prev,
      buttons: [...(prev.buttons || []), { type: 'QUICK_REPLY', text: 'New Button' }]
    }));
  };

  const handleButtonChange = (index: number, field: string, value: string) => {
    const updatedButtons = [...(newTemplate.buttons || [])];
    updatedButtons[index] = { ...updatedButtons[index], [field]: value };
    setNewTemplate(prev => ({ ...prev, buttons: updatedButtons }));
  };

  const handleRemoveButton = (index: number) => {
    const updatedButtons = [...(newTemplate.buttons || [])];
    updatedButtons.splice(index, 1);
    setNewTemplate(prev => ({ ...prev, buttons: updatedButtons }));
  };

  // Match only the display name. The Meta name is fixed at submission and
  // cannot be renamed, so a template renamed from "TestRun1" to
  // "HaryanaCampaign1" still carries meta name "testrun1" -- matching that
  // made the old name keep surfacing in searches the user had moved on from.
  const query = search.trim().toLowerCase();
  const visibleTemplates = query
    ? templates.filter(t => (t.name || '').toLowerCase().includes(query))
    : templates;

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 tracking-tight">Message Templates</h1>
          <p className="text-xs text-slate-400 mt-0.5">Manage your WhatsApp message templates</p>
        </div>
        {!isCreating && (
          <div className="flex items-center gap-2">
          <button
            onClick={() => handleSync()}
            disabled={syncing}
            title="Fetch the latest review status from Meta"
            className="h-8 px-3 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-mono-code font-semibold rounded flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <span className={`material-symbols-outlined text-[16px] ${syncing ? 'animate-spin' : ''}`}>sync</span>
            {syncing ? 'Syncing...' : 'Sync Status'}
          </button>
          <button
            onClick={() => { resetForm(); setIsCreating(true); }}
            className="h-8 px-4 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono-code font-semibold rounded shadow-sm transition-all flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[16px]">add</span>
            Create Template
          </button>
          </div>
        )}
      </div>

      {!isCreating && (
        <div className="mb-4 relative max-w-md">
          <span className="material-symbols-outlined text-[18px] text-slate-500 absolute left-3 top-1/2 -translate-y-1/2">
            search
          </span>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search templates by name..."
            className="w-full bg-slate-900 border border-slate-800 focus:border-emerald-500 rounded pl-10 pr-8 py-2 text-sm text-slate-200 outline-none transition-colors"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              title="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              <span className="material-symbols-outlined text-[16px]">close</span>
            </button>
          )}
        </div>
      )}

      {isCreating ? (
        <div className="flex gap-6 items-start h-full pb-10">
          <div className="flex-1 bg-slate-900 border border-slate-800 rounded-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-100 border-b border-slate-800 pb-2">{editingId ? 'Edit Template' : 'New Template'}</h2>

            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-semibold">Template Name</label>
              <input
                type="text"
                value={newTemplate.name}
                onChange={e => setNewTemplate(prev => ({ ...prev, name: e.target.value }))}
                className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none transition-colors"
                placeholder="e.g., promotional_offer_v1"
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-semibold">Header Type</label>
              <select
                value={newTemplate.header_type || 'NONE'}
                onChange={e => setNewTemplate(prev => ({ ...prev, header_type: e.target.value, header_content: '' }))}
                className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none transition-colors"
              >
                <option value="NONE">None</option>
                <option value="IMAGE">Image</option>
                <option value="VIDEO">Video</option>
              </select>
            </div>

            {newTemplate.header_type !== 'NONE' && (
              <div className="space-y-2">
                <div className="flex items-center gap-4 text-xs font-semibold text-slate-400">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="headerSourceType"
                      value="URL"
                      checked={headerSourceType === 'URL'}
                      onChange={() => setHeaderSourceType('URL')}
                      className="accent-emerald-500"
                    />
                    URL
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="headerSourceType"
                      value="UPLOAD"
                      checked={headerSourceType === 'UPLOAD'}
                      onChange={() => setHeaderSourceType('UPLOAD')}
                      className="accent-emerald-500"
                    />
                    Upload from computer
                  </label>
                </div>

                {headerSourceType === 'URL' ? (
                  <div className="space-y-1">
                    <label className="text-xs text-slate-400 font-semibold">Media URL</label>
                    <input
                      type="text"
                      value={newTemplate.header_content || ''}
                      onChange={e => setNewTemplate(prev => ({ ...prev, header_content: e.target.value }))}
                      className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none transition-colors"
                      placeholder="https://example.com/image.jpg"
                    />
                  </div>
                ) : (
                  <div className="space-y-1">
                    <label className="text-xs text-slate-400 font-semibold flex justify-between">
                      <span>Choose {newTemplate.header_type === 'IMAGE' ? 'Image' : 'Video'} File</span>
                      {selectedFile && <span className="text-emerald-400">{(selectedFile.size / (1024*1024)).toFixed(2)} MB</span>}
                    </label>
                    <input
                      type="file"
                      accept={newTemplate.header_type === 'IMAGE' ? 'image/jpeg, image/png, image/webp' : 'video/mp4'}
                      onChange={e => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setSelectedFile(file);
                          const url = URL.createObjectURL(file);
                          setPreviewMediaUrl(url);
                          // Clear URL content since we use upload
                          setNewTemplate(prev => ({ ...prev, header_content: '' }));
                        } else {
                          setSelectedFile(null);
                          setPreviewMediaUrl(null);
                        }
                      }}
                      className="w-full text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-emerald-950 file:text-emerald-400 hover:file:bg-emerald-900 transition-colors"
                    />
                    {selectedFile && (
                      <div className="text-xs text-slate-500 mt-1">
                        Selected: {selectedFile.name}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-semibold flex justify-between">
                <span>Message Body</span>
                <span className="text-slate-500">Use {'{{name}}'} for business name</span>
              </label>
              <textarea
                value={newTemplate.body}
                onChange={e => setNewTemplate(prev => ({ ...prev, body: e.target.value }))}
                className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none transition-colors h-32"
                placeholder="Hello {{name}}, we have a special offer..."
              />
            </div>

            <div className="space-y-1">
              <label className="text-xs text-slate-400 font-semibold">Footer (Optional)</label>
              <input
                type="text"
                value={newTemplate.footer || ''}
                onChange={e => setNewTemplate(prev => ({ ...prev, footer: e.target.value }))}
                className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none transition-colors"
                placeholder="Reply STOP to unsubscribe"
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label className="text-xs text-slate-400 font-semibold">Buttons (Optional)</label>
                <button
                  onClick={handleAddButton}
                  className="text-[10px] bg-slate-800 hover:bg-slate-700 px-2 py-1 rounded text-emerald-400 font-semibold transition-colors"
                >
                  + Add Button
                </button>
              </div>

              {newTemplate.buttons?.map((btn: any, idx: number) => (
                <div key={idx} className="flex gap-2 items-center bg-slate-950 p-2 rounded border border-slate-800">
                  <select
                    value={btn.type}
                    onChange={e => handleButtonChange(idx, 'type', e.target.value)}
                    className="bg-slate-900 border border-slate-700 rounded text-xs p-1 outline-none w-32 text-slate-200"
                  >
                    <option value="QUICK_REPLY">Quick Reply</option>
                    <option value="URL">Visit Website</option>
                    <option value="PHONE_NUMBER">Call Phone</option>
                  </select>
                  <input
                    type="text"
                    value={btn.text}
                    onChange={e => handleButtonChange(idx, 'text', e.target.value)}
                    className="flex-1 bg-slate-900 border border-slate-700 rounded text-xs p-1.5 outline-none text-slate-200"
                    placeholder="Button Text"
                  />
                  <button onClick={() => handleRemoveButton(idx)} className="text-rose-400 hover:text-rose-300">
                    <span className="material-symbols-outlined text-[16px]">close</span>
                  </button>
                </div>
              ))}
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
              <button
                onClick={resetForm}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={isUploading || saving}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold rounded shadow transition-colors disabled:opacity-50"
              >
                {isUploading ? 'Uploading & Saving...'
                  : saving ? 'Saving...'
                  : editingId ? 'Save Changes'
                  : 'Save & Submit for Review'}
              </button>
            </div>
          </div>

          <div className="w-[340px] shrink-0 sticky top-6">
            <h3 className="text-xs text-center font-semibold text-slate-400 mb-3 tracking-widest uppercase">Live Preview</h3>
            <WhatsAppPreview
              businessName="Demo Business"
              templateBody={newTemplate.body || ''}
              headerType={newTemplate.header_type}
              headerContent={headerSourceType === 'UPLOAD' ? previewMediaUrl : newTemplate.header_content}
              footer={newTemplate.footer}
              buttons={newTemplate.buttons}
            />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {loading ? (
            <div className="text-slate-500 text-sm">Loading templates...</div>
          ) : visibleTemplates.length === 0 ? (
            <div className="col-span-full p-8 border border-slate-800 border-dashed rounded-lg flex flex-col items-center justify-center text-slate-500">
              <span className="material-symbols-outlined text-4xl mb-2">dashboard_customize</span>
              <p>{search ? `No templates match "${search}".` : 'No templates created yet.'}</p>
            </div>
          ) : (
            visibleTemplates.map(t => (
              <div key={t.template_id} className="bg-slate-900 border border-slate-800 rounded-lg p-5 flex flex-col hover:border-slate-700 transition-colors">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <h3 className="font-semibold text-slate-200 truncate">{t.name}</h3>
                    <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold border ${statusStyle(statusLabel(t))}`}>
                        {statusLabel(t)}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold border ${categoryStyle(t.category)}`}
                        title="Meta billing category"
                      >
                        {categoryLabel(t.category)}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {!t.meta_template_name && (
                      <button
                        onClick={() => handleSubmitForReview(t)}
                        title="Submit to Meta for review"
                        className="text-slate-500 hover:text-emerald-400 transition-colors"
                      >
                        <span className="material-symbols-outlined text-[18px]">cloud_upload</span>
                      </button>
                    )}
                    <button
                      onClick={() => startEdit(t)}
                      title="Edit template"
                      className="text-slate-500 hover:text-sky-400 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[18px]">edit</span>
                    </button>
                    <button
                      onClick={() => handleDelete(t.template_id)}
                      title="Delete template"
                      className="text-slate-500 hover:text-rose-400 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[18px]">delete</span>
                    </button>
                  </div>
                </div>
                {/* Header media / text */}
                {t.header_type && t.header_type !== 'NONE' && (
                  <div className="mb-3">
                    <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1.5">
                      Header · {t.header_type}
                    </div>
                    {t.header_type === 'IMAGE' && resolveMediaUrl(t.header_content) && (
                      <img
                        src={resolveMediaUrl(t.header_content) as string}
                        alt="Template header"
                        className="w-full h-36 object-cover rounded border border-slate-800"
                      />
                    )}
                    {t.header_type === 'VIDEO' && resolveMediaUrl(t.header_content) && (
                      <video
                        src={resolveMediaUrl(t.header_content) as string}
                        controls
                        className="w-full h-36 object-cover rounded border border-slate-800 bg-slate-950"
                      />
                    )}
                    {t.header_type === 'TEXT' && t.header_content && (
                      <div className="text-sm font-semibold text-slate-200 bg-slate-950 border border-slate-800 rounded px-3 py-2">
                        {t.header_content}
                      </div>
                    )}
                  </div>
                )}

                {/* Body - shown in full, preserving the template's line breaks */}
                <div className="mb-3">
                  <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1.5">Body</div>
                  <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-950 border border-slate-800 rounded px-3 py-2">
                    {t.body}
                  </div>
                </div>

                {/* Footer */}
                {t.footer && (
                  <div className="mb-3">
                    <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1.5">Footer</div>
                    <div className="text-xs text-slate-500 italic bg-slate-950 border border-slate-800 rounded px-3 py-2">
                      {t.footer}
                    </div>
                  </div>
                )}

                {/* Buttons */}
                {Array.isArray(t.buttons) && t.buttons.length > 0 && (
                  <div className="mb-3">
                    <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1.5">Buttons</div>
                    <div className="flex flex-col gap-1.5">
                      {t.buttons.map((btn: any, idx: number) => (
                        <div
                          key={idx}
                          className="text-xs text-sky-400 bg-slate-950 border border-slate-800 rounded px-3 py-1.5 flex items-center gap-1.5"
                        >
                          <span className="material-symbols-outlined text-[14px]">
                            {btn.type === 'URL' ? 'open_in_new' : btn.type === 'PHONE_NUMBER' ? 'call' : 'reply'}
                          </span>
                          <span className="truncate">{btn.text}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-auto text-xs text-slate-500 border-t border-slate-800 pt-3 flex items-center justify-between gap-2">
                  <span>Created: {new Date(t.created_at).toLocaleDateString()}</span>
                  {t.meta_template_name && (
                    <span className="font-mono-code text-slate-500 truncate">
                      {t.meta_template_name} · {t.language_code}
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
