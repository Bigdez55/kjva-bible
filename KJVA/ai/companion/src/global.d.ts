declare global {
  interface Window {
    companion: {
      ask(user: string, message: string): Promise<{
        response: string;
        latency_ms?: number;
        tool_result?: unknown;
        agent?: string;
      }>;
      dismiss(): Promise<boolean>;
      /** Health check for the AI agent runtime (polls /healthz via IPC). */
      healthCheck?(): Promise<{ status: string }>;
    };
  }
}

export {};
