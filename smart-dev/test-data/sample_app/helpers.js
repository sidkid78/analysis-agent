// Small JS helper with a debug statement (intentional).
export function clamp(x, lo, hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

export const formatName = (first, last) => {
  console.log("formatting", first, last); // debug statement (intentional)
  return `${last}, ${first}`;
};
