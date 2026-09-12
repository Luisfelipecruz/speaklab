import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// Next's own flat configs: its rules, React's and React Hooks', with the Core Web Vitals
// rules as errors, and typescript-eslint's recommended rules on top.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // Two rules React Hooks' recommended set takes from the React Compiler: no ref read or
    // written during render, and no state set synchronously inside an effect. This code is
    // written to the rules of hooks and exhaustive dependencies, which stay on; adopting
    // the compiler's rules means rewriting the recorders and the hooks they flag, and is a
    // change of its own.
    rules: {
      "react-hooks/refs": "off",
      "react-hooks/set-state-in-effect": "off",
    },
  },
  globalIgnores(["node_modules/**", ".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);

export default eslintConfig;
