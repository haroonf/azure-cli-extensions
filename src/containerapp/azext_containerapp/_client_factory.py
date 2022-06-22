# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# pylint: disable=line-too-long, consider-using-f-string

from azure.cli.core.commands.client_factory import get_mgmt_service_client
from azure.cli.core.profiles import ResourceType
from azure.cli.core.azclierror import CLIInternalError


# pylint: disable=inconsistent-return-statements
def ex_handler_factory(no_throw=False):
    def _polish_bad_errors(ex):
        import json
        try:
            content = json.loads(ex.response.content)
            if 'message' in content:
                detail = content['message']
            elif 'Message' in content:
                detail = content['Message']

            ex = CLIInternalError(detail)
        except Exception:  # pylint: disable=broad-except
            pass
        if no_throw:
            return ex
        raise ex
    return _polish_bad_errors


def handle_raw_exception(e):
    import json

    stringErr = str(e)
    if "response" in stringErr.lower():
        stringErr = stringErr[stringErr.lower().rindex("response"):]

    if "{" in stringErr and "}" in stringErr:
        jsonError = stringErr[stringErr.index("{"):stringErr.rindex("}") + 1]
        jsonError = json.loads(jsonError)

        if 'error' in jsonError:
            jsonError = jsonError['error']

            if 'code' in jsonError and 'message' in jsonError:
                code = jsonError['code']
                message = jsonError['message']
                raise CLIInternalError('({}) {}'.format(code, message))
        elif "Message" in jsonError:
            message = jsonError["Message"]
            raise CLIInternalError(message)
        elif "message" in jsonError:
            message = jsonError["message"]
            raise CLIInternalError(message)
    raise e


def providers_client_factory(cli_ctx, subscription_id=None):
    return get_mgmt_service_client(cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES, subscription_id=subscription_id).providers


def cf_resource_groups(cli_ctx, subscription_id=None):
    return get_mgmt_service_client(cli_ctx, ResourceType.MGMT_RESOURCE_RESOURCES,
                                   subscription_id=subscription_id).resource_groups


def log_analytics_client_factory(cli_ctx):
    from azure.mgmt.loganalytics import LogAnalyticsManagementClient
    return get_mgmt_service_client(cli_ctx, LogAnalyticsManagementClient).workspaces


def log_analytics_shared_key_client_factory(cli_ctx):
    from azure.mgmt.loganalytics import LogAnalyticsManagementClient
    return get_mgmt_service_client(cli_ctx, LogAnalyticsManagementClient).shared_keys


def app_client_factory(cli_ctx, *_):
    from azure.mgmt.appcontainers import ContainerAppsAPIClient
    from azure.cli.core.commands.client_factory import get_mgmt_service_client
    return get_mgmt_service_client(cli_ctx, ContainerAppsAPIClient)


def cf_containerapps(cli_ctx, *_):
    return app_client_factory(cli_ctx).container_apps


def cf_managedenvs(cli_ctx, *_):
    return app_client_factory(cli_ctx).managed_environments


def cf_revisions(cli_ctx, *_):
    return app_client_factory(cli_ctx).container_apps_revisions


def cf_replicas(cli_ctx, *_):
    return app_client_factory(cli_ctx).container_apps_revision_replicas


def cf_dapr_components(cli_ctx, *_):
    return app_client_factory(cli_ctx).dapr_components


def cf_certificates(cli_ctx, *_):
    return app_client_factory(cli_ctx).certificates


def cf_namespaces(cli_ctx, *_):
    return app_client_factory(cli_ctx).namespaces

def cf_storages(cli_ctx, *_):
    return app_client_factory(cli_ctx).managed_environments_storages
