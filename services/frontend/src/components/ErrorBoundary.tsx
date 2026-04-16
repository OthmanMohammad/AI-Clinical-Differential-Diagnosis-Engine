/**
 * Application-level error boundary with recovery.
 *
 * Renders a clean error card instead of the white screen of death, and
 * exposes a "try again" button that remounts the tree.
 */

import * as React from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { logger } from "@/lib/logger";

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  override state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, info: React.ErrorInfo): void {
    logger.error("app.unhandled_error", {
      message: error.message,
      stack: error.stack,
      componentStack: info.componentStack,
    });
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  override render() {
    if (this.state.hasError) {
      return (
        <div className="bg-background flex h-screen w-screen items-center justify-center p-8">
          <div className="border-destructive/40 bg-destructive/5 w-full max-w-md rounded-lg border p-6 shadow-lg">
            <div className="flex items-start gap-3">
              <div className="bg-destructive/15 flex h-10 w-10 shrink-0 items-center justify-center rounded-full">
                <AlertTriangle className="text-destructive h-5 w-5" />
              </div>
              <div className="flex-1">
                <h2 className="text-foreground text-base font-semibold">Something went wrong</h2>
                <p className="text-muted-foreground mt-1 text-xs">
                  The application hit an unexpected error. You can try to recover without reloading
                  the page.
                </p>
                {this.state.error && (
                  <pre className="border-border bg-card text-muted-foreground mt-3 max-h-32 overflow-auto rounded-md border p-2 font-mono text-[10px]">
                    {this.state.error.message}
                  </pre>
                )}
                <div className="mt-4 flex gap-2">
                  <Button size="sm" onClick={this.reset} className="gap-1.5">
                    <RefreshCcw className="h-3 w-3" />
                    Try again
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
                    Reload page
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
