/**
 * Generic schema registry table.
 *
 * Renders the standard Descriptor / Definition_Node / Status / Actions table
 * that appears in the Classification, Attribution, and Affiliation schema tabs.
 *
 * All three versions share the same four core columns. The Affiliation version
 * adds a "Directed" column between Description and Status. This is handled via
 * the `extraColumns` escape hatch: an ordered list of { header, renderCell }
 * pairs that are inserted before the fixed Status + Actions columns.
 *
 * Usage (basic — Classification / Attribution):
 *   <RegistryTable
 *     items={labels}
 *     loading={loading}
 *     title="Registry_Interface"
 *     headerIcon="terminal"
 *     emptyMessage="NO_ENTRIES — DEPLOY FIRST ENTITY TO INITIALISE REGISTRY"
 *     getId={(l) => l.id}
 *     getName={(l) => l.name}
 *     getDescription={(l) => l.description}
 *     getColor={(l) => l.color}
 *     getEnabled={(l) => l.enabled}
 *     onToggleEnabled={...}
 *     onDelete={...}
 *   />
 *
 * Usage (with extra column — Affiliation):
 *   <RegistryTable
 *     ...
 *     extraColumns={[{
 *       header: "Directed",
 *       align: "center",
 *       renderCell: (rt) => <MaterialIcon name={rt.directed ? "arrow_forward" : "swap_horiz"} />,
 *     }]}
 *   />
 */

import { useState } from "react";
import { MaterialIcon } from "../MaterialIcon";

export interface ExtraColumn<T> {
  header: string;
  /** Horizontal alignment of both the <th> and <td>. Defaults to "left". */
  align?: "left" | "center" | "right";
  renderCell: (item: T) => React.ReactNode;
}

export interface RegistryTableProps<T> {
  items: T[];
  loading: boolean;
  /** Displayed in the header bar, e.g. "Registry_Interface", "Role_Registry" */
  title: string;
  /** Material icon name shown next to the title, e.g. "terminal", "hub", "account_tree" */
  headerIcon: string;
  /** Text shown in the empty-state row, e.g. "NO_ENTRIES — DEPLOY FIRST ENTITY TO INITIALISE REGISTRY" */
  emptyMessage: string;
  /** Numeric ID accessor used as the React key and for delete callbacks. */
  getId: (item: T) => number;
  /** Name accessor — rendered as the primary label in the Descriptor cell. */
  getName: (item: T) => string;
  /** Description accessor — rendered in the Definition_Node cell. */
  getDescription: (item: T) => string;
  /**
   * Color accessor — returns a hex string with or without a leading `#`.
   * Used for the color-bar accent and the status badge styling.
   */
  getColor: (item: T) => string;
  /** Enabled accessor — controls the ACTIVE / DISABLED status badge. */
  getEnabled: (item: T) => boolean;
  /**
   * Optional extra columns inserted between the Definition_Node column and
   * the Status column. Use this for domain-specific fields like "Directed".
   */
  extraColumns?: ExtraColumn<T>[];
  onToggleEnabled: (item: T) => void;
  onDelete: (id: number) => Promise<boolean>;
}

export function RegistryTable<T>({
  items,
  loading,
  title,
  headerIcon,
  emptyMessage,
  getId,
  getName,
  getDescription,
  getColor,
  getEnabled,
  extraColumns = [],
  onToggleEnabled,
  onDelete,
}: RegistryTableProps<T>) {
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleDelete(id: number) {
    setDeletingId(id);
    await onDelete(id);
    setDeletingId(null);
  }

  // Total column count: Descriptor + Definition_Node + extras + Status + Actions
  const totalColumns = 4 + extraColumns.length;

  return (
    <div className="bg-surface-container-low min-h-full flex flex-col">
      {/* Header bar */}
      <div className="p-6 border-b border-outline-variant/10 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <MaterialIcon name={headerIcon} className="text-primary" />
          <h2 className="font-headline text-xl tracking-tight uppercase font-bold">{title}</h2>
        </div>
        <span className="font-mono text-[10px] text-outline">
          {loading ? "LOADING..." : `${items.length} ENTRIES`}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-surface-container-highest/50">
              <th className="px-6 py-4 font-mono text-[10px] text-outline uppercase tracking-widest border-b border-outline-variant/10">
                Descriptor
              </th>
              <th className="px-6 py-4 font-mono text-[10px] text-outline uppercase tracking-widest border-b border-outline-variant/10">
                Definition_Node
              </th>
              {extraColumns.map((col) => (
                <th
                  key={col.header}
                  className={`px-6 py-4 font-mono text-[10px] text-outline uppercase tracking-widest border-b border-outline-variant/10 ${{ left: "text-left", center: "text-center", right: "text-right" }[col.align ?? "left"]}`}
                >
                  {col.header}
                </th>
              ))}
              <th className="px-6 py-4 font-mono text-[10px] text-outline uppercase tracking-widest border-b border-outline-variant/10 text-right">
                Status
              </th>
              <th className="px-6 py-4 font-mono text-[10px] text-outline uppercase tracking-widest border-b border-outline-variant/10 text-right">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/5">
            {/* Loading state */}
            {loading && items.length === 0 && (
              <tr>
                <td
                  colSpan={totalColumns}
                  className="px-6 py-12 text-center font-mono text-[10px] text-outline uppercase tracking-widest"
                >
                  LOADING_REGISTRY...
                </td>
              </tr>
            )}

            {/* Empty state */}
            {!loading && items.length === 0 && (
              <tr>
                <td
                  colSpan={totalColumns}
                  className="px-6 py-12 text-center font-mono text-[10px] text-outline uppercase tracking-widest"
                >
                  {emptyMessage}
                </td>
              </tr>
            )}

            {/* Data rows */}
            {items.map((item) => {
              const id = getId(item);
              const name = getName(item);
              const description = getDescription(item);
              const colorHex = `#${getColor(item).replace(/^#/, "")}`;
              const enabled = getEnabled(item);

              return (
                <tr
                  key={id}
                  className="hover:bg-surface-container-high transition-colors group"
                >
                  {/* Descriptor: color accent bar + name + ID */}
                  <td className="px-6 py-5">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-2 h-8 shrink-0"
                        style={{ backgroundColor: colorHex }}
                      />
                      <div className="flex flex-col">
                        <span
                          className="font-mono text-sm font-bold tracking-tight"
                          style={{ color: colorHex }}
                        >
                          {name}
                        </span>
                        <span className="font-mono text-[8px] text-outline-variant">
                          ID: {id}
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Description */}
                  <td className="px-6 py-5">
                    <p className="text-xs text-on-surface-variant max-w-xs leading-relaxed">
                      {description}
                    </p>
                  </td>

                  {/* Extra columns (e.g. Directed for Affiliation) */}
                  {extraColumns.map((col) => (
                    <td
                      key={col.header}
                      className={`px-6 py-5 ${{ left: "text-left", center: "text-center", right: "text-right" }[col.align ?? "left"]}`}
                    >
                      {col.renderCell(item)}
                    </td>
                  ))}

                  {/* Status badge */}
                  <td className="px-6 py-5 text-right">
                    {enabled ? (
                      <div
                        className="inline-flex items-center gap-2 px-3 py-1 border"
                        style={{
                          backgroundColor: `${colorHex}1a`,
                          borderColor: `${colorHex}33`,
                        }}
                      >
                        <span className="w-1.5 h-1.5" style={{ backgroundColor: colorHex }} />
                        <span className="font-mono text-[9px]" style={{ color: colorHex }}>
                          ACTIVE
                        </span>
                      </div>
                    ) : (
                      <div className="inline-flex items-center gap-2 px-3 py-1 bg-surface-container-highest border border-outline-variant/30">
                        <span className="w-1.5 h-1.5 bg-outline-variant" />
                        <span className="font-mono text-[9px] text-outline-variant">DISABLED</span>
                      </div>
                    )}
                  </td>

                  {/* Actions */}
                  <td className="px-6 py-5 text-right">
                    <div className="flex justify-end gap-1 opacity-40 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => onToggleEnabled(item)}
                        title={enabled ? "Disable" : "Enable"}
                        className="p-2 hover:bg-surface-container-highest text-outline hover:text-primary transition-colors"
                      >
                        <MaterialIcon
                          name={enabled ? "toggle_on" : "toggle_off"}
                          className="text-sm"
                        />
                      </button>
                      <button
                        onClick={() => handleDelete(id)}
                        disabled={deletingId === id}
                        title="Delete"
                        className="p-2 hover:bg-error/10 text-outline hover:text-error transition-colors disabled:opacity-30"
                      >
                        <MaterialIcon name="delete_outline" className="text-sm" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
