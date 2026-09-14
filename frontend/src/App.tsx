import React from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { LayoutDashboard, Database, Briefcase, Settings } from 'lucide-react';
import DashboardView from './views/DashboardView';
import BusinessesView from './views/BusinessesView';
import JobsView from './views/JobsView';
import ConfigView from './views/ConfigView';

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex w-full h-full min-h-screen">
      {/* Sidebar Navigation */}
      <aside className="w-64 glass-panel m-4 flex-col justify-between rounded-xl sticky top-4" style={{ height: 'calc(100vh - 32px)' }}>
        <div className="p-6">
          <h1 className="text-xl font-bold text-gradient mb-8 flex items-center gap-2">
            <Database size={24} className="text-indigo" />
            AutoGMap
          </h1>
          <nav className="flex-col gap-2">
            <NavLink 
              to="/dashboard" 
              className={({isActive}) => `btn w-full justify-start ${isActive ? 'btn-primary' : 'btn-secondary'}`}
            >
              <LayoutDashboard size={18} />
              Dashboard
            </NavLink>
            <NavLink 
              to="/businesses" 
              className={({isActive}) => `btn w-full justify-start ${isActive ? 'btn-primary' : 'btn-secondary mt-2'}`}
            >
              <Database size={18} />
              Business Data
            </NavLink>
            <NavLink 
              to="/jobs" 
              className={({isActive}) => `btn w-full justify-start ${isActive ? 'btn-primary' : 'btn-secondary mt-2'}`}
            >
              <Briefcase size={18} />
              Jobs Monitor
            </NavLink>
            <NavLink 
              to="/config" 
              className={({isActive}) => `btn w-full justify-start ${isActive ? 'btn-primary' : 'btn-secondary mt-2'}`}
            >
              <Settings size={18} />
              Configuration
            </NavLink>
          </nav>
        </div>
        <div className="p-6 border-t border-[rgba(255,255,255,0.08)] text-xs text-muted">
          Autonomous Data Engine<br/>v2.0.0
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 p-8 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/dashboard" element={<DashboardView />} />
          <Route path="/businesses" element={<BusinessesView />} />
          <Route path="/jobs" element={<JobsView />} />
          <Route path="/config" element={<ConfigView />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
}

export default App;
