import Link from "next/link";
import { ApiErrorPanel } from "@/components/api-error";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/empty";
import { api } from "@/lib/api";
import { formatDate, formatTimestamp } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function ReviewsPage() {
  let reviews;
  try {
    reviews = await api.reviews();
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Review history</h1>
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Each week&apos;s written review, with the numbers it was written against.
        </p>
      </div>

      {reviews.length === 0 ? (
        <Empty
          title="No weeks reviewed yet"
          hint="Reviews are generated from the week screen; that arrives in W4."
        />
      ) : (
        <div className="space-y-4">
          {reviews.map((review) => (
            <Card key={review.week_start}>
              <CardHeader>
                <CardTitle>
                  <Link href={`/week/${review.week_start}`} className="hover:underline">
                    Week of {formatDate(review.week_start)}
                  </Link>
                </CardTitle>
                <span className="text-xs text-neutral-500 dark:text-neutral-400">
                  {review.achieved_count}/{review.measurable_count} goals ·{" "}
                  {review.unplanned_count} unplanned · written{" "}
                  {formatTimestamp(review.generated_at)}
                </span>
              </CardHeader>
              <CardBody>
                <div className="text-sm whitespace-pre-wrap">{review.summary}</div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
