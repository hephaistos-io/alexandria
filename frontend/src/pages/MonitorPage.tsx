import { ClassificationCore } from "../components/monitor/ClassificationCore";
import { EventLog } from "../components/monitor/EventLog";
import { IngestionChart } from "../components/monitor/IngestionChart";
import { MetricsGrid } from "../components/monitor/MetricsGrid";
import { PageHeader } from "../components/monitor/PageHeader";

export function MonitorPage() {
  return (
    <div>
      <PageHeader />
      <div className="grid grid-cols-12 gap-6 px-6 pb-12">
        <IngestionChart />
        <ClassificationCore />
        <EventLog />
        <MetricsGrid />
      </div>
    </div>
  );
}
