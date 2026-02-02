import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { MainLayout } from './components/layout/MainLayout';

// Pages
import { Dashboard } from './pages/Dashboard';
import { Agents } from './pages/Agents';
import { AgentChat } from './pages/AgentChat';
import { MarketData } from './pages/MarketData';
import { Trading } from './pages/Trading';
import { Strategies } from './pages/Strategies';
import { Performance } from './pages/Performance';
import { Forecasts } from './pages/Forecasts';
import { Backtesting } from './pages/Backtesting';
import { DataQuality } from './pages/DataQuality';
import { Optimization } from './pages/Optimization';
import { Settings } from './pages/Settings';

// Create query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5000,
    },
  },
});

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route element={<MainLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/agent-chat" element={<AgentChat />} />
              <Route path="/market" element={<MarketData />} />
              <Route path="/trading" element={<Trading />} />
              <Route path="/strategies" element={<Strategies />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/forecasts" element={<Forecasts />} />
              <Route path="/backtesting" element={<Backtesting />} />
              <Route path="/data-quality" element={<DataQuality />} />
              <Route path="/optimization" element={<Optimization />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
          </Routes>
        </BrowserRouter>

        {/* Toast Notifications */}
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: '#1e293b',
              color: '#f1f5f9',
              border: '1px solid #334155',
            },
            success: {
              iconTheme: {
                primary: '#22c55e',
                secondary: '#f1f5f9',
              },
            },
            error: {
              iconTheme: {
                primary: '#ef4444',
                secondary: '#f1f5f9',
              },
            },
          }}
        />
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
