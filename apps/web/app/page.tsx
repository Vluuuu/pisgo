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
        <p className="workspace-label">Perencanaan panen</p>
      </header>

      <PredictionWorkflow />

      <footer className="site-footer">
        <p>PisGo · Operasional Cavendish</p>
        <p>Prediksi dan optimasi masih menggunakan model pengembangan.</p>
      </footer>
    </main>
  );
}
