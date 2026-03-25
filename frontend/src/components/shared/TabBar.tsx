interface Tab<T extends string> {
  value: T;
  label: string;
}

interface TabBarProps<T extends string> {
  tabs: Tab<T>[];
  activeTab: T;
  onTabChange: (tab: T) => void;
}

export function TabBar<T extends string>({ tabs, activeTab, onTabChange }: TabBarProps<T>) {
  return (
    <div className="bg-surface-container-low border-b border-outline-variant/10 px-6 flex items-center gap-0 shrink-0">
      {tabs.map(({ value, label }) => {
        const isActive = activeTab === value;
        return (
          <button
            key={value}
            onClick={() => onTabChange(value)}
            className={
              isActive
                ? "text-primary border-b-2 border-primary h-12 flex items-center px-4 text-xs font-mono tracking-widest uppercase"
                : "text-outline h-12 flex items-center px-4 text-xs font-mono tracking-widest uppercase hover:text-on-surface transition-colors"
            }
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
