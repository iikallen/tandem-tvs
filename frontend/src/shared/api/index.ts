export interface OrgUnitSummary {
  external_id: string;
  name: string;
  kind: string;
  parent_external_id: string | null;
}

export interface Me {
  portal_id: string;
  full_name: string;
  email: string;
  job_title: string;
  phone: string;
  avatar_url: string;
  org_unit: OrgUnitSummary | null;
  module_roles: string[];
}

export interface Employee {
  portal_id: string;
  full_name: string;
  email: string;
  job_title: string;
  phone: string;
  avatar_url: string;
  org_unit_external_id: string | null;
  roles: string[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw new ApiError(
      response.status,
      body?.error?.code ?? "api_error",
      body?.error?.message ?? response.statusText,
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  me: () => get<Me>("/api/v1/me"),
  employees: (search: string) =>
    get<Employee[]>(
      `/api/v1/organization/employees?search=${encodeURIComponent(search)}`,
    ),
};
