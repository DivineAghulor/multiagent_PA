import { ApiErrorPanel } from "@/components/api-error";
import {
  DecompositionChat,
  StartExistingDecomposition,
  StartNewDecomposition,
} from "@/components/decomposition-chat";
import { DraftLost } from "@/components/draft-lost";
import { ApiError, api } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * ?session=<id> resumes a draft (so a reload keeps it); ?project=<id> offers
 * to start one for that project; neither starts a new project.
 */
export default async function DecomposePage({
  searchParams,
}: {
  searchParams: Promise<{ session?: string; project?: string }>;
}) {
  const { session: sessionId, project } = await searchParams;

  try {
    const health = await api.health();
    const modelReady = health.provider_key_configured;

    if (sessionId) {
      try {
        const session = await api.decompositionSession(sessionId);
        return <DecompositionChat initial={session} modelReady={modelReady} />;
      } catch (error) {
        if (error instanceof ApiError && error.type === "session_expired") {
          return <DraftLost what="project breakdown" restartHref={project ? `/decompose?project=${project}` : "/decompose"} />;
        }
        throw error;
      }
    }

    if (project) {
      const detail = await api.project(Number(project));
      return (
        <StartExistingDecomposition projectId={detail.id} projectName={detail.name} modelReady={modelReady} />
      );
    }

    return <StartNewDecomposition modelReady={modelReady} />;
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }
}
