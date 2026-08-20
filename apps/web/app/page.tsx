import Image from "next/image";
import { PredictionWorkflow } from "@/components/prediction/prediction-workflow";

export default function Home() {
  return (
    <main className="app-shell" id="top">
      <a className="skip-link" href="#controls">Langsung ke kontrol analisis</a>

      <header className="product-bar">
        <a className="brand" href="#top" aria-label="PisGo, kembali ke atas">
          <Image
            src="/brand/pisgo-mark.svg"
            alt=""
            width={32}
            height={30}
            className="brand-mark"
            priority
          />
          <Image
            src="/brand/pisgo-wordmark.svg"
            alt="PisGo"
            width={96}
            height={31}
            className="brand-wordmark"
            priority
          />
        </a>
      </header>

      <PredictionWorkflow />

      <footer className="site-footer">
        <div className="footer-brand">
          <Image
            src="/brand/pisgo-mark.svg"
            alt=""
            width={20}
            height={19}
            className="footer-mark"
            aria-hidden="true"
          />
          <p>PisGo · Sistem Keputusan Panen & Logistik Pisang Cavendish</p>
        </div>
        <p className="footer-note">Prototipe pengembangan: prediksi kematangan masih menggunakan model dasar pengembangan.</p>
      </footer>
    </main>
  );
}
