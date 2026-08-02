/** The K-OS mark — shattered fragments resolving into a knowledge graph.
 *
 *  Used everywhere the brand appears inside the app. The launcher icons carry
 *  a dark rounded tile, which is right on a taskbar and wrong on a surface
 *  that is already dark, so this draws the transparent version.
 *
 *  `busy` is why this replaced a spinning CSS ring rather than simply sitting
 *  beside it: the menu bar's old orb doubled as the agent-activity indicator,
 *  and dropping it would have removed a real signal. The glow carries it now.
 */
export default function Mark({ size = 16, busy = false, title }: {
  size?: number;
  busy?: boolean;
  title?: string;
}) {
  return (
    <img
      src="/k-os-mark.png"
      width={size}
      height={size}
      alt={title ?? ""}
      aria-hidden={title ? undefined : true}
      className={busy ? "kos-mark busy" : "kos-mark"}
      style={{ display: "block", flex: "none" }}
      draggable={false}
    />
  );
}
