import {
  organizationsSchema,
  managedOrganizationSchema,
  type CreateOrganizationForm,
  type EditOrganizationForm,
  type Organization,
} from "../schemas/organizations";
import { apiRequest, apiRequestVoid } from "./client";

export const organizationsQueryKey = ["organizations"] as const;

export function linkNationalOrganization(
  organizationId: number,
  nationalId: string,
  csrfToken: string,
): Promise<Organization> {
  return apiRequest(
    `/organizaciones/${organizationId}/vinculo-nacional`,
    managedOrganizationSchema,
    {
      method: "PATCH",
      headers: { "X-CSRF-Token": csrfToken },
      body: JSON.stringify({ ong_nacional_id: nationalId || null }),
    },
  );
}

export function getOrganizations(): Promise<Organization[]> {
  return apiRequest("/organizaciones", organizationsSchema);
}

export function createOrganization(
  values: CreateOrganizationForm,
  csrfToken: string,
): Promise<Organization> {
  return apiRequest("/organizaciones", managedOrganizationSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({
      ...values,
      email_contacto: values.tipo === "ONG" ? values.email_contacto || null : undefined,
    }),
  });
}

export function updateOrganization(
  organizationId: number,
  values: EditOrganizationForm,
  csrfToken: string,
): Promise<Organization> {
  return apiRequest(
    `/organizaciones/${organizationId}`,
    managedOrganizationSchema,
    {
      method: "PATCH",
      headers: { "X-CSRF-Token": csrfToken },
      body: JSON.stringify(values),
    },
  );
}

export function deactivateOrganization(
  organizationId: number,
  csrfToken: string,
): Promise<void> {
  return apiRequestVoid(`/organizaciones/${organizationId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function reactivateOrganization(
  organizationId: number,
  csrfToken: string,
): Promise<Organization> {
  return apiRequest(
    `/organizaciones/${organizationId}`,
    managedOrganizationSchema,
    {
      method: "PATCH",
      headers: { "X-CSRF-Token": csrfToken },
      body: JSON.stringify({ activa: true }),
    },
  );
}

export function retryNationalProvisioning(
  organizationId: number,
  csrfToken: string,
): Promise<Organization> {
  return apiRequest(
    `/organizaciones/${organizationId}/aprovisionamiento-nacional`,
    managedOrganizationSchema,
    { method: "POST", headers: { "X-CSRF-Token": csrfToken } },
  );
}
