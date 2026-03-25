export function PageHeader() {
  return (
    <div className="px-6 pt-6 pb-4 flex items-start justify-between">
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="font-mono text-[10px] text-tertiary">LIVE_STREAM_v4.2 &gt;</span>
          <div className="w-1.5 h-1.5 bg-tertiary animate-pulse" />
        </div>
        <h1 className="font-headline text-5xl font-black leading-none text-on-surface uppercase">
          Classification &amp;{" "}
          <span className="text-primary-container">Ingestion</span>
        </h1>
      </div>

      <div className="text-right font-mono text-[10px] text-outline space-y-1">
        <p>SYSTEM_UPTIME: 142:08:12</p>
        <p>QUEUE_LATENCY: 4ms</p>
        <p>THREAD_POOL: 8/12</p>
      </div>
    </div>
  );
}
