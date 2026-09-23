import { ApiErrorPanel } from "@/components/api-error";
import { WeekView } from "@/components/week-view";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function CurrentWeekPage() {
  try {
    // "This week" and "today" both come from the server (API-3): a browser in
    // another timezone must not disagree with the agents about which week it is.
    const [week, health] = await Promise.all([api.currentWeek(), api.health()]);
    return <WeekView week={week} today={health.today} modelReady={health.provider_key_configured} />;
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }
}
