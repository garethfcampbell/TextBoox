import { useGenerateIdea, useGenerateBook, useGetJobStatus } from "@workspace/api-client-react";

export function useTextbookIdea() {
  return useGenerateIdea();
}

export function useTextbookGenerator() {
  return useGenerateBook();
}

export function useTextbookJob(jobId: string | null) {
  return useGetJobStatus(jobId || "", {
    query: {
      enabled: !!jobId,
      retry: false, // We handle errors via status text or let polling handle transient 404s
      refetchInterval: (query) => {
        const data = query.state.data as any;
        const status = data?.status;
        // Keep polling while queued, pending, or running
        if (!data || status === 'queued' || status === 'pending' || status === 'running') {
          return 3000;
        }
        return false;
      }
    }
  });
}
