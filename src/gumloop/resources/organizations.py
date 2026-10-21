from __future__ import annotations

from typing import Literal

from gumloop._http import AsyncHttpClient
from gumloop._http import HttpClient
from gumloop.types import AuditLogsResponse
from gumloop.types import DataExport
from gumloop.types import DataExportDownload
from gumloop.types import DataExportRequest
from gumloop.types import MembershipResponse
from gumloop.types import OrganizationsResponse
from gumloop.types import RoleCreditLimit
from gumloop.types import RoleCreditLimitsResponse


def _audit_params(
    organization_id: str,
    start_time: str,
    end_time: str,
    page: int,
    page_size: int,
    event_types: list[str] | None,
    user_ids: list[str] | None,
    ip_addresses: list[str] | None,
    workspace_ids: list[str] | None,
    entity_ids: list[str] | None,
) -> dict:
    return {
        "organization_id": organization_id,
        "start_time": start_time,
        "end_time": end_time,
        "page": page,
        "page_size": page_size,
        **{
            key: ",".join(value)
            for key, value in {
                "event_types": event_types,
                "user_ids": user_ids,
                "ip_addresses": ip_addresses,
                "workspace_ids": workspace_ids,
                "entity_ids": entity_ids,
            }.items()
            if value is not None
        },
    }


class Organizations:
    """Organization administration. Requires personal API key or OAuth; team keys are unsupported.

    Reads of credit limits require view_permission_groups; writes and role membership require
    manage_permission_groups. Audit reads require view_audit_logs. Workspace membership requires
    project add/remove_member or organization manage_project_access, with role-ceiling checks.
    Exports require export_personal_data or export_org_data and the applicable plan.
    """

    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def list(self) -> OrganizationsResponse:
        return OrganizationsResponse.model_validate(self._client.get("organizations"))

    def list_role_credit_limits(
        self, organization_id: str, *, page_size: int = 20, cursor: str | None = None
    ) -> RoleCreditLimitsResponse:
        return RoleCreditLimitsResponse.model_validate(
            self._client.get(
                f"organizations/{organization_id}/roles/credit-limits",
                params={"page_size": page_size, "cursor": cursor},
            )
        )

    def get_role_credit_limit(self, organization_id: str, role_id: str) -> RoleCreditLimit:
        return RoleCreditLimit.model_validate(
            self._client.get(f"organizations/{organization_id}/roles/{role_id}/credit-limit")
        )

    def set_role_credit_limit(
        self, organization_id: str, role_id: str, monthly_credit_limit: int | None
    ) -> RoleCreditLimit:
        """Set a monthly per-member cap; None clears the role's cap."""
        return RoleCreditLimit.model_validate(
            self._client.put(
                f"organizations/{organization_id}/roles/{role_id}/credit-limit",
                json={"monthly_credit_limit": monthly_credit_limit},
            )
        )

    def audit_logs(
        self,
        organization_id: str,
        *,
        start_time: str,
        end_time: str,
        page: int = 1,
        page_size: int = 50,
        event_types: list[str] | None = None,
        user_ids: list[str] | None = None,
        ip_addresses: list[str] | None = None,
        workspace_ids: list[str] | None = None,
        entity_ids: list[str] | None = None,
    ) -> AuditLogsResponse:
        return AuditLogsResponse.model_validate(
            self._client.get(
                "get_audit_logs",
                params=_audit_params(
                    organization_id,
                    start_time,
                    end_time,
                    page,
                    page_size,
                    event_types,
                    user_ids,
                    ip_addresses,
                    workspace_ids,
                    entity_ids,
                ),
            )
        )

    def manage_workspace_user(
        self,
        organization_id: str,
        workspace_id: str,
        user_email: str,
        *,
        action: Literal["add", "remove"],
        is_admin: bool = False,
    ) -> MembershipResponse:
        return MembershipResponse.model_validate(
            self._client.post(
                "manage_workspace_users",
                json={
                    "organization_id": organization_id,
                    "workspace_id": workspace_id,
                    "user_email": user_email,
                    "action": action,
                    "is_admin": is_admin,
                },
            )
        )

    def manage_role_user(
        self, organization_id: str, role_id: str, user_email: str, *, action: Literal["add", "remove"]
    ) -> MembershipResponse:
        return MembershipResponse.model_validate(
            self._client.post(
                "manage_permission_group_users",
                json={
                    "organization_id": organization_id,
                    "group_id": role_id,
                    "user_email": user_email,
                    "action": action,
                },
            )
        )

    def export_data(self, request: DataExportRequest) -> DataExport:
        """Create an export with explicit personal/organization scope. No audit-log exports."""
        return DataExport.model_validate(self._client.post("export_data", json=request.model_dump(exclude_none=True)))

    def export_status(self, export_id: str, *, download_url: bool = False) -> DataExport | DataExportDownload:
        """Get status, or request a short-lived URL once completed. Only the creator can read it."""
        result = self._client.get(
            "export_status", params={"data_export_id": export_id, "download_url": str(download_url).lower()}
        )
        return (
            DataExportDownload.model_validate(result) if "download_url" in result else DataExport.model_validate(result)
        )


class AsyncOrganizations:
    """Organization administration. Requires personal API key or OAuth; team keys are unsupported.

    Reads of credit limits require view_permission_groups; writes and role membership require
    manage_permission_groups. Audit reads require view_audit_logs. Workspace membership requires
    project add/remove_member or organization manage_project_access, with role-ceiling checks.
    Exports require export_personal_data or export_org_data and the applicable plan.
    """

    def __init__(self, client: AsyncHttpClient) -> None:
        self._client = client

    async def list(self) -> OrganizationsResponse:
        return OrganizationsResponse.model_validate(await self._client.get("organizations"))

    async def list_role_credit_limits(
        self, organization_id: str, *, page_size: int = 20, cursor: str | None = None
    ) -> RoleCreditLimitsResponse:
        return RoleCreditLimitsResponse.model_validate(
            await self._client.get(
                f"organizations/{organization_id}/roles/credit-limits",
                params={"page_size": page_size, "cursor": cursor},
            )
        )

    async def get_role_credit_limit(self, organization_id: str, role_id: str) -> RoleCreditLimit:
        return RoleCreditLimit.model_validate(
            await self._client.get(f"organizations/{organization_id}/roles/{role_id}/credit-limit")
        )

    async def set_role_credit_limit(
        self, organization_id: str, role_id: str, monthly_credit_limit: int | None
    ) -> RoleCreditLimit:
        """Set a monthly per-member cap; None clears the role's cap."""
        return RoleCreditLimit.model_validate(
            await self._client.put(
                f"organizations/{organization_id}/roles/{role_id}/credit-limit",
                json={"monthly_credit_limit": monthly_credit_limit},
            )
        )

    async def audit_logs(
        self,
        organization_id: str,
        *,
        start_time: str,
        end_time: str,
        page: int = 1,
        page_size: int = 50,
        event_types: list[str] | None = None,
        user_ids: list[str] | None = None,
        ip_addresses: list[str] | None = None,
        workspace_ids: list[str] | None = None,
        entity_ids: list[str] | None = None,
    ) -> AuditLogsResponse:
        return AuditLogsResponse.model_validate(
            await self._client.get(
                "get_audit_logs",
                params=_audit_params(
                    organization_id,
                    start_time,
                    end_time,
                    page,
                    page_size,
                    event_types,
                    user_ids,
                    ip_addresses,
                    workspace_ids,
                    entity_ids,
                ),
            )
        )

    async def manage_workspace_user(
        self,
        organization_id: str,
        workspace_id: str,
        user_email: str,
        *,
        action: Literal["add", "remove"],
        is_admin: bool = False,
    ) -> MembershipResponse:
        return MembershipResponse.model_validate(
            await self._client.post(
                "manage_workspace_users",
                json={
                    "organization_id": organization_id,
                    "workspace_id": workspace_id,
                    "user_email": user_email,
                    "action": action,
                    "is_admin": is_admin,
                },
            )
        )

    async def manage_role_user(
        self, organization_id: str, role_id: str, user_email: str, *, action: Literal["add", "remove"]
    ) -> MembershipResponse:
        return MembershipResponse.model_validate(
            await self._client.post(
                "manage_permission_group_users",
                json={
                    "organization_id": organization_id,
                    "group_id": role_id,
                    "user_email": user_email,
                    "action": action,
                },
            )
        )

    async def export_data(self, request: DataExportRequest) -> DataExport:
        """Create an export with explicit personal/organization scope. No audit-log exports."""
        return DataExport.model_validate(
            await self._client.post("export_data", json=request.model_dump(exclude_none=True))
        )

    async def export_status(self, export_id: str, *, download_url: bool = False) -> DataExport | DataExportDownload:
        """Get status, or request a short-lived URL once completed. Only the creator can read it."""
        result = await self._client.get(
            "export_status", params={"data_export_id": export_id, "download_url": str(download_url).lower()}
        )
        return (
            DataExportDownload.model_validate(result) if "download_url" in result else DataExport.model_validate(result)
        )
