import { Button, Card, DataTable, ErrorState, LoadingState, PageHeader, useToast } from "@bloodlink/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { donorApi } from "../../api/endpoints";
import { useDonorProfile, queryKeys } from "../../app/hooks";
function SubscriptionsPage({ user }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const profile = useDonorProfile();
  const subscriptions = useQuery({
    queryKey: queryKeys.subscriptions,
    queryFn: () => donorApi.subscriptions(),
    retry: false
  });
  const nearby = useQuery({
    queryKey: ["donor", "nearby-hospitals"],
    queryFn: () => donorApi.nearbyHospitals(),
    enabled: Boolean(profile.data)
  });
  const columns = [
    { key: "hospital", header: "Hospital", render: (row) => row.hospitalName ?? "\u2014" },
    { key: "location", header: "Locality", render: (row) => row.locationLabel ?? "\u2014" },
    { key: "groups", header: "Alert groups", render: (row) => row.bloodGroups.length ? row.bloodGroups.join(", ") : "All compatible" },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (row) => <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          try {
            await donorApi.unsubscribe(row.id);
            await queryClient.invalidateQueries({ queryKey: queryKeys.subscriptions });
            toast.success("Unfollowed", `${row.hospitalName} will no longer alert you.`);
          } catch (caught) {
            toast.error("Could not unfollow", caught.message);
          }
        }}
      >
          Unfollow
        </Button>
    }
  ];
  return <><PageHeader
    title="Hospital alerts"
    subtitle="Follow a hospital to hear about its requests that match your group — even when you are not the nearest match."
  /><Card title="Hospitals I follow">{subscriptions.isLoading ? <LoadingState /> : subscriptions.error ? <ErrorState message={subscriptions.error.message} onRetry={() => subscriptions.refetch()} /> : <DataTable
    columns={columns}
    rows={subscriptions.data?.items ?? []}
    rowKey={(row) => row.id}
    emptyTitle="You do not follow any hospital yet"
    emptyHint="Follow the hospitals you would travel for; BloodLink then alerts you on their requests."
  />}</Card><div style={{ marginTop: "var(--bl-space-5)" }}><Card title="Verified hospitals near you" subtitle="Distance is shown as a band; exact locations stay internal.">{!profile.data ? <p className="bl-muted">Create a donor profile to see nearby hospitals.</p> : nearby.isLoading ? <LoadingState /> : <div className="bl-grid-cards">{(nearby.data?.items ?? []).map((hospital) => <Card key={hospital.id} flat title={hospital.name} subtitle={hospital.locationLabel}><div className="bl-row-between"><span className="bl-subtle">{hospital.distanceBand}</span><Button
    variant="outline"
    size="sm"
    onClick={async () => {
      try {
        await donorApi.subscribe(hospital.id, []);
        await queryClient.invalidateQueries({ queryKey: queryKeys.subscriptions });
        toast.success("Following", `You will hear about requests at ${hospital.name}.`);
      } catch (caught) {
        toast.error("Could not follow", caught.message);
      }
    }}
  >
                      Follow
                    </Button></div></Card>)}</div>}</Card></div>{user ? null : null}</>;
}
export {
  SubscriptionsPage
};
