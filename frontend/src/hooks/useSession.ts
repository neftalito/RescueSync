import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { getSession } from "../api/auth";
import type { Session } from "../schemas/auth";

export const sessionQueryKey = ["session"] as const;

export function useSession(): UseQueryResult<Session, Error> {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: getSession,
    retry: false,
    staleTime: 60_000,
  });
}
