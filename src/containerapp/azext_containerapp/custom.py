# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.azclierror import (ResourceNotFoundError, ValidationError)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.util import sdk_no_wait
from knack.util import CLIError

from ._client_factory import handle_raw_exception
from ._clients import KubeEnvironmentClient, ManagedEnvironmentClient
from ._models import KubeEnvironment, ContainerAppsConfiguration, AppLogsConfiguration, LogAnalyticsConfiguration
from ._utils import _validate_subscription_registered, _get_location_from_resource_group, _ensure_location_allowed

def create_containerapp(cmd, resource_group_name, name, location=None, tags=None):
    raise CLIError('TODO: Implement `containerapp create`')


def create_kube_environment(cmd,
                            name,
                            resource_group_name,
                            logs_customer_id,
                            logs_key,
                            logs_destination="log-analytics",
                            location=None,
                            instrumentation_key=None,
                            controlplane_subnet_resource_id=None,
                            app_subnet_resource_id=None,
                            docker_bridge_cidr=None,
                            platform_reserved_cidr=None,
                            platform_reserved_dns_ip=None,
                            internal_only=False,
                            tags=None,
                            no_wait=False):

    location = location or _get_location_from_resource_group(cmd.cli_ctx, resource_group_name)
    
    _validate_subscription_registered(cmd, "Microsoft.Web")
    _ensure_location_allowed(cmd, location, "Microsoft.Web")

    containerapps_config_def = ContainerAppsConfiguration

    if instrumentation_key is not None:
        containerapps_config_def["daprAIInstrumentationKey"] = instrumentation_key

    if controlplane_subnet_resource_id is not None:
        if not app_subnet_resource_id:
            raise ValidationError('App subnet resource ID needs to be supplied with controlplane subnet resource ID.')
        containerapps_config_def["controlPlaneSubnetResourceId"] = controlplane_subnet_resource_id

    if app_subnet_resource_id is not None:
        if not controlplane_subnet_resource_id:
            raise ValidationError('Controlplane subnet resource ID needs to be supplied with app subnet resource ID.')
        containerapps_config_def["appSubnetResourceId"] = app_subnet_resource_id

    if docker_bridge_cidr is not None:
        containerapps_config_def["dockerBridgeCidr"] = docker_bridge_cidr

    if platform_reserved_cidr is not None:
        containerapps_config_def["platformReservedCidr"] = platform_reserved_cidr

    if platform_reserved_dns_ip is not None:
        containerapps_config_def["platformReservedDnsIP"] = platform_reserved_dns_ip

    if internal_only:
        if not controlplane_subnet_resource_id or not app_subnet_resource_id:
            raise ValidationError('Controlplane subnet resource ID and App subnet resource ID need to be supplied for internal only environments.')
        containerapps_config_def["internalOnly"] = True

    log_analytics_config_def = LogAnalyticsConfiguration
    log_analytics_config_def["customerId"] = logs_customer_id
    log_analytics_config_def["sharedKey"] = logs_key

    app_logs_config_def = AppLogsConfiguration
    app_logs_config_def["destination"] = logs_destination
    app_logs_config_def["logAnalyticsConfiguration"] = log_analytics_config_def

    kube_def = KubeEnvironment
    kube_def["location"] = location
    kube_def["properties"]["internalLoadBalancerEnabled"] = False
    kube_def["properties"]["environmentType"] = "managed"
    kube_def["properties"]["type"] = "managed"
    kube_def["properties"]["appLogsConfiguration"] = app_logs_config_def
    kube_def["properties"]["containerAppsConfiguration"] = containerapps_config_def
    kube_def["tags"] = tags

    try:
        return sdk_no_wait(no_wait, KubeEnvironmentClient.create,
                           cmd=cmd, resource_group_name=resource_group_name,
                           name=name, kube_environment_envelope=kube_def)
    except Exception as e:
        handle_raw_exception(e)


def update_kube_environment(cmd,
                            name,
                            resource_group_name,
                            tags=None,
                            no_wait=False):
    raise CLIError('Containerapp env update is not yet implemented')


def delete_kube_environment(cmd, name, resource_group_name):
    try:
        return KubeEnvironmentClient.delete(cmd=cmd, name=name, resource_group_name=resource_group_name)
    except CLIError as e:
        handle_raw_exception(e)


def show_kube_environment(cmd, name, resource_group_name):
    try:
        return KubeEnvironmentClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except CLIError as e:
        handle_raw_exception(e)


def list_kube_environments(cmd, resource_group_name=None):
    try:
        kube_envs = []
        if resource_group_name is None:
            kube_envs = KubeEnvironmentClient.list_by_subscription(cmd=cmd)
        else:
            kube_envs = KubeEnvironmentClient.list_by_resource_group(cmd=cmd, resource_group_name=resource_group_name)

        return [e for e in kube_envs if "properties" in e and
            "environmentType" in e["properties"] and
            e["properties"]["environmentType"] and
            e["properties"]["environmentType"].lower() == "managed"]
    except CLIError as e:
        handle_raw_exception(e)


def show_managed_environment(cmd, name, resource_group_name):
    try:
        return ManagedEnvironmentClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except CLIError as e:
        handle_raw_exception(e)


def list_managed_environments(cmd, resource_group_name=None):
    try:
        managed_envs = []
        if resource_group_name is None:
            managed_envs = ManagedEnvironmentClient.list_by_subscription(cmd=cmd)
        else:
            managed_envs = ManagedEnvironmentClient.list_by_resource_Group(cmd=cmd, resource_group_name=resource_group_name)

        return [e for e in managed_envs if "properties" in e and
            "environmentType" in e["properties"] and
            e["properties"]["environmentType"] and
            e["properties"]["environmentType"].lower() == "managed"]
    except CLIError as e:
        handle_raw_exception(e)
