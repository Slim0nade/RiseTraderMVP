import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Home,
  Activity,
  TrendingUp,
  Target,
  BarChart3,
  Brain,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/utils/cn';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const navItems = [
  { path: '/', icon: Home, label: 'Dashboard' },
  { path: '/agents', icon: Activity, label: 'Agents' },
  { path: '/market', icon: TrendingUp, label: 'Market Data' },
  { path: '/trading', icon: Target, label: 'Trading' },
  { path: '/strategies', icon: BarChart3, label: 'Strategies' },
  { path: '/forecasts', icon: Brain, label: 'Forecasts' },
  { path: '/performance', icon: BarChart3, label: 'Performance' },
  { path: '/settings', icon: Settings, label: 'Settings' },
];

export const Sidebar: React.FC<SidebarProps> = ({ collapsed, onToggle }) => {
  return (
    <aside
      className={cn(
        'bg-dark-900 border-r border-dark-700 flex flex-col transition-all duration-300',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-dark-700">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-primary-500 to-primary-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-lg">R</span>
            </div>
            <span className="font-bold text-dark-50 text-lg">RiseTrader</span>
          </div>
        )}
        <button
          onClick={onToggle}
          className="p-1.5 hover:bg-dark-800 rounded-lg transition-colors"
        >
          {collapsed ? (
            <ChevronRight className="w-5 h-5 text-dark-400" />
          ) : (
            <ChevronLeft className="w-5 h-5 text-dark-400" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors',
                'hover:bg-dark-800',
                isActive
                  ? 'bg-primary-500/10 text-primary-500'
                  : 'text-dark-400 hover:text-dark-200'
              )
            }
            title={collapsed ? item.label : undefined}
          >
            <item.icon className="w-5 h-5 flex-shrink-0" />
            {!collapsed && <span className="font-medium">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-dark-700">
        {!collapsed && (
          <div className="text-xs text-dark-500">
            <p>Version 1.0.0</p>
            <p className="mt-1">© 2024 RiseTrader</p>
          </div>
        )}
      </div>
    </aside>
  );
};
