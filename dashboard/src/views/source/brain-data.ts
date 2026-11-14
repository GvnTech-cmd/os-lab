import { useSource } from "./client";
import { brainPath } from "./brain-model";
export function useBrainProvider(file?: string) {
  let path = ""; let invalid = false;
  try { if (file) path = brainPath(file); } catch { invalid = true; }
  const state = useSource<Record<string, unknown>>(path);
  return { ...state, unavailable: !file, error: invalid ? "Invalid Brain provider path" : state.error };
}
