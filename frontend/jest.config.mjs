/**
 * Jest, driven through Next's own transform.
 *
 * `next/jest` is what makes the two toolchains agree: it compiles tests with the same
 * SWC configuration that compiles the application, and stubs the things a browser has
 * and a test runner does not (CSS imports, `next/font`, static assets). Writing a
 * hand-rolled babel or ts-jest transform instead is the fast way to a suite that passes
 * on code the build rejects.
 *
 * The `@/*` alias is mapped here rather than inherited from tsconfig.json. It has to be:
 * SWC rewrites nothing, so Jest's own resolver is what sees `@/lib/api`, and without the
 * mapping `jest.mock("@/lib/api")` fails with "cannot find module" while the plain
 * import beside it appears to work.
 *
 * `.mjs` rather than `.ts`, matching eslint.config.mjs: a TypeScript config file needs a
 * loader that has to be installed and kept in step with Jest, and the config is fifteen
 * lines of data.
 */

import nextJest from "next/jest.js";

const createJestConfig = nextJest({ dir: "./" });

/** @type {import('jest').Config} */
const config = {
  testEnvironment: "jsdom",

  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },

  // After the environment exists, not before: it registers jest-dom's matchers on the
  // `expect` the tests use, and it patches browser APIs onto a jsdom `window` that
  // `setupFiles` would run too early to see.
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],

  testPathIgnorePatterns: ["/node_modules/", "/.next/"],

  // Tests live beside the code they test. A separate __tests__ tree drifts out of step
  // with a rename, and this project renames things.
  testMatch: ["**/*.test.ts", "**/*.test.tsx"],

  collectCoverageFrom: [
    "src/**/*.{ts,tsx}",
    "!src/**/*.test.{ts,tsx}",
    "!src/components/ui/**",
    "!src/app/**/layout.tsx",
  ],
};

export default createJestConfig(config);
