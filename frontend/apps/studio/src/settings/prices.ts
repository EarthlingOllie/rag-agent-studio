import type { Schemas } from "@studio/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { failed } from "./credentials";

export type CredentialPrices = Schemas["CredentialPricesOut"];
export type ModelPrices = Schemas["ModelPricesOut"];
export type PriceOverride = Schemas["OverridePricesRequest"];
export type PriceKind = "input" | "output" | "cached_input";

export const PRICE_KINDS: { kind: PriceKind; name: string }[] = [
  { kind: "input", name: "Input" },
  { kind: "output", name: "Output" },
  { kind: "cached_input", name: "Cached input" },
];

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 6 });

/** A price as the API gives it (a decimal string, US dollars per million tokens), for people. */
export function formatPrice(amount: string): string {
  return money.format(Number(amount));
}

/** A price an Owner typed: blank keeps the platform's (null), otherwise up to six decimals. */
export function parsePrice(typed: string): string | null | undefined {
  const trimmed = typed.trim();
  if (trimmed === "") return null;
  return /^\d{1,6}(\.\d{1,6})?$/.test(trimmed) ? trimmed : undefined;
}

const pricesKey = (organisationId: string, credentialId: string) => ["credential-prices", organisationId, credentialId] as const;

export function useCredentialPrices(organisationId: string, credentialId: string) {
  return useQuery({
    queryKey: pricesKey(organisationId, credentialId),
    queryFn: async (): Promise<CredentialPrices> => {
      const { data, error, response } = await api.GET("/api/organisations/{organisation_id}/credentials/{credential_id}/prices", {
        params: { path: { organisation_id: organisationId, credential_id: credentialId } },
      });
      if (!data) throw failed(response, error);
      return data;
    },
  });
}

export function useOverridePrices(organisationId: string, credentialId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: PriceOverride): Promise<ModelPrices> => {
      const { data, error, response } = await api.PUT("/api/organisations/{organisation_id}/credentials/{credential_id}/prices", {
        params: { path: { organisation_id: organisationId, credential_id: credentialId } },
        body,
      });
      if (!data) throw failed(response, error);
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData<CredentialPrices>(pricesKey(organisationId, credentialId), (listed) =>
        listed && { ...listed, models: listed.models.map((row) => (row.model === saved.model ? saved : row)) },
      );
    },
  });
}
