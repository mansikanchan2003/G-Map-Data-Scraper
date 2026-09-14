import { useEffect, useState, useCallback } from 'react';
import { ConfigService } from '../api';
import { Loader2, ChevronLeft, ChevronRight } from 'lucide-react';

export default function ConfigView() {
  const [locations, setLocations] = useState<any>({ items: [], total: 0, page: 1, total_pages: 1 });
  const [categories, setCategories] = useState<any>({ items: [], total: 0, page: 1, total_pages: 1 });
  const [loadingLoc, setLoadingLoc] = useState(true);
  const [loadingCat, setLoadingCat] = useState(true);
  
  const [locPage, setLocPage] = useState(1);
  const [catPage, setCatPage] = useState(1);

  const loadLocations = useCallback(async () => {
    setLoadingLoc(true);
    try {
      const res = await ConfigService.getLocations(locPage, 20);
      setLocations(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingLoc(false);
    }
  }, [locPage]);

  const loadCategories = useCallback(async () => {
    setLoadingCat(true);
    try {
      const res = await ConfigService.getCategories(catPage, 20);
      setCategories(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingCat(false);
    }
  }, [catPage]);

  useEffect(() => { loadLocations(); }, [loadLocations]);
  useEffect(() => { loadCategories(); }, [loadCategories]);

  return (
    <div className="flex-col gap-6 w-full max-w-7xl mx-auto">
      <header className="mb-6">
        <h1>Source Configuration</h1>
        <p>Currently loaded locations and categories forming the discovery matrix.</p>
      </header>

      <div className="flex gap-6 h-full">
        {/* Locations Column */}
        <div className="flex-col gap-4 flex-1">
          <div className="glass-card flex-1 flex flex-col p-0 overflow-hidden min-h-[500px]">
            <div className="p-4 border-b border-[rgba(255,255,255,0.08)] bg-[rgba(15,23,42,0.8)]">
              <h3 className="mb-0 text-lg">Loaded Locations ({locations.total})</h3>
            </div>
            
            <div className="table-container flex-1 overflow-y-auto border-none rounded-none">
              {loadingLoc ? (
                <div className="flex h-32 items-center justify-center">
                  <Loader2 className="animate-spin text-cyan" size={24} />
                </div>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Pincode</th>
                      <th>Coordinates</th>
                      <th>Radius</th>
                    </tr>
                  </thead>
                  <tbody>
                    {locations.items.map((loc: any) => (
                      <tr key={loc.location_id}>
                        <td className="font-medium text-cyan">{loc.pincode}</td>
                        <td className="text-sm">{loc.latitude?.toFixed(4)}, {loc.longitude?.toFixed(4)}</td>
                        <td className="text-sm">{loc.radius_km} km</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="p-3 border-t border-[rgba(255,255,255,0.08)] flex justify-between items-center bg-[rgba(15,23,42,0.8)]">
              <div className="text-xs text-muted">Page {locations.page} of {locations.total_pages}</div>
              <div className="flex gap-2">
                <button className="btn btn-secondary px-2 py-1 text-xs" disabled={!locations.has_prev} onClick={() => setLocPage(p => p - 1)}><ChevronLeft size={14} /></button>
                <button className="btn btn-secondary px-2 py-1 text-xs" disabled={!locations.has_next} onClick={() => setLocPage(p => p + 1)}><ChevronRight size={14} /></button>
              </div>
            </div>
          </div>
        </div>

        {/* Categories Column */}
        <div className="flex-col gap-4 flex-1">
          <div className="glass-card flex-1 flex flex-col p-0 overflow-hidden min-h-[500px]">
            <div className="p-4 border-b border-[rgba(255,255,255,0.08)] bg-[rgba(15,23,42,0.8)]">
              <h3 className="mb-0 text-lg">Loaded Categories ({categories.total})</h3>
            </div>
            
            <div className="table-container flex-1 overflow-y-auto border-none rounded-none">
              {loadingCat ? (
                <div className="flex h-32 items-center justify-center">
                  <Loader2 className="animate-spin text-cyan" size={24} />
                </div>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Category Name</th>
                      <th>Persona</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categories.items.map((cat: any) => (
                      <tr key={cat.category_id}>
                        <td className="font-medium text-indigo">{cat.category_name}</td>
                        <td className="text-sm text-muted">{cat.persona || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="p-3 border-t border-[rgba(255,255,255,0.08)] flex justify-between items-center bg-[rgba(15,23,42,0.8)]">
              <div className="text-xs text-muted">Page {categories.page} of {categories.total_pages}</div>
              <div className="flex gap-2">
                <button className="btn btn-secondary px-2 py-1 text-xs" disabled={!categories.has_prev} onClick={() => setCatPage(p => p - 1)}><ChevronLeft size={14} /></button>
                <button className="btn btn-secondary px-2 py-1 text-xs" disabled={!categories.has_next} onClick={() => setCatPage(p => p + 1)}><ChevronRight size={14} /></button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
