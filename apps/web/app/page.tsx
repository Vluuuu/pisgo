import { PathIcon } from "@phosphor-icons/react/dist/ssr";
import { PredictionWorkflow } from "@/components/prediction/prediction-workflow";

export default function Home() {
  return (
    <main className="app-shell" id="top">
      <a className="skip-link" href="#controls">Skip to analysis controls</a>

      <header className="product-bar">
        <a className="brand" href="#top" aria-label="PisGo, back to top">
          <PathIcon aria-hidden="true" size={18} weight="bold" />
          <span className="brand-name">PisGo</span>
        </a>
        <p className="workspace-label">Harvest planning</p>
      </header>

      <PredictionWorkflow />

      <footer className="site-footer">
        <p>PisGo · Cavendish operations</p>
        <p>Prediction and optimizer use development baselines.</p>
      </footer>
    </main>
  );
}
