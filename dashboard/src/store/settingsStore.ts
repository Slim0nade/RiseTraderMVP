import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { UserSettings } from '@/types';

interface SettingsState extends UserSettings {
  updateSettings: (settings: Partial<UserSettings>) => void;
  resetSettings: () => void;
}

const defaultSettings: UserSettings = {
  theme: 'dark',
  default_symbol: 'CrudeOIL',
  default_timeframe: 'M1',
  notifications_enabled: true,
  alert_settings: {
    pnl_threshold: 1000,
    risk_alerts: true,
    agent_errors: true,
  },
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      ...defaultSettings,

      updateSettings: (settings) =>
        set((state) => ({
          ...state,
          ...settings,
        })),

      resetSettings: () => set(defaultSettings),
    }),
    {
      name: 'risetrader-settings',
    }
  )
);
