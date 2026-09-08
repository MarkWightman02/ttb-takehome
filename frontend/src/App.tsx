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
            Upload one alcohol label image and extract its text using local OCR.
          </p>
        </div>

        <aside className="prototype-note" aria-labelledby="preview-title">
          <h2 id="preview-title">OCR preview</h2>
          <p>
            Image upload and raw text extraction are available. Application data
            entry and compliance verification are not implemented yet.
          </p>
        </aside>

        <ol className="review-steps" aria-label="Label OCR workflow">
          <li>
            <section className="step-card" aria-labelledby="application-title">
              <div className="step-heading">
                <span className="step-number" aria-hidden="true">
                  1
                </span>
                <h2 id="application-title">Application data</h2>
                <span className="planned-label">Planned</span>
              </div>
              <p>
                Enter the brand name, alcohol content and other details from the
                application for comparison with the label.
              </p>
              <div className="placeholder">
                <p>Application-data form coming next</p>
              </div>
            </section>
          </li>
          <LabelOcrWorkflow />
        </ol>
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
