/** Signed fixed-point with a true minus sign: +1.20 / −0.40 / 0.00 */
export const sgn = (n: number, d = 2) => (n < 0 ? '−' : n > 0 ? '+' : '') + Math.abs(n).toFixed(d)
/** HH:MM:SS.mmm (UTC) */
export const clk = (ms: number) => new Date(ms).toISOString().slice(11, 23)
/** HH:MM:SS.s (UTC) */
export const clkS = (ms: number) => new Date(ms).toISOString().slice(11, 21)
export const ageStr = (ms: number) =>
  ms < 0 ? '≤0 s (clock skew)'
    : ms < 10000 ? (ms / 1000).toFixed(1) + ' s'
      : ms < 60000 ? Math.floor(ms / 1000) + ' s'
        : Math.floor(ms / 60000) + 'm ' + String(Math.floor(ms / 1000) % 60).padStart(2, '0') + 's'
/** Bearing in degrees clockwise from north for an ENU delta. */
export const bearingDeg = (dx: number, dy: number) => Math.round(((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360)
export const pad3 = (n: number) => String(n).padStart(3, '0')
