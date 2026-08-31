# TASK-B3-SPIKE — OmniRoute TS-Configs ohne vollen Build auswertbar?

## 1. Belegte Aussage: JA (einzeln evaluierbar, ohne vollen Build)

Die Provider-/Model-Configs von OmniRoute sind reines TypeScript unter
`open-sse/config/**` (Repo `diegosouzapw/OmniRoute`). Sie lassen sich ohne
vollstaendigen Produktions-Build (`next build`, `esbuild`-Bundle, `dist/`)
einzeln auswerten — mit `tsx` als Transpile-on-Demand-Loader.

Kommandobeleg (gegen einen sauberen `--depth 1`-Clone ohne `node_modules`,
ohne `dist/`, keine `npm install`):

```
git clone --depth 1 https://github.com/diegosouzapw/OmniRoute.git
cd OmniRoute
echo 'import { PROVIDER_MODELS } from "./open-sse/config/providerModels.ts";
console.log(Object.keys(PROVIDER_MODELS).length);' > _t.ts
npx --yes tsx _t.ts
```

Ausgabe: `229` (Anzahl Provider-Aliase im REGISTRY). Kaltlauf ≈ 3 s,
nur `tsx` wird via `npx --yes` on-demand bezogen.

Verifizierte Einzelwerte (bereits vorhandenes `deepseek-v4-pro`-Binaer-Modell):

```
getProviderModels("deepseek") -> [
  { id:"deepseek-v4-pro",  name:"DeepSeek V4 Pro (0813)", contextLength:1000000,
    maxOutputTokens:384000, supportsReasoning:true,
    supportedThinkingEfforts:["none","low","high","max"], toolCalling:true },
  { id:"deepseek-v4-flash", name:"DeepSeek V4 Flash (0731)", contextLength:1000000,
    maxOutputTokens:384000, supportsReasoning:true, toolCalling:true }
]
getDefaultModel("openai") -> "gpt-5.6"
```

## 2. Alternativweg (nur fuer den Fall "nein" — nicht benoetigt)

Entfaellt: Ergebnis ist "ja".

## 3. Erkenntnis fuer die Integration (nicht Scope, nur Notiz)

- Die Model-Capability-Werte (`contextLength`, `maxInputTokens`,
  `maxOutputTokens`, `toolCalling`, `supportsVision`, `supportsReasoning`,
  `supportedThinkingEfforts`, `targetFormat`, `unsupportedParams`) stecken in
  `RegistryEntry.models[]`, assembliert in
  `open-sse/config/providers/index.ts` -> `REGISTRY`, und werden ueber
  `providerRegistry.ts::generateModels()` in den Lazy-Proxy
  `PROVIDER_MODELS` (providerModels.ts:11) gehoben.
- Zwei Import-Auflagen: (a) Path-Alias `@/* -> ./src/*` (tsconfig.json:19-24)
  fuer `src/shared/network/privateHost` — tsx loest den Alias via tsconfig;
  (b) `.ts`-Suffix-Imports (`allowImportingTsExtensions`) — tsx akzeptiert sie.
- `privateHost.ts` ist bewusst plattform-frei (kein `node:*`-Import, kein
  `@/`-Alias) und daher fuer einen CLI-Dump ohne Browser-Bundle sicher.
