# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from platform import platform
from azure.cli.core.azclierror import (ResourceNotFoundError, ValidationError)
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.util import sdk_no_wait
from knack.util import CLIError
from knack.log import get_logger

from ._client_factory import handle_raw_exception
from ._clients import ManagedEnvironmentClient
from ._models import ManagedEnvironment, VnetConfiguration, AppLogsConfiguration, LogAnalyticsConfiguration
from ._utils import _validate_subscription_registered, _get_location_from_resource_group, _ensure_location_allowed

logger = get_logger(__name__)


def create_containerapp(cmd, resource_group_name, name, location=None, tags=None):
    raise CLIError('TODO: Implement `containerapp create`')


def create_managed_environment(cmd,
                              name,
                              resource_group_name,
                              logs_customer_id,
                              logs_key,
                              logs_destination="log-analytics",
                              location=None,
                              instrumentation_key=None,
                              infrastructure_subnet_resource_id=None,
                              app_subnet_resource_id=None,
                              docker_bridge_cidr=None,
                              platform_reserved_cidr=None,
                              platform_reserved_dns_ip=None,
                              internal_only=False,
                              tags=None,
                              no_wait=False):

    location = location or _get_location_from_resource_group(cmd.cli_ctx, resource_group_name)

    _validate_subscription_registered(cmd, "Microsoft.App")
    _ensure_location_allowed(cmd, location, "Microsoft.App")

    log_analytics_config_def = LogAnalyticsConfiguration
    log_analytics_config_def["customerId"] = logs_customer_id
    log_analytics_config_def["sharedKey"] = logs_key

    app_logs_config_def = AppLogsConfiguration
    app_logs_config_def["destination"] = logs_destination
    app_logs_config_def["logAnalyticsConfiguration"] = log_analytics_config_def

    managed_env_def = ManagedEnvironment
    managed_env_def["location"] = location
    managed_env_def["properties"]["internalLoadBalancerEnabled"] = False
    managed_env_def["properties"]["appLogsConfiguration"] = app_logs_config_def
    managed_env_def["tags"] = tags

    if instrumentation_key is not None:
        managed_env_def["properties"]["daprAIInstrumentationKey"] = instrumentation_key

    if infrastructure_subnet_resource_id or app_subnet_resource_id or docker_bridge_cidr or platform_reserved_cidr or platform_reserved_dns_ip:
        vnet_config_def = VnetConfiguration

        if infrastructure_subnet_resource_id is not None:
            if not app_subnet_resource_id:
                raise ValidationError('App subnet resource ID needs to be supplied with controlplane subnet resource ID.')
            vnet_config_def["infrastructureSubnetId"] = infrastructure_subnet_resource_id

        if app_subnet_resource_id is not None:
            if not infrastructure_subnet_resource_id:
                raise ValidationError('Infrastructure subnet resource ID needs to be supplied with app subnet resource ID.')
            vnet_config_def["runtimeSubnetId"] = app_subnet_resource_id

        if docker_bridge_cidr is not None:
            vnet_config_def["dockerBridgeCidr"] = docker_bridge_cidr

        if platform_reserved_cidr is not None:
            vnet_config_def["platformReservedCidr"] = platform_reserved_cidr

        if platform_reserved_dns_ip is not None:
            vnet_config_def["platformReservedDnsIP"] = platform_reserved_dns_ip

        managed_env_def["properties"]["vnetConfiguration"] = vnet_config_def

    if internal_only:
        if not infrastructure_subnet_resource_id or not app_subnet_resource_id:
            raise ValidationError('Infrastructure subnet resource ID and App subnet resource ID need to be supplied for internal only environments.')
        managed_env_def["properties"]["internalLoadBalancerEnabled"] = True

    try:
        r = ManagedEnvironmentClient.create(
            cmd=cmd, resource_group_name=resource_group_name, name=name, managed_environment_envelope=managed_env_def, no_wait=no_wait)

        if "properties" in r and "provisioningState" in r["properties"] and r["properties"]["provisioningState"].lower() == "waiting" and not no_wait:
            logger.warning('Containerapp environment creation in progress. Please monitor the creation using `az containerapp show -n {} -g {}`'.format(name, resource_group_name))

        return r
    except Exception as e:
        handle_raw_exception(e)


def update_managed_environment(cmd,
                            name,
                            resource_group_name,
                            tags=None,
                            no_wait=False):
    raise CLIError('Containerapp env update is not yet supported.')

    _validate_subscription_registered(cmd, "Microsoft.App")

    managed_env_def = ManagedEnvironment
    managed_env_def["tags"] = tags

    try:
        r = ManagedEnvironmentClient.update(
            cmd=cmd, resource_group_name=resource_group_name, name=name, managed_environment_envelope=managed_env_def, no_wait=no_wait)

        if "properties" in r and "provisioningState" in r["properties"] and r["properties"]["provisioningState"].lower() == "waiting" and not no_wait:
            logger.warning('Containerapp environment update in progress. Please monitor the creation using `az containerapp show -n {} -g {}`'.format(name, resource_group_name))

        return r
    except Exception as e:
        handle_raw_exception(e)


def show_managed_environment(cmd, name, resource_group_name):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        return ManagedEnvironmentClient.show(cmd=cmd, resource_group_name=resource_group_name, name=name)
    except CLIError as e:
        handle_raw_exception(e)


def list_managed_environments(cmd, resource_group_name=None):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        managed_envs = []
        if resource_group_name is None:
            managed_envs = ManagedEnvironmentClient.list_by_subscription(cmd=cmd)
        else:
            managed_envs = ManagedEnvironmentClient.list_by_resource_group(cmd=cmd, resource_group_name=resource_group_name)

        return managed_envs
    except CLIError as e:
        handle_raw_exception(e)


def delete_managed_environment(cmd, name, resource_group_name, no_wait=False):
    _validate_subscription_registered(cmd, "Microsoft.App")

    try:
        r = ManagedEnvironmentClient.delete(cmd=cmd, name=name, resource_group_name=resource_group_name, no_wait=no_wait)
        if not r and not no_wait:
            logger.warning('Containerapp environment successfully deleted')
        return r
    except CLIError as e:
        handle_raw_exception(e)
