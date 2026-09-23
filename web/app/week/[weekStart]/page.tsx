import { ApiErrorPanel } from "@/components/api-error";
import { WeekView } from "@/components/week-view";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function WeekPage({
  params,
}: {
  params: Promise<{ weekStart: string }>;
}) {
  const { weekStart } = await params;
  try {
    const [week, health] = await Promise.all([api.week(weekStart), api.health()]);
    return <WeekView week={week} today={health.today} modelReady={health.provider_key_configured} />;
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }
}
