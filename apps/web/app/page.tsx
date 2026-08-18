import { PathIcon } from "@phosphor-icons/react/dist/ssr";
import { PredictionWorkflow } from "@/components/prediction/prediction-workflow";

export default function Home() {
  return (
    <main className="app-shell" id="top">
      <a className="skip-link" href="#controls">Langsung ke kontrol analisis</a>

      <header className="product-bar">
        <a className="brand" href="#top" aria-label="PisGo, kembali ke atas">
          <PathIcon aria-hidden="true" size={18} weight="bold" />
          <span className="brand-name">PisGo</span>
        </a>
        <p className="workspace-label">Perencanaan panen</p>
      </header>

      <PredictionWorkflow />

      <footer className="site-footer">
        <p>PisGo · Operasional Cavendish</p>
        <p>Prototipe: prediksi kematangan masih memakai model dasar, bukan model ML final.</p>
      </footer>
    </main>
  );
}
