/**
 * Generates a random 6-digit uppercase hex color string (without the # prefix).
 *
 * Example output: "A3F21C"
 *
 * This is used to pre-populate color fields in forms so every new entity or
 * role type gets a distinct default color without the user having to type one.
 */
export function randomColor(): string {
  return Math.floor(Math.random() * 0xffffff)
    .toString(16)
    .padStart(6, "0")
    .toUpperCase();
}
