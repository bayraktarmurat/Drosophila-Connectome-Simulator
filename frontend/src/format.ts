/** Format a possibly-missing number; null/undefined/NaN become an em dash. */
export function formatNumber(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (!Number.isFinite(value)) {
    if (value > 0) {
      return "+∞";
    }
    return "−∞";
  }
  return value.toFixed(digits);
}

export function formatScientific(value: number): string {
  return value.toExponential(2);
}

export function signLabel(sign: number): string {
  if (sign > 0) {
    return "excitatory";
  }
  if (sign < 0) {
    return "inhibitory";
  }
  return "modulatory";
}

/** Human-readable neuron name: instance (or type) plus bodyId. */
export function neuronName(instance: string, type: string, bodyId: number): string {
  let name = type;
  if (instance.length > 0) {
    name = instance;
  }
  return `${name} (${bodyId})`;
}
