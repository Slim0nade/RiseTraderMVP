import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen bg-dark-950 flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-dark-900 rounded-lg border border-dark-700 p-8 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-danger-500/10 rounded-full mb-4">
              <AlertTriangle className="w-8 h-8 text-danger-500" />
            </div>
            <h2 className="text-2xl font-bold text-dark-50 mb-2">Something went wrong</h2>
            <p className="text-dark-400 mb-6">
              An unexpected error occurred. Please refresh the page or contact support if the
              problem persists.
            </p>
            {this.state.error && (
              <details className="text-left mb-6">
                <summary className="text-sm text-dark-500 cursor-pointer hover:text-dark-400">
                  Error details
                </summary>
                <pre className="mt-2 p-3 bg-dark-950 rounded text-xs text-danger-400 overflow-auto">
                  {this.state.error.toString()}
                </pre>
              </details>
            )}
            <button
              onClick={() => window.location.reload()}
              className="px-6 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors"
            >
              Refresh Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
