import React, { useState } from 'react';
import { Settings as SettingsIcon, Save, Bell, Shield, Moon, Sun } from 'lucide-react';
import { useSettingsStore } from '@/store/settingsStore';
import toast from 'react-hot-toast';

export const Settings: React.FC = () => {
  const settings = useSettingsStore();
  const [apiKey, setApiKey] = useState(settings.api_key || '');
  const [defaultSymbol, setDefaultSymbol] = useState(settings.default_symbol);
  const [defaultTimeframe, setDefaultTimeframe] = useState(settings.default_timeframe);
  const [notificationsEnabled, setNotificationsEnabled] = useState(settings.notifications_enabled);
  const [pnlThreshold, setPnlThreshold] = useState(settings.alert_settings.pnl_threshold);
  const [riskAlerts, setRiskAlerts] = useState(settings.alert_settings.risk_alerts);
  const [agentErrors, setAgentErrors] = useState(settings.alert_settings.agent_errors);

  const handleSave = () => {
    settings.updateSettings({
      api_key: apiKey,
      default_symbol: defaultSymbol,
      default_timeframe: defaultTimeframe,
      notifications_enabled: notificationsEnabled,
      alert_settings: {
        pnl_threshold: pnlThreshold,
        risk_alerts: riskAlerts,
        agent_errors: agentErrors,
      },
    });
    toast.success('Settings saved successfully');
  };

  const handleReset = () => {
    if (confirm('Are you sure you want to reset all settings to defaults?')) {
      settings.resetSettings();
      setApiKey('');
      setDefaultSymbol('CrudeOIL');
      setDefaultTimeframe('M1');
      setNotificationsEnabled(true);
      setPnlThreshold(1000);
      setRiskAlerts(true);
      setAgentErrors(true);
      toast.success('Settings reset to defaults');
    }
  };

  const toggleTheme = () => {
    const newTheme = settings.theme === 'dark' ? 'light' : 'dark';
    settings.updateSettings({ theme: newTheme });
    toast.success(`Theme changed to ${newTheme} mode`);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-dark-50 mb-2">Settings</h1>
        <p className="text-dark-400">Configure your dashboard preferences</p>
      </div>

      {/* API Configuration */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-primary-500/10 rounded-lg">
            <Shield className="w-5 h-5 text-primary-500" />
          </div>
          <h2 className="text-xl font-semibold text-dark-50">API Configuration</h2>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">API Key</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter your API key"
              className="w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-dark-200 placeholder-dark-500 focus:outline-none focus:border-primary-500 transition-colors"
            />
            <p className="text-xs text-dark-500 mt-1">
              Your API key is stored locally and never shared
            </p>
          </div>
        </div>
      </div>

      {/* Display Settings */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-primary-500/10 rounded-lg">
            <SettingsIcon className="w-5 h-5 text-primary-500" />
          </div>
          <h2 className="text-xl font-semibold text-dark-50">Display Settings</h2>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">Theme</label>
            <button
              onClick={toggleTheme}
              className="flex items-center gap-2 px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-dark-200 hover:border-primary-500 transition-colors"
            >
              {settings.theme === 'dark' ? (
                <>
                  <Moon className="w-4 h-4" />
                  <span>Dark Mode</span>
                </>
              ) : (
                <>
                  <Sun className="w-4 h-4" />
                  <span>Light Mode</span>
                </>
              )}
            </button>
          </div>

          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">Default Symbol</label>
            <select
              value={defaultSymbol}
              onChange={(e) => setDefaultSymbol(e.target.value)}
              className="w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-dark-200 focus:outline-none focus:border-primary-500 transition-colors"
            >
              <option value="CrudeOIL">Crude Oil</option>
              <option value="DXY">DXY</option>
              <option value="VIX">VIX</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Default Timeframe
            </label>
            <select
              value={defaultTimeframe}
              onChange={(e) => setDefaultTimeframe(e.target.value)}
              className="w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-dark-200 focus:outline-none focus:border-primary-500 transition-colors"
            >
              <option value="M1">1 Minute</option>
              <option value="M5">5 Minutes</option>
              <option value="M15">15 Minutes</option>
              <option value="H1">1 Hour</option>
            </select>
          </div>
        </div>
      </div>

      {/* Notification Settings */}
      <div className="bg-dark-900 rounded-lg border border-dark-700 p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-primary-500/10 rounded-lg">
            <Bell className="w-5 h-5 text-primary-500" />
          </div>
          <h2 className="text-xl font-semibold text-dark-50">Notifications</h2>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-dark-300">Enable Notifications</p>
              <p className="text-xs text-dark-500">Receive alerts for important events</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={notificationsEnabled}
                onChange={(e) => setNotificationsEnabled(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-dark-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-dark-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
            </label>
          </div>

          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              P&L Alert Threshold ($)
            </label>
            <input
              type="number"
              value={pnlThreshold}
              onChange={(e) => setPnlThreshold(Number(e.target.value))}
              className="w-full px-4 py-2 bg-dark-800 border border-dark-700 rounded-lg text-dark-200 focus:outline-none focus:border-primary-500 transition-colors"
            />
            <p className="text-xs text-dark-500 mt-1">
              Get notified when P&L exceeds this threshold
            </p>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-dark-300">Risk Alerts</p>
              <p className="text-xs text-dark-500">Alerts for risk limit violations</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={riskAlerts}
                onChange={(e) => setRiskAlerts(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-dark-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-dark-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
            </label>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-dark-300">Agent Error Alerts</p>
              <p className="text-xs text-dark-500">Notifications for agent failures</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={agentErrors}
                onChange={(e) => setAgentErrors(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-dark-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-dark-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-500"></div>
            </label>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-6 py-3 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors font-medium"
        >
          <Save className="w-4 h-4" />
          Save Settings
        </button>
        <button
          onClick={handleReset}
          className="px-6 py-3 bg-dark-800 text-dark-300 rounded-lg hover:bg-dark-700 transition-colors font-medium"
        >
          Reset to Defaults
        </button>
      </div>
    </div>
  );
};
