import { useEffect, useState, useCallback } from 'react';
import { BusinessesService } from '../api';
import { Search, Download, ChevronLeft, ChevronRight, X, Loader2, MapPin } from 'lucide-react';

export default function BusinessesView() {
  const [data, setData] = useState<any>({ items: [], total: 0, page: 1, total_pages: 1 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedBiz, setSelectedBiz] = useState<any>(null);

  // Filters
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [districtFilter, setDistrictFilter] = useState('');
  const [isValidFilter, setIsValidFilter] = useState('true'); // Default to valid

  // Debounce search
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1); // Reset to page 1 on new search
    }, 500);
    return () => clearTimeout(handler);
  }, [search]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: any = { page, page_size: 100 };
      if (debouncedSearch) params.search = debouncedSearch;
      if (stateFilter) params.state = stateFilter;
      if (districtFilter) params.district = districtFilter;
      if (isValidFilter !== 'all') params.is_valid = isValidFilter === 'true';

      const res = await BusinessesService.getBusinesses(params);
      setData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to load business data');
    } finally {
      setLoading(false);
    }
  }, [page, debouncedSearch, stateFilter, districtFilter, isValidFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleExport = () => {
    BusinessesService.downloadCsv(); // Downloads all data ignoring pagination (handled by backend streaming)
  };

  return (
    <div className="flex-col gap-6 w-full max-w-7xl mx-auto relative h-full">
      <header className="flex justify-between items-center mb-6">
        <div>
          <h1>Business Data Explorer</h1>
          <p>Browse and export discovered business records</p>
        </div>
        <button onClick={handleExport} className="btn btn-primary">
          <Download size={18} /> Export CSV
        </button>
      </header>

      {/* Filters */}
      <div className="glass-card mb-6 flex items-end gap-4 flex-wrap">
        <div className="input-group flex-1 min-w-[250px]">
          <label className="input-label">Search Name/Address</label>
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <input 
              type="text" 
              className="input-field w-full pl-9" 
              placeholder="e.g. Axis Bank..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
        </div>
        <div className="input-group w-48">
          <label className="input-label">State</label>
          <input 
            type="text" 
            className="input-field" 
            placeholder="e.g. DELHI" 
            value={stateFilter}
            onChange={e => {setStateFilter(e.target.value); setPage(1);}}
          />
        </div>
        <div className="input-group w-48">
          <label className="input-label">District</label>
          <input 
            type="text" 
            className="input-field" 
            placeholder="e.g. NEW DELHI" 
            value={districtFilter}
            onChange={e => {setDistrictFilter(e.target.value); setPage(1);}}
          />
        </div>
        <div className="input-group w-48">
          <label className="input-label">Validation Status</label>
          <select 
            className="input-field" 
            value={isValidFilter}
            onChange={e => {setIsValidFilter(e.target.value); setPage(1);}}
          >
            <option value="true">Valid Only (Default)</option>
            <option value="false">Invalid / Failed</option>
            <option value="all">All Records</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="glass-card border-red-500 text-red-500 mb-6">
          <p>{error}</p>
        </div>
      )}

      {/* Data Table */}
      <div className="glass-card p-0 overflow-hidden flex-1 flex flex-col min-h-[500px]">
        <div className="table-container flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex h-64 items-center justify-center">
              <Loader2 className="animate-spin text-cyan" size={32} />
            </div>
          ) : data.items.length === 0 ? (
            <div className="flex h-64 items-center justify-center text-muted">
              No business records found matching the current filters.
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Phone</th>
                  <th>District / State</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((biz: any) => (
                  <tr 
                    key={biz.business_id} 
                    className="cursor-pointer hover:bg-[rgba(255,255,255,0.05)]"
                    onClick={() => setSelectedBiz(biz)}
                  >
                    <td className="font-medium max-w-xs truncate">{biz.name}</td>
                    <td className="text-muted">{biz.category}</td>
                    <td>{biz.phone || '-'}</td>
                    <td className="text-muted text-xs uppercase">
                      {biz.district || 'N/A'}, {biz.state || 'N/A'}
                    </td>
                    <td>
                      <span className={`badge ${biz.is_valid ? 'badge-success' : 'badge-error'}`}>
                        {biz.is_valid ? 'Valid' : 'Invalid'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination Footer */}
        <div className="p-4 border-t border-[rgba(255,255,255,0.08)] flex justify-between items-center bg-[rgba(15,23,42,0.8)]">
          <div className="text-sm text-muted">
            Showing <span className="text-primary font-medium">{data.items.length > 0 ? (data.page - 1) * data.page_size + 1 : 0}</span> to <span className="text-primary font-medium">{Math.min(data.page * data.page_size, data.total)}</span> of <span className="text-primary font-medium">{data.total.toLocaleString()}</span> records
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted">Page {data.page} of {data.total_pages || 1}</span>
            <div className="flex gap-2">
              <button 
                className="btn btn-secondary px-2 py-1" 
                disabled={!data.has_prev}
                onClick={() => setPage(p => Math.max(1, p - 1))}
              >
                <ChevronLeft size={18} /> Prev
              </button>
              <button 
                className="btn btn-secondary px-2 py-1" 
                disabled={!data.has_next}
                onClick={() => setPage(p => p + 1)}
              >
                Next <ChevronRight size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Slide-out Detail Panel */}
      {selectedBiz && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setSelectedBiz(null)} />
          <div className="relative w-full max-w-md bg-surface h-full shadow-glass border-l border-color p-6 overflow-y-auto animate-in slide-in-from-right duration-200" style={{ backgroundColor: 'var(--bg-surface)' }}>
            <button 
              className="absolute top-4 right-4 text-muted hover:text-primary transition-colors"
              onClick={() => setSelectedBiz(null)}
            >
              <X size={24} />
            </button>
            
            <h2 className="text-xl pr-8 mb-1">{selectedBiz.name}</h2>
            <div className="text-cyan text-sm mb-6 font-medium">{selectedBiz.category}</div>
            
            <div className="flex-col gap-6">
              <div>
                <h4 className="text-xs uppercase text-muted tracking-wider mb-2">Location & Address</h4>
                <p className="text-sm bg-[rgba(0,0,0,0.2)] p-3 rounded-lg border border-[rgba(255,255,255,0.05)]">
                  {selectedBiz.address}
                </p>
                <div className="flex justify-between mt-2 text-sm">
                  <span className="text-muted">District: <span className="text-primary">{selectedBiz.district || '-'}</span></span>
                  <span className="text-muted">State: <span className="text-primary">{selectedBiz.state || '-'}</span></span>
                </div>
              </div>
              
              <div>
                <h4 className="text-xs uppercase text-muted tracking-wider mb-2">Contact Info</h4>
                <div className="bg-[rgba(0,0,0,0.2)] p-3 rounded-lg border border-[rgba(255,255,255,0.05)] text-sm flex-col gap-2">
                  <div className="flex justify-between">
                    <span className="text-muted">Phone</span>
                    <span className="font-medium">{selectedBiz.phone || 'Not available'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Email</span>
                    <span className="font-medium">{selectedBiz.email || 'Not available'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Website</span>
                    {selectedBiz.website ? (
                      <a href={selectedBiz.website} target="_blank" rel="noopener noreferrer" className="text-cyan hover:underline truncate max-w-[200px]">
                        {selectedBiz.website}
                      </a>
                    ) : (
                      <span className="font-medium">Not available</span>
                    )}
                  </div>
                </div>
              </div>

              <div>
                <h4 className="text-xs uppercase text-muted tracking-wider mb-2">Metadata</h4>
                <div className="bg-[rgba(0,0,0,0.2)] p-3 rounded-lg border border-[rgba(255,255,255,0.05)] text-sm flex-col gap-2">
                  <div className="flex justify-between">
                    <span className="text-muted">Status</span>
                    <span className={`badge ${selectedBiz.is_valid ? 'badge-success' : 'badge-error'}`}>
                      {selectedBiz.is_valid ? 'Valid' : 'Invalid'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Discovered At</span>
                    <span>{new Date(selectedBiz.discovered_at).toLocaleString()}</span>
                  </div>
                </div>
              </div>

              {selectedBiz.google_maps_url && (
                <div className="mt-4">
                  <a 
                    href={selectedBiz.google_maps_url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="btn btn-primary w-full"
                  >
                    <MapPin size={16} /> Open in Google Maps
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
