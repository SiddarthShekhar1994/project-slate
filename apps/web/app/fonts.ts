import { Caveat, Manrope, STIX_Two_Text } from "next/font/google";

export const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });
export const stix = STIX_Two_Text({
  subsets: ["latin"],
  variable: "--font-stix",
  display: "swap",
  style: ["normal", "italic"],
});
export const caveat = Caveat({ subsets: ["latin"], variable: "--font-caveat", display: "swap" });
