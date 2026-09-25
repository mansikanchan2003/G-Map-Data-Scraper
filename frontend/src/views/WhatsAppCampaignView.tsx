import React, { useState, useEffect } from 'react';
import { 
  fetchAccounts, 
  fetchTemplates, 
  validateContacts, 
  createCampaign,
  downloadCleanedData,
  connectAccount,
  type WhatsAppAccount,
  type WhatsAppTemplate,
  type ValidationResponse
} from '../api/whatsapp';
import { fetchBusinesses } from '../api';
import { WhatsAppPreview } from '../components/WhatsAppPreview';
import * as XLSX from 'xlsx';

export const WhatsAppCampaignView: React.FC = () => {
  const [step, setStep] = useState<number>(1);
  const [accounts, setAccounts] = useState<WhatsAppAccount[]>([]);
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  
  // Step 1: Data & Account
  const [dataSource, setDataSource] = useState<'scraped' | 'upload'>('scraped');
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  
  // Scraped Data State
  const [scrapedFilterState, setScrapedFilterState] = useState<string>('All');
  const [scrapedSearch, setScrapedSearch] = useState<string>('');
  
  // Validation State
  const [validationResult, setValidationResult] = useState<ValidationResponse | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  
  // Step 2: Template
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('');
  
  // Step 4: Campaign creation
  const [campaignName, setCampaignName] = useState<string>('');
  const [campaignSuccessId, setCampaignSuccessId] = useState<string | null>(null);

  useEffect(() => {
    fetchAccounts().then(accs => {
      setAccounts(accs);
      if (accs.length > 0) setSelectedAccountId(accs[0].account_id);
    });
    fetchTemplates().then(setTemplates);
  }, []);

  const handleVerifyConnection = async () => {
    setLoading(true);
    try {
      const updatedAccount = await connectAccount();
      const accs = await fetchAccounts();
      setAccounts(accs);
      setSelectedAccountId(updatedAccount.account_id);
      alert("Account verified and connected successfully!");
    } catch (err: any) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsValidating(true);
    setValidationResult(null);

    const reader = new FileReader();
    reader.onload = async (evt) => {
      try {
        const bstr = evt.target?.result;
        const wb = XLSX.read(bstr, { type: 'binary' });
        const wsname = wb.SheetNames[0];
        const ws = wb.Sheets[wsname];
        const data = XLSX.utils.sheet_to_json(ws, { header: 1 }) as any[][];
        
        if (data.length < 2) {
          alert("File has no data.");
          setIsValidating(false);
          return;
        }

        // Find columns
        const headers = data[0].map(h => String(h).toLowerCase());
        const nameIdx = headers.findIndex(h => h.includes('name') || h.includes('business'));
        const phoneIdx = headers.findIndex(h => h.includes('phone') || h.includes('mobile') || h.includes('contact'));

        if (phoneIdx === -1) {
          alert("Could not find a phone/mobile column.");
          setIsValidating(false);
          return;
        }

        const contacts = data.slice(1).map(row => ({
          name: nameIdx !== -1 ? String(row[nameIdx] || '') : '',
          phone: row[phoneIdx] !== undefined ? row[phoneIdx] : '' // Pass raw to backend
        })).filter(c => c.phone !== '');

        const result = await validateContacts(contacts);
        setValidationResult(result);
      } catch (err: any) {
        alert("Error parsing file: " + err.message);
      } finally {
        setIsValidating(false);
      }
    };
    reader.readAsBinaryString(file);
  };

  const handleFetchScrapedData = async () => {
    setIsValidating(true);
    setValidationResult(null);
    try {
      // In a real app we might paginate or just ask backend to validate by filters directly.
      // For this isolated demo, we'll fetch up to a max (e.g., 500) or we could have backend do it.
      // We will fetch 1000 items from the standard API and pass them.
      const res = await fetchBusinesses({ 
        page: 1, 
        page_size: 1000, 
        search: scrapedSearch, 
        state: scrapedFilterState !== 'All' ? scrapedFilterState : undefined 
      });
      
      const contacts = res.items.map(b => ({
        name: b.name,
        phone: b.phone,
        business_id: b.business_id
      }));

      const result = await validateContacts(contacts);
      setValidationResult(result);
    } catch (err: any) {
      alert("Error fetching data: " + err.message);
    } finally {
      setIsValidating(false);
    }
  };

  const handleRunCampaign = async () => {
    if (!campaignName) {
      alert("Please enter a campaign name.");
      return;
    }
    setLoading(true);
    try {
      const camp = await createCampaign({
        name: campaignName,
        template_id: selectedTemplateId,
        account_id: selectedAccountId,
        data_source_type: dataSource,
        contacts: validationResult?.valid_contacts || []
      });
      setCampaignSuccessId(camp.campaign_id);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  };

  const activeTemplate = templates.find(t => t.template_id === selectedTemplateId);
  const activeAccount = accounts.find(a => a.account_id === selectedAccountId);

  if (campaignSuccessId) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-950 p-6 text-slate-100">
        <div className="bg-slate-900 border border-slate-800 p-8 rounded-xl max-w-md text-center">
          <span className="material-symbols-outlined text-6xl text-emerald-500 mb-4">check_circle</span>
          <h2 className="text-2xl font-semibold mb-2">Campaign Created</h2>
          <p className="text-slate-400 mb-6 text-sm">
            The campaign has been scheduled and is processing in the background.
          </p>
          <button 
            onClick={() => window.location.hash = 'whatsapp-history'}
            className="px-6 py-2.5 bg-sky-600 hover:bg-sky-500 text-white rounded font-semibold text-sm transition-colors"
          >
            View Campaign History
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full bg-slate-950 text-slate-100 overflow-y-auto">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900 shrink-0">
        <h1 className="text-2xl font-semibold tracking-tight">WhatsApp Campaign Builder</h1>
        <p className="text-xs text-slate-400 mt-1">Configure and send targeted WhatsApp messages</p>
      </div>

      {/* Stepper */}
      <div className="px-6 py-4 bg-slate-900/50 border-b border-slate-800 shrink-0 flex items-center gap-4">
        {[
          { num: 1, title: 'Data & Account' },
          { num: 2, title: 'Template' },
          { num: 3, title: 'Review' },
          { num: 4, title: 'Confirm' }
        ].map(s => (
          <div key={s.num} className={`flex items-center gap-2 ${step === s.num ? 'text-sky-400 font-semibold' : 'text-slate-500'}`}>
            <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border ${step === s.num ? 'border-sky-400 bg-sky-950/30' : 'border-slate-700 bg-slate-900'}`}>
              {s.num}
            </div>
            <span className="text-sm">{s.title}</span>
            {s.num < 4 && <div className="w-8 h-px bg-slate-800 ml-2" />}
          </div>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 p-6 overflow-y-auto">
        <div className="max-w-4xl mx-auto space-y-6">
          
          {step === 1 && (
            <div className="space-y-6">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                <h3 className="text-sm font-semibold mb-4 text-slate-200">1. WhatsApp Sending Account</h3>
                <select 
                  value={selectedAccountId}
                  onChange={e => setSelectedAccountId(e.target.value)}
                  className="w-full max-w-md bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200 outline-none"
                >
                  {accounts.length === 0 && <option value="">No accounts found</option>}
                  {accounts.map(a => (
                    <option key={a.account_id} value={a.account_id}>
                      {a.phone_number} {a.display_name ? `(${a.display_name})` : ''} - {a.status}
                    </option>
                  ))}
                </select>
                {activeAccount && (
                  <div className="flex items-center gap-4 mt-3">
                    <div className={`text-xs inline-flex items-center gap-1.5 px-2 py-1 rounded border ${activeAccount.status === 'Connected' ? 'border-emerald-800 bg-emerald-950/30 text-emerald-400' : 'border-amber-800 bg-amber-950/30 text-amber-400'}`}>
                      <span className="material-symbols-outlined text-[14px]">
                        {activeAccount.status === 'Connected' ? 'check_circle' : 'warning'}
                      </span>
                      {activeAccount.status}
                    </div>
                  </div>
                )}
                
                <div className="mt-4">
                  <button
                    onClick={handleVerifyConnection}
                    disabled={loading}
                    className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-sm font-semibold rounded shadow transition-colors flex items-center gap-2"
                  >
                    <span className="material-symbols-outlined text-[18px]">sync</span>
                    {loading ? 'Verifying...' : 'Verify Connection'}
                  </button>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                <div className="flex items-center gap-4 mb-5 border-b border-slate-800 pb-4">
                  <button 
                    onClick={() => { setDataSource('scraped'); setValidationResult(null); }}
                    className={`px-4 py-2 text-sm font-semibold rounded-md border ${dataSource === 'scraped' ? 'bg-sky-900/40 border-sky-700 text-sky-400' : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-300'}`}
                  >
                    Use Scraped Data
                  </button>
                  <button 
                    onClick={() => { setDataSource('upload'); setValidationResult(null); }}
                    className={`px-4 py-2 text-sm font-semibold rounded-md border ${dataSource === 'upload' ? 'bg-sky-900/40 border-sky-700 text-sky-400' : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-300'}`}
                  >
                    Upload CSV / Excel
                  </button>
                </div>

                {dataSource === 'scraped' && (
                  <div className="space-y-4">
                    <div className="flex gap-3 items-center">
                      <input 
                        type="text"
                        placeholder="Search keyword..."
                        value={scrapedSearch}
                        onChange={e => setScrapedSearch(e.target.value)}
                        className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm outline-none text-slate-200"
                      />
                      <select 
                        value={scrapedFilterState}
                        onChange={e => setScrapedFilterState(e.target.value)}
                        className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm outline-none text-slate-200"
                      >
                        <option value="All">All States</option>
                        <option value="DELHI">Delhi</option>
                        <option value="MAHARASHTRA">Maharashtra</option>
                      </select>
                      <button 
                        onClick={handleFetchScrapedData}
                        disabled={isValidating}
                        className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded text-sm font-semibold text-slate-200 transition-colors"
                      >
                        {isValidating ? 'Validating...' : 'Load & Validate'}
                      </button>
                    </div>
                  </div>
                )}

                {dataSource === 'upload' && (
                  <div className="border-2 border-dashed border-slate-700 rounded-lg p-8 text-center hover:bg-slate-800/50 transition-colors relative">
                    <input 
                      type="file" 
                      accept=".csv, .xlsx, .xls"
                      onChange={handleFileUpload}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    <span className="material-symbols-outlined text-4xl text-slate-500 mb-2">upload_file</span>
                    <h3 className="text-sm font-semibold text-slate-300">Click or drag CSV/Excel file to upload</h3>
                    <p className="text-xs text-slate-500 mt-1">Requires "Name" and "Phone" columns.</p>
                    {isValidating && <p className="text-sky-400 text-sm mt-3 font-semibold animate-pulse">Validating file...</p>}
                  </div>
                )}
              </div>

              {validationResult && (
                <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-sm font-semibold text-slate-200">Validation Report</h3>
                    <button 
                      onClick={() => downloadCleanedData(validationResult.valid_contacts)}
                      className="text-[11px] px-2 py-1 bg-emerald-900/30 text-emerald-400 border border-emerald-800 rounded flex items-center gap-1 hover:bg-emerald-900/50"
                    >
                      <span className="material-symbols-outlined text-[14px]">download</span>
                      Download Cleaned Data
                    </button>
                  </div>
                  
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                    <div className="bg-slate-950 border border-slate-800 rounded py-3">
                      <div className="text-2xl font-bold text-slate-300">{validationResult.total_records.toLocaleString()}</div>
                      <div className="text-[10px] uppercase text-slate-500 tracking-wider">Total Records</div>
                    </div>
                    <div className="bg-slate-950 border border-slate-800 rounded py-3">
                      <div className="text-2xl font-bold text-emerald-400">{validationResult.final_sendable_contacts.toLocaleString()}</div>
                      <div className="text-[10px] uppercase text-slate-500 tracking-wider">Sendable</div>
                    </div>
                    <div className="bg-slate-950 border border-slate-800 rounded py-3">
                      <div className="text-xl font-bold text-rose-400">{validationResult.invalid_numbers.toLocaleString()}</div>
                      <div className="text-[10px] uppercase text-slate-500 tracking-wider">Invalid</div>
                    </div>
                    <div className="bg-slate-950 border border-slate-800 rounded py-3">
                      <div className="text-xl font-bold text-amber-400">{validationResult.duplicates_removed.toLocaleString()}</div>
                      <div className="text-[10px] uppercase text-slate-500 tracking-wider">Duplicates</div>
                    </div>
                  </div>

                  <div className="mt-4 flex justify-end">
                    <button 
                      onClick={() => setStep(2)}
                      disabled={validationResult.final_sendable_contacts === 0 || !selectedAccountId}
                      className="px-6 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded shadow transition-colors"
                    >
                      Next: Choose Template
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
              <h3 className="text-sm font-semibold mb-4 text-slate-200">Select Message Template</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[400px] overflow-y-auto">
                {templates.map(t => (
                  <div 
                    key={t.template_id} 
                    onClick={() => setSelectedTemplateId(t.template_id)}
                    className={`p-4 rounded-lg border cursor-pointer transition-colors ${selectedTemplateId === t.template_id ? 'bg-sky-900/20 border-sky-500 ring-1 ring-sky-500/50' : 'bg-slate-950 border-slate-800 hover:border-slate-600'}`}
                  >
                    <div className="font-semibold text-slate-200">{t.name}</div>
                    <div className="text-xs text-slate-500 mt-1 line-clamp-2">{t.body}</div>
                  </div>
                ))}
              </div>
              <div className="mt-6 flex justify-between">
                <button 
                  onClick={() => setStep(1)}
                  className="px-4 py-2 text-slate-400 hover:text-slate-200 text-sm font-semibold transition-colors"
                >
                  Back
                </button>
                <button 
                  onClick={() => setStep(3)}
                  disabled={!selectedTemplateId}
                  className="px-6 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold rounded shadow transition-colors"
                >
                  Next: Preview
                </button>
              </div>
            </div>
          )}

          {step === 3 && activeTemplate && (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 flex flex-col items-center">
              <h3 className="text-sm font-semibold mb-6 text-slate-200 w-full">Message Preview</h3>
              
              <WhatsAppPreview 
                businessName="Sample Business Pvt Ltd"
                templateBody={activeTemplate.body}
                headerType={activeTemplate.header_type}
                headerContent={activeTemplate.header_content}
                footer={activeTemplate.footer}
                buttons={activeTemplate.buttons}
              />

              <div className="mt-8 flex justify-between w-full">
                <button 
                  onClick={() => setStep(2)}
                  className="px-4 py-2 text-slate-400 hover:text-slate-200 text-sm font-semibold transition-colors"
                >
                  Back
                </button>
                <button 
                  onClick={() => setStep(4)}
                  className="px-6 py-2 bg-sky-600 hover:bg-sky-500 text-white text-sm font-semibold rounded shadow transition-colors"
                >
                  Next: Confirm
                </button>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
              <h3 className="text-lg font-semibold mb-6 text-slate-100 border-b border-slate-800 pb-3">Final Confirmation</h3>
              
              <div className="space-y-4 mb-8">
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-slate-400 font-semibold">Campaign Name</label>
                  <input 
                    type="text" 
                    value={campaignName}
                    onChange={e => setCampaignName(e.target.value)}
                    className="max-w-md bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded px-3 py-2 text-sm text-slate-200 outline-none"
                    placeholder="e.g., Diwali Offer Batch 1"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-y-4 text-sm bg-slate-950 p-5 rounded border border-slate-800">
                <div className="text-slate-500 font-semibold">Total Contacts:</div>
                <div className="text-slate-200 font-mono-code">{validationResult?.total_records}</div>
                
                <div className="text-slate-500 font-semibold">Valid Contacts (Sending):</div>
                <div className="text-emerald-400 font-mono-code font-bold">{validationResult?.final_sendable_contacts}</div>
                
                <div className="text-slate-500 font-semibold">Skipped / Invalid:</div>
                <div className="text-slate-400 font-mono-code">{(validationResult?.invalid_numbers || 0) + (validationResult?.duplicates_removed || 0)}</div>
                
                <div className="text-slate-500 font-semibold">Template Used:</div>
                <div className="text-slate-200">{activeTemplate?.name}</div>

                <div className="text-slate-500 font-semibold">WhatsApp Number:</div>
                <div className="text-slate-200 font-mono-code">{activeAccount?.phone_number}</div>
              </div>

              <div className="mt-8 flex justify-between items-center">
                <button 
                  onClick={() => setStep(3)}
                  className="px-4 py-2 text-slate-400 hover:text-slate-200 text-sm font-semibold transition-colors"
                >
                  Back
                </button>
                <button 
                  onClick={handleRunCampaign}
                  disabled={loading || !campaignName}
                  className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold rounded shadow-lg transition-colors flex items-center gap-2"
                >
                  {loading ? (
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <span className="material-symbols-outlined text-[20px]">send</span>
                  )}
                  {loading ? 'Starting...' : 'Run WhatsApp Campaign'}
                </button>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
};
