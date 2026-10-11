import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { session } from "../api/client";
import { authApi, donorApi, notificationApi } from "../api/endpoints";
const queryKeys = {
  me: ["me"],
  notifications: (unreadOnly) => ["notifications", unreadOnly],
  donorProfile: ["donor", "profile"],
  donorMatches: ["donor", "matches"],
  donorResponses: ["donor", "responses"],
  donations: ["donations"],
  subscriptions: ["donor", "subscriptions"],
  conversations: ["conversations"]
};
function useCurrentUser() {
  const enabled = Boolean(session.accessToken());
  const query = useQuery({
    queryKey: queryKeys.me,
    queryFn: authApi.me,
    enabled,
    retry: false,
    staleTime: 6e4
  });
  return {
    user: query.data ?? null,
    isLoading: query.isLoading && enabled,
    error: query.error,
    refetch: query.refetch
  };
}
function useNotifications(enabled) {
  return useQuery({
    queryKey: queryKeys.notifications(false),
    queryFn: () => notificationApi.list(false),
    enabled,
    refetchInterval: 3e4
  });
}
function useDonorProfile() {
  return useQuery({ queryKey: queryKeys.donorProfile, queryFn: donorApi.profile, retry: false });
}
function useDonorMatches(enabled = true) {
  return useQuery({ queryKey: queryKeys.donorMatches, queryFn: donorApi.matchedRequests, enabled });
}
function useDonorResponses(enabled = true) {
  return useQuery({ queryKey: queryKeys.donorResponses, queryFn: donorApi.responses, enabled });
}
function useDonations() {
  return useQuery({ queryKey: queryKeys.donations, queryFn: donorApi.donations });
}
function useAcceptRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, eta, remarks }) => donorApi.accept(requestId, { confirmation: "EXPLICIT", etaMinutes: eta, remarks }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.donorMatches });
      queryClient.invalidateQueries({ queryKey: queryKeys.donorResponses });
    }
  });
}
function useWithdrawResponse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ responseId, reason }) => donorApi.withdraw(responseId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.donorResponses });
      queryClient.invalidateQueries({ queryKey: queryKeys.donorMatches });
    }
  });
}
export {
  queryKeys,
  useAcceptRequest,
  useCurrentUser,
  useDonations,
  useDonorMatches,
  useDonorProfile,
  useDonorResponses,
  useNotifications,
  useWithdrawResponse
};
