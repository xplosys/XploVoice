import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#eef4ff", 100: "#dbe6ff", 500: "#3b5bfd", 600: "#2f47e0", 700: "#2438b5", 900: "#141f5c" },
      },
    },
  },
  plugins: [],
} satisfies Config;
