import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Condensed } from "next/font/google";
import "leaflet/dist/leaflet.css";
import "./globals.css";

const ibmPlexSans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-ibm-plex-sans", display: "swap" });
const ibmPlexSansCondensed = IBM_Plex_Sans_Condensed({ subsets: ["latin"], weight: ["600", "700"], variable: "--font-ibm-plex-sans-condensed", display: "swap" });
const ibmPlexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-ibm-plex-mono", display: "swap" });

export const metadata: Metadata = {
  title: "PisGo | Cavendish Decision Tool",
  description: "Plan Cavendish harvest and shipping from fruit age, visual maturity, target maturity, and route duration.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body className={`${ibmPlexSans.variable} ${ibmPlexSansCondensed.variable} ${ibmPlexMono.variable}`}>{children}</body>
    </html>
  );
}
