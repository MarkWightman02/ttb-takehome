import { useEffect, useState } from 'react';

type ConnectionState = 'checking' | 'available' | 'unavailable';

export function BackendHealth() {
  const [connection, setConnection] = useState<ConnectionState>('checking');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => {
      controller.abort();
      if (active) setConnection('unavailable');
    }, 5_000);

    async function checkHealth() {
      try {
        const response = await fetch('/api/health', {
          signal: controller.signal,
          cache: 'no-store',
        });
        if (!response.ok) throw new Error('Health request failed');

        const result: unknown = await response.json();
        const healthy =
          typeof result === 'object' &&
          result !== null &&
          'status' in result &&
          result.status === 'ok';

        if (active && !controller.signal.aborted) {
          setConnection(healthy ? 'available' : 'unavailable');
        }
      } catch {
        if (active) setConnection('unavailable');
      } finally {
        window.clearTimeout(timeout);
      }
    }

    void checkHealth();
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  const messages: Record<ConnectionState, string> = {
    checking: 'Checking backend connection…',
    available: 'Backend available',
    unavailable: 'Backend unavailable. Start the API, then try again.',
  };

  return (
    <aside
      className="developer-health"
      aria-label="Development connection status"
    >
      <span className="developer-label">Development only</span>
      <p className={`health-message health-${connection}`} role="status">
        {messages[connection]}
      </p>
      <button
        type="button"
        disabled={connection === 'checking'}
        onClick={() => {
          setConnection('checking');
          setAttempt((current) => current + 1);
        }}
      >
        Check connection
      </button>
    </aside>
  );
}
