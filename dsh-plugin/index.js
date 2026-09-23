import z from '@deepseek-ai/schemastery';

export const Config = z.object({
  environment: z.union(['sandbox', 'production']).default('sandbox').volatile(),
  sandboxSignMode: z.union(['simple', 'standard']).default('simple').volatile(),
  productionSignMode: z.union(['simple', 'standard']).default('simple').volatile(),
});

// This root row owns the live settings namespace and browser page. Tools live
// inside the dedicated agent preset so other presets keep their own catalog.
export function apply() {}
