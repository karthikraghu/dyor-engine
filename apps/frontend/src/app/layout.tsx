import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trader Engine",
  description: "Local dashboard for strategy decisions and sandbox backtests.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
