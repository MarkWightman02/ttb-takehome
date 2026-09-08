import { BackendHealth } from './components/BackendHealth';

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
            A standalone prototype to help reviewers compare alcohol label
            information with application data.
          </p>
        </div>

        <aside className="prototype-note" aria-labelledby="preview-title">
          <h2 id="preview-title">Foundation preview</h2>
          <p>
            This version shows the application layout. Entering data, uploading
            labels and verifying labels are not available yet.
          </p>
        </aside>

        <ol className="review-steps" aria-label="Planned label review workflow">
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
          <li>
            <section className="step-card" aria-labelledby="upload-title">
              <div className="step-heading">
                <span className="step-number" aria-hidden="true">
                  2
                </span>
                <h2 id="upload-title">Label upload</h2>
                <span className="planned-label">Planned</span>
              </div>
              <p>
                Add an image of one alcohol label to review alongside the
                application details.
              </p>
              <div className="placeholder upload-placeholder">
                <p>Label upload is not available yet</p>
              </div>
            </section>
          </li>
          <li className="results-step">
            <section className="step-card" aria-labelledby="results-title">
              <div className="step-heading">
                <span className="step-number" aria-hidden="true">
                  3
                </span>
                <h2 id="results-title">Verification results</h2>
                <span className="planned-label">Planned</span>
              </div>
              <p>
                Review comparisons and clear explanations of any differences or
                items that need attention.
              </p>
              <div className="placeholder results-placeholder">
                <p>No verification has been performed.</p>
                <p>
                  Results will appear here once label verification is
                  implemented.
                </p>
              </div>
            </section>
          </li>
        </ol>
      </main>

      <footer className="page-width site-footer">
        <p>
          Standalone prototype. No label files are collected in this version.
        </p>
        {import.meta.env.DEV && <BackendHealth />}
      </footer>
    </>
  );
}
