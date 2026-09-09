import { BackendHealth } from './components/BackendHealth';
import { LabelOcrWorkflow } from './components/LabelOcrWorkflow';

export default function App() {
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
          <p className="eyebrow">Single-label review</p>
          <h1>TTB Label Verification</h1>
          <p className="lede">
            Compare application data and review Government Health Warning
            evidence from one alcohol label image.
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

        <LabelOcrWorkflow />
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
