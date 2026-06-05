import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const src = resolve(__dirname, "..", "..", "src", "openval");
const dst = resolve(__dirname, "..", "api", "openval");

if (!existsSync(src)) {
  console.error(`copy-openval: source not found at ${src}`);
  process.exit(1);
}
rmSync(dst, { recursive: true, force: true });
cpSync(src, dst, { recursive: true });
console.log(`copy-openval: ${src} -> ${dst}`);
