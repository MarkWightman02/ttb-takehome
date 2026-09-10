import { useState } from 'react';
import { BackendHealth } from './components/BackendHealth';
import { BatchVerificationWorkflow } from './components/BatchVerificationWorkflow';
import { LabelOcrWorkflow } from './components/LabelOcrWorkflow';

export default function App() {
  const [workflow, setWorkflow] = useState<'single' | 'batch'>('single');
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="site-header">
        <div className="page-width masthead">
          <span className="wordmark">TTB</span>
          <span>Label review prototype</span>
        </div>
      </header>

      <main id="main-content" className="page-width" tabIndex={-1}>
        <div className="page-intro">
          <p className="eyebrow">
            {workflow === 'single'
              ? 'Single-label review'
              : 'Optional batch review'}
          </p>
          <h1>Verify label artwork against application data</h1>
          <p className="lede">
            Enter the values from the COLA application, then upload the
            submitted label artwork. The tool extracts label information and
            highlights matches, discrepancies, and items requiring manual
            review.
          </p>
        </div>

        <aside className="prototype-note" aria-labelledby="preview-title">
          <h2 id="preview-title">Reviewer decision support</h2>
          <p>
            Results identify matches, differences, and uncertain evidence for
            manual review. They do not approve, reject, or determine legal
            compliance.
          </p>
        </aside>

        <nav className="workflow-selector" aria-label="Verification workflow">
          <button
            type="button"
            aria-pressed={workflow === 'single'}
            onClick={() => setWorkflow('single')}
          >
            Single label
          </button>
          <button
            type="button"
            aria-pressed={workflow === 'batch'}
            onClick={() => setWorkflow('batch')}
          >
            Batch verification
          </button>
        </nav>

        {workflow === 'single' ? (
          <LabelOcrWorkflow />
        ) : (
          <BatchVerificationWorkflow />
        )}
      </main>

      <footer className="page-width site-footer">
        <p>
          Standalone prototype. Label images are processed for the current
          request and are not retained by the application.
        </p>
        {import.meta.env.DEV && <BackendHealth />}
      </footer>
    </>
  );
}
