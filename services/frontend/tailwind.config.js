/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        disease: "#7F77DD",
        symptom: "#888780",
        gene: "#1D9E75",
        drug: "#BA7517",
        phenotype: "#378ADD",
        anatomy: "#2D9E5B",
      },
    },
  },
  plugins: [],
};
