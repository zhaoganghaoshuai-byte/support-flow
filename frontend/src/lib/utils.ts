import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function externalSourceUrl(value?: string | null) {
  if (!value) return undefined;
  try {
    const parsed = new URL(value);
    return !parsed.username &&
      !parsed.password &&
      (parsed.protocol === "https:" || parsed.protocol === "http:")
      ? parsed.href
      : undefined;
  } catch {
    return undefined;
  }
}
