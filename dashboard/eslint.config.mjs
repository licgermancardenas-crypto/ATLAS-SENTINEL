import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // vendorizado por prebuild (scripts/copiar-worker-maplibre.mjs): es el
    // dist minificado de maplibre, no código propio -- sin esto agrega ~1.076
    // warnings que tapan los que sí importan
    "public/maplibre/**",
  ]),
]);

export default eslintConfig;
