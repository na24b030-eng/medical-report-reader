import sharp from "sharp";
import { mkdir } from "node:fs/promises";
await mkdir("samples", { recursive: true });
const svg = `<svg width="1200" height="400" xmlns="http://www.w3.org/2000/svg"><rect width="1200" height="400" fill="white"/><g font-family="Arial" fill="#253c33"><text x="60" y="80" font-size="35">CBC</text><text x="60" y="180" font-size="28">Hemoglobin 10.2 g/dL (Low) Reference: 12.0-15.0</text><text x="60" y="260" font-size="28">WBC 11,200 /uL (High) Reference: 4000-11000</text></g></svg>`;
await sharp(Buffer.from(svg)).png().toFile("samples/report.png");
