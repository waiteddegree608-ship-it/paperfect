import React, { Component, ErrorInfo, ReactNode } from "react";

interface Props { children: ReactNode; }
interface State { hasError: boolean; error: Error | null; }

export class ErrorBoundary extends Component<Props, State> {
  public state: State = { hasError: false, error: null };
  public static getDerivedStateFromError(error: Error): State { return { hasError: true, error }; }
  public componentDidCatch(error: Error, errorInfo: ErrorInfo) { console.error("Uncaught error:", error, errorInfo); }
  public render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "20px", color: "red", background: "black", height: "100vh" }}>
          <h1>Runtime Crash Occurred</h1>
          <pre style={{ whiteSpace: "pre-wrap" }}>{this.state.error?.toString()}</pre>
          <pre style={{ whiteSpace: "pre-wrap", marginTop: "10px", fontSize: "12px", color: "#ccc" }}>{this.state.error?.stack}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}
