import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode; fallback: (error: Error) => ReactNode };
type State = { error: Error | null };

export default class MapLoadBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ChainSight] Map component failed to render or load its chunk.", error, info.componentStack);
  }

  render() {
    return this.state.error ? this.props.fallback(this.state.error) : this.props.children;
  }
}
