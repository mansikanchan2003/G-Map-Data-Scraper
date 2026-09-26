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

// Meta keys a template by name + language, and the pair is fixed once the
// template is approved. Picking the wrong one is therefore not a label you can
// correct later — it is a template you have to replace.
const LANGUAGES: { code: string; label: string }[] = [
  { code: 'hi', label: 'Hindi' },
  { code: 'pa', label: 'Punjabi' },
  { code: 'en_US', label: 'English (US)' },
  { code: 'en_GB', label: 'English (UK)' },
  { code: 'en', label: 'English' },
  { code: 'mr', label: 'Marathi' },
  { code: 'gu', label: 'Gujarati' },
  { code: 'bn', label: 'Bengali' },
  { code: 'ta', label: 'Tamil' },
  { code: 'te', label: 'Telugu' },
  { code: 'kn', label: 'Kannada' },
  { code: 'ml', label: 'Malayalam' },
  { code: 'ur', label: 'Urdu' },
];

const languageLabel = (code?: string | null) =>
  LANGUAGES.find(l => l.code === code)?.label || code || '\u2014';

// Scripts are not languages, but a body written in Devanagari is certainly not
// English — which is the mistake worth catching before submission, because
// after approval the language can no longer be changed.
const SCRIPTS: { name: string; test: RegExp; languages: string[] }[] = [
  { name: 'Devanagari', test: /[\u0900-\u097F]/, languages: ['hi', 'mr'] },
  { name: 'Gurmukhi', test: /[\u0A00-\u0A7F]/, languages: ['pa'] },
  { name: 'Gujarati', test: /[\u0A80-\u0AFF]/, languages: ['gu'] },
  { name: 'Bengali', test: /[\u0980-\u09FF]/, languages: ['bn'] },
  { name: 'Tamil', test: /[\u0B80-\u0BFF]/, languages: ['ta'] },
  { name: 'Telugu', test: /[\u0C00-\u0C7F]/, languages: ['te'] },
  { name: 'Kannada', test: /[\u0C80-\u0CFF]/, languages: ['kn'] },
  { name: 'Malayalam', test: /[\u0D00-\u0D7F]/, languages: ['ml'] },
];

/**
 * Returns a warning when the body's script cannot belong to the chosen
 * language, or null when it is consistent (or cannot be judged).
 */
const languageMismatch = (body: string, code?: string | null): string | null => {
  if (!body || !code) return null;
  const script = SCRIPTS.find(s => s.test.test(body));
  if (!script) return null;
  if (script.languages.includes(code)) return null;
  return `This body is written in ${script.name}, but the language is set to ` +
    `${languageLabel(code)}. Meta fixes a template's language at approval, so this ` +
    `cannot be corrected afterwards — ${script.languages.map(languageLabel).join(' or ')} ` +
    `is probably what you want.`;
};


type SortState = { col: 'name' | 'updated'; dir: 'asc' | 'desc' };

/** A column header that sorts, and shows which way it is currently sorting. */
const SortHeader: React.FC<{
  label: string;
  col: SortState['col'];
  sort: SortState;
  onSort: (s: SortState) => void;
}> = ({ label, col, sort, onSort }) => {
  const active = sort.col === col;
  return (
    <th className="px-3 py-2.5 text-xs font-semibold text-slate-400">
      <button
        onClick={() => onSort({ col, dir: active && sort.dir === 'asc' ? 'desc' : 'asc' })}
        className={`flex items-center gap-0.5 transition-colors cursor-pointer ${
          active ? 'text-slate-100' : 'hover:text-slate-200'
        }`}
      >
        {label}
        <span className={`material-symbols-outlined text-[15px] ${active ? 'opacity-100' : 'opacity-30'}`}>
          {active && sort.dir === 'desc' ? 'arrow_downward' : 'arrow_upward'}
        </span>
      </button>
    </th>
  );
};


export const WhatsAppTemplatesView: React.FC = () => {
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const [isCreating, setIsCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sort, setSort] = useState<SortState>({ col: 'updated', dir: 'desc' });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [headerSourceType, setHeaderSourceType] = useState<'URL' | 'UPLOAD'>('URL');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewMediaUrl, setPreviewMediaUrl] = useState<string | null>(null);

  const [newTemplate, setNewTemplate] = useState<Partial<WhatsAppTemplate>>({
    name: '',
    // Hindi rather than English: every template this account sends is written
    // in an Indian language, and the previous silent default to en_US is how
    // ten Hindi and Punjabi templates came to be registered as English.
    language_code: 'hi',
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
      language_code: t.language_code || 'en_US',
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
  // A template Meta has already accepted has its language fixed there; editing
  // ours would only make the two disagree and break the send lookup.
  const editingTemplate = editingId ? templates.find(t => t.template_id === editingId) : null;
  const languageLocked = Boolean(editingTemplate?.meta_template_name);
  const mismatchWarning = languageMismatch(newTemplate.body || '', newTemplate.language_code);

  const query = search.trim().toLowerCase();

  // Offered filters are derived from the templates that exist, so the list can
  // never present a choice that matches nothing.
  const categoryOptions = Array.from(
    new Set(templates.map(t => (t.category || '').toUpperCase()).filter(Boolean))
  ).sort();
  const statusOptions = Array.from(new Set(templates.map(statusLabel))).sort();

  const visibleTemplates = templates
    .filter(t => !query || (t.name || '').toLowerCase().includes(query))
    .filter(t => !categoryFilter || (t.category || '').toUpperCase() === categoryFilter)
    .filter(t => !statusFilter || statusLabel(t) === statusFilter)
    .slice()
    .sort((a, b) => {
      const dir = sort.dir === 'asc' ? 1 : -1;
      if (sort.col === 'name') {
        return dir * (a.name || '').localeCompare(b.name || '');
      }
      const at = new Date(a.updated_at || a.created_at).getTime();
      const bt = new Date(b.updated_at || b.created_at).getTime();
      return dir * (at - bt);
    });

  const visibleIds = visibleTemplates.map(t => t.template_id);
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every(id => selectedIds.includes(id));

  const toggleSelected = (id: string) =>
    setSelectedIds(prev => (prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]));

  // Select-all covers what is on screen, not the whole table: acting on rows a
  // filter is hiding is how people delete things they never saw.
  const toggleSelectAll = () =>
    setSelectedIds(prev => (allVisibleSelected ? prev.filter(id => !visibleIds.includes(id)) : Array.from(new Set([...prev, ...visibleIds]))));

  const handleBulkDelete = async () => {
    if (!window.confirm(`Delete ${selectedIds.length} template(s)? This cannot be undone.`)) return;
    setBulkDeleting(true);
    const failures: string[] = [];
    for (const id of selectedIds) {
      try {
        await deleteTemplate(id);
      } catch (err: any) {
        // A template still linked to a campaign is refused by the API. Report
        // it by name rather than letting one refusal abandon the rest.
        const name = templates.find(t => t.template_id === id)?.name || id;
        failures.push(`${name}: ${err.message}`);
      }
    }
    setBulkDeleting(false);
    setSelectedIds([]);
    await loadTemplates();
    if (failures.length) {
      alert(`${failures.length} of ${failures.length + (selectedIds.length - failures.length)} could not be deleted:\n\n${failures.join('\n')}`);
    }
  };

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
              <label className="text-xs text-slate-400 font-semibold flex items-center justify-between">
                <span>Language</span>
                {languageLocked && (
                  <span className="text-[10px] font-normal text-slate-500">
                    Fixed at approval
                  </span>
                )}
              </label>
              <select
                value={newTemplate.language_code || 'hi'}
                disabled={languageLocked}
                onChange={e => setNewTemplate(prev => ({ ...prev, language_code: e.target.value }))}
                className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {LANGUAGES.map(l => (
                  <option key={l.code} value={l.code}>{l.label} ({l.code})</option>
                ))}
              </select>
              {languageLocked ? (
                <p className="text-[11px] text-slate-500">
                  Meta keys this template by name and language, so it cannot be changed
                  once approved. A different language needs a new template.
                </p>
              ) : mismatchWarning ? (
                <p className="text-[11px] text-amber-400 flex items-start gap-1.5">
                  <span className="material-symbols-outlined text-[14px] mt-px shrink-0">warning</span>
                  {mismatchWarning}
                </p>
              ) : null}
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
        <>
        {/* Filter bar. Category and status are the two facets that change how a
            template behaves — one decides its price, the other whether it can
            send at all. */}
        <div className="flex flex-wrap items-center gap-2 mb-3 pb-3 border-b border-slate-800">
          <span className="text-xs text-slate-500 font-medium mr-1">Filter By</span>

          <select
            value={categoryFilter}
            onChange={e => setCategoryFilter(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1.5 focus:border-sky-600 focus:outline-none cursor-pointer"
          >
            <option value="">Category</option>
            {categoryOptions.map(c => (
              <option key={c} value={c}>{categoryLabel(c)}</option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1.5 focus:border-sky-600 focus:outline-none cursor-pointer"
          >
            <option value="">Status</option>
            {statusOptions.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          {(categoryFilter || statusFilter || search) && (
            <button
              onClick={() => { setCategoryFilter(''); setStatusFilter(''); setSearch(''); }}
              className="text-xs text-sky-400 hover:text-sky-300 transition-colors flex items-center gap-1"
            >
              <span className="material-symbols-outlined text-[14px]">filter_alt_off</span>
              Clear filters
            </button>
          )}

          <span className="ml-auto text-xs text-slate-500">
            {visibleTemplates.length} of {templates.length}
          </span>
        </div>

        {/* Bulk bar, shown only when a selection exists so it never takes space
            it has not earned. */}
        {selectedIds.length > 0 && (
          <div className="flex items-center gap-3 mb-3 px-3 py-2 bg-slate-900 border border-slate-700 rounded">
            <span className="text-xs text-slate-300 font-medium">
              {selectedIds.length} selected
            </span>
            <button
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
              className="text-xs text-rose-400 hover:text-rose-300 transition-colors flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span className="material-symbols-outlined text-[15px]">delete</span>
              {bulkDeleting ? 'Deleting...' : 'Delete selected'}
            </button>
            <button
              onClick={() => setSelectedIds([])}
              className="text-xs text-slate-400 hover:text-slate-200 transition-colors ml-auto"
            >
              Clear selection
            </button>
          </div>
        )}

        <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead className="bg-slate-950 border-b border-slate-800">
                <tr>
                  <th className="px-3 py-2.5 w-10">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAll}
                      aria-label="Select all templates"
                      className="accent-sky-500 cursor-pointer"
                    />
                  </th>
                  <SortHeader label="Template Name" col="name" sort={sort} onSort={setSort} />
                  <th className="px-3 py-2.5 text-xs font-semibold text-slate-400">Meta Name</th>
                  <th className="px-3 py-2.5 text-xs font-semibold text-slate-400">Category</th>
                  <th className="px-3 py-2.5 text-xs font-semibold text-slate-400">Preview</th>
                  <th className="px-3 py-2.5 text-xs font-semibold text-slate-400">Language</th>
                  <SortHeader label="Last Updated" col="updated" sort={sort} onSort={setSort} />
                  <th className="px-3 py-2.5 text-xs font-semibold text-slate-400 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {loading ? (
                  <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-500">Loading templates...</td></tr>
                ) : visibleTemplates.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-10 text-center text-slate-500">
                      <span className="material-symbols-outlined text-3xl block mb-1">dashboard_customize</span>
                      {templates.length === 0
                        ? 'No templates created yet.'
                        : 'No templates match these filters.'}
                    </td>
                  </tr>
                ) : (
                  visibleTemplates.map(t => {
                    const label = statusLabel(t);
                    const expanded = expandedId === t.template_id;
                    return (
                      <React.Fragment key={t.template_id}>
                        <tr className="hover:bg-slate-800/40 transition-colors">
                          <td className="px-3 py-2.5">
                            <input
                              type="checkbox"
                              checked={selectedIds.includes(t.template_id)}
                              onChange={() => toggleSelected(t.template_id)}
                              aria-label={`Select ${t.name}`}
                              className="accent-sky-500 cursor-pointer"
                            />
                          </td>
                          <td className="px-3 py-2.5 font-medium text-slate-200 max-w-[180px]">
                            <span className="block truncate" title={t.name}>{t.name}</span>
                          </td>
                          <td className="px-3 py-2.5 font-mono-code text-xs text-slate-500 max-w-[150px]">
                            <span className="block truncate" title={t.meta_template_name || undefined}>
                              {t.meta_template_name || '—'}
                            </span>
                          </td>
                          <td className="px-3 py-2.5">
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold border ${categoryStyle(t.category)}`}
                              title="Meta billing category"
                            >
                              {categoryLabel(t.category)}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-xs text-slate-400 max-w-[260px]">
                            <span className="block truncate" title={t.body}>{t.body}</span>
                          </td>
                          <td className="px-3 py-2.5">
                            {/* One chip per template: the dot carries the review
                                state, the text the language it was approved in. */}
                            <span
                              className={`inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded border font-semibold ${statusStyle(label)}`}
                              title={`${label} · ${languageLabel(t.language_code)} (${t.language_code})`}
                            >
                              <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-current" />
                              {languageLabel(t.language_code)}
                            </span>
                          </td>
                          <td className="px-3 py-2.5 text-xs text-slate-400 whitespace-nowrap">
                            {new Date(t.updated_at || t.created_at).toLocaleDateString(undefined,
                              { day: '2-digit', month: 'short', year: 'numeric' })}
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="flex items-center justify-end gap-1.5">
                              {!t.meta_template_name && (
                                <button
                                  onClick={() => handleSubmitForReview(t)}
                                  title="Submit to Meta for review"
                                  className="text-slate-500 hover:text-emerald-400 transition-colors"
                                >
                                  <span className="material-symbols-outlined text-[17px]">cloud_upload</span>
                                </button>
                              )}
                              <button
                                onClick={() => startEdit(t)}
                                title="Edit template"
                                className="text-slate-500 hover:text-sky-400 transition-colors"
                              >
                                <span className="material-symbols-outlined text-[17px]">edit_square</span>
                              </button>
                              <button
                                onClick={() => setExpandedId(expanded ? null : t.template_id)}
                                title={expanded ? 'Hide full template' : 'Show full template'}
                                className={`transition-colors ${expanded ? 'text-sky-400' : 'text-slate-500 hover:text-sky-400'}`}
                              >
                                <span className="material-symbols-outlined text-[17px]">
                                  {expanded ? 'expand_less' : 'list'}
                                </span>
                              </button>
                              <button
                                onClick={() => handleDelete(t.template_id)}
                                title="Delete template"
                                className="text-slate-500 hover:text-rose-400 transition-colors"
                              >
                                <span className="material-symbols-outlined text-[17px]">delete</span>
                              </button>
                            </div>
                          </td>
                        </tr>

                        {/* A table row cannot hold an image and four sections, so
                            the full template opens underneath the row it belongs
                            to rather than in a dialog that hides the list. */}
                        {expanded && (
                          <tr className="bg-slate-950/60">
                            <td colSpan={8} className="px-4 py-4">
                              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                <div className="flex flex-col gap-3">
                                  {t.header_type && t.header_type !== 'NONE' && (
                                    <div>
                                      <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1.5">
                                        Header · {t.header_type}
                                      </div>
                                      {t.header_type === 'IMAGE' && resolveMediaUrl(t.header_content) && (
                                        <img
                                          src={resolveMediaUrl(t.header_content) as string}
                                          alt="Template header"
                                          className="w-full max-h-64 object-contain rounded border border-slate-800 bg-slate-950"
                                        />
                                      )}
                                      {t.header_type === 'VIDEO' && resolveMediaUrl(t.header_content) && (
                                        <video
                                          src={resolveMediaUrl(t.header_content) as string}
                                          controls
                                          className="w-full max-h-64 object-contain rounded border border-slate-800 bg-slate-950"
                                        />
                                      )}
                                      {t.header_type === 'TEXT' && t.header_content && (
                                        <div className="text-sm font-semibold text-slate-200 bg-slate-900 border border-slate-800 rounded px-3 py-2">
                                          {t.header_content}
                                        </div>
                                      )}
                                    </div>
                                  )}

                                  <div>
                                    <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1.5">Body</div>
                                    <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed bg-slate-900 border border-slate-800 rounded px-3 py-2">
                                      {t.body}
                                    </div>
                                  </div>

                                  {t.footer && (
                                    <div>
                                      <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1.5">Footer</div>
                                      <div className="text-xs text-slate-500 italic bg-slate-900 border border-slate-800 rounded px-3 py-2">
                                        {t.footer}
                                      </div>
                                    </div>
                                  )}

                                  {Array.isArray(t.buttons) && t.buttons.length > 0 && (
                                    <div>
                                      <div className="text-[10px] uppercase text-slate-500 tracking-wider mb-1.5">Buttons</div>
                                      <div className="flex flex-col gap-1.5">
                                        {t.buttons.map((btn: any, idx: number) => (
                                          <div
                                            key={idx}
                                            className="text-xs text-sky-400 bg-slate-900 border border-slate-800 rounded px-3 py-1.5 flex items-center gap-1.5"
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
                                </div>

                                <div className="flex flex-col gap-2 text-xs text-slate-500">
                                  <div className="flex items-center gap-2">
                                    <span className="uppercase tracking-wider text-[10px]">Review status</span>
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-semibold border ${statusStyle(label)}`}>
                                      {label}
                                    </span>
                                  </div>
                                  <div>Created: {new Date(t.created_at).toLocaleString()}</div>
                                  <div>Updated: {new Date(t.updated_at || t.created_at).toLocaleString()}</div>
                                  {t.last_used_at && <div>Last used: {new Date(t.last_used_at).toLocaleString()}</div>}
                                  <div className="font-mono-code break-all">Local id: {t.template_id}</div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
        </>
      )}
    </div>
  );
};
