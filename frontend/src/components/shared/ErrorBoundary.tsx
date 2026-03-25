import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary] Uncaught render error:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="flex flex-col items-center justify-center h-full bg-surface text-on-surface font-mono">
        <div className="bg-surface-container border-l-2 border-error p-8 max-w-xl w-full">
          <p className="text-[10px] text-outline uppercase tracking-widest mb-4">
            System fault
          </p>
          <p className="text-xl font-headline font-black text-on-surface mb-2">
            Render error
          </p>
          <p className="text-sm text-on-surface-variant mb-6 break-words">
            {this.state.error?.message ?? "An unexpected error occurred."}
          </p>
          <div className="flex gap-3">
            <button
              onClick={this.handleReset}
              className="px-4 py-2 text-[10px] uppercase tracking-widest bg-surface-container-high text-on-surface hover:bg-primary hover:text-on-primary transition-colors"
            >
              Try again
            </button>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 text-[10px] uppercase tracking-widest border border-outline-variant text-outline hover:border-primary hover:text-primary transition-colors"
            >
              Reload
            </button>
          </div>
        </div>
      </div>
    );
  }
}
